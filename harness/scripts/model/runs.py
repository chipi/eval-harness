"""Runs and their scores (RFC-032 step 4): one collection, `data/runs/<run_id>/`, every pass of a system over a
dataset, each score of it under it.

    runs/<run_id>/run.json                        the pass: system, dataset, purpose, machine, settings, fingerprint
    runs/<run_id>/outputs.jsonl                   what the system answered, per item
    runs/<run_id>/scores/<key>/score.json         the scorer, the reference, the label it is read under
    runs/<run_id>/scores/<key>/metrics.json       the score: what it measured, where it differs from the run
    runs/<run_id>/scores/<key>/predictions.jsonl  its rows, per item

A score's key is `<scorer>@<reference>`: the scorer an adapter's 12 characters of sha256 or a judge scorer's id, the
reference `gold.<dataset>`, `silver.<dataset>`, `labels.<dataset>.<set>` or, for a judge, its judging set.

`record(score)` is what one record of a scored run says, the run's facts with the score's over them, as a run's
metrics.json said before this step: every reader takes `(score directory, record)` pairs. What a folder used to mean
is a field: the run's `purpose` (run, repeat, pair, retime) and `machine`, the score's `label` ("silver",
"rescored cd35dc1f", "judged/judge-summ-v1"). The arm a view reads is a system on a dataset under one label, the
score's and the run's purpose's joined ("rescored cd35dc1f, repeats")."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._number import counted, is_number, is_scored

RUN = "run.json"
SCORE = "score.json"
METRICS = "metrics.json"
ROWS = "predictions.jsonl"
OUTPUTS = "outputs.jsonl"

PURPOSES = ("run", "repeat", "pair", "retime")
#: What a run's purpose adds to the label of the arm it is read in (a re-timing is named by its machine).
PURPOSE_LABEL = {"run": "", "repeat": "repeats", "pair": "pair"}
#: Run fields that the record of a scored run did not hold before step 4 (what a folder meant, when the pass
#: started, the prompt versions it sent, the settings its rows share): facts of the pass, never a score's to unset.
RUN_ONLY = ("purpose", "machine", "of", "started_at", "prompt_versions", "call")
#: Of a measured run's first record, what belongs to the score it made rather than to the pass.
SCORE_KEYS = (
    "scores",
    "primary_metric",
    "metric_kinds",
    "metric_directions",
    "metric_descriptions",
    "reference_tier",
    "rescore_dropped_metrics",
    "derived",
    "source_created_at",
)


def root(scratch: bool = False, data: Path | None = None) -> Path:
    """data/runs; .build/scratch/runs for a throwaway pass (`evh run --scratch`), which nothing that reads runs sees.
    `data`: another data directory than the project's (a deployment's copy of it, which the catalog reads)."""
    if scratch:
        return _common.SCRATCH_RUNS
    return _common.RUNS if data is None or Path(data) == _common.DATA else Path(data) / "runs"


def run_dir(run_id: str, scratch: bool = False, data: Path | None = None) -> Path:
    """A run's directory."""
    return root(scratch, data) / run_id


def is_score(d: Path) -> bool:
    """Whether `d` is a score's directory (runs/<id>/scores/<key>)."""
    return Path(d).parent.name == "scores"


def run_of(score_dir: Path) -> Path:
    """The run a score is of."""
    return Path(score_dir).parent.parent


def reference_part(reference_id: str | None) -> str:
    """A reference id as it sits in a score's key: `gold/x` is `gold.x`; none is `none`."""
    return str(reference_id).replace("/", ".") if reference_id else "none"


def key(scorer: str, reference: str | None) -> str:
    """A score's key: `<scorer>@<reference>`."""
    if not scorer or "/" in scorer or "@" in scorer:
        raise ValueError(f"a score's scorer is a hash or a judge scorer's id, not {scorer!r}")
    return f"{scorer}@{reference_part(reference)}"


def scorer_of(rec: dict[str, Any]) -> str:
    """The scorer of a record, 12 characters (RFC-022): a re-score's `derived.with.sha256`, else the adapter's
    `sha256` its fingerprint's instrument records; "" when it records neither."""
    with_ = (rec.get("derived") or {}).get("with") or {}
    sha = with_.get("sha256") or (
        ((rec.get("fingerprint") or {}).get("instrument") or {}).get("adapter") or {}
    ).get("sha256")
    return str(sha or "")[:12]


def machine_of(fingerprint: dict | None) -> str:
    """The machine a run ran on, as its label says it: the operating system of its fingerprint's runner."""
    plat = str(((fingerprint or {}).get("runner") or {}).get("platform") or "")
    return plat.split("/", 1)[0].lower()


