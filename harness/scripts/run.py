"""Run one system on one dataset; emit a run directory.

A run records THREE things, and is worthless without all of them:

    build               which build produced these numbers  (build.ref)
    system              what was evaluated                  (system_id: the system's id, RFC-032)
    data                what it was measured on             (dataset_id)

Drop any one and the number cannot be attributed to anything.

REPEAT is not a convenience. Before believing a delta between two arms you must
know the arm's own run-to-run spread — otherwise you are promoting noise. A real
example: one ASR model showed 0.058 WER spread on BYTE-IDENTICAL input, wider
than most deltas anyone was arguing about.

    evh run --system demo --dataset tickets_v1
    evh run --system demo --dataset tickets_v1 --repeat 3 --goal tickets_summary --round r2

WIRING YOUR SYSTEM IN: edit `scripts/adapter.py`. Nothing in this file needs to
change — it times the call, records what it cost, scores the output against the
reference if one exists, and aggregates. That split is the point: the generic
half stays generic.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evaluation_harness import _artifact, _common, _jsonout, _outputs, _progress, _spend, _store
from evaluation_harness._adapter import (
    call_once,
    calls_per_item,
    load_adapter,
    metric_descriptions,
    metric_directions,
    metric_kinds,
    primary_metric,
    same_at,
    score_wants_source,
    transient_markers,
)
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    BUNDLED_ADAPTER_ID,
    DATA,
    EXIT_NOTHING,
    EXIT_STOPPED,
    EXIT_TRY_LATER,
    GOALS,
    LABELS_PREFIX,
    MATERIALIZED,
    REFERENCES,
    ROOT,
    RUNS,
    build_info,
    classify_metrics,
    die,
    env_float,
    goal_required_from,
    how,
    load_dataset,
    load_goals,
    now,
    plain_id_ok,
    warn_if_ignored,
)
from evaluation_harness._fingerprint import build_fingerprint
from evaluation_harness._number import counted, is_scored
from evaluation_harness._providers import priced_by_table, secret_params, temperature
from evaluation_harness._record import (
    aggregate_scores,
    cut_off_items,
    empty_at_cap_note,
    non_number,
    run_level_scores,
    run_record,
    run_scorer,
)
from evaluation_harness._retry import call_with_retries, is_transient
from evaluation_harness.model import datasets as _datasets
from evaluation_harness.model import results as _results
from evaluation_harness.model import rounds as _model_rounds
from evaluation_harness.model import runs as _model_runs
from evaluation_harness.ops import legacy


class _Resumed:
    """Stands in for an adapter's `Result` when an item is replayed from disk.

    The core has no Result class of its own -- every adapter defines one -- so a resumed
    item needs an object exposing the same read surface. Every call-derived field is
    None on purpose: a replayed item had no latency, no tokens and no cost IN THIS PASS,
    and reporting zeros would quietly pull the run's mean latency toward nought by an
    amount that depends on how far the previous attempt happened to get.
    """

    __slots__ = (
        "cost_usd",
        "extra",
        "latency_ms",
        "meta",
        "output",
        "tokens_in",
        "tokens_out",
    )

    def __init__(self, output: str, prior: dict[str, Any] | None = None) -> None:
        """`prior` is the item's row from the run being resumed, when one was found.

        WHAT CHANGED AND WHY. Every field here used to be None, on the reasoning in the
        docstring above -- a replayed item spent no time and no money IN THIS PASS. That
        is true of this pass and false of the results, and the results are what the run
        reports. The consequences were concrete:

          - the money vanished. A resumed run reported $0.03 for $0.05 of actual spend,
            because the items paid for in the first pass reported nothing.
          - `_meta` vanished with it. For retrieval that is `llm_raw`, `first_stage` and
            `ranking`; without them a resumed retrieval or NER run cannot be reported at
            all, and the diagnostics this repo added specifically to explain an arm's
            behaviour are gone for exactly the items that were hardest to get.

        Carrying the ORIGINAL numbers is not the same as reporting zeros, which is what
        the old docstring was arguing against. They were measured, on the same machine,
        against the same item, by the pass that produced the output being replayed. A
        resumed run should look like the run that would have happened without the crash,
        and `resumed` flags every replayed row so a reader can separate them.
        """
        prior = prior or {}
        self.output = output
        self.cost_usd = prior.get("cost_usd")
        self.latency_ms = prior.get("latency_ms")
        self.tokens_in = prior.get("tokens_in")
        self.tokens_out = prior.get("tokens_out")
        # The adapter's own call-time numbers -- `input_truncated`, `truncated`,
        # `reasoning_tokens`, `llm_parsed` -- ride in `Result.extra`, and used to be
        # dropped here. The aggregate averages only the rows that carry a key, so a
        # resumed `bart_s` reported input_truncated 0.75: 3 of the 4 items computed
        # fresh, against a true 46 of 200.
        #
        # The first fix carried every numeric key of the prior row that the core does not
        # own. That also carried the prior pass's SCORES, and any score the current scorer
        # no longer emits -- references absent, a metric renamed -- then reached the
        # aggregate from the replayed rows alone, reported as if measured. A prior row
        # cannot tell an extra from a score by looking at it, so every row records its
        # extras under `_extra` (empty when it has none), and exactly that is carried.
        self.extra: dict[str, float] = {
            k: float(v)
            for k, v in (prior.get("_extra") or {}).items()  # none when the run resumed from kept no rows
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        self.meta: dict[str, Any] = dict(prior.get("_meta") or {})
        self.meta["resumed_from_disk"] = True


#: What a call-once item the earlier run's process died in is called: a start mark and no row (RFC-038 1.3).
IN_DOUBT = "in doubt: its call started and the run stopped before it ended"
#: What a run of a call-once arm says first (and what its dry run says too).
CALL_ONCE_LINE = (
    "  calls each item once (the adapter declares CALL_ONCE): no retry, a failure is a failed item, and --resume\n"
    "  does not call a failed or in-doubt item again unless --recall-failed names them"
)
#: How many of the items a resume does not call again a run lists one by one.
HELD_LISTED = 20


def _held_items(
    items: list[dict[str, Any]],
    prior_out: dict[str, str],
    prior_rows: dict[str, dict[str, Any]],
    started: set[str],
) -> dict[str, str]:
    """{item_id: why} of the items a call-once run's earlier attempt called and did not finish with an output (RFC-038
    1.3), in dataset order: one whose row says it failed (its call raised: its effect may have happened) and one with a
    start mark and no row (the process died during its call). An item with an output, and one never attempted, are not
    in it."""
    held: dict[str, str] = {}
    for it in items:
        iid = it["item_id"]
        if iid in prior_out:
            continue
        row = prior_rows.get(iid)
        if row is not None and row.get("failed") == 1.0:
            held[iid] = str((row.get("_meta") or {}).get("call_error") or "failed (its error was not kept)")
        elif row is None and iid in started:
            held[iid] = IN_DOUBT
    return held


def _say_held(held: dict[str, str], recall: bool) -> None:
    """The items a resume of a call-once run does not call (or, with `--recall-failed`, calls again), by id and why."""
    if not held:
        return
    if recall:
        print(
            f"  --recall-failed: {len(held)} item(s) called once already are called again, once each "
            "(their side effects happen again)"
        )
    else:
        print(
            f"  {len(held)} item(s) were called once already and not again: --recall-failed calls them again, "
            "and repeats their side effects"
        )
    for iid, why in list(held.items())[:HELD_LISTED]:
        print(f"      {iid}  {why}")
    if len(held) > HELD_LISTED:
        print(f"      ... and {len(held) - HELD_LISTED} more (the run record lists them all)")


def _failed_result(exc: BaseException, once: bool) -> Any:
    """The empty `Result` of an item whose call raised: with the `meta` and `cost_usd` the exception carried (a
    trial's directory, what the call spent), and under call once the error itself, which `--resume` lists."""
    from evaluation_harness.adapter import Result  # noqa: PLC0415

    meta = dict(getattr(exc, "meta", None) or {})
    if once:
        meta["call_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return Result(output="", meta=meta, cost_usd=getattr(exc, "cost_usd", None))


def _keep_artifact(res: Any, said: set[str]) -> None:
    """The artifact an item's `meta` names (RFC-038), as the row keeps it: a clean path relative to the project, or, when
    it does not name a place inside it, dropped with `artifact_refused` saying why (the item's answer is good, so it is
    not failed). A stored path is something a server reads later, so what was given is never stored. Said once per why."""
    meta = getattr(res, "meta", None)
    if not isinstance(meta, dict) or _artifact.KEY not in meta:
        return
    rel, why = _artifact.normalise(meta.pop(_artifact.KEY))
    if rel is not None:
        meta[_artifact.KEY] = rel
        return
    reason = why or "not a path"
    meta[_artifact.REFUSED] = reason
    if reason not in said:
        said.add(reason)
        print(f"  artifact dropped: {reason}")


def _timed(call_system: Any) -> Any:
    """`call_system`, timed by the core: latency_ms is the wall-clock of the attempt that
    answered (not the retries' backoff), unless the adapter reported its own. Only the bundled
    adapter timed itself, so a project's adapter written as INTEGRATION shows recorded no
    latency, and the leaderboard silently had no speed to weigh against quality."""

    def call(text: str, params: dict[str, Any]) -> Any:
        started = time.perf_counter()
        res = call_system(text, params)
        if getattr(res, "latency_ms", None) is None:
            try:
                res.latency_ms = round((time.perf_counter() - started) * 1000, 3)
            except (AttributeError, TypeError):  # a frozen result: it keeps what it has
                pass
        return res

    return call


#: A warm-up that returns faster than this loaded nothing (a no-op warmup(), a hosted arm): it is not reported as work.
#: The window is wall time, and a process that is descheduled inside it counts the wait. Measured for a warm-up that
#: does nothing: 0.04 ms idle, but with the machine at 2x its cores and the test suite's own runs competing, 4 of 160
#: runs read 5.0 to 11.4 ms (a 5 ms threshold said "warmed up in 6ms"); 100,000 bare windows at 4x its cores: p99.9
#: 9 ms, 5 over 25 ms, 1 over 50 ms. 25 ms is twice the worst of the runs. A model load and a call to a hosted model
#: take longer; a call to a model already loaded on the same machine can be faster, and is then reported as nothing.
WARMUP_NOTHING_MS = 25.0

UNREACHABLE = (
    "Connection refused",
    "No route to host",
    "Network is unreachable",
    "Name or service not known",
    "nodename nor servname",
    "Temporary failure in name resolution",
)


class ServerUnreachable(RuntimeError):
    """An item's every model call failed because the server could not be reached."""


class SystematicFailure(RuntimeError):
    """Most items failed: an adapter or configuration error, not unlucky items, so the pass stops."""


#: A failed item is scored and the pass goes on (A5, owner 2026-11-05), until failures are this many AND this share
#: of the items called: then it is the adapter, not the items, and zeros would hide it.
FAILED_STOP_COUNT, FAILED_STOP_SHARE = 5, 0.2


def _unreachable(res: Any) -> str | None:
    """The error, when every call an adapter reports (`meta["calls"]`) failed reaching its server.

    An adapter that turns a failed call into an answer (the triage fleet defers it, and the replay
    records "no terminal decision") wrote a complete-looking run when a tunnel dropped: 54 and 65
    refused items scored as the model's no-decisions (2026-10-31). A model's own failure, the same
    way twice at temperature 0, is still a measurement; only a server that is not there stops."""
    calls = (getattr(res, "meta", None) or {}).get("calls") or []
    errors = [str(c.get("error") or "") for c in calls if isinstance(c, dict)]
    if errors and all(any(m in e for m in UNREACHABLE) for e in errors):
        return errors[-1][:160]
    return None


def _say_stopped(run_dir: Path, n_items: int, arm: str, exc: BaseException) -> None:
    """What a run that stopped mid-pass left, and the two ways on: resume it, or delete it.
    A crash used to end in the adapter's traceback alone, the run directory stayed with no
    metrics.json, and the next `validate` failed V7 with nothing having said why."""
    done = _outputs.count(run_dir)
    what = "interrupted" if isinstance(exc, KeyboardInterrupt) else f"{type(exc).__name__}: {str(exc)[:160]}"
    print(
        f"\nSTOPPED: run {run_dir.name} stopped after {done} of {n_items} item(s) ({what}).\n"
        f"  Its outputs so far are in {run_dir}.\n"
        "  Fix the cause, then either resume it (items already done are not called again):\n"
        "    "
        + how(
            f"evh run {arm} --resume {run_dir.name}",
            f'make run {arm.replace("--system ", "SYSTEM=").replace("--dataset ", "DATASET=")} ARGS="--resume {run_dir.name}"',
        )
        + f"\n  or delete {run_dir} (until one or the other, `validate` fails V7 on it).",
        file=sys.stderr,
    )


def _reference_for(dataset_id: str) -> tuple[Path | None, str | None]:
    """Prefer gold over silver, and report which was used.

    A score against silver is not a score against gold, and a report that does
    not say which is unreadable six months later.
    """
    for tier in ("gold", "silver"):
        d = REFERENCES / tier / dataset_id
        if _store.is_dir(d):
            return d, tier
    return None, None


def _score_failure_of(adapter_path: Path | None) -> Any:
    """The adapter's score_failure(reference), when it defines one (A5): what a failed item scores."""
    from evaluation_harness._adapter import _module_or_none  # noqa: PLC0415

    return getattr(_module_or_none(adapter_path), "score_failure", None)


def _recorded_outputs(cfg: dict[str, Any], adapter_path: Path | None) -> dict[str, str]:
    """A recorded arm's outputs (RFC-023): for each item of its dataset, the capture's record of the same id, read
    by the adapter's `recorded_output(record)` when it has one, else the record's field named by `field`. Refused
    when the capture lacks an item, or neither reader is there. The capture's sha256 is set on the params, so the
    run's fingerprint names exactly what was read."""
    import hashlib  # noqa: PLC0415

    from evaluation_harness._adapter import _module_or_none  # noqa: PLC0415
    from evaluation_harness.dataset_from_capture import load_capture  # noqa: PLC0415

    params = cfg.setdefault("params", {})
    capture = params.get("capture")
    if not capture:
        die(
            f"{cfg.get('system_id')}: provider recorded needs params.capture, the capture its outputs come from",
            "bad-argument",
        )
    _doc, recs = load_capture(capture)
    by_id = {r["id"]: r for r in recs}
    mod = _module_or_none(adapter_path)
    hook = getattr(mod, "recorded_output", None)
    field = params.get("field")
    if not callable(hook) and not field:
        die(
            f"{cfg.get('system_id')}: a recorded arm reads each output with the adapter's recorded_output(record), "
            "or from the record's field named by params.field; it has neither",
            "invalid-file",
        )
    out: dict[str, str] = {}
    missing = []
    for it in load_dataset(cfg["dataset_id"]).get("items") or []:
        rec = by_id.get(it["item_id"])
        if rec is None:
            missing.append(it["item_id"])
            continue
        out[it["item_id"]] = str(hook(rec) if callable(hook) else (rec.get("fields") or {}).get(field, ""))
    if missing:
        die(
            f"capture {capture} has no record for {len(missing)} item(s) of {cfg['dataset_id']}: {', '.join(missing[:8])}",
            "not-found",
        )
    from evaluation_harness._common import CAPTURES  # noqa: PLC0415

    params["capture_sha256"] = hashlib.sha256(
        _store.read_bytes(CAPTURES / capture / "capture.json")
    ).hexdigest()
    print(f"  a recorded arm: {len(out)} output(s) read from the capture {capture}, no system called")
    return out


#: Above this many items a pass prints a progress line for every k-th item, not every one.
PROGRESS_ALL_UP_TO = 2000


def progress_every(n_items: int) -> int:
    """k: a progress line for every item up to PROGRESS_ALL_UP_TO items, else about 200 lines per pass."""
    return 1 if n_items <= PROGRESS_ALL_UP_TO else -(-n_items // 200)


def _outcome(res: Any, scored: dict[str, Any], primary: str | None, resumed: bool) -> str:
    """One word for an item's progress line: resumed, error (a call the adapter reports failed), empty, the primary
    metric's value when the item has one, else ok."""
    if resumed:
        return "resumed"
    calls = (getattr(res, "meta", None) or {}).get("calls") or []
    if any(isinstance(c, dict) and c.get("error") for c in calls):
        return "error"
    if not (res.output or "").strip():
        return "empty"
    value = scored.get(primary) if primary else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{primary}={value:.4g}"
    return "ok"


def spend_basis(
    billed_usd: float, other_usd: float, priced: bool = False, sources: Iterable[str] = ()
) -> str:
    """Where a spend came from, in the words `evh run` and `evh arm-smoke` share: a Result's cost_usd is the
    provider's bill when its meta carries one (usage.cost); the rest is the adapter's own figure when its meta names
    a `cost_source` (a gateway key's spend, say), else tokens x the system's usd_per_mtok_in / _out when the call was
    priced by it (`priced`: the bundled providers mark such a call), else the adapter's own figure."""
    named = sorted({s for s in sources if s})
    # The adapter's own word on where its figure came from wins: a system declares prices for the dry run's estimate
    # whatever its adapter reports (review, 2026-11-19: a gateway's spend was called the price table's).
    if named:
        other = f"the adapter's own figure, cost_source {', '.join(named)}"
    elif priced:
        other = "the system's price table: tokens x usd_per_mtok_in / usd_per_mtok_out"
    else:
        other = "the adapter's own figure"
    # Half the last printed digit: a run's recorded total_cost_usd is rounded to 8 places and a bill is not, so the
    # rest is ~1e-9 of rounding, not a second source, and "$0.000000 the system's price table" read as one.
    if billed_usd > 0 and other_usd < 5e-7:
        return "the provider's bill"
    if billed_usd <= 0:
        return f"{other}, the provider sent no bill"
    return f"${billed_usd:.6f} the provider's bill, ${other_usd:.6f} {other}"


def is_priced(params: dict[str, Any]) -> bool:
    """Whether a system declares both prices, so a cost without a bill is its price table's."""
    return params.get("usd_per_mtok_in") is not None and params.get("usd_per_mtok_out") is not None


#: How far a bill may stray from the system's declared prices before a run says so (a fifth either way), as
#: judge-score says it of a judge (judge_score.PRICE_DRIFT).
PRICE_DRIFT = 1.2


def price_drift(rows: Iterable[dict[str, Any]], params: dict[str, Any]) -> str | None:
    """A note when the provider's bill for these item rows strays from what the system's declared prices give for the
    same tokens: every dry run estimates at those prices (the 0.8.0 newcomer run's judge, billed 2.5x its prices, was
    estimated at half its bill). None when the system declares no prices or no row carries a bill."""
    if not is_priced(params):
        return None
    billed = priced = 0.0
    for r in rows:
        cost = ((r.get("_meta") or {}).get("usage") or {}).get("cost")
        if cost is None:
            continue
        billed += float(cost)
        priced += float(r.get("tokens_in") or 0) / 1e6 * float(params["usd_per_mtok_in"]) + float(
            r.get("tokens_out") or 0
        ) / 1e6 * float(params["usd_per_mtok_out"])
    if not (billed and priced) or 1 / PRICE_DRIFT <= billed / priced <= PRICE_DRIFT:
        return None
    return (
        f"NOTE: the provider billed ${billed:.6f}, {billed / priced:.2f}x what the system's declared prices give for "
        f"the same tokens (${priced:.6f}: usd_per_mtok_in {params['usd_per_mtok_in']}, usd_per_mtok_out "
        f"{params['usd_per_mtok_out']}); a dry run estimates at those prices, so correct them in the system"
    )


def cost_source(meta: dict[str, Any] | None) -> str | None:
    """The `cost_source` an adapter names in a result's meta when no bill came with it, else None."""
    meta = meta or {}
    if (meta.get("usage") or {}).get("cost") is not None:
        return None
    src = meta.get("cost_source")
    return src if isinstance(src, str) and src else None


#: A pass says how long it has left once that is at least this many seconds (a fast arm's lines stay as they were).
SAY_LEFT_FROM_S = 30.0


def progress_line(
    n: int, total: int, item_id: str, outcome: str, seconds: float, spent: float, elapsed: float | None = None
) -> str:
    """`[n/N] <item_id> <outcome> <seconds>s`, plus the running cost once there is one, and with `elapsed` (the pass's
    seconds so far) the time left at its pace so far, when that is SAY_LEFT_FROM_S or more: a CPU model at 6 to 31 s an
    item said nothing of the 5.7 minutes its 20 items took (the 0.8.0 newcomer run)."""
    line = f"  [{n}/{total}] {item_id} {outcome} {seconds:.1f}s"
    line += f"  ${spent:.4f} so far" if spent else ""
    left = (elapsed / n) * (total - n) if elapsed is not None and n else 0.0
    if left >= SAY_LEFT_FROM_S:
        line += f"  about {round(left / 60)} min left" if left >= 90 else f"  about {round(left)} s left"
    return line


def one_pass(
    ds: dict[str, Any],
    cfg: dict[str, Any],
    idx: int,
    resume_dir: Path | None = None,
    prior_rows: dict[str, dict[str, Any]] | None = None,
    live_dir: Path | None = None,
    *,
    call_system: Any,
    score: Any,
    extra_transient: tuple = (),
    scored_against: tuple[Path | None, str | None] | None = None,
    recorded: dict[str, str] | None = None,
    primary: str | None = None,
    score_failure: Any = None,
    score_run: Any = None,
    per_item: Any = None,
    once: bool = False,
    same: Any = None,
    recall: bool = False,
) -> dict[str, Any]:
    """One pass over the dataset. ``score_failure`` is the adapter's optional score_failure(reference): what an item
    whose call failed scores (A5); without it, an empty answer's score. ``scored_against`` is (the folder, its tier) the caller chose: a label set with
    --labels; by default the dataset's gold, else its silver. ``recorded`` ({item_id: output}) is a recorded arm's
    outputs, read from a capture: no system is called for them (RFC-023). ``call_system``/``score`` are INJECTED rather than
    imported at module scope, because which adapter runs is a property of the arm now. ``primary`` names the metric
    each item's progress line shows. ``per_item(item)`` gives params added to an item's call (a replay's item and code,
    RFC-030); with ``once`` each item is called exactly once, a failure recorded and never retried (a retry would
    repeat a replay's side effects). A resumed pass with ``once`` does not call again an item the earlier run called
    once and did not finish (a failed row, a start mark with no row) unless ``recall`` names them (RFC-038)."""
    mat = MATERIALIZED / ds["dataset_id"]
    if not _store.is_dir(mat):
        die(
            f"{ds['dataset_id']} is not materialized.\n"
            f"  "
            + how(
                f"evh dataset-materialize --dataset-id {ds['dataset_id']}",
                f"make dataset-materialize DATASET_ID={ds['dataset_id']}",
            ),
            "not-materialized",
        )
    params = dict(cfg.get("params") or {})
    params.setdefault("seed", idx)
    ref_dir, ref_tier = scored_against or _reference_for(ds["dataset_id"])
    # Labels that hold only under production's action (RFC-031 L3): where this run acted otherwise it has no observed
    # outcome of its own, so the item is not scored (counted: "not scorable under this variant").
    from evaluation_harness._label_sets import action_bound  # noqa: PLC0415

    bound = action_bound(ref_dir)
    not_scorable: list[str] = []

    predictions: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}
    by_run = score_run
    run_items: list[dict[str, Any]] = []
    spent = 0.0
    # What this process may still spend (RFC-026 step 5): EVAL_MAX_COST_USD, or what the round left it, less what the
    # passes before this one spent, so `--repeat 3` stops at one cap in total, not three.
    cap = _spend.left()
    capped_at: str | None = None
    n_replayed = 0
    failed_items: list[dict[str, str]] = []
    n_called = 0
    carried_keys: set = set()

    # WRITE EACH OUTPUT THE MOMENT IT EXISTS, not at the end of the pass.
    #
    # Outputs used to accumulate in `outputs` and reach disk only after the whole loop
    # returned, so ANY exception -- an unhandled provider error, a Ctrl-C, a laptop lid
    # -- discarded every item already paid for. Worse, the resume path reads exactly
    # this directory, so the feature meant to rescue you had nothing to read: the two
    # failures compounded into "a crash costs you the entire arm".
    #
    # The cost of writing incrementally is one synced line per item (RFC-024). The cost of not
    # doing it was measured in dollars.
    if live_dir is not None:
        _store.mkdir(live_dir, parents=True, exist_ok=True)
    live = _outputs.writer(live_dir) if live_dir is not None else None
    # The previous attempt's outputs (RFC-024: its outputs.jsonl), read once.
    prior_out = _outputs.outputs(resume_dir) if resume_dir is not None else {}
    held: dict[str, str] = {}
    if once and resume_dir is not None:
        held = _held_items(ds["items"], prior_out, prior_rows or {}, _outputs.started(resume_dir))
        _say_held(held, recall)
    n_failed_called = 0
    stop_after: str | None = None
    artifact_said: set[str] = set()

    n_items = len(ds["items"])
    every = progress_every(n_items)
    if every > 1 and idx == 0:
        print(f"  {n_items} items: a progress line for every {every}th item and the last")

    pass_started = time.perf_counter()
    for n, item in enumerate(ds["items"], 1):
        item_started = time.perf_counter()
        # Resume: an item already produced is not PAID for twice -- but it is still
        # SCORED, which is the whole point of the pass.
        #
        # This used to `continue` here, skipping the scoring below, so a resumed item
        # produced no prediction row and no score. A fully-resumed run therefore emitted
        # an empty `predictions.jsonl` and a metrics file with no scores in it, while
        # reporting success. The outputs were all present and none of them counted.
        carried = item["item_id"] in held and not recall
        resumed = item["item_id"] in prior_out or carried

        if not resumed and _spend.stops(spent, cap, cfg.get("params")):
            # Check BEFORE the call: the cap is a ceiling on spend, not a report of
            # having exceeded it. A resumed item costs nothing, so the cap cannot stop it.
            capped_at = item["item_id"]
            break

        rel = item.get("source_path") or item["item_id"]
        src = mat / rel
        source_text = _store.read_text(src, encoding="utf-8", errors="replace")

        commit_here: str | None = None  # a replay's commit for this item (RFC-030), on its row
        if resumed:
            res: Any = _Resumed(prior_out.get(item["item_id"], ""), (prior_rows or {}).get(item["item_id"]))
            if carried:  # called once already, not again: still a failed item of this run, with its error
                res.meta["call_error"] = held[item["item_id"]]
                failed_items.append({"item_id": item["item_id"], "error": held[item["item_id"]]})
        elif recorded is not None:
            from evaluation_harness.adapter import Result  # noqa: PLC0415

            res = Result(output=recorded[item["item_id"]], cost_usd=0.0)
        else:
            # EVERY adapter gets retries, whether or not its author wrote any. This used
            # to be the adapter's business, and one adapter simply had none -- so a
            # single upstream 429 discarded an arm mid-sweep along with the items
            # already paid for.
            n_called += 1
            if (
                once and live_dir is not None
            ):  # on disk before the call: a kill during it leaves the item in doubt
                _outputs.mark_started(live_dir, item["item_id"])
            try:
                call_params = {**params, **per_item(item)} if per_item is not None else params
                commit_here = (call_params.get("code") or {}).get("commit") if per_item is not None else None
                res = (
                    _timed(call_system)(source_text, call_params)
                    if once
                    else call_with_retries(
                        _timed(call_system),
                        (source_text, call_params),
                        extra_transient=extra_transient,
                        label=f"item {item['item_id'][:8]}",
                    )
                )
            except SystemExit:
                raise
            except _common.CostCapExceeded as exc:
                # The provider layer's own count reached the cap (an adapter that reported less than it paid):
                # stopped as at the cap, before this item's output is written, so --resume calls it again. A call-once
                # item was called, so it is a failed item (its effect may have happened) and the run stops after it.
                if not once:
                    capped_at = item["item_id"]
                    break
                failed_items.append(
                    {"item_id": item["item_id"], "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
                )
                print(f"      FAILED item {item['item_id'][:8]}: {type(exc).__name__}: {str(exc)[:160]}")
                res = _failed_result(exc, once)
                stop_after = item["item_id"]
            except Exception as exc:  # an item's failure is recorded, not raised (A5)
                if not once and is_transient(exc, extra_transient):
                    # The provider kept failing past every retry: weather, not this item. Stop, as for an
                    # unreachable server, so --resume calls it again later.
                    raise ServerUnreachable(
                        f"item {item['item_id']}: the provider kept failing after its retries: {type(exc).__name__}: {exc}"
                    ) from exc
                failed_items.append(
                    {"item_id": item["item_id"], "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
                )
                print(f"      FAILED item {item['item_id'][:8]}: {type(exc).__name__}: {str(exc)[:160]}")
                n_failed_called += 1
                if n_failed_called > FAILED_STOP_COUNT and n_failed_called > FAILED_STOP_SHARE * n_called:
                    raise SystematicFailure(
                        f"{n_failed_called} of the {n_called} items called failed (the last: "
                        f"{failed_items[-1]['error']}): an adapter or configuration error, not the items"
                    ) from exc
                res = _failed_result(exc, once)
            _keep_artifact(res, artifact_said)
            if res.cost_usd:
                spent += res.cost_usd
                _spend.add(res.cost_usd)
            unreachable = _unreachable(res)
            if unreachable:
                # Before the output is written, so `--resume` calls this item again.
                raise ServerUnreachable(f"item {item['item_id']}: every model call failed: {unreachable}")
        failed = bool(failed_items) and failed_items[-1]["item_id"] == item["item_id"]
        outputs[item["item_id"]] = res.output

        reference = None
        if ref_dir is not None:
            rf = ref_dir / f"{item['item_id']}.txt"
            if _store.is_file(rf):
                reference = _store.read_text(rf, encoding="utf-8", errors="replace")

        # Pass the SOURCE when the scorer wants it. Facets that compare the output to the
        # INPUT — grounding, compression — cannot be computed from output+reference alone,
        # and a scorer asking for a third argument used to get None silently: the
        # hallucination check simply never ran and nothing said so.
        # A failed item scores as an empty answer (0 on most measures), or as the adapter's score_failure(reference)
        # says when it has one: a failure never makes an arm look better.
        try:
            if (
                item["item_id"] in bound
                and not failed
                and not (same or (lambda a, b: a.strip() == b.strip()))(res.output, bound[item["item_id"]])
            ):
                scored = {}
                not_scorable.append(item["item_id"])
            elif failed and score_failure is not None:
                scored = score_failure(reference)
            else:
                scored = (
                    score(res.output, reference, source_text)
                    if score_wants_source(score)
                    else score(res.output, reference)
                )
        except (
            BaseException
        ):  # the scorer raised: the output is kept all the same, as when it was written first
            if live is not None and not resumed and not failed:
                live.add(item["item_id"], res.output)
            raise
        if (bad := non_number(scored)) is not None:
            # RFC-041 F7: a score that is not a number (NaN, an infinity, None) is a failed item, never a mean's term:
            # recorded with its reason, scored as a failed item is, its output not written (--resume calls it again).
            if not failed:
                failed_items.append({"item_id": item["item_id"], "error": bad})
                print(f"      FAILED item {item['item_id'][:8]}: {bad}")
                if not resumed and recorded is None:
                    n_failed_called += 1
                    if n_failed_called > FAILED_STOP_COUNT and n_failed_called > FAILED_STOP_SHARE * n_called:
                        raise SystematicFailure(
                            f"{n_failed_called} of the {n_called} items called failed (the last: {bad}): "
                            "an adapter or configuration error, not the items"
                        )
                failed = True
                scored = (
                    score_failure(reference)
                    if score_failure is not None
                    else score("", reference, source_text)
                    if score_wants_source(score)
                    else score("", reference)
                )
            # what the failed item's own score holds that is a number stays; a measure its fallback could not score
            # either (NaN, an infinity, None) counts 0, as a failed item does: dropped, the mean ran over the other items
            # and the failure made the arm look better (review, 2026-11-24). A boolean or text is no score: left out.
            scored = {
                k: v if non_number({k: v}) is None else counted(v)
                for k, v in scored.items()
                if non_number({k: v}) is None or is_scored(v)
            }
        # A failed item's output is not written: --resume calls it again.
        if live is not None and not resumed and not failed:
            # One synced line per item: `--resume` treats a complete line as proof the item is done, and a torn
            # last line (a kill mid-append) as not done, so a half-written output is never replayed and scored.
            live.add(item["item_id"], res.output)
        row: dict[str, Any] = {"item_id": item["item_id"], **scored}
        if by_run is not None:
            run_items.append(
                {"item_id": item["item_id"], "output": res.output, "reference": reference, "scores": scored}
            )
        # 0/1 on every row: its mean is the share of the pass that failed.
        row["failed"] = 1.0 if failed else 0.0
        # On EVERY row, not just the resumed ones: the aggregate averages only the rows
        # that carry a key, so a flag set on resumed items alone would report 1.0
        # whether one item was replayed or all of them. As 0/1 on every row its mean is
        # the SHARE of the run that was replayed, which is the number worth knowing.
        row["resumed"] = 1.0 if resumed else 0.0
        for field_name in ("latency_ms", "tokens_in", "tokens_out", "cost_usd"):
            v = getattr(res, field_name)
            if v is not None:
                row[field_name] = float(v)
        # If an adapter ever names an extra the same as a score, the score just computed
        # against the current code wins on a replayed row.
        extra = {k: float(v) for k, v in res.extra.items() if not (resumed and k in scored)}
        row.update(extra)
        # The extras again, by name, so a later `--resume` can carry exactly these and
        # never mistake a score for one. `_`-prefixed, so never aggregated.
        # On EVERY row, empty or not: written only when non-empty, a row with no extras read
        # on resume as one from before `_extra` existed.
        row["_extra"] = extra
        if resumed:
            n_replayed += 1
            carried_keys.update(extra)
        # Raw provider metadata rides along under a `_`-prefixed key. Everything
        # `_`-prefixed is excluded from the aggregation below, so an adapter can record
        # a nested dict (a usage object, a finish_reason) without the mean-of-every-key
        # loop trying to average it.
        if res.meta:
            row["_meta"] = res.meta
        if commit_here:
            row["_commit"] = (
                commit_here  # the commit this item ran at: what a label's reproduction is dated by (X2)
            )
        predictions.append(row)

        # THE ROW GOES TO DISK NOW, NOT AT THE END OF THE PASS.
        #
        # `predictions.jsonl` is written after one_pass RETURNS, so a crashed run has
        # its outputs and nothing else. Round 2 taught the resume path to carry each
        # replayed item's cost, tokens and _meta forward -- from predictions.jsonl,
        # which by construction does not exist in the one case resume is for. So the
        # fix worked for a tidy re-run and not for a crash, and RUNBOOK said "a
        # replayed item keeps what was measured" for exactly the case where it did not.
        # Found by external review.
        #
        # Appended per item, so a kill at item k leaves k rows. Not atomic-per-file
        # because it is an append, but a torn final line is discarded on read.
        if live_dir is not None and (
            not resumed or carried
        ):  # a carried failure too: a stopped resume keeps it
            _outputs.append_partial(live_dir, row)
        _progress.step(n, n_items)

        if n % every == 0 or n == n_items:
            print(
                progress_line(
                    n,
                    n_items,
                    item["item_id"],
                    "called once already" if carried else _outcome(res, scored, primary, resumed),
                    time.perf_counter() - item_started,
                    spent,
                    time.perf_counter() - pass_started,
                ),
                flush=True,
            )
        if stop_after is not None:
            capped_at = stop_after
            break

    # A replay's history confound (RFC-031 P1) is counted over every item of the run, as its note says: an adapter
    # may mark only the items where production acted, and the mean over those alone said 5 of 34 where the note said
    # 5 of 287 (the fleet's beta). An unmarked item met no reaction to an action the variant did not take.
    if any("history_confound" in r for r in predictions):
        for r in predictions:
            r.setdefault("history_confound", 0.0)
    scores = aggregate_scores(predictions, digits=6)
    run_metrics: list[str] = []
    if by_run is not None and run_items:
        whole = run_level_scores(by_run, run_items, scores)
        scores.update(whole)
        run_metrics = sorted(whole)
    # WAS THIS ARM ONE SYSTEM? A gateway can serve the same model from several hosts and
    # switch between calls. If it did, the arm's 20 items were not produced by one system
    # and its mean mixes two -- which is exactly the confound the fingerprint exists to
    # rule out, happening below the level the fingerprint can see. Counted here so the
    # run says so instead of the numbers quietly absorbing it.
    providers: dict[str, int] = {}
    for pred in predictions:
        name = (pred.get("_meta") or {}).get("provider")
        if name:
            providers[name] = providers.get(name, 0) + 1
    # CUT OFF AT max_tokens. An output that stopped at the cap is a truncated answer scored as
    # if it were whole: a frontier arm at max_tokens 80 ended 19 of 20 summaries mid-sentence and
    # the run said nothing. The provider's finish_reason says so when the adapter records it;
    # tokens_out reaching the cap says so otherwise.
    cap = params.get("max_tokens")
    cut = cut_off_items(predictions, cap)
    if cut:
        # An EMPTY reply at the cap is a model that spent the whole budget before it answered (reasoning, say).
        blank = [i for i in cut if not (outputs.get(i) or "").strip()]
        spent_note = f"\n    {empty_at_cap_note(blank)}" if blank else ""
        print(
            f"  WARNING: {len(cut)} of {len(predictions)} output(s) stopped at max_tokens={cap} "
            f"({', '.join(cut[:6])}{' ...' if len(cut) > 6 else ''}).{spent_note}\n"
            "    They are scored as if complete. Raise max_tokens (a new system_id) and run again."
        )
    resume_note = None
    if n_replayed:
        resume_note = {
            "replayed_items": n_replayed,
            "carried_extra_keys": sorted(carried_keys),
        }
    return {
        "predictions": predictions,
        "scores": scores,
        "run_metrics": run_metrics,
        "resume": resume_note,
        "providers_seen": providers,
        "outputs": outputs,
        "reference_tier": ref_tier,
        "capped_at": capped_at,
        "spent_usd": round(spent, 8),
        "failed_items": failed_items,
        "not_scorable": not_scorable,
        "recalled": list(held) if recall else [],
    }


def _cost_coverage(rows: list[dict[str, Any]]) -> dict[str, int] | None:
    """How many of the items that did not fail reported a cost, when only some did (a failed item is named in
    `failed_items`); None when all did or none did: no cost reported is unknown, and the run then records no total, so
    a total is never the sum of some items passed off as all (RFC-041 F7)."""
    done = [r for r in rows if not r.get("failed")]
    known = sum(1 for r in done if "cost_usd" in r)
    return {"items_with_cost": known, "items": len(done)} if 0 < known < len(done) else None


def _confound(rows: list[dict[str, Any]]) -> dict[str, int] | None:
    """A replay's history confound (RFC-031 P1): how many rows its adapter marked, of how many; None when it marks none."""
    marked = [r for r in rows if "history_confound" in r]
    if not marked:
        return None
    return {"items": sum(1 for r in marked if r.get("history_confound") == 1.0), "of": len(rows)}


def _smoke_cost(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """What the last `evh arm-smoke` of this system measured, from its model record: {per_item_usd, items, at,
    model_record}; None when the system names no record, the record holds no smoke of it, or it priced nothing."""
    from evaluation_harness import _models  # noqa: PLC0415

    if not cfg.get("model_record"):
        return None
    smoke = ((_models.find(DATA, cfg["model_record"]) or {}).get("smokes") or {}).get(cfg["system_id"]) or {}
    report = smoke.get("report") or {}
    costs = [i["cost_usd"] for i in report.get("items") or [] if i.get("cost_usd") is not None]
    if not costs:
        return None
    return {
        "per_item_usd": sum(costs) / len(costs),
        "items": len(costs),
        "at": smoke.get("at"),
        "model_record": cfg["model_record"],
    }


def _cap_shown(cap: float | None) -> str:
    return _spend.shown(cap) + (" — set EVAL_MAX_COST_USD" if cap is None else " (EVAL_MAX_COST_USD)")


def _dry_run(
    ds: dict[str, Any],
    cfg: dict[str, Any],
    repeat: int,
    adapter_path: Path | None = None,
    config_path: Path | None = None,
    once: bool = False,
    only: int | None = None,
    note: str | None = None,
    adapter_id: str = BUNDLED_ADAPTER_ID,
) -> int:
    """Shape and cost the sweep without calling anything.

    The estimate counts what the system alone shows: one call per item (or the adapter's declared
    `CALLS_PER_ITEM`), the prompt in and max_tokens out, each call as large as the first. It is NOT an upper
    bound: an adapter that calls the system several times per item, or whose conversation grows, costs more.
    What an arm-smoke of this system measured is shown beside it, and is the number to set a cap from.
    """
    params = dict(cfg.get("params") or {})
    items = ds["items"]
    mat = MATERIALIZED / ds["dataset_id"]
    item_chars = sum(
        len(_store.read_text(mat / (i.get("source_path") or i["item_id"]), errors="replace"))
        for i in items
        if _store.is_file(mat / (i.get("source_path") or i["item_id"]))
    )
    # The prompt the system gives is sent with every item (the bundled adapter sends `prompt`, a blank line, the
    # item). An adapter that builds its own prompt elsewhere cannot be asked for it, so that part is not counted.
    prompt = params.get("prompt")
    if not isinstance(prompt, str):  # the prompts it declares (RFC-028): a version's or a file's text
        from evaluation_harness import _prompts  # noqa: PLC0415

        prompt = "\n\n".join(_prompts.declared_texts(cfg).values()) or None
    prompt_chars = (len(prompt) + 2) * len(items) if isinstance(prompt, str) else 0
    chars = item_chars + prompt_chars
    # ~4 chars per token is the usual English rule of thumb; it is a rule of
    # thumb, and the number below inherits that.
    est_in = chars / 4
    est_out = int(params.get("max_tokens", 600)) * len(items)
    declared = calls_per_item(adapter_path, params)
    per_item = declared or 1
    calls = len(items) * repeat * per_item if only is None else only * per_item
    share = (
        1.0 if only is None else only / max(len(items), 1)
    )  # a resume pays for the items it calls, not all of them

    print("DRY RUN — nothing was called\n")
    # What runs: the bundled adapter's provider (echo unless the system names one), or the project's own adapter, which
    # reads `provider` only if its system sets one: echo is the bundled adapter's default, not a fact about another.
    custom = adapter_id != BUNDLED_ADAPTER_ID
    provider = params.get("provider") if custom else params.get("provider", "echo")
    what = " / ".join(
        x for x in (f"adapter {adapter_id}" if custom else "", provider, params.get("model")) if x
    )
    print(f"  system      {cfg['system_id']}  ({what})")
    print(f"  dataset     {ds['dataset_id']}  ({len(items)} items)")
    print(f"  repeats     {repeat}")
    if once:
        print(CALL_ONCE_LINE)
    if note:
        print(f"  {note}")
    print(f"  API calls   {calls}")
    print(
        f"              {per_item} per item, declared by the adapter (CALLS_PER_ITEM)"
        if declared
        else "              one per item: an adapter that calls the system several times per item makes more"
    )
    counted = (
        "item text + the system's prompt; a prompt the adapter adds itself is not counted"
        if prompt_chars
        else "item text only; a prompt the adapter adds is not counted"
    )
    print(f"  input       ~{est_in / 1000:.1f}k tokens/pass (from {chars / 1000:.0f}k chars: {counted})")
    print(f"  output      <= {est_out / 1000:.1f}k tokens/pass (max_tokens x items)")

    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    est = None
    if pin is None or pout is None:
        print("\n  No price in the system, so no estimate. Add usd_per_mtok_in /")
        print("  usd_per_mtok_out and the run will record what it actually cost.")
    else:
        est = (est_in / 1e6 * float(pin) + est_out / 1e6 * float(pout)) * repeat * per_item * share
        print(
            f"\n  ESTIMATE    ~${est:.4f}  ({per_item} call(s) per item, each the prompt in and max_tokens out;"
            " NOT an upper bound:"
        )
        print("              a conversation that grows, or an adapter that calls more than that, costs more)")
        print(
            "              It assumes every reply is max_tokens long: a model that answers in a sentence usually costs"
            " less (an arm-smoke measures it)."
        )
    measured = _smoke_cost(cfg)
    projected = None
    if measured:
        pass_usd = measured["per_item_usd"] * len(items)
        projected = pass_usd * repeat
        print(
            f"  MEASURED    ${measured['per_item_usd']:.5f}/item = ${pass_usd:.4f} per pass of {len(items)} items,"
            f" ${projected:.4f} at {repeat} repeat(s)"
        )
        print(
            f"              from the arm-smoke of {measured['items']} item(s) at {measured['at']}"
            f" (model record {measured['model_record']}); set a cap from this"
        )
    else:
        where = f" --system {cfg['system_id']} --dataset {cfg['dataset_id']}"
        if cfg.get("model_record"):
            print(f"  MEASURED    none for {cfg['system_id']}: no arm-smoke of it is recorded")
            print(f"              run `evh arm-smoke{where}` and set a cap from what it measures")
        else:
            # A smoke is kept on a model's deployment (RFC-032): with no model record there is nowhere to keep it.
            print(
                f"  MEASURED    none for {cfg['system_id']}: it names no model record, so an arm-smoke of it is not kept"
            )
            print(
                f"              run `evh arm-smoke{where}` for what 3 items cost (its `full run:` line) and set a cap"
                " from that"
            )
    cap = env_float("EVAL_MAX_COST_USD")
    print("  cap         " + _cap_shown(cap))
    _jsonout.value(
        "dry_run",
        {
            "system_id": cfg["system_id"],
            "dataset_id": ds["dataset_id"],
            "adapter": adapter_id,
            "provider": provider,
            "model": params.get("model"),
            "items": len(items),
            "repeats": repeat,
            "api_calls": calls,
            "input_tokens_per_pass": est_in,
            "input_tokens_counts": counted,
            "output_tokens_per_pass_max": est_out,
            "estimate_usd": est,
            "estimate_is_upper_bound": False,
            "estimate_basis": f"{per_item} call(s) per item, prompt in and max_tokens out",
            "calls_per_item": per_item,
            "calls_per_item_declared": declared is not None,
            "measured_usd_per_item": measured["per_item_usd"] if measured else None,
            "measured_projected_usd": projected,
            "measured_from": (
                {
                    "arm_smoke_at": measured["at"],
                    "items": measured["items"],
                    "model_record": measured["model_record"],
                }
                if measured
                else None
            ),
            "cap_usd": cap,
        },
    )
    return 0


def _faithfulness_gate(
    plan: Any, ds: dict[str, Any], adapter_id: str, adapter_path: Path | None, ref_tier: str | None, args: Any
) -> dict[str, Any]:
    """A replay's faithfulness (RFC-030), as the run records it: refused when it is scored (a reference or a label
    set) and the latest record does not let it be, unless a person passes --unfaithful."""
    from evaluation_harness import _coderec, _faith, _replay  # noqa: PLC0415
    from evaluation_harness._fingerprint import items_digest  # noqa: PLC0415

    state = _faith.gate(
        plan.model_id,
        ds["dataset_id"],
        items_digest(ds),
        _coderec.versions_sha256(plan.record),
        _replay.adapter_identity(adapter_id, adapter_path, plan)["sha256"],
    )
    commits = plan.commits()
    print(
        f"  replay of {plan.model_id}: {len(plan.items)} items at "
        + (f"the candidate {plan.candidate[:12]}" if plan.candidate else f"{len(commits)} recorded commit(s)")
    )
    print(f"  {_faith.said(state)}")
    if state["faithful"] or not ref_tier or args.dry_run:
        return state
    if not args.unfaithful:
        die(
            f"{_faith.said(state)}.\n  A replay is scored against a reference only once it reproduces production "
            f"(RFC-030): evh faithfulness --system {args.system} --production <production's arm>, then name each "
            f"disagreement whose cause is outside the system (evh faithfulness-name --model {plan.model_id} --item "
            "ITEM --cause ...), or score it anyway as a person with --unfaithful.",
            "not-allowed",
        )
    from evaluation_harness._actor import require_named  # noqa: PLC0415

    who = require_named("scoring an unfaithful replay")
    if who["type"] != "person":
        die(
            "an agent cannot score an unfaithful replay; a person passes --unfaithful (RFC-030)",
            "not-allowed",
        )
    print("  WARNING: scored with --unfaithful: this run and every page showing it say so")
    return {**state, "unfaithful_by": who}


def _prompt_versions(
    adapter_path: Path | None, adapter_id: str, cfg: dict[str, Any], fingerprint: dict[str, Any]
) -> dict[str, str]:
    """{name: version id} of the prompts this run sends (RFC-032 step 4b): what the adapter's `prompts(params)`
    gives, recorded as prompt versions, only when the fingerprint declares a `prompt_sha256` (the adapter sent a
    prompt) and only a text of that hash (the version is the prompt the fingerprint names). Outside the fingerprint's
    hash: a run's fingerprint is what it was before runs named their prompt."""
    from evaluation_harness import _prompts  # noqa: PLC0415
    from evaluation_harness._adapter import prompts as adapter_prompts  # noqa: PLC0415

    declared = (((fingerprint.get("settings") or {}).get("declared")) or {}).get("prompt_sha256")
    if not declared:
        return {}
    out: dict[str, str] = {}
    for name, text in sorted(adapter_prompts(adapter_path, dict(cfg.get("params") or {})).items()):
        data = text.encode("utf-8")
        if _prompts.sha256(data) != declared:
            print(
                f"  note: prompt {name}: not the prompt the fingerprint declares (prompt_sha256): not recorded"
            )
            continue
        _prompts.check_name(name, f"{adapter_id}'s prompts()")
        rec, _new = _prompts.record(
            name,
            data,
            source={"adapter": adapter_id, "system": cfg.get("system_id")},
            note=f"sent by a run of {cfg.get('system_id')}",
        )
        out[name] = rec["id"]
    return out


def _refuse_unrelated_of(of: str, cfg: dict[str, Any], purpose: str) -> None:
    """Refuse, before any call, an `--of` that names a run of another system or dataset: a `purpose` of that run is no
    re-run of it (RFC-041 F7: `of` is a link the readers follow, so a writer records only one that holds)."""
    of_rec = _model_runs.run(of) or {}
    wrong = [
        k for k, w in (("system", "system_id"), ("dataset", "dataset_id")) if of_rec.get(w) != cfg.get(w)
    ]
    if wrong:
        die(
            f"--of {of}: a run of {of_rec.get('system_id')} on {of_rec.get('dataset_id')}, and this run is of "
            f"{cfg['system_id']} on {cfg['dataset_id']}: a {purpose} names a run of its own system and dataset "
            f"({' and '.join(wrong)} differ). Name that run, or make this one without --purpose {purpose}.",
            "mismatch",
        )


def _repeat_reading(
    of: str, fingerprint: dict[str, Any], cfg: dict[str, Any], label_as: str
) -> dict[str, Any]:
    """Where a `--purpose repeat --of <run>` run will be read (model.runs.repeat_reading)."""
    mine = {"dataset_id": cfg["dataset_id"], "system_id": cfg["system_id"], "fingerprint": fingerprint}
    return _model_runs.repeat_reading(of, mine, label_as)


def _says_repeat(of: str, reading: dict[str, Any]) -> tuple[str, str]:
    """What a `--purpose repeat --of <run>` run tells, before its first call and again as its last line: whether it will
    be read in the arm of the run it repeats (the same measurement taken again), or under `repeats` as another one, and
    what differs (RFC-041 F2)."""
    arm = reading["arm"]
    build = f" (the {_model_runs.HARNESS} differs)" if reading["notes"] else ""
    if reading["joins"]:
        return (
            (
                f"  repeat of {of}: the same measurement (data, deployment, settings, adapter), so this run joins its "
                f"arm {arm} and is averaged with it{build}"
            ),
            f"  repeat of {of}: joined {arm}{build}",
        )
    what = ", ".join(reading["why"])
    return (
        (
            f"  repeat of {of}: not the same measurement ({what}), so this run is read under `repeats` ({arm}), a "
            f"separate arm, and is not averaged with {of}; to join its arm, run it again as {of} was run"
        ),
        f"  repeat of {of}: read under `repeats` ({arm}), not in {of}'s arm: {what}",
    )


def _refuse_repeat_of_retired(rnd: dict[str, Any], system_id: str, label: str, of: str) -> None:
    """Refuse, before any call, a repeat that joins the arm of a run the round retired: a run made in a round brings
    its system back into play, and a repeat of a retired arm's run is not a reason to (the round's arm would come back
    silently)."""
    arm = _model_rounds.retired_arm(rnd, system_id, label)
    if arm is not None:
        die(
            f"--of {of}: {system_id}'s arm in round {rnd['round_id']} is retired ({(arm.get('retired') or {}).get('reason') or 'no reason'}), "
            "and this repeat would join it and bring it back into play. Repeat the run outside the round (leave out "
            "--round), or bring the arm back on purpose with a run of its own.",
            "bad-argument",
        )


def _refuse_repeat_beside_run(system_id: str, dataset_id: str, repeat: int) -> None:
    """Refuse, before any call, a --repeat set of a system on a dataset where it already has a plain run: the set is
    meant to be the arm's measurement, so beside the run it makes two measurements of one system id, which every
    reader averages and validate's V8 fails once committed. The 0.8.0 newcomer run paid for a --repeat 3 after its
    plain run, then failed V8; repeating the run it has is what measures its noise. Other runs of a system already
    run (a changed prompt, a replay at a new commit, another reference) are the harness's own paths and are not refused
    here. A pair the project allows (`duplicate_ok` in validate.json) passes."""
    # validate.json read here, not through validate_tree: a checker imported by a run would join the code a run's
    # fingerprint hashes (measuring_modules), and move every run's code hash.
    policy_file = _common.DATA / "validate.json"
    try:
        policy = (
            json.loads(_store.read_text(policy_file, encoding="utf-8")) if _store.is_file(policy_file) else {}
        )
    except ValueError:
        policy = {}  # validate names a broken policy; it is no reason to refuse a run here
    allowed = {tuple(x) for x in ((policy if isinstance(policy, dict) else {}).get("duplicate_ok") or [])}
    if (dataset_id, system_id) in allowed:
        return
    found = _model_runs.scored(dataset_id, system_id=system_id)
    newest = _model_runs.latest(found)
    if newest is None:
        return
    have = sorted({_model_runs.run_of(sd).name for sd, _rec in found})
    last = _model_runs.run_of(newest[0]).name
    die(
        f"{system_id} already has a measured run on {dataset_id}: {', '.join(have)}. A --repeat {repeat} set beside it "
        "would be a second measurement of the same arm: every reader averages them, and validate fails V8 once they "
        "are committed.\n"
        f"  To measure its noise, repeat the run it has, once per repeat: evh run --system {system_id} --dataset "
        f"{dataset_id} --purpose repeat --of {last}\n"
        "  Run as that run was run (the same data, deployment, settings and adapter), each repeat joins its arm: the arm is "
        "then read as one measurement over all its runs. A repeat that differs in any of them is read under `repeats`, as "
        "another measurement.\n"
        f"  To measure it as a set from the start, delete that run first: evh data-rm --path runs/{last}",
        "would-overwrite",
    )


def _resume_source(
    resume: str | None, cfg: dict[str, Any], runs: Path = RUNS
) -> tuple[Path | None, dict[str, dict[str, Any]]]:
    """For `--resume <run_id>`: (its run directory, {item_id: its row}); (None, {}) without. The run is looked
    for in `runs` (data/runs, or the scratch runs of a --scratch pass). Dies when the run cannot be resumed as this
    arm."""
    if not resume:
        return None, {}
    resume_dir = runs / resume
    if not _outputs.own(resume_dir):
        die(f"cannot resume: no outputs in {resume_dir} (the {_common.store()} store)", "not-found")

    # RESUMING FROM ANOTHER ARM'S OUTPUTS WAS ACCEPTED WITHOUT A WORD.
    #
    # `--resume` took a run id and read its outputs. Nothing compared that
    # run's arm to the one being launched, so
    #   make run CONFIG=arm_glm_s.yaml ARGS="--resume <a qwen_s run>"
    # replayed qwen_s's answers, scored them, and recorded the whole thing as glm_s --
    # a fabricated result with a valid fingerprint. One mistyped run id in a recovery
    # command, which is exactly when the operator is rushed. Found by external review.
    #
    # The dataset must match too: replaying answers produced against different items is
    # the same failure wearing different clothes.
    prior_rows: dict[str, dict[str, Any]] = {}
    # WHAT ARM DID THESE OUTPUTS COME FROM? A crashed run has no metrics.json --
    # it is written after the pass returns -- so the previous version of this check
    # could only WARN, and
    #     make run CONFIG=arm_a.yaml ARGS="--resume <crashed arm_b run>"
    # exited 0 having recorded arm_a with arm_b's answers. The guard covered the
    # tidy case and not the crash, which is the only case resume exists for.
    #
    # `run.json` is now written BEFORE the first item, so identity survives a kill.
    ident = _model_runs.run(runs / resume)
    if ident is None:
        die(
            f"cannot resume: {resume} has no run.json, so the "
            f"arm that produced those outputs cannot be identified.\n"
            f"  Resuming anyway would replay whatever is in that directory and record it "
            f"under {cfg.get('system_id')!r}.",
            "not-found",
        )
    if ident.get("system_id") and ident["system_id"] != cfg.get("system_id"):
        die(
            f"cannot resume: {resume} is arm {ident['system_id']!r}, "
            f"this system is {cfg.get('system_id')!r}.\n"
            f"  Resuming would replay another arm's answers and record them "
            f"under this one.",
            "mismatch",
        )
    if ident.get("dataset_id") and ident["dataset_id"] != cfg.get("dataset_id"):
        die(
            f"cannot resume: {resume} ran on dataset "
            f"{ident['dataset_id']!r}, this system is on "
            f"{cfg.get('dataset_id')!r}.",
            "mismatch",
        )

    # THE PRIOR ROWS, so a replayed item keeps the cost, tokens, latency and _meta
    # measured for it. The row checkpoint is appended DURING the pass and so
    # survives a crash; predictions.jsonl is the tidy-exit copy of the same thing.
    first = _model_runs.first_score(runs / resume)
    for partial in (True, False):
        at = runs / resume if partial else first
        if at is None:
            continue
        got = _outputs.rows(
            at, partial=partial, errors="replace"
        )  # a torn final line from a kill mid-append is skipped
        if got is None:
            continue
        src = at / (_outputs.ROWS if partial else _outputs.PREDICTIONS)
        for r in got:
            if r.get("item_id"):
                if not isinstance(r.get("_extra"), dict):
                    die(
                        f"cannot resume: {src} has rows without `_extra`; it was not written "
                        f"by this version of the harness",
                        "invalid-file",
                    )
                # A finished run's rows have the run's settings taken off (RFC-033): put back, or the resumed run that
                # replays them holds rows without them and has no `call` to hoist.
                prior_rows.setdefault(
                    r["item_id"], r if partial else _results.restore_call(r, ident.get("call"))
                )
    if not prior_rows:
        print(
            f"  WARNING: {resume} carries no per-item rows — replayed items "
            f"will report no cost, tokens or _meta."
        )
    return resume_dir, prior_rows


def body(**inputs: Any) -> int:
    """Run a system on a dataset."""
    args = legacy.namespace(inputs, "run")
    # Redirected to a log, stdout is block-buffered and a watcher saw nothing for minutes (stderr, where --json sends
    # the progress, can be as well): a line is written when it is printed, whatever the stream is.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(line_buffering=True)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    from evaluation_harness.model.systems import arm_of  # noqa: PLC0415

    if args.run_id:
        plain_id_ok(args.run_id, "--run-id")

    cfg, args.config = arm_of(args.system, args.dataset, args.goal, args.round)
    # A system may name a model record (RFC-020, optional): its settings come from the record, under the
    # system's own params, so every arm of that model runs the way it was onboarded. With `deployment:` it
    # also names where it runs (RFC-021): the fingerprint takes the deployment's facts from the record.
    from evaluation_harness import _models  # noqa: PLC0415

    try:
        cfg = _models.resolve(cfg, DATA)
    except ValueError as exc:
        die(f"{args.config}: {exc}", "invalid-file")
    call_system, score, adapter_id, adapter_path, warmup, model_fingerprint = load_adapter(
        cfg.get("adapter"), Path(args.config)
    )
    recorded = None
    if (cfg.get("params") or {}).get("provider") == "recorded":
        recorded = _recorded_outputs(cfg, adapter_path)
        warmup = None  # nothing is called, so nothing is warmed up
    declared_kinds = metric_kinds(adapter_path)
    # A key written into the system would be copied into every run record (metrics.json), and
    # from there onto pages: refused, with the way that keeps it out.
    secrets = secret_params(dict(cfg.get("params") or {}))
    if secrets:
        die(
            f"{args.config}: params {', '.join(secrets)} look like a credential written into the system. "
            "Put the key in the environment (.env) and name the variable with api_key_env, or let the "
            "provider read its usual variable; a key in a system is copied into every run record.",
            "not-configured",
        )

    # A run names the goal it answers (data/goals/<goal_id>.yaml). Refused before a cent is
    # spent when the goal does not exist: a run filed under a typo answers nothing.
    if cfg.get("goal") and _store.is_dir(GOALS) and cfg["goal"] not in load_goals():
        die(
            f"--goal {cfg['goal']!r} is not in {GOALS} (known: {', '.join(sorted(load_goals())) or 'none'})",
            "not-found",
        )
    if not cfg.get("goal") and not args.scratch and (since := goal_required_from()):
        die(
            f"goals are required from {since} (data/goals/policy.yaml): name the goal this run answers with --goal "
            "(evh goal-list)",
            "bad-argument",
        )
    # A run may name a round of its goal (ADR-0004, optional): refused before a cent is spent
    # when the round does not exist, is closed, or runs on another dataset.
    from evaluation_harness import _rounds  # noqa: PLC0415

    rnd = _rounds.config_round(cfg, args.config)
    # A hypothesis (ADR-0025, optional) is refused with the same words validate V20 uses.
    from evaluation_harness import _hypothesis  # noqa: PLC0415

    bad_hypothesis = _hypothesis.problems(cfg, args.config)
    if bad_hypothesis:
        die(f"{args.config}: " + "; ".join(bad_hypothesis), "invalid-file")
    ds = load_dataset(cfg["dataset_id"])
    # A replay (RFC-030): the system's own code at the commit each item came from, items in order, each called once.
    from evaluation_harness import _replay  # noqa: PLC0415

    if _replay.is_replay(cfg):
        _replay.refuse_flags(args)
        if recorded is not None:
            die(
                f"{args.config}: a replay calls the system's code; provider recorded calls nothing",
                "invalid-file",
            )
    plan = _replay.prepare(cfg, args.config, ds, adapter_path)
    # CALL ONCE (RFC-038): the adapter says each item's call has an effect that a retry would repeat. A recorded arm calls
    # nothing, so it is not call-once whatever its adapter says.
    declared_once = recorded is None and call_once(adapter_path, dict(cfg.get("params") or {}))
    once = plan is not None or declared_once
    if args.recall_failed:
        if not args.resume:
            die(
                "--recall-failed names the items an earlier run called once and did not finish, to call them again: "
                "it goes with --resume RUN",
                "bad-argument",
            )
        if not declared_once:
            die(
                f"--recall-failed: {cfg['system_id']} is not call-once (its adapter declares no CALL_ONCE or "
                "call_once(params)): its failed items were retried, and --resume calls them again without a flag",
                "bad-argument",
            )
    if args.items is not None:
        if not _store.is_file(args.items):
            die(f"--items {args.items}: no such file", "not-found")
        wanted = [
            ln.strip() for ln in _store.read_text(args.items, encoding="utf-8").splitlines() if ln.strip()
        ]
        known_ids = {it["item_id"] for it in ds.get("items") or []}
        missing = sorted(set(wanted) - known_ids)
        if missing:
            die(
                f"--items: {len(missing)} id(s) not in {cfg['dataset_id']}: {', '.join(missing[:5])}",
                "not-found",
            )
        if not wanted:
            die(f"--items {args.items}: no item ids in it", "not-enough")
        keep = set(wanted)
        ds = {**ds, "items": [it for it in ds["items"] if it["item_id"] in keep]}
        print(f"  --items: {len(ds['items'])} of {len(known_ids)} items of {cfg['dataset_id']}")
    # A SEALED SIDE IS HELD OUT (the fleet's feedback 29): refused before a cent is spent, unless an unseal named
    # this system in advance.
    from evaluation_harness import _seal  # noqa: PLC0415

    _seal.refuse_if_sealed(cfg["dataset_id"], "a run", cfg["system_id"])
    stamp = now().replace(":", "").replace("-", "")
    base_id = args.run_id or f"{cfg['system_id']}_{stamp}"
    build = build_info()
    ref_dir, ref_tier = _reference_for(cfg["dataset_id"])
    ref_id = str(ref_dir.relative_to(REFERENCES)) if ref_dir else None
    if args.labels:
        from evaluation_harness._common import LABELS_TIER, labels_reference, scored_against_dir  # noqa: PLC0415

        ref_id = labels_reference(args.labels, cfg["dataset_id"])
        ref_dir, ref_tier = scored_against_dir(ref_id), LABELS_TIER
    # A run scored against a label set is a run like any other; its score is read as an arm of its own, as a
    # re-score against one is (its label names the set).
    runs = _model_runs.root(args.scratch)
    label_as = _datasets.label_of(ref_id.removeprefix(LABELS_PREFIX)) if args.labels and ref_id else ""
    if args.of and not _model_runs.run(args.of):
        die(f"--of {args.of}: no run of that id in {runs}", "not-found")
    if args.of and args.purpose != "run":
        _refuse_unrelated_of(args.of, cfg, args.purpose)
    if args.purpose == "repeat" and not args.of and not args.scratch:
        die(
            "--purpose repeat names the run it repeats: add --of RUN (a run with no --of is read under `repeats`, "
            "joined to no arm, so nothing says what it repeats)",
            "bad-argument",
        )
    if args.purpose == "run" and args.of:
        die("--of names the run a re-run re-does: give its --purpose (repeat, retime, pair)", "bad-argument")
    if args.purpose == "run" and args.repeat > 1 and not args.resume and not args.scratch and not args.labels:
        _refuse_repeat_beside_run(cfg["system_id"], cfg["dataset_id"], args.repeat)
    # HOW MANY ITEMS HAVE A REFERENCE, counted before any call. A metric scored against a
    # missing reference is not computed, so with gold for 20 of 200 items the run's mean is a
    # mean over 20, recorded as a 200-item gold run. None is a refusal (nothing would be
    # scored and the calls would be paid for); some is a warning, and the count is recorded.
    coverage = None
    if ref_tier and ref_dir is not None:
        ids = [it["item_id"] for it in ds.get("items") or []]
        have = sum(1 for i in ids if _store.is_file(ref_dir / f"{i}.txt"))
        coverage = {"items_with_reference": have, "items": len(ids)}
        if have == 0:
            die(
                f"{ref_tier} references for {cfg['dataset_id']} are at {ref_dir}, but none of its "
                f"{len(ids)} items has a file there (<item_id>.txt): nothing would be scored.\n"
                "  Check the file names against the dataset's item ids.",
                "mismatch",
            )
        if have < len(ids):
            print(
                f"  WARNING: only {have} of {len(ids)} items have a {ref_tier} reference: quality is a "
                f"mean over those {have}, and the run records that (reference_coverage)."
            )
    if args.labels:
        print(f"  scoring against the label set {ref_id} (labels, not a reference)")
    elif ref_tier:
        print(f"  scoring against {ref_tier.upper()} references for {cfg['dataset_id']}")
    else:
        print(f"  no reference set for {cfg['dataset_id']} — quality cannot be scored.")
        print(
            "  a reference set is labels you promote (RFC-023): a run of the arm you trust most as a model's labels,"
        )
        print("    evh label-from-run --run <run_id> --set <name>")
        print(
            f"  (or a person's: evh label-sheet --dataset-id {cfg['dataset_id']} --out sheet.csv, then evh label-import),"
        )
        print(
            f"  then: evh reference-promote --dataset-id {cfg['dataset_id']} --labels <name> --tier gold|silver "
            '--reason "…" --by <you>'
        )
    if build["ref"] == "unknown":
        print("  WARNING: could not identify the build — this run is not attributable")
    faith = (
        _faithfulness_gate(plan, ds, adapter_id, adapter_path, ref_tier, args) if plan is not None else None
    )

    if args.dry_run:
        calls_only, note = None, None
        if args.resume and declared_once:  # what the resume would call, not the whole dataset
            rdir, prows = _resume_source(args.resume, cfg, runs)
            assert rdir is not None
            done = _outputs.outputs(rdir)
            held = _held_items(ds["items"], done, prows, _outputs.started(rdir))
            fresh = [it for it in ds["items"] if it["item_id"] not in done and it["item_id"] not in held]
            calls_only = len(fresh) + (len(held) if args.recall_failed else 0)
            note = (
                f"resume {args.resume}: {len(done)} done (read, not called), {len(held)} called once already "
                f"({'CALLED AGAIN, --recall-failed: their side effects repeat' if args.recall_failed else 'not called; --recall-failed would call them'}), "
                f"{len(fresh)} never attempted (called): {calls_only} call(s) in all"
            )
        return _dry_run(
            ds, cfg, args.repeat, adapter_path, args.config, declared_once, calls_only, note, adapter_id
        )

    if declared_once:
        print(CALL_ONCE_LINE)

    # WARM UP once per arm, before anything is timed. Two jobs in one:
    #
    #   measurement — a local model's first call includes loading its weights. Left in the
    #   timed path that cost lands in latency_ms and gets amortised over the dataset, so
    #   the arm looks catastrophically slow on 5 items and fine on 500: the metric would
    #   be measuring dataset size.
    #
    #   pre-flight — a bad key or an absent model fails HERE, before any item is paid for,
    #   instead of on item 34 of 50 after you have already paid for 33.
    #
    # Once per ARM, not per repeat: REPEAT exists to measure the arm's own jitter, and
    # letting load variance into that measures the wrong thing.
    # The prompts the system declares (RFC-028): each file's version found or recorded, the adapter given their text
    # (and a per-run copy of a prompt root), the fingerprint their hashes. The run record keeps the system's params.
    from evaluation_harness import _prompts  # noqa: PLC0415

    resolved = _prompts.resolve(cfg, args.config, cfg["system_id"])
    if resolved is not None:
        import atexit  # noqa: PLC0415

        atexit.register(_prompts.remove_copy, resolved)
    call_cfg = {**cfg, "params": {**dict(cfg.get("params") or {}), **(resolved or {}).get("params", {})}}
    from evaluation_harness._adapter import prompt_problem  # noqa: PLC0415

    if problem := prompt_problem(adapter_path, call_cfg["params"]):
        die(f"{cfg['system_id']}: {problem}; nothing was run", "invalid-file")
    if plan is not None:
        _replay.environment()
    warmup_ms: float | None = None
    if warmup is not None:
        started = time.perf_counter()
        try:
            # Retried too. Warm-up is a real network call, and a transient failure here
            # aborted the arm before a single item was attempted -- a safety check that
            # invents a new way to lose a run is not a safety check.
            call_with_retries(
                warmup,
                (dict(call_cfg["params"]),),
                label="warm-up",
                extra_transient=transient_markers(adapter_path),
            )
        except Exception as exc:  # noqa: BLE001 - fail before spending, with the reason
            die(
                f"warm-up failed for {cfg['system_id']}: {type(exc).__name__}: {exc}\n"
                "  nothing was run and nothing was spent.",
                "failed",
            )
        warmup_ms = round((time.perf_counter() - started) * 1000, 3)
        if warmup_ms < WARMUP_NOTHING_MS:
            print("  warm-up: nothing to load for this arm (a hosted or no-model arm); timing is unaffected")
        else:
            print(f"  warmed up in {warmup_ms:.0f}ms — timing below excludes it")

    fingerprint = build_fingerprint(
        root=ROOT,
        data_dir=DATA,
        dataset=ds,
        reference_id=ref_id,
        reference_tier=ref_tier,
        system_id=cfg["system_id"],
        params=dict(cfg.get("params") or {}),
        adapter_id=adapter_id,
        adapter_path=adapter_path,
        model_hook=model_fingerprint,
        cfg=cfg,
        prompt_settings=(resolved or {}).get("settings"),
        replay=plan,
    )
    print(f"  fingerprint {fingerprint['hash'][:12]}")
    repeat_says, repeat_joins = None, False
    if args.purpose == "repeat" and args.of and not args.scratch:
        reading = _repeat_reading(args.of, fingerprint, cfg, label_as)
        repeat_joins = reading["joins"]
        if reading["joins"] and rnd is not None:
            _refuse_repeat_of_retired(rnd, cfg["system_id"], reading["label"], args.of)
        repeat_says = _says_repeat(args.of, reading)
        print(repeat_says[0])
    prompt_versions = {} if args.scratch else _prompt_versions(adapter_path, adapter_id, cfg, fingerprint)
    # A DIRTY TREE IS NOT A VERSION. The fingerprint records it, but a field nobody reads
    # is not a warning: a 72-run sweep completed with `harness.dirty: true` throughout, so
    # its `harness.commit` identified code that was never what ran, and nothing said so
    # until the runs were audited afterwards. Say it at the top of the run, where the
    # person paying for it will see it.
    if (fingerprint.get("instrument", {}).get("harness", {}) or {}).get("dirty"):
        print(
            "  WARNING: harness tree is DIRTY — the recorded commit does not identify\n"
            "           the code that is about to run. Commit first for a reproducible\n"
            "           record, or accept that this run cannot be reproduced from its\n"
            "           own fingerprint."
        )

    # `--resume` WITH `--repeat N` REPLAYS THE SAME OUTPUTS N TIMES. Each repeat reads
    # the same resume directory, so every pass after the first is a copy of the same
    # answers -- and each one carries their cost again, so an arm that cost $1 reports
    # $3 across three "repeats" that measured nothing. The two flags mean opposite
    # things: --repeat asks for N independent measurements, --resume says do not
    # measure what you already have. Found by external review.
    if args.resume and args.repeat > 1:
        die(
            "--resume and --repeat are mutually exclusive.\n"
            "  --repeat N asks for N INDEPENDENT passes; --resume says replay what is\n"
            "  already on disk. Together, every repeat after the first replays the same\n"
            "  outputs and re-counts their cost.\n"
            "  Resume the interrupted pass with --repeat 1, then run the rest.",
            "bad-argument",
        )

    resume_dir, prior_rows = _resume_source(args.resume, cfg, runs)
    if not args.scratch:
        warn_if_ignored(runs)

    made: list[Path] = []
    written: list[dict[str, Any]] = []

    capped = False
    per_repeat: list[dict[str, float]] = []
    if args.repeat > 1 and cfg.get("model_record") and cfg.get("deployment"):
        rec = _models.find(DATA, cfg["model_record"]) or {}
        dep = _models.deployment_of(rec, cfg["deployment"]) or {}
        # Determinism is a deployment's, not a model's: the same weights differ between machines.
        same = (((dep.get("onboarding") or {}).get("report") or {}).get("deterministic")) is True
        if same and temperature(cfg.get("params") or {}) == 0:
            where = f" on {cfg['deployment']}"
            print(
                f"  NOTE: {cfg['model_record']} gave the same output twice{where} when it was onboarded, and this arm "
                f"runs at temperature 0: expect its {args.repeat} passes to be identical. The spread comes from "
                "other deployments (machines, builds) or a temperature above 0."
            )
    # Read once, before the first call: what the system says now and whether it was committed already.
    hypothesis = _hypothesis.record_for(cfg, args.config, build, now())
    if hypothesis:
        print(f"  hypothesis  named in advance: {_hypothesis.said(hypothesis['hypothesis_in_advance'])}")

    # A run is never written into another run's directory. The id is the system and the start to the second, so two
    # runs of one system started in the same second shared a directory, and the second wrote over the first, a
    # committed run included (2026-11-04). An id already taken: the next second's stamp; a --run-id taken: refused.
    def taken(base: str) -> bool:
        return _store.exists(runs / base) or any(
            _store.exists(runs / f"{base}_r{i + 1}") for i in range(args.repeat)
        )

    if args.run_id:
        if taken(base_id):
            die(
                f"--run-id {base_id}: {runs / base_id} exists: a run is never written into another; name a new id",
                "would-overwrite",
            )
    else:
        for _ in range(30):
            if not taken(base_id):
                break
            time.sleep(1.0)
            base_id = f"{cfg['system_id']}_{now().replace(':', '').replace('-', '')}"
        else:
            die(
                f"{runs}: every run id for {cfg['system_id']} in the last 30 seconds is taken; run again",
                "failed",
            )
    if rnd is not None and recorded is None:
        # A round with a budget (RFC-026 step 5): what it has left, reserved before the first call; refused when
        # nothing is left. Two arms started at once share what is left, never both all of it.
        share = _spend.reserve(rnd, "run")
        if share is not None:
            print(f"  round {rnd['round_id']}: ${share:.4f} of its budget reserved for this run")
    for i in range(args.repeat):
        run_id = base_id if args.repeat == 1 else f"{base_id}_r{i + 1}"
        run_dir = runs / run_id
        _spend.add_run(run_id)
        # The output directory exists BEFORE the pass starts, so each item lands on disk
        # as it is produced and a crash leaves something to resume from.
        #
        # AND SO DOES THE RUN'S IDENTITY. `metrics.json` is written after the pass
        # returns, so a crashed run could not say which arm produced its outputs --
        # which made `--resume`'s arm guard unenforceable in the one case resume is
        # for. This is small, written first, and never rewritten.
        _store.mkdir(run_dir, parents=True, exist_ok=True)
        identity = {
            "system_id": cfg.get("system_id"),
            "dataset_id": cfg.get("dataset_id"),
            "started_at": now(),
            "run_id": run_id,
            "purpose": args.purpose,
            "build": build,  # a crashed run still says which build made it (V3)
            **({"of": args.of} if args.of else {}),
            **({"call_once": True} if declared_once else {}),
        }
        _model_runs.write_run(run_id, identity, scratch=args.scratch)
        try:
            result = one_pass(
                {**ds, "items": plan.items} if plan is not None else ds,
                call_cfg,
                i,
                resume_dir=resume_dir,
                prior_rows=prior_rows,
                live_dir=run_dir,
                call_system=call_system,
                score=score,
                extra_transient=transient_markers(adapter_path),
                score_failure=_score_failure_of(adapter_path),
                score_run=run_scorer(adapter_path),
                scored_against=(ref_dir, ref_tier),
                recorded=recorded,
                primary=primary_metric(adapter_path, cfg.get("params") or {}),
                per_item=_replay.item_params(plan) if plan is not None else None,
                once=once,
                same=same_at(adapter_path),
                recall=args.recall_failed,
            )
        except BaseException as exc:
            _say_stopped(
                run_dir, len(ds.get("items") or []), f"--system {args.system} --dataset {args.dataset}", exc
            )
            if isinstance(exc, SystematicFailure):
                die(str(exc), "failed")
            if isinstance(exc, ServerUnreachable):
                sys.exit(EXIT_TRY_LATER)  # said above in full; a traceback adds nothing
            raise
        _store.mkdir(run_dir, parents=True, exist_ok=True)
        # The outputs were appended as produced; the finished file is every output in dataset order, a resumed
        # item's included (it came from the PREVIOUS run, and this one must be self-contained), a failed item's
        # left out (not done: --resume calls it again). The row checkpoint goes: predictions.jsonl has the rows.
        failed_ids = {f["item_id"] for f in result.get("failed_items") or []}
        _outputs.finish(
            run_dir,
            {k: v for k, v in result["outputs"].items() if k not in failed_ids},
            [it["item_id"] for it in ds.get("items") or []],
        )

        metrics = run_record(
            run_id=run_id,
            dataset_id=cfg["dataset_id"],
            system_id=cfg["system_id"],
            build=build,
            scores=result["scores"],
            n_items=len(result["predictions"]),
            # The metrics score_run() computed over the whole run: one number each, no per-item values to test.
            run_metrics=result.get("run_metrics") or None,
            # The knobs this run ACTUALLY used, not just the system's name. A system_id
            # names a file, and a file can be edited after the run — so without this a run
            # cannot say what produced it, only which YAML was pointed at. It also lets V5
            # tell a deterministic repeat (same params, same scores — expected) from two
            # different systems landing on byte-identical output (worth a look).
            params=dict(cfg.get("params") or {}),
            # WHICH scorer produced these numbers. A scorer is half of what a number means,
            # so a run that does not name it cannot be compared to one that used another.
            adapter=adapter_id,
            # The adapter's own reading of its metrics, carried on the run so a leaderboard
            # built later does not have to guess what `compression` is.
            metric_kinds=dict(declared_kinds or {}),
            metric_directions=metric_directions(adapter_path),
            metric_descriptions=metric_descriptions(adapter_path) or None,
            providers_seen=result.get("providers_seen") or {},
            primary_metric=primary_metric(adapter_path, cfg.get("params") or {}),
            # Outside `scores` on purpose: real, worth seeing, but not the arm's per-item
            # speed — and in scores it would reach the leaderboard's speed column and V5's
            # duplicate key, where it means something else.
            warmup_ms=warmup_ms,
            # What this number depended on, and one hash over all of it. A comparison is
            # only valid if exactly one field moved; this is what makes that checkable
            # rather than asserted.
            fingerprint=fingerprint,
            # What the run is FOR, and the output format it was asked for: outside the
            # fingerprint on purpose. Neither changes what was measured, only what it answers.
            goal=cfg.get("goal") or None,
            round=cfg.get("round") or None,
            model_record=cfg.get("model_record") or None,
            deployment_id=cfg.get("deployment") or None,
            format=cfg.get("format") or None,
            expect_identical_to=cfg.get("expect_identical_to") or None,
            **hypothesis,
            reference_tier=result["reference_tier"] or None,
            reference_coverage=coverage
            if coverage and coverage["items_with_reference"] < coverage["items"]
            else None,
            # What a resumed run carried from the pass it replayed, on the record rather
            # than only in the terminal: which extras came forward, and for how many
            # replayed items nothing could.
            resume=result.get("resume") or None,
            failed_items=result.get("failed_items") or None,
            call_once=True if declared_once else None,
            recalled=result.get("recalled") or None,
            not_scorable=result.get("not_scorable") or None,
            history_confound=_confound(result["predictions"]),
            cost_coverage=_cost_coverage(result["predictions"]),
            repeat_index=(i + 1) if args.repeat > 1 else None,
            faithfulness=faith,
        )
        # The pass (run.json: what ran, on what, how) and the score it made (scores/<scorer>@<reference>/), its rows
        # beside it (RFC-032 step 4). The settings every row holds (RFC-033) are the run's, in run.json, and not in the
        # rows: worked out here, in memory, so the rows are written once.
        call = _results.run_call(result["predictions"])
        rows = [_results.strip_call(r, call) for r in result["predictions"]]
        _model_runs.write_run(
            run_id,
            {
                **_model_runs.run_part(metrics),
                "started_at": identity["started_at"],
                **({"prompt_versions": prompt_versions} if prompt_versions else {}),
                **({"call": call} if call else {}),
                "purpose": args.purpose,
                "machine": _model_runs.machine_of(metrics.get("fingerprint")),
                **({"of": args.of} if args.of else {}),
            },
            scratch=args.scratch,
        )
        score_dir = _model_runs.write_score(
            run_id,
            _model_runs.scorer_of(metrics),
            ref_id,
            metrics,
            label_as=label_as,
            first=True,
            scratch=args.scratch,
        )
        _outputs.write_rows(score_dir, rows)
        if (metrics.get("history_confound") or {}).get("items"):
            hc = metrics["history_confound"]
            print(
                f"  note: history confound: {hc['items']} of {hc['of']} item(s) met a human reaction recorded after "
                "an action production took and this variant did not (RFC-031): its score there reads that reaction"
            )
            from evaluation_harness import _exposure  # noqa: PLC0415

            if not _exposure.applies(
                cfg["dataset_id"]
            ):  # a held-out side's ids stay off the record: a count only
                ids = [r["item_id"] for r in result["predictions"] if r.get("history_confound") == 1.0]
                _store.write_text(
                    run_dir / "confound.jsonl", "".join(json.dumps({"item_id": i}) + "\n" for i in ids)
                )
        made.append(score_dir)
        if rnd is not None and not args.scratch:
            # The run joins its system's arm in the round (RFC-032 step 5), read under the label of its own score.
            from evaluation_harness import _actor  # noqa: PLC0415

            joined = _rounds.join(
                rnd["goal"],
                rnd["round_id"],
                cfg["system_id"],
                run_id,
                _model_runs.label(score_dir),
                _actor.actor(),
                repeat_joins,
            )
            if joined is None:
                print(
                    f"  note: {rnd['round_id']} reads {cfg['system_id']} under a re-score this run is not yet: it is "
                    f"read in the round once re-scored (evh rescore --goal {rnd['goal']} --round {rnd['round_id']})"
                )
        written.append(
            {
                "run_id": run_id,
                "system_id": cfg["system_id"],
                "dataset_id": cfg["dataset_id"],
                "dir": str(run_dir),
                "n_items": metrics["n_items"],
                "total_cost_usd": result["scores"].get("total_cost_usd"),
                "capped_at": result["capped_at"] or None,
                "call_once": declared_once,
                "failed_items": result.get("failed_items") or [],
            }
        )
        per_repeat.append(result["scores"])
        if result.get("not_scorable"):
            print(
                f"  note: {len(result['not_scorable'])} item(s) not scorable under this variant: their label holds "
                "only under production's action, and this run acted otherwise (RFC-031); left out of its scores"
            )
        print(
            f"  {run_id}  "
            + "  ".join(
                f"{k}={v}" for k, v in result["scores"].items() if not k.startswith(BOOKKEEPING_PREFIXES)
            )
        )
        if result["capped_at"]:
            capped = True
            if _spend.zero_blocked(_spend.cap(), call_cfg.get("params")):
                print(f"\n  {args.system}: {_spend.ZERO_CAP_HINT}")
            print(
                f"\n  COST CAP HIT at item {result['capped_at']} — "
                f"spent ${result['spent_usd']:.4f} this pass, ${_spend.spent():.4f} in all, of the cap "
                f"(${_spend.cap() or 0:.4f}: EVAL_MAX_COST_USD, or what the round left this run).\n"
                f"  Partial results kept. Raise the cap and resume without paying twice:\n"
                f"    "
                + how(
                    f"evh run --system {args.system} --dataset {args.dataset} --resume {run_id}",
                    f'make run SYSTEM={args.system} DATASET={args.dataset} ARGS="--resume {run_id}"',
                )
            )
            break

    if args.repeat > 1:
        print(f"\n  Arm spread over {args.repeat} repeats (max - min on identical input):")
        shown = sorted(k for k in per_repeat[0] if not k.startswith(BOOKKEEPING_PREFIXES))
        w = max(len(k) for k in shown)
        kinds = classify_metrics(
            (_model_runs.record(made[-1]) or {}).get("metric_kinds") or {} if made else {}
        )
        for k in shown:
            vals = [r[k] for r in per_repeat if k in r]
            spread = max(vals) - min(vals)
            # Determinism is a property of what an arm OUTPUTS; cost and time vary with the
            # tokens and the machine, and a stored per-item mean is rounded.
            if kinds.get(k) in ("cost", "speed"):
                verdict = f"{kinds[k]}, not a quality metric"
            else:
                verdict = "deterministic" if spread == 0 else f"treat deltas below {spread:.6f} as noise"
            print(f"    {k:{w}} spread={spread:.6f}   {verdict}")
        # The arm-level spread can be 0 while items move (or move while the mean stays): say how many ITEMS
        # every repeat scored the same, so k repeats are read as k samples only when they are (feedback 33).
        from evaluation_harness._runs import repeat_agreement, say_agreement  # noqa: PLC0415

        prim = (_model_runs.record(made[-1]) or {}).get("primary_metric") if made else None
        ag = repeat_agreement([(d, {}) for d in made], prim) if prim else None
        if ag:
            print(
                f"    {say_agreement(f'per item, on {prim}', ag)}; read {ag['items']} items, "
                f"not {ag['item_runs']} item-runs (pair-test counts each item once)"
            )

    print(f"\nwrote {len(made)} run(s) to {runs}")
    for d in made:
        print(f"  run {_model_runs.run_of(d).name}")
    _jsonout.value("runs", written)
    # What this command spent, so nobody adds up total_cost_usd by hand across repeats.
    spent = sum(
        float(((_model_runs.record(d) or {}).get("scores") or {}).get("total_cost_usd") or 0) for d in made
    )
    if spent:
        from evaluation_harness import _runs  # noqa: PLC0415
        from evaluation_harness.cost_report import billed_and_recorded  # noqa: PLC0415

        billed = sum(billed_and_recorded(d)[0] for d in made)
        sources = {s for d in made for r in _runs.item_rows(d) if (s := cost_source(r.get("_meta")))}
        by_table = any(priced_by_table(r.get("_meta")) for d in made for r in _runs.item_rows(d))
        basis = spend_basis(billed, max(spent - billed, 0.0), by_table, sources)
        print(f"spent ${spent:.6f} ({basis})")
        drift = price_drift((r for d in made for r in _runs.item_rows(d)), call_cfg["params"])
        if drift:
            print(drift)

    # A CAPPED RUN IS NOT A SUCCESSFUL RUN, AND AN EMPTY ONE CERTAINLY IS NOT.
    #
    # This returned 0 whatever happened. `EVAL_MAX_COST_USD=0` wrote a run directory
    # holding `"scores": {}` and zero prediction rows, printed the cost-cap notice, and
    # exited 0 -- so a sweep script or CI job saw success and moved on, leaving a run
    # that measured nothing sitting in data/runs/ looking like the others. Found by
    # external review.
    #
    # Partial results are still KEPT on disk and the resume hint still prints: that part
    # of the design was deliberate and is not changed. What changes is that the caller is
    # told, because "the cap stopped me after 3 of 200 items" and "I measured 200 items"
    # must not both be exit 0.
    empty = [d for d in made if not ((_model_runs.record(d) or {}).get("scores") or {})]
    if empty:
        print(f"\n  FAILED: {len(empty)} run(s) scored NO items and carry empty scores:")
        for d in empty:
            print(f"    {_model_runs.run_of(d).name}")
        print("  Nothing was measured. Raise EVAL_MAX_COST_USD, or check the adapter.")
        return EXIT_NOTHING
    if capped:
        # Distinct from EXIT_NOTHING so a caller can tell "stopped early with usable partial
        # results" from "produced nothing".
        print(f"\n  Stopped early by the cost cap — exit {EXIT_STOPPED}. Partial results above are kept.")
        return EXIT_STOPPED
    if not args.scratch:
        warn_if_ignored(runs)
    if repeat_says:
        print(repeat_says[1])
    return 0