def _json(path: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def run(run_id_or_dir: str | Path, data: Path | None = None) -> dict[str, Any] | None:
    """A run's run.json, or None."""
    d = run_id_or_dir if isinstance(run_id_or_dir, Path) else run_dir(run_id_or_dir, data=data)
    return _json(Path(d) / RUN)


def meta(score_dir: Path) -> dict[str, Any]:
    """A score's score.json: {scorer, reference, label}."""
    return _json(Path(score_dir) / SCORE) or {}


def record(score_dir: Path) -> dict[str, Any] | None:
    """What a scored run's record says: the run's facts with the score's over them (the keys the score unsets
    removed). None when either is missing or unreadable."""
    sd = Path(score_dir)
    r = run(run_of(sd)) if is_score(sd) else None
    s = _json(sd / METRICS)
    if r is None or s is None:
        return None
    unset = set(meta(sd).get("unset") or ())
    out = {k: v for k, v in r.items() if k not in unset}
    out.update(s)
    scores = out.get("scores")
    if isinstance(scores, dict) and any(not is_number(v) for v in scores.values()):
        out["scores"] = _means_counted(sd, scores)
    return out


def _means_counted(score_dir: Path, scores: dict[str, Any]) -> dict[str, Any]:
    """A run's means with every one that is not a number (a run recorded before RFC-041 F7, whose mean over an item with
    no number in it is NaN) worked again over its items, each item's score as `_number.counted` reads it (a failed
    item's 0), as `evh run` records the mean now. A mean that no item row carries (a run-level metric) is left out: no
    "nan" in a table."""
    from evaluation_harness import _outputs  # noqa: PLC0415

    rows = _outputs.rows(Path(score_dir), errors="replace", meta=False) or []
    out: dict[str, Any] = {}
    for k, v in scores.items():
        if is_number(v):
            out[k] = v
        elif held := [counted(r[k]) for r in rows if "item_id" in r and k in r and is_scored(r[k])]:
            out[k] = round(sum(held) / len(held), 6)
    return out


#: What `same_measurement` names when two runs' harness code differs: said, never a reason to read them apart.
HARNESS = "harness build"


def same_measurement(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, list[str]]:
    """Whether run `b` taken again is `a`: (the same measurement, what differs). `a` and `b` are two runs' own records
    (run.json, never a score's: a re-score or a judging keeps no fingerprint hash, its parts were not measured
    together). The same measurement is the same system on the same dataset, with equal data, deployment and settings
    (the fingerprint's `data_sha256`, `deployment_sha256`, `settings_sha256`) and the same adapter (its own
    `instrument.adapter.sha256`: the scorer). The harness's own code (`instrument.harness.code_sha256`) may differ: a
    repeat made on a later build of the harness joins, and the difference is named (HARNESS), last. What blocks it
    is named: "system", "dataset", "data", "deployment", "settings", "adapter", "fingerprint version", and a part
    or a fingerprint one side never recorded ("settings (not recorded)", "fingerprint (not recorded)")."""
    why = [k for k, w in (("system", "system_id"), ("dataset", "dataset_id")) if a.get(w) != b.get(w)]
    fa, fb = a.get("fingerprint") or {}, b.get("fingerprint") or {}
    if not fa or not fb:
        why.append("fingerprint (not recorded)")
        return False, why
    if not fa.get("version") or fa.get("version") != fb.get("version"):
        why.append("fingerprint version")
        return False, why
    for part in ("data", "deployment", "settings"):
        x, y = fa.get(f"{part}_sha256"), fb.get(f"{part}_sha256")
        if not x or not y:
            why.append(f"{part} (not recorded)")
        elif x != y:
            why.append(part)
    ax, ay = ((f.get("instrument") or {}).get("adapter", {}).get("sha256") for f in (fa, fb))
    if not ax or not ay:
        why.append("adapter (not recorded)")
    elif ax != ay:
        why.append("adapter")
    hx, hy = ((f.get("instrument") or {}).get("harness", {}).get("code_sha256") for f in (fa, fb))
    ok = not why
    if hx and hy and hx != hy:
        why.append(HARNESS)
    return ok, why


def _resolve(
    base: Path, rj: dict[str, Any], seen: tuple[str, ...] = ()
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """What a repeat joins: (the run record it is read with, why it joins none, what differs without keeping it from
    joining). A repeat names the run it repeats (`of`) and joins it when that run is there and is the same measurement
    (`same_measurement`); a repeat of a repeat follows `of` to the run at the root, and joins only when every link
    does, a link read under `repeats` (or missing, or looping back) being the end of it. None, [], [] for a run that
    is no repeat."""
    of = rj.get("of")
    me = str(rj.get("run_id") or "")
    if (rj.get("purpose") or "run") != "repeat" or not of:
        return None, [], []
    if of in seen or of == me:
        return None, [f"`of` {of} loops back"], []
    target = run(base / str(of))
    if target is None:
        return None, [f"{of} is not there"], []
    ok, diff = same_measurement(rj, target)
    if not ok:
        return None, [d for d in diff if d != HARNESS], []
    if (target.get("purpose") or "run") == "repeat" and target.get("of"):
        root_, why, _ = _resolve(base, target, (*seen, me))
        if root_ is None:
            return None, [f"{of} is itself read under repeats ({'; '.join(why)})"], []
    return target, [], [d for d in diff if d == HARNESS]


def _by_purpose(base: Path, rj: dict[str, Any], seen: tuple[str, ...] = ()) -> str:
    """What a run's purpose adds to the label of the arm it is read in: a repeat that joins the run it repeats adds
    what that run adds (a repeat of a re-timing is read in the re-timing's arm)."""
    target, _why, _note = _resolve(base, rj, seen)
    if target is not None:
        return _by_purpose(base, target, (*seen, str(rj.get("run_id"))))
    purpose = rj.get("purpose") or "run"
    return (rj.get("machine") or "") if purpose == "retime" else PURPOSE_LABEL.get(purpose, purpose)


def repeat_reading(
    of_id: str, mine: dict[str, Any], label_as: str = "", scratch: bool = False
) -> dict[str, Any]:
    """Where a repeat of run `of_id` will be read, before it has run. `mine`: the repeat's dataset_id, system_id and
    fingerprint; `label_as`: the label its score will carry. {"joins": whether it is read in the arm of the run it
    repeats, "why": what keeps it from it (named as `same_measurement` names them), "notes": what differs and does not
    keep it (the harness build), "arm": the arm it is read in, "label": its label}."""
    rj = {**mine, "purpose": "repeat", "of": of_id, "run_id": ""}
    target, why, notes = _resolve(root(scratch), rj)
    by = _by_purpose(root(scratch), target) if target is not None else "repeats"
    lbl = ", ".join(x for x in (label_as, by) if x)
    return {
        "joins": target is not None,
        "why": why,
        "notes": notes,
        "arm": f"{arm_prefix(lbl)}/{mine.get('dataset_id')}/{mine.get('system_id')}",
        "label": lbl,
    }


def _run_record(score_dir: Path, rec: dict[str, Any]) -> dict[str, Any]:
    """The pass a score is of, as run.json says it (a re-score's own record holds no fingerprint hash: its parts were
    not measured together), else the record given."""
    return (run(run_of(Path(score_dir))) if is_score(Path(score_dir)) else None) or rec


def _is_repeat(rec: dict[str, Any]) -> bool:
    """Whether a record is of a repeat that names the run it repeats: the only run that reads another run."""
    return (rec.get("purpose") or "run") == "repeat" and bool(rec.get("of"))


def joined(score_dir: Path, rec: dict[str, Any] | None = None) -> tuple[str, list[str]] | None:
    """(the run this run is a repeat of, what differs and does not keep it from being read in that run's arm: the harness
    build) when it is read in that run's arm, else None."""
    rec = rec if rec is not None else record(score_dir) or {}
    if not _is_repeat(rec):
        return None
    rj = _run_record(score_dir, rec)
    target, _why, notes = _resolve(run_of(Path(score_dir)).parent, rj)
    return (str(rj["of"]), notes) if target is not None else None


def joins(score_dir: Path, rec: dict[str, Any] | None = None) -> str | None:
    """The id of the run this run is a repeat of, when it is read in that run's arm: a `--purpose repeat --of X` run that
    is the same measurement as X (`same_measurement`), X itself a plain run or a repeat that joins one. None for any
    other run, and for a repeat of a run that is gone or measured something else: that one is read under `repeats`."""
    found = joined(score_dir, rec)
    return found[0] if found else None


def label(score_dir: Path, rec: dict[str, Any] | None = None) -> str:
    """The label of the arm a score is read in: the score's own and the run's purpose's, joined ("" for a run's first
    score of a plain run). A repeat that joins the run it repeats (`joins`) takes what that run's purpose adds, so it
    is read where that run is, under its own score's label."""
    rec = rec if rec is not None else record(score_dir) or {}
    own = str(meta(score_dir).get("label") or "")
    purpose = rec.get("purpose") or "run"
    if _is_repeat(rec):
        by_purpose = _by_purpose(
            run_of(Path(score_dir)).parent, {**_run_record(score_dir, rec), "purpose": purpose}
        )
    else:
        by_purpose = (
            (rec.get("machine") or "") if purpose == "retime" else PURPOSE_LABEL.get(purpose, purpose)
        )
    return ", ".join(x for x in (own, by_purpose) if x)


def read_under(score_dir: Path, lbl: str) -> bool:
    """Whether a score is read under the label `lbl`; or is a repeat that now joins its original's arm while `lbl` is the
    label a round recorded it under (`repeats`): a round reads what it recorded, and no migration relabels it (RFC-041
    F2, RUNBOOK 1531), so that is no problem of the round."""
    return label(score_dir) == lbl or (lbl == PURPOSE_LABEL["repeat"] and joins(score_dir) is not None)


def arm_prefix(lbl: str) -> str:
    """The first part of an arm's id: `runs` for a label of none, else the label as a slug (`rescored-cd35dc1f`)."""
    return "runs" if not lbl else re.sub(r"[^a-z0-9]+", "-", lbl.lower()).strip("-")


def arm_of(score_dir: Path, rec: dict[str, Any] | None = None) -> str:
    """`<prefix>/<dataset>/<system>`: the arm a score is read in. The one place that says it (RFC-041 F2)."""
    rec = rec if rec is not None else record(score_dir) or {}
    return f"{arm_prefix(label(score_dir, rec))}/{rec.get('dataset_id')}/{rec.get('system_id')}"


def latest_key(rec: dict[str, Any]) -> tuple[str, str]:
    """What orders runs by how late they were measured: (created_at, run_id). A run id can be anything (`--run-id`), so
    it only breaks a tie."""
    return str(rec.get("created_at") or ""), str(rec.get("run_id") or "")


def latest(runs: Iterable[tuple[Path, dict[str, Any]]]) -> tuple[Path, dict[str, Any]] | None:
    """The latest of these scored runs: the greatest (created_at, run_id), None for none. The one reading of "the
    latest run"; no reader orders by name or by the order the directory lists them."""
    return max(runs, key=lambda x: latest_key(x[1]), default=None)


def reference_of(rec: dict[str, Any]) -> str:
    """The reference a scored run was read against, "" for none."""
    return str(((rec.get("fingerprint") or {}).get("data") or {}).get("reference_id") or "")


def runs_of_arm(
    runs: Iterable[tuple[Path, dict[str, Any]]],
) -> tuple[list[tuple[Path, dict[str, Any]]], list[tuple[Path, dict[str, Any]]]]:
    """(kept, left out) of the scores `arm_of` puts in one arm: the ones scored against the reference of its latest run,
    in the order given. Runs scored against another were averaged in whatever they measured against (a run on silver
    and a run on gold read as repeats of one measurement); they are left out, and the caller names them."""
    runs = list(runs)
    last = latest(runs)
    if last is None:
        return [], []
    ref = reference_of(last[1])
    return [x for x in runs if reference_of(x[1]) == ref], [x for x in runs if reference_of(x[1]) != ref]


def read_arms(
    scores: Iterable[tuple[Path, dict[str, Any]]],
) -> tuple[list[tuple[Path, dict[str, Any]]], list[tuple[Path, dict[str, Any]]]]:
    """(read, left out) of any scores, arm by arm (`runs_of_arm`), each in the order given."""
    scores = list(scores)
    groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for sd, rec in scores:
        groups.setdefault(arm_of(sd, rec), []).append((sd, rec))
    left = {sd for xs in groups.values() for sd, _rec in runs_of_arm(xs)[1]}
    return [x for x in scores if x[0] not in left], [x for x in scores if x[0] in left]


def set_of(runs: Iterable[tuple[Path, dict[str, Any]]]) -> list[tuple[Path, dict[str, Any]]]:
    """The runs of one arm that make up its repeat set: those whose record has `repeat_index` (`evh run --repeat N`),
    those that join the run they repeat (`joins`), and the runs those name. What the run is called says nothing: a
    user's `--run-id foo_r1` and `foo_r2` are two plain runs."""
    runs = list(runs)
    joining = {run_of(sd).name: joins(sd, rec) for sd, rec in runs}
    named = {j for j in joining.values() if j}
    return [
        (sd, rec)
        for sd, rec in runs
        if rec.get("repeat_index") or joining[run_of(sd).name] or run_of(sd).name in named
    ]


def is_set(runs: Iterable[tuple[Path, dict[str, Any]]]) -> bool:
    """Whether these runs, read as one arm, are one repeat set: each is a member (`set_of`)."""
    runs = list(runs)
    return bool(runs) and len(set_of(runs)) == len(runs)


def run_ids(data: Path | None = None, base: Path | None = None) -> list[str]:
    """Every run's id, sorted. `base`: a directory of runs beside the project's data (`evh score-preview` reads the
    re-scores it made in a temporary one)."""
    base = Path(base) if base else root(data=data)
    if not _store.is_dir(base):
        return []
    return sorted(d.name for d in _store.iterdir(base) if _store.is_file(d / RUN))


def scores_of(run_id_or_dir: str | Path, data: Path | None = None) -> list[Path]:
    """A run's score directories, sorted by key."""
    d = run_id_or_dir if isinstance(run_id_or_dir, Path) else run_dir(run_id_or_dir, data=data)
    base = Path(d) / "scores"
    if not _store.is_dir(base):
        return []
    return sorted(s for s in _store.iterdir(base) if _store.is_file(s / METRICS))


def scored(
    dataset_id: str | None = None,
    *,
    label_is: str | None = "",
    system_id: str | None = None,
    match: str | None = None,
    data: Path | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Every score with its record, by run id then key: optionally on one dataset, read under one label (`""`: the
    arm a plain run's first score is read in; None: any), of one system or of systems whose id contains `match`, from
    the project's runs or another data directory's."""
    out = []
    for rid in run_ids(data):
        for sd in scores_of(rid, data):
            rec = record(sd)
            if rec is None or not rec.get("system_id"):
                continue
            if dataset_id is not None and rec.get("dataset_id") != dataset_id:
                continue
            if system_id is not None and rec.get("system_id") != system_id:
                continue
            if match and match not in str(rec["system_id"]):
                continue
            if label_is is not None and label(sd, rec) != label_is:
                continue
            out.append((sd, rec))
    return out


def labels(data: Path | None = None) -> list[str]:
    """Every label a score is read under, "" (plain runs) first."""
    seen = {label(sd, rec) for sd, rec in scored(label_is=None, data=data)}
    return sorted(seen, key=lambda x: (x != "", x))


def first_score(run_id_or_dir: str | Path, data: Path | None = None) -> Path | None:
    """The score a run made when it ran (its score.json says `first`), else None."""
    for sd in scores_of(run_id_or_dir, data):
        if meta(sd).get("first"):
            return sd
    return None


def split(rec: dict[str, Any], run_rec: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """A scored run's record as the score keeps it beside its run's run.json: the keys whose value differs from the
    run's, and the run's keys the record does not hold (the score unsets them)."""
    base = {k: v for k, v in (run_rec or {}).items() if k not in RUN_ONLY}
    own = {k: v for k, v in rec.items() if k not in base or base[k] != v}
    unset = sorted(k for k in base if k not in rec)
    return own, unset


def run_part(rec: dict[str, Any]) -> dict[str, Any]:
    """Of a measured run's record, what the pass itself is (the record less what its score measured)."""
    return {k: v for k, v in rec.items() if k not in SCORE_KEYS}


def write_score(
    run_id: str,
    scorer: str,
    reference: str | None,
    rec: dict[str, Any],
    *,
    label_as: str = "",
    first: bool = False,
    scratch: bool = False,
) -> Path:
    """Write a score of a run from its full record (as `record` reads it back): score.json and metrics.json. The
    rows are the caller's to write in the returned directory (`_outputs`). Returns the score's directory."""
    run_rec = run(run_dir(run_id, scratch))
    if run_rec is None:
        raise ValueError(f"no run {run_id!r} to score")
    own, unset = split(rec, run_rec)
    sd = run_dir(run_id, scratch) / "scores" / key(scorer, reference)
    _store.mkdir(sd, parents=True, exist_ok=True)
    m: dict[str, Any] = {"scorer": scorer, "reference": reference, "label": label_as}
    if first:
        m["first"] = True
    if unset:
        m["unset"] = unset
    _store.write_text(sd / SCORE, json.dumps(m, indent=2, ensure_ascii=False) + "\n")
    _store.write_text(sd / METRICS, json.dumps(own, indent=2, ensure_ascii=False) + "\n")
    return sd


def write_run(run_id: str, rec: dict[str, Any], scratch: bool = False) -> Path:
    """Write a run's run.json; returns the run's directory."""
    if rec.get("purpose", "run") not in PURPOSES:
        raise ValueError(f"a run's purpose is one of {', '.join(PURPOSES)}, not {rec.get('purpose')!r}")
    d = run_dir(run_id, scratch)
    _store.mkdir(d, parents=True, exist_ok=True)
    _store.write_text(d / RUN, json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    return d


def iter_records(data: Path | None = None) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Every score with its record, any label (for checks that read them all)."""
    yield from scored(label_is=None, data=data)
