"""What the catalog and the run inspector need from a project's data, and the harness's own answer.

An ADAPTER answers questions about a project's runs: which arms exist, what each scored per
item, which way is better, what references exist, and what one arm wrote for one item. The
catalog builder (catalog_build.py) and the inspector server (catalog_serve.py) only ever ask
these questions, so a project with its own layout writes one adapter and gets both (ADR-0002).

    catalog:
      adapter: tools/my_adapter.py:Adapter     # in the project's config.yaml, or --adapter

Without one, HarnessAdapter reads the harness's own layout:

    <data>/runs/<run_id>/{run.json, outputs.jsonl}
    <data>/runs/<run_id>/scores/<key>/{score.json, metrics.json, predictions.jsonl}   (model/runs)
    <data>/references/<tier>/<dataset_id>/<item_id>.txt

An ARM is a string id the adapter chooses. HarnessAdapter's is `<label prefix>/<dataset_id>/<system id>`
(model.runs.arm_id): every score of a system on a dataset read under one label, averaged per item, exactly as
`pair-test` and `family-test` read them, so the inspector and the command line give the same p.

Item text (outputs, references) is only ever returned by item_view / reference_view. The static
catalog never embeds it. The local inspector shows it; a public server (--public) serves it only for
what the deployment names with --publish outputs / --publish references, and never the item itself:
an output can quote its input, and a reference can be a dataset's licensed text.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import importlib.util
import itertools
import json
import re
import statistics
import sys
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Protocol

HERE = Path(__file__).resolve().parent

from evaluation_harness import (  # noqa: E402
    _common,
    _label_sets,
    _outputs,
    _picks,
    _store,
    _tags,
)
from evaluation_harness._common import (  # noqa: E402
    BOOKKEEPING_PREFIXES,
    ModuleNotLoadable,
    is_descriptive,
    load_goals,
    load_module,
)
from evaluation_harness._fields import fieldset_problems, load_fieldset  # noqa: E402 -- part of the adapter contract
from evaluation_harness._fingerprint import items_digest  # noqa: E402
from evaluation_harness._record import derived_with  # noqa: E402
from evaluation_harness._runs import item_rows, lower_is_better_on, read_metrics, score_of  # noqa: E402
from evaluation_harness.model import dataset_views as model_dataset_views  # noqa: E402
from evaluation_harness.model import datasets as model_datasets  # noqa: E402
from evaluation_harness.model import goals as model_goals  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402
from evaluation_harness.model import scorer_views as model_scorer_views  # noqa: E402
from evaluation_harness.model import spend as model_spend  # noqa: E402
from evaluation_harness.model import view_cache  # noqa: E402
from evaluation_harness.model.entity import Problem  # noqa: E402
from evaluation_harness.model.spend import number, token_total  # noqa: E402


def _memo(fn):
    """Cache a method's answers on its instance. `functools.lru_cache` on a method keys on
    `self` in a module-level cache, so every adapter ever made (one per test, per server
    start) stays alive with its data; this cache goes when the adapter does. One lock per instance: catalog-serve
    answers on threads, and two building `_index` at once each reset what the other was filling (a KeyError, a 500)."""
    slot = f"_memo_{fn.__name__}"

    @wraps(fn)
    def wrapper(self, *args):
        cache = self.__dict__.setdefault(slot, {})
        if args in cache:
            return cache[args]
        with self.__dict__.setdefault("_memo_lock", threading.RLock()):
            if args not in cache:
                cache[args] = fn(self, *args)
        return cache[args]

    return wrapper


_TOKENS = itertools.count(1)


def _values_in(sc: dict) -> int:
    """What one arm's scores weigh in the view cache: the per-item values (and repeats) they hold."""
    return sum(
        len(m.get("values") or ())
        + (sum(map(len, r.values())) if isinstance(r := m.get("repeats"), dict) else 0)
        for m in sc.values()
    )


def scores_once(adapter, held: bool = False):
    """The adapter, its `scores` read once per arm from now on: for a process that answers once and exits (a view,
    a build). `evh goal-list` read 1,054 arms' scores for 686 arms (the collect, the goals' groups and the adapter's own
    `describe` asking again): 79% of its CPU. Set on the instance, so the adapter's own `self.scores` reads it too.
    Callers only read what `scores` returns (every caller gets the same dict).
    `held`: for a process that answers again and again (catalog-serve, the MCP server, a notebook): the scores are
    kept by the model's view cache (model/view_cache), bounded, and dropped when the data changes; under a token of
    this adapter, which its `refresh()` replaces. Without it every arm is kept, for as long as the adapter lives.
    What is kept is the read before the exposure filter (`_exposure.aware`), filtered again on every call: kept after
    it, a cached answer said nothing of the items it left out, and one call's --include-exposed was kept for others."""
    unfiltered = adapter.__dict__.get("_scores_unfiltered")
    read = unfiltered or adapter.scores
    if held:

        def scores(arm, rescore=False):
            token = adapter.__dict__.setdefault("_view_token", next(_TOKENS))
            return view_cache.get(
                ("scores", token, arm, bool(rescore)), lambda: read(arm, rescore), weigh=_values_in
            )

    else:
        kept: dict = {}

        def scores(arm, rescore=False):
            k = (arm, bool(rescore))  # scores(arm) and scores(arm, rescore=False) are one read
            if k not in kept:
                kept[k] = read(arm, rescore)
            return kept[k]

    if unfiltered is None:
        adapter.scores = scores
    else:
        from evaluation_harness import _exposure  # noqa: PLC0415

        adapter._scores_unfiltered = scores
        adapter.scores = _exposure.filtered(scores, getattr(adapter, "data_dir", None))
    return adapter


def _replay_of(m: dict) -> dict | None:
    """A run's replay (RFC-030), from its fingerprint and record: {record, candidate, commits, faithfulness}."""
    code = ((m.get("fingerprint") or {}).get("deployment") or {}).get("code") or {}
    if not code.get("record"):
        return None
    return {
        "record": code["record"],
        "candidate": code.get("candidate"),
        "commits": len(code.get("commits") or {}),
        "faithfulness": m.get("faithfulness"),
        "history_confound": m.get("history_confound"),
    }


class Adapter(Protocol):
    """The questions the catalog and the inspector ask. Every method must be cheap to call
    twice. The server caches `scores`, and the built-in adapter its index of runs, until the data changes: it then
    calls the adapter's `refresh()` (optional: an adapter that has none keeps what it cached) and rebuilds the pages."""

    #: What one item is called on the pages ("item", "episode", "article").
    item_word: str
    #: The data directory, served read-only by the inspector ("files" links open it).
    data_dir: Path

    #: Per-item facts that are never a default yardstick (length, latency): the scatter's x axis.
    @property
    def shape_metrics(self) -> tuple: ...

    #: Whether scores(arm, rescore=True) can compute what is not on record.
    can_rescore: bool

    def arms(self) -> list[str]:
        """Every arm id, for the catalog and the inspector's picker."""

    def arms_of(self, path: str) -> list[str]:
        """The arm ids a path the caller selected yields (often [path] itself); [] if none."""

    def describe(self, arm: str) -> dict:
        """{"id", "label", "dataset", "task"}; "dataset" is "" when none is recorded. Optional
        keys the pages use: "reference" (the reference id its scores are measured against),
        "judge" (the judge scorer that scored it), "wrote_reference" (True when this arm wrote
        the reference it is scored against), "goal", "format", "primary", "runs"."""

    def scores(self, arm: str, rescore: bool = False) -> dict[str, dict]:
        """{metric: {"source": str, "values": {item_id: float}}}."""

    @property
    def preferred_metrics(self) -> tuple:
        """Every arm's primary metric, most common first: the inspector's default yardstick."""

    def recorded_means(self, arm: str) -> dict[str, float]:
        """Run-level averages, for arms with no per-item scores: shown, never tested."""

    def input_hashes(self, arm: str) -> dict[str, str]:
        """{item_id: hash of the input the arm read}, where recorded."""

    def notes(self, arm: str) -> list[str]:
        """Why something could not be scored, or which of its runs were left out, in words."""

    def lower_is_better(self, metric: str, dataset: str | None = None) -> bool:
        """Whether a decrease in this metric is an improvement."""
        ...

    def is_neutral(self, metric: str, dataset: str | None = None) -> bool:
        """A measurement with no better direction (length, counts), on `dataset`; with no
        dataset, on every dataset that records it."""

    def references(self) -> list[dict]:
        """[{"id", "tier", "dataset", "task", "archived", "format"}]; optional, for the reference's
        page: "items", "author" (the system that wrote it), "from_run", "model", "created_at",
        "caveat"."""

    def reference_format(self, ref: str) -> str:
        """The output format a reference was written for, compared with the format an arm was asked
        for (`output_format()["asked"]`) to flag a mismatch; "" when unknown, which never flags."""
        ...

    def reference_archived(self, ref: str) -> bool:
        """Whether a reference has been archived."""
        ...

    def output_format(self, arm: str) -> dict:
        """{"asked", "got", "how"}: the output format the arm was asked for and produced."""

    def item_view(self, arm: str, item: str) -> dict:
        """One arm's output for one item, as one of the inspector's view kinds:
        {"kind": "text", "text": ...}; {"kind": "none", "note": ...}; or a structured output,
        {"kind": "insights", "items": [{"text", "grounded"}], "quotes": n} (claims, each grounded
        in the source or not), {"kind": "nodes", "groups": {name: [str]}} (named groups) or
        {"kind": "entities", "items": [str]}. Any of them may carry "info": {label: value}."""

    def reference_view(self, ref: str, item: str) -> dict:
        """One reference's text for one item: {"kind": "text", "text": ...} or {"kind": "none"}."""
        ...

    def goals(self) -> list[dict]:
        """Every goal (goal.schema.json): what the evaluations are FOR. [] when there are none.
        The goal an arm names is `describe(arm)["goal"]`."""

    # Optional (ADR-0003); `item_fields(A, dataset)` below answers for an adapter without it.
    # def item_fields(self, dataset: str) -> dict:
    #     {"fieldset": <fieldset.schema.json document> or None, "values": {item_id: {field: value}}}
    # Optional: served_dirs, a tuple of further directories under the project the inspector
    # may serve read-only (the catalog's links into a project's reports); none by default.
    # Optional: how many items a dataset has. Without it the catalog shows the most items any
    # arm scored, which undercounts a dataset no arm covered fully.
    # def dataset_items(self, dataset: str) -> Optional[int]: ...
    # Optional: what each metric measures, for the metrics page. Without it the page shows the
    # harness's own metrics' descriptions and the rest as undescribed.
    # def metric_descriptions(self) -> dict[str, str]: ...
    # Optional: what an arm was measured under, {"machine.platform": ..., "library.torch": ...,
    # "deployment.machine": ..., "harness.version": ..., "scorer.sha256": ..., "data.items_sha256": ...,
    # "reference.sha256": ...}; the inspector lists what differs between the arms it compares.
    # `machine.*` is the runner (where evh ran, outside the fingerprint's hash), `deployment.*` where
    # the system under test ran.
    # def conditions(self, arm: str) -> dict[str, str]: ...
    # Optional: the current baselines (run-promote, RFC-027), one per goal and dataset (goal None: the dataset's own),
    # [{"version", "dataset", "run", "arm", "reason", "promoted_at", "tier", "goal", "actor", "evidence"}], oldest
    # promotion first; the pages lead with them, the answer so far.
    # def baselines(self) -> list[dict]: ...
    # Optional: the arm id of a system on a dataset (`evh round-list`, `evh comparison-show --round` and the
    # round pages build arm ids with it): `runs/<dataset>/<system_id>` when absent.
    # def arm_of(self, dataset: str, system_id: str) -> str: ...
    # Optional: whether a metric needs no reference (the bill, the clock, token counts), so arms
    # scored against different references can still be compared on it. When absent, a metric
    # whose name contains cost, latency or tokens is taken to need none.
    # def reference_free(self, metric: str) -> bool: ...
    # Optional: what each model's weights are, {model: {"weights": "open" | "proprietary",
    # "licence": ...}}, keyed by the model a run records; the arms page filters on it.
    # def model_facts(self) -> dict[str, dict]: ...
    # Optional: the model records (data/models/) with the arms that use each, [{"record": {...},
    # "arms": [arm id]}]; the Models page and the arms page's model badge read it.
    # def models(self) -> list[dict]: ...
    # Optional: a goal's studies (RFC-029), [{"study", "status", "round", "baseline", "rows", "spent_usd", "end",
    # "confirms"}]; a goal page shows them.
    # def studies(self, goal: str) -> list[dict]: ...
    # Optional: eval rounds (ADR-0004), each round's record with "arms", the arm ids in play, "retired_arms", the arm ids
    # it retired, and "arm_records", the arms as the round stores them (model/rounds);
    # a goal page shows them as its history.
    # def rounds(self) -> list[dict]: ...
    # Optional: every dataset id, including those no arm has run on yet.
    # def datasets(self) -> list[str]: ...
    # Optional: the version a dataset was made from, {"dataset_id", "added", "removed",
    # "changed"} (item id lists), or None; the dataset pages link the versions both ways.
    # def dataset_lineage(self, dataset: str) -> Optional[dict]: ...
    # Optional: when a dataset was frozen (ISO); the home page counts it new from that day, and
    # from its first run when this is absent or "".
    # def dataset_created(self, dataset: str) -> str: ...
    # Optional: a dataset's own labels and origin, {"tags": {key: value}, "origin": "..."}: the
    # datasets page groups and filters by its tags (RFC-019) and says where it came from.
    # def dataset_meta(self, dataset: str) -> dict: ...
    # Optional: what is inside a dataset, without its text (`evh dataset-profile` writes it to
    # data/profiles/<dataset>.json): {"items": {"n", "kind", "words"}, "references": [...],
    # "rows": [{"item_id", "words", "reference", "source_url"?, "text"?}], "source", "items_sha256"},
    # or None; the dataset page shows it.
    # def dataset_profile(self, dataset: str) -> Optional[dict]: ...
    # Optional: an arm's runs, oldest first, [{"run_id", "created_at", "items", "cost_usd",
    # "derived"}] ("derived": "" for a measured run, else how it was made: rescore, judge,
    # reparse); the arm page lists them and the home page's activity counts them.
    # def arm_runs(self, arm: str) -> list[dict]: ...
    # Optional: what an arm was asked to do, {"system_id", "params", "adapter", "deployment"}, params
    # without credentials, "deployment" the model-record deployment its system named ("" for none);
    # the arm page shows it.
    # def arm_config(self, arm: str) -> dict: ...
    # Optional: what was spent and when, [{"at", "usd", "tokens", "kind": "arm" | "judge",
    # "dataset", "what", "arm" (a measured run's arm, optional)}] (usd or tokens None when unknown), each measured run and each judging
    # day once; the home page's spend chart, in USD or in tokens, and the activity page per arm.
    # def spend(self) -> list[dict]: ...


def item_fields(A, dataset: str) -> dict:
    """A dataset's declared fields and its items' values, from the adapter if it answers, else
    none: the pages then show no fields."""
    fn = getattr(A, "item_fields", None)
    got = fn(dataset) if callable(fn) else None
    return got if isinstance(got, dict) and got.get("fieldset") else {"fieldset": None, "values": {}}


def _flat_conditions(fp: dict) -> dict[str, str]:
    """A run fingerprint's conditions as {group.field: value} (see HarnessAdapter.conditions)."""
    out: dict[str, str] = {}
    runner = fp.get("runner") or {}
    for k, v in runner.items():
        if v is not None and k != "libraries":
            out[f"machine.{k}"] = str(v)
    dep = fp.get("deployment") or {}
    for k, v in (runner.get("libraries") or dep.get("libraries") or {}).items():
        out[f"library.{k}"] = str(v)
    for k, v in (dep.get("where") or {}).items():
        if v:
            out[f"deployment.{k}"] = str(v)
    server = dep.get("server") or {}
    if server.get("name"):
        out["deployment.server"] = " ".join(x for x in (server["name"], server.get("version")) if x)
    for k in ("model", "source"):
        if dep.get(k):
            out[f"deployment.{k}"] = str(dep[k])
    weights = dep.get("weights") or {}
    build = weights.get("digest") or weights.get("revision") or weights.get("file_hash")
    if build:
        out["deployment.build"] = str(build)
    if weights.get("quantization") or weights.get("precision"):
        out["deployment.quantization"] = str(weights.get("quantization") or weights.get("precision"))
    hosted = dep.get("hosted") or {}
    if hosted.get("provider_id"):
        out["deployment.upstream"] = str(hosted["provider_id"])
    inst = fp.get("instrument") or {}
    harness = inst.get("harness") or {}
    for k in ("version", "code_sha256"):
        if harness.get(k) is not None:
            out[f"harness.{k}"] = str(harness[k])
    adapter = inst.get("adapter") or {}
    for k in ("id", "sha256"):
        if adapter.get(k) is not None:
            out[f"scorer.{k}"] = str(adapter[k])
    data = fp.get("data") or {}
    if data.get("items_sha256"):
        out["data.items_sha256"] = str(data["items_sha256"])
    if data.get("references_sha256"):
        out["reference.sha256"] = str(data["references_sha256"])
    if fp.get("version") is not None:
        out["fingerprint.version"] = str(fp["version"])
    return out


def measured(m: dict, first: bool) -> tuple[bool, str]:
    """(re-scored or re-parsed in place, when it was measured). The score a run made when it ran, re-scored where it
    lay (its record has `derived`), is still the run that was measured (its calls, its bill), dated when it was, which
    the run id keeps (created_at was rewritten with the re-score's time). Any other score: (False, its created_at)."""
    made = m.get("created_at") or ""
    if not (first and m.get("derived")):
        return False, made
    stamp = re.search(r"_(\d{8})T(\d{6})Z$", str(m.get("run_id") or ""))
    if stamp:
        day, hms = stamp.groups()
        made = f"{day[:4]}-{day[4:6]}-{day[6:]}T{hms[:2]}:{hms[2:4]}:{hms[4:]}Z"
    return True, made


def _json(p: Path | None):
    if p is None:
        return None
    try:
        return json.loads(_store.read_text(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _numeric(row: dict) -> dict:
    """Every score on a row, read as pair-test reads one (`_runs.score_of`), so the inspector's
    p and pair-test's are the same computation, not two that agree on clean data."""
    return {
        k: v for k in row if not k.startswith(BOOKKEEPING_PREFIXES) and (v := score_of(row, k)) is not None
    }


def _plain_name(name: str) -> bool:
    """A file's name and nothing else: an item id from a request never reaches outside its run."""
    return bool(name) and "/" not in name and "\\" not in name and ".." not in name and "\0" not in name


def _ignored_runs(run_jsons: list[Path]) -> set[Path]:
    """Of these run.json files, the ones git ignores (a run on this disk only: the local catalog shows what a clone, CI
    and the published one show)."""
    return _common.ignored_paths(run_jsons)


def _promoted_from_now(pf: Any) -> Any:
    """A reference's promoted_from with its system named by the id it has now (the manifest keeps the id it was
    promoted under: it is part of the hash every run scored against it records, RFC-032 step 3)."""
    src = (pf or {}).get("source") if isinstance(pf, dict) else None
    if not isinstance(src, dict) or not src.get("config_id"):
        return pf
    return {**pf, "source": {**src, "config_id": _common.system_now(src["config_id"])}}


class HarnessAdapter:
    """The harness's own data tree. Arms are systems on a dataset, repeats averaged per item."""

    item_word = "item"
    can_rescore = False
    #: The arms read through only some of their runs ({arm id: run ids}; only_runs), None for every run of every arm.
    _only: dict[str, set[str]] | None = None

    def captures(self) -> list[dict]:
        """Every capture in the data tree, as `evh capture-list` lists them (RFC-019): the Captures page reads these."""
        return model_dataset_views.capture_views(self.data_dir, check_format=False)

    @_memo
    def scorers(self) -> list[dict]:
        """Every judge scorer in the data tree, as `evh scorer-list` lists them (RFC-032 step 7), whatever its format (the
        catalog reads copies): the Scorers page reads these."""
        return model_scorer_views.list_scorers(self.data_dir, check_format=False)

    @_memo
    def scorer(self, scorer_id: str) -> dict:
        """One judge scorer, as `evh scorer-show` shows it: its judges, validation, checks, judging sets and the judged
        scores it made."""
        return model_scorer_views.show_scorer(scorer_id, self.data_dir, check_format=False)

    def __init__(self, data_dir: Path | None = None, runs_root: Path | None = None):
        self.data_dir = Path(data_dir or _common.DATA)
        # The project's goals (EVAL_GOALS_DIR when set) unless a data directory is named.
        self.goals_dir = _common.GOALS if data_dir is None else model_goals.GOAL.under(self.data_dir).base()
        # Where the runs are read from: the data directory's runs, or another directory of runs beside the project's
        # references and goals (evh score-preview reads re-scores it made in a temporary directory, RFC-022).
        self.runs_root = Path(runs_root) if runs_root else model_runs.root(data=self.data_dir)

    # The dataset-family files are read through model/datasets, under this adapter's data directory (the project's,
    # or another, as the release's copy); a tree of another format is read as it is (the catalog reads copies).

    def _dataset_file(self, dataset: str) -> Path:
        return model_datasets.record_file(dataset, self.data_dir)

    def _labels_file(self, set_id: str) -> Path | None:
        """A label set's labels.json, None for an id that names none (a run's reference id is read as it was written)."""
        try:
            return model_datasets.LABEL_SET.under(self.data_dir).path(set_id)
        except Problem:
            return None

    def _capture_ids(self) -> tuple[Path, list[str]]:
        """The captures' folder and the captures in it."""
        ent = model_datasets.CAPTURE.under(self.data_dir)
        return ent.base(), ent.ids(check_format=False)

    # -- arms ---------------------------------------------------------------------------
    @_memo
    def _index(self) -> dict[str, list[Path]]:
        """{arm id: [score dirs]}: every score of every run, grouped by the label it is read under, its dataset and
        its system (model.runs.arm_id). A run git ignores is not read: the local catalog shows what a clone, CI and the
        published one show, never runs that exist on this disk only. Outside a git checkout every run is read."""
        out: dict[str, list[Path]] = {}
        runs = [self.runs_root / rid for rid in model_runs.run_ids(base=self.runs_root)]
        skipped = _ignored_runs([r / model_runs.RUN for r in runs])
        refs: dict[Path, str] = {}
        made: dict[Path, str] = {}
        # What each score's record says, read once; and the label each arm is read under. Kept on the adapter only
        # when the index is whole (below): a server that refreshes while a request reads them never shows half.
        rec: dict[Path, dict] = {}
        label: dict[str, str] = {}
        # Every score seen, before any is set aside below: what was billed counts the runs behind them all.
        every: list[tuple[str, Path, dict, str]] = []
        for r in runs:
            if r / model_runs.RUN in skipped:
                continue
            for d in model_runs.scores_of(r):
                m = model_runs.record(d)
                if not m or not m.get("dataset_id") or not m.get("system_id"):
                    continue
                arm = model_runs.arm_id(d, m)
                rec[d] = m
                label[arm] = model_runs.label(d, m)
                every.append((m["dataset_id"], d, m, arm))
                out.setdefault(arm, []).append(d)
                refs[d] = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id") or ""
                made[d] = m.get("created_at") or ""
        out = dict(sorted(out.items(), key=lambda kv: (not kv[0].startswith("runs/"), kv[0])))
        for arm, keep in (self._only or {}).items():
            if arm in out:
                out[arm] = [d for d in out[arm] if model_runs.run_of(d).name in keep]
        # ONE REFERENCE PER ARM: the one its latest run was scored against. An arm's runs were
        # averaged whatever they were scored against, so a run on silver and a run on gold read
        # as two repeats of one measurement. Runs on another reference are left out, and said so.
        stale: dict[str, list[str]] = {}
        for arm, dirs in out.items():
            # Latest by when it was measured, not by its run id (a --run-id can be anything).
            ref = refs[max(dirs, key=lambda d: (made[d], rec[d]["run_id"]))]
            old = [d for d in dirs if refs[d] != ref]
            if old:
                out[arm] = [d for d in dirs if refs[d] == ref]
                was = sorted({refs[d] or "no reference" for d in old})
                stale[arm] = [
                    (
                        f"{len(old)} earlier run(s) scored against {', '.join(was)} left out: this arm is read "
                        f"against {ref or 'no reference'}, the reference of its latest run"
                    )
                ]
        self._rec, self._label, self._every, self._stale = rec, label, every, stale
        return out

    def only_runs(self, keep: dict[str, set[str]]) -> HarnessAdapter:
        """This adapter with each arm named in `keep` read through only those runs (by run id), every other arm as it
        is: a round reads the runs it recorded, so a later run of one of its systems never moves what it decided. A
        new adapter, with nothing read yet; this one is unchanged. Its `scores` is its own: the read-once cache and the
        exposure filter this one carries (scores_once, _exposure.aware) are set on it afresh, never copied, since a copy
        reads this adapter's runs."""
        from evaluation_harness import _exposure  # noqa: PLC0415

        own = ("_view_token", "_only", "scores", "_scores_unfiltered")
        view = type(self).__new__(type(self))
        view.__dict__.update(
            {k: v for k, v in self.__dict__.items() if not k.startswith("_memo_") and k not in own}
        )
        view._only = {arm: set(runs) for arm, runs in keep.items()}
        if "_scores_unfiltered" in self.__dict__:
            _exposure.aware(view)
        return scores_once(view) if "scores" in self.__dict__ else view

    def refresh(self) -> None:
        """Forget what this adapter has read: the next question reads the data again. catalog-serve calls it when the
        data changed (a write through its API, or a change it noticed), so the server never answers from the index of runs
        it made when it started."""
        with self.__dict__.setdefault("_memo_lock", threading.RLock()):
            for slot in [k for k in self.__dict__ if k.startswith("_memo_") and k != "_memo_lock"]:
                del self.__dict__[slot]
            # the scores the view cache holds for it are another adapter's now
            self.__dict__.pop("_view_token", None)

    def read_as(self, arm: str) -> str:
        """The label the arm's scores are read under ("" for the plain arm; model.runs.label): what a folder used to
        say, "silver", "repeats", "rescored cd35dc1f", "judged/judge-summ-v1"."""
        self._index()
        return self._label.get(arm, "")

    def _run_id(self, d: Path) -> str:
        """The id of the run a score is of."""
        return model_runs.run_of(d).name

    def arms(self) -> list[str]:
        """Return all arm ids."""
        return list(self._index())

    def arms_of(self, path: str) -> list[str]:
        """The arm ids a path the caller selected yields; [] if none."""
        path = path.strip("/")
        if path in self._index():
            return [path]
        # a run, or one of its scores' directories, selects the arms it belongs to
        return [
            a
            for a, ds in self._index().items()
            if any(
                path in (f"runs/{self._run_id(d)}", d.relative_to(self.runs_root.parent).as_posix())
                for d in ds
            )
        ]

    def _dirs(self, arm: str) -> list[Path]:
        return self._index().get(arm, [])

    @_memo
    def _metrics(self, arm: str) -> dict:
        # Once per arm, for as long as the index it is read from: an inspector answer read every arm's
        # record again (7,370 reads for 40 answers, a third of each). Callers only read it.
        ds = self._dirs(arm)
        return self._record(ds[-1]) if ds else {}

    def _record(self, d: Path) -> dict:
        """A score's record, as the index read it (read now for a directory it did not list)."""
        self._index()
        return self._rec[d] if d in self._rec else (read_metrics(d) or {})

    def same_output(self, arm: str):
        """`same(a, b)` for this arm's outputs (RFC-023): its adapter's, else the same text."""
        from evaluation_harness._adapter import same_of  # noqa: PLC0415

        return same_of(self._metrics(arm).get("adapter"))

    def describe(self, arm: str) -> dict:
        """Return arm metadata: id, label, dataset, task, etc."""
        base, _, rest = arm.rpartition("/")
        dataset = base.rpartition("/")[2]
        m = self._metrics(arm)
        n = len(self._dirs(arm))
        label = rest + (f" · {self.read_as(arm)}" if self.read_as(arm) else "")
        label += f" ×{n}" if n > 1 else ""
        judged = derived_with(m, "judge").get("scorer_id")
        primary = m.get("primary_metric") or ""
        if judged:  # a judged run's headline is the judge's score, not the source run's metric
            keys = set(self.scores(arm))
            primary = next(
                (
                    k
                    for k in ("judge_score", "judge_score_unvalidated", "judge_won", "judge_won_unvalidated")
                    if k in keys
                ),
                primary,
            )
        ref = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id", "")
        if (ref or "").startswith(_common.LABELS_PREFIX):
            # A label set a model's run made (RFC-023): its arm scored against it is graded against its own outputs.
            src = (_json(self._labels_file(ref.removeprefix(_common.LABELS_PREFIX))) or {}).get(
                "source"
            ) or {}
            author = src.get("config_id") if src.get("kind") == "model" else None
            labels_source = str(src.get("kind") or "")
        else:
            author = next((r.get("author") for r in self.references() if r["id"] == ref), None)
            labels_source = ""
        params = m.get("params") or {}
        return {
            "id": arm,
            "label": label,
            "dataset": dataset,
            "task": judged or primary,
            "primary": primary,
            "runs": n,
            "goal": m.get("goal", ""),
            "format": m.get("format", ""),
            "reference": ref,
            # A judged run keeps its source run's reference_id, but its scores are the judges'.
            "judge": judged or "",
            # Graded against its own outputs: the arm whose run (or system) wrote the reference.
            "wrote_reference": bool(author) and not judged and author == m.get("system_id"),
            "reference_author": author or "",
            # Scored against a label set (RFC-023): its source (person, model, rule), for the chip.
            "labels_source": labels_source,
            # Production's recorded decisions (RFC-023): the capture they came from; no model was called.
            "recorded": str(params.get("capture") or "") if params.get("provider") == "recorded" else "",
            # A replay of a system's code (RFC-030): its code record, a candidate's commit, and its faithfulness.
            "replay": _replay_of(m),
        }

    # -- scores -------------------------------------------------------------------------
    def scores(self, arm: str, rescore: bool = False) -> dict[str, dict]:
        """Return per-item scores for this arm: {metric: {source, values}}."""
        acc: dict[str, dict[str, list]] = {}
        for d in self._dirs(arm):
            # A page may show a run with a corrupt line; a statistical test may not (strict).
            for r in item_rows(d, strict=False, meta=False):
                for k, v in _numeric(r).items():
                    acc.setdefault(k, {}).setdefault(r["item_id"], []).append(v)
        n = len(self._dirs(arm))
        src = "predictions.jsonl" + (f" (mean of {n} repeats)" if n > 1 else "")
        # With repeats, each item's values are kept beside their mean, so a goal can combine them another way
        # (`primary.reduce`, stats.reduce_repeats).
        return {
            k: {
                "source": src,
                "values": {i: statistics.fmean(v) for i, v in items.items()},
                **({"repeats": items} if n > 1 else {}),
            }
            for k, items in acc.items()
        }

    @property
    def preferred_metrics(self) -> tuple:
        """Every arm's primary metric, most common first: the inspector's default yardstick."""
        return self._preferred_metrics()

    @_memo
    def _preferred_metrics(self) -> tuple:
        from collections import Counter  # noqa: PLC0415

        c = Counter(self._metrics(arm).get("primary_metric") for arm in self._index())
        return tuple(k for k, _ in c.most_common() if k)

    def recorded_means(self, arm: str) -> dict[str, float]:
        """Return run-level averages for arms with no per-item scores, and an arm's run-level metrics (score_run():
        one number per run) whatever it has."""
        m = self._metrics(arm)
        sc = _numeric(m.get("scores") or {})
        if any(_outputs.has_rows(d) for d in self._dirs(arm)):
            return {k: sc[k] for k in m.get("run_metrics") or [] if k in sc}
        return sc

    def input_hashes(self, arm: str) -> dict[str, str]:
        """Return per-item input hashes where recorded."""
        return {}  # the dataset's per-item sha256 is the input, for every arm alike

    def notes(self, arm: str) -> list[str]:
        """Return notes explaining why something could not be scored, or what was left out."""
        self._index()
        return list(getattr(self, "_stale", {}).get(arm, []))

    def renamed_systems(self) -> dict[str, str]:
        """{old id: new id} for the systems a migration renamed (data/renames.json, RFC-032 step 3): their old arm
        pages redirect to the new ones."""
        f = self.data_dir / "renames.json"
        if not _store.is_file(f):
            return {}
        try:
            return dict(json.loads(_store.read_text(f, encoding="utf-8")).get("systems") or {})
        except (ValueError, AttributeError):
            return {}

    def renamed_arms(self) -> dict[str, str]:
        """{old arm id: new arm id} for the arms a migration renamed (data/renames.json, RFC-032 step 4): their old
        pages redirect to the new ones."""
        f = self.data_dir / "renames.json"
        if not _store.is_file(f):
            return {}
        try:
            return dict(json.loads(_store.read_text(f, encoding="utf-8")).get("arms") or {})
        except (ValueError, AttributeError):
            return {}

    @_memo
    def lower_is_better(self, metric: str, dataset: str | None = None) -> bool:
        """Whether a decrease in this metric is an improvement, by the rule every command uses
        (`_runs.lower_is_better_on`: the goal, then the adapter's declaration, then the name
        table), over the runs on `dataset`. Over every dataset, a declaration on one flipped
        the metric's direction on another."""
        runs = [
            (d, m)
            for arm, ds in self._index().items()
            if dataset is None or arm.rsplit("/", 2)[-2] == dataset
            for d in ds
            for m in [self._record(d)]
        ]
        goals = {g["goal_id"]: g for g in self.goals()}
        return lower_is_better_on(runs, metric, goals)

    @_memo
    @_memo
    def _descriptive_by_dataset(self) -> dict:
        """{dataset: {metric: whether a run there declares it descriptive}}, over each arm's
        latest run."""
        out: dict = {}
        for arm, ds in self._index().items():
            m = self._record(ds[-1])
            seen = out.setdefault(arm.rsplit("/", 2)[-2], {})
            for k, v in (m.get("metric_kinds") or {}).items():
                seen[k] = seen.get(k, False) or v == "descriptive"
        return out

    def _descriptive(self) -> frozenset:
        return frozenset(k for seen in self._descriptive_by_dataset().values() for k, d in seen.items() if d)

    def is_neutral(self, metric: str, dataset: str | None = None) -> bool:
        """Whether this metric is descriptive (neither better nor worse) on `dataset`, as its
        runs declare it, else by the harness's names. With no dataset: descriptive on every
        dataset that declares it. One adapter's declaration made a metric neutral on every other
        dataset: SummEval's descriptive `parsed` hid the classifiers' quality `parsed`."""
        if is_descriptive(metric):
            return True
        by_ds = self._descriptive_by_dataset()
        if dataset is not None:
            return bool(by_ds.get(dataset, {}).get(metric))
        declared = [seen[metric] for seen in by_ds.values() if metric in seen]
        return bool(declared) and all(declared)

    def arm_of(self, dataset: str, system_id: str) -> str:
        """The arm id of a system's runs on a dataset, read as a goal reads them (the plain label):
        `runs/<dataset>/<system id>`."""
        return f"{model_runs.arm_prefix('')}/{dataset}/{system_id}"

    @_memo
    def _kinds(self) -> dict:
        out: dict = {}
        for ds in self._index().values():
            out.update(self._record(ds[-1]).get("metric_kinds") or {})
        return out

    def reference_free(self, metric: str) -> bool:
        """A cost or speed metric (as the runs declare it, else by the harness's names) needs no
        reference: it is measured off the bill and the clock."""
        from evaluation_harness._common import classify_metrics  # noqa: PLC0415

        return classify_metrics(self._kinds()).get(metric) in ("cost", "speed")

    @property
    def shape_metrics(self) -> tuple:
        """Latency and the output's size (descriptive kinds measured in words or characters):
        the inspector's scatter axes, never a default yardstick."""
        size = sorted(k for k in self._descriptive() if "words" in k or "chars" in k)
        return ("latency_ms", *size)

    # -- references and outputs -----------------------------------------------------------
    @_memo
    def references(self) -> list[dict]:
        """Return all reference sets: {id, tier, dataset, task, archived, format}, plus what
        the set's manifest.json says (reference-promote and reference-manifest write one): author,
        from_run, model, created_at, items, caveat, and "fetched" (its texts are not here: a
        reference the project does not redistribute, listed from its manifest)."""
        ent = model_datasets.REFERENCE.under(self.data_dir)
        ids = ent.ids(check_format=False)
        out = []
        for tier in ("gold", "silver"):
            for rid in (i for i in ids if i.split("/", 1)[0] == tier):
                mf = _json(ent.path(rid)) or {}
                out.append(
                    {
                        "id": rid,
                        "tier": tier,
                        # The manifest names the dataset; the directory names the reference
                        # (a second gold for one dataset has a name of its own).
                        "dataset": mf.get("dataset_id") or rid.split("/", 1)[1],
                        "task": "",
                        "archived": False,
                        "format": "",
                        "dir": model_datasets.reference_dir(rid, self.data_dir),
                        "items": model_datasets.reference_items(mf),
                        "fetched": not model_datasets.has_reference_texts(rid, self.data_dir),
                        "source": mf.get("source"),
                        "author": _common.system_now(mf.get("authored_by")),
                        "from_run": (mf.get("from_run") or {}).get("run_id"),
                        "model": mf.get("model"),
                        "created_at": mf.get("created_at"),
                        "caveat": mf.get("caveat"),
                        "promoted_from": _promoted_from_now(mf.get("promoted_from")),
                        "reason": mf.get("reason"),
                        "promoted_by": mf.get("promoted_by"),
                    }
                )
        return out

    def deploy_sheet(self, arm: str) -> dict | None:
        """What production must match to run this arm (RFC-023, `evh deploy-sheet`), with a check against each capture
        whose records say what production ran (the arm's adapter's `production_ran`); None when the arm's system was
        never promoted, or its sheet cannot be read here."""
        from collections import Counter  # noqa: PLC0415

        from evaluation_harness import deploy_sheet as dsh  # noqa: PLC0415
        from evaluation_harness._adapter import adapter_module  # noqa: PLC0415

        cid = self._metrics(arm).get("system_id")
        if not cid:
            return None
        try:
            sh = dsh.sheet(cid, self.data_dir, self.runs_root)
        except SystemExit:
            return None
        if not sh.get("promoted"):
            return None
        checks = []
        caps, capture_ids = self._capture_ids()
        if callable(getattr(adapter_module(sh["_adapter_spec"]), "production_ran", None)):
            for cap in capture_ids:
                try:
                    got = dsh.check(sh, cap, caps)
                except SystemExit:  # a record changed since it was captured: that capture says nothing here
                    continue
                if any(k["match"] or k["differ"] for k in got["keys"].values()):
                    for k in got["keys"].values():
                        k["differ"] = dict(Counter(k["differ"]).most_common())
                    got["ok"] = all(not k["differ"] and not k["missing"] for k in got["keys"].values())
                    checks.append(got)
        return {**{k: v for k, v in sh.items() if not k.startswith("_")}, "captures": checks}

    def tag_counts(self, dataset: str, arm: str) -> dict | None:
        """The failure modes tagged on this arm's outputs on `dataset` (PLAN_0.8.0 D1), every tag set summed:
        {"outputs": read, "tagged": with a failure, "modes": {mode: n}}; None when nothing of it was tagged."""
        runs = {self._run_id(d): arm for d in self._dirs(arm)}
        got = _tags.counts(dataset, runs, self.data_dir).get(arm)
        if not got or not got["outputs"]:
            return None
        return {"outputs": got["outputs"], "tagged": got["tagged"], "modes": got["modes"]}

    def label_sets(self) -> list[dict]:
        """Every label set (RFC-023): {dataset, set, id ("<dataset>/<set>"), source, n_items, guideline, created_at,
        items {item: {"item_sha256"}}}, from data/labels/<dataset>/<set>/labels.json; [] when there are none."""
        out = []
        for doc in _label_sets.sets(self.data_dir):
            d = Path(doc["_dir"])
            out.append(
                {
                    "dataset": str(doc.get("dataset_id") or d.parent.name),
                    "set": str(doc.get("set") or d.name),
                    "id": f"{d.parent.name}/{d.name}",
                    "source": doc.get("source") or {},
                    "n_items": doc.get("n_items") or len(doc.get("items") or {}),
                    "guideline": doc.get("guideline"),
                    "created_at": doc.get("created_at"),
                    "items": doc.get("items") or {},
                    "dir": d,
                }
            )
        return out

    def label_coverage(self, dataset: str) -> dict:
        """{"sets": [{set..., "covers": [item ids]}], "agreement": [{"a", "b", **_label_sets.compare(...)}]}: the label
        sets covering this dataset's items, matched by the item's sha256 (labels follow the item), and how two compare
        on the items both label (where the label texts are here; a release keeps only labels.json). One decision with
        `evh dataset-list` (_label_sets.coverage, agreement)."""
        by_key = {(ls["dataset"], ls["set"]): ls for ls in self.label_sets()}
        sets = []
        for c in _label_sets.coverage(dataset, self.data_dir, texts=False):
            ls = by_key[(c["dataset_id"], c["set"])]
            sets.append({**{k: v for k, v in ls.items() if k not in ("items", "dir")}, "covers": c["items"]})
        return {"sets": sets, "agreement": _label_sets.agreement(dataset, self.data_dir)}

    def item_labels(self, dataset: str, item: str) -> list[dict]:
        """Every label one item has (RFC-023): {set ("<dataset>/<set>"), kind, by, text} from each set holding an item
        with its bytes (labels follow the item); the text only where it is here (a release keeps labels.json only)."""
        return _label_sets.item_labels(dataset, item, self.data_dir)

    def picks_waiting(self, dataset: str) -> list[dict]:
        """The picks waiting for this dataset (data/picks.jsonl, ADR-0023): the items whose latest line is a pick
        naming it as a target. A release does not carry the pick list, so a published catalog shows none."""
        return _picks.waiting(dataset, data=self.data_dir, strict=False)

    @_memo
    def metric_descriptions(self) -> dict[str, str]:
        """{metric: what it measures}: what the runs recorded (their adapter's METRIC_DESCRIPTIONS
        then), overlaid by what each run's adapter says today, which is the authority on what its
        metrics mean (as for metric kinds): a description is documentation, so it is read from the
        code, not frozen with the measurement. An adapter that cannot be imported here leaves the
        recorded one."""
        from evaluation_harness._adapter import recorded_metric_descriptions  # noqa: PLC0415

        out: dict[str, str] = {}
        adapters: set[str] = set()
        for ds in self._index().values():
            for d in ds:
                m = self._record(d)
                out.update(m.get("metric_descriptions") or {})
                if m.get("adapter"):
                    adapters.add(m["adapter"])
        for spec in sorted(adapters):
            out.update(recorded_metric_descriptions(spec) or {})
        return out

    def reference_format(self, ref: str) -> str:
        """This layout records no format for a reference: "", which never flags a mismatch."""
        return ""

    def reference_archived(self, ref: str) -> bool:
        """Return whether a reference has been archived."""
        return False

    def output_format(self, arm: str) -> dict:
        """Return the output format this arm was asked for and produced."""
        fmt = self._metrics(arm).get("format", "")
        return {"asked": fmt, "got": "", "how": "config" if fmt else ""}

    def item_view(self, arm: str, item: str) -> dict:
        """Return one arm's output for one item."""
        if not _plain_name(item):
            return {"kind": "none", "note": "not an item id"}
        dirs = self._dirs(arm)
        for d in reversed(dirs):  # the latest repeat
            text = _outputs.output(d, item)
            if text is not None:
                info = {"run": self._run_id(d)}
                if len(dirs) > 1:
                    # One output beside a score that is the mean of every repeat: say so.
                    info["shown"] = (
                        f"the latest of {len(dirs)} repeats; the score is the mean of all {len(dirs)}"
                    )
                # A judged arm: what each judge gave this output, beside it (the replies themselves
                # are under data/judge-verdicts/, withheld ones in their .withheld/).
                if derived_with(self._metrics(arm), "judge"):
                    for k, v in sorted(self.scores(arm).items()):
                        if k.startswith("judge_") and item in v["values"]:
                            info[k.removeprefix("judge_")] = f"{v['values'][item]:.3g}"
                return {
                    "kind": "text",
                    "text": text,
                    "info": info,
                }
        return {"kind": "none", "note": "No stored output for this item (the run's outputs.jsonl)."}

    def reference_view(self, ref: str, item: str) -> dict:
        """Return one reference's text for one item."""
        r = next((x for x in self.references() if x["id"] == ref), None)
        f = model_datasets.reference_text_file(ref, item, self.data_dir) if r and _plain_name(item) else None
        if f and _store.is_file(f):
            return {"kind": "text", "text": _store.read_text(f, encoding="utf-8", errors="replace")}
        return {"kind": "none"}

    def _materialized(self, dataset: str) -> Path:
        return model_datasets.materialized_dir(dataset, self.data_dir)

    def item_text(self, dataset: str, item: str) -> dict:
        """The item every arm read, from the dataset's materialized copy (the local inspector
        only shows it)."""
        ds = _json(self._dataset_file(dataset)) or {}
        rel = next(
            (it.get("source_path") or it["item_id"] for it in ds.get("items") or [] if it["item_id"] == item),
            None,
        )
        f = self._materialized(dataset) / rel if rel else None
        if f and _store.is_file(f):
            return {"kind": "text", "text": _store.read_text(f, encoding="utf-8", errors="replace")}
        return {
            "kind": "none",
            "note": f"Not on this machine: evh dataset-materialize --dataset-id {dataset}",
        }

    # -- goals --------------------------------------------------------------------------
    @_memo
    def goals(self) -> list[dict]:
        """Return all goals: what the evaluations are for (the loader every command uses)."""
        return [dict(g, goal_id=gid) for gid, g in load_goals(self.goals_dir).items() if g]

    def dataset_items(self, dataset: str) -> int | None:
        """Return how many items a dataset has, or None if not recorded."""
        ds = _json(self._dataset_file(dataset))
        return len(ds.get("items") or []) if isinstance(ds, dict) else None

    @_memo
    def conditions(self, arm: str) -> dict[str, str]:
        """What the arm's runs were measured under, flattened from their fingerprints: the
        machine, library versions, the harness, the scorer (adapter), the items and the
        reference's bytes. Not the arm's own params or model: those are what an arm varies. A
        field the arm's repeats disagree on reads "varies: a | b"."""
        seen: dict[str, list[str]] = {}
        for d in self._dirs(arm):
            fp = self._record(d).get("fingerprint") or {}
            flat = _flat_conditions(fp)
            for k, v in flat.items():
                if v not in seen.setdefault(k, []):
                    seen[k].append(v)
        return {k: vs[0] if len(vs) == 1 else "varies: " + " | ".join(vs) for k, vs in seen.items()}

    @_memo
    def model_facts(self) -> dict[str, dict]:
        """Each model alias a run records, to its weights and licence, from the model records
        (data/models/, model.schema.json); {} without them."""
        from evaluation_harness import _models  # noqa: PLC0415

        return _models.facts(self.data_dir)

    @_memo
    def models(self) -> list[dict]:
        """Each model record (data/models/) with the arms that use it: an arm uses a record when its
        system names it (`model_record`, as its run recorded) or its run's params.model is one of the
        record's aliases."""
        from evaluation_harness import _models  # noqa: PLC0415
        from evaluation_harness.model import faithfulness as model_faithfulness  # noqa: PLC0415

        recs = [model_faithfulness.with_summaries(r, self.data_dir) for r in _models.load(self.data_dir)]
        ids = {r.get("model_id") for r in recs}
        alias = {a: r.get("model_id") for r in recs for a in r.get("aliases") or []}
        used: dict = {r.get("model_id"): [] for r in recs}
        for arm in self.arms():
            m = self._metrics(arm)
            rid = m.get("model_record")
            if rid not in ids:
                rid = alias.get((m.get("params") or {}).get("model"))
            if rid in used:
                used[rid].append(arm)
        return [{"record": r, "arms": sorted(used[r.get("model_id")])} for r in recs]

    @_memo
    def rounds(self) -> list[dict]:
        """Eval rounds (ADR-0004, optional): each round's record, plus "arms" (the arm ids in play, as the round
        stores them, those the index has), "arm_records" (the arms as stored) and "retired_arms" (the arm ids it
        retired, and every other arm a retired arm's runs are scored in: a re-score of a retired run is retired
        with it); model.rounds.listing."""
        from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

        return model_rounds.listing(
            self.data_dir, {arm: [self._run_id(d) for d in dirs] for arm, dirs in self._index().items()}
        )

    @_memo
    def baselines(self) -> list[dict]:
        """The current baseline of every goal on every dataset, and of every dataset's own (a run with no goal: goal
        None) (RFC-027), oldest promotion first, each with the arm its run belongs to."""
        from evaluation_harness import _baselines  # noqa: PLC0415

        out = []
        for b in sorted(_baselines.all_current(self.data_dir), key=lambda x: str(x.get("promoted_at") or "")):
            run = b.get("promoted_from")
            if not run or not b.get("dataset_id"):
                continue
            # A re-score is a score of the run it re-scored; the baseline's arm is the run's own.
            hits = [a for a, ds in self._index().items() if any(self._run_id(d) == run for d in ds)]
            arm = next((a for a in hits if a.startswith("runs/")), hits[0] if hits else None)
            out.append(
                {
                    "version": b.get("version"),
                    "dataset": b["dataset_id"],
                    "run": run,
                    "arm": arm,
                    "reason": b.get("reason", ""),
                    "promoted_at": b.get("promoted_at", ""),
                    "tier": b.get("reference_tier"),
                    "goal": b.get("goal"),
                    "actor": b.get("actor"),
                    "evidence": b.get("evidence"),
                    "migrated": bool(b.get("migrated")),
                }
            )
        return out

    def baseline_versions(self, goal: str | None, dataset: str) -> list[dict]:
        """Every version of one baseline line, oldest first (RFC-027): the history the goal page folds."""
        from evaluation_harness import _baselines  # noqa: PLC0415

        return _baselines.versions(goal, dataset, self.data_dir)

    def studies(self, goal: str) -> list[dict]:
        """A goal's studies (RFC-029), each one's state, trials and confirmations, read from this adapter's data."""
        from evaluation_harness.model import study_views  # noqa: PLC0415

        return study_views.of_goal(goal, self.data_dir)

    def datasets(self) -> list[str]:
        """Every frozen dataset, run or not: a new version has a page before its first run."""
        return model_datasets.DATASET.under(self.data_dir).ids(check_format=False)

    def dataset_lineage(self, dataset: str) -> dict | None:
        """The version this dataset was made from (`derived_from`), or None."""
        ds = _json(self._dataset_file(dataset))
        got = ds.get("derived_from") if isinstance(ds, dict) else None
        return got if isinstance(got, dict) and got.get("dataset_id") else None

    def dataset_created(self, dataset: str) -> str:
        """When the dataset was frozen (`created_at`), or "" when its file does not say."""
        ds = _json(self._dataset_file(dataset))
        got = ds.get("created_at") if isinstance(ds, dict) else None
        return got if isinstance(got, str) else ""

    def dataset_meta(self, dataset: str) -> dict:
        """The dataset's `tags`, and its origin in a few words: a capture it was made from (with the
        selection; `capture` names it, for the link to it), or the version it was derived from; {} when its file
        says neither."""
        got = _json(self._dataset_file(dataset))
        if not isinstance(got, dict):
            return {}
        ds: dict = got
        tags: dict = ds["tags"] if isinstance(ds.get("tags"), dict) else {}
        mf: dict = ds["made_from"] if isinstance(ds.get("made_from"), dict) else {}
        origin = ""
        if mf.get("capture"):
            bits = [f"capture {mf['capture']}"]
            bits += [f"where {w}" for w in mf.get("where") or []]
            if mf.get("one_per"):
                bits.append(f"one per {mf['one_per']}")
            origin = ", ".join(bits)
        elif isinstance(ds.get("derived_from"), dict) and ds["derived_from"].get("dataset_id"):
            origin = f"version of {ds['derived_from']['dataset_id']}"
        return {
            "tags": {str(k): str(v) for k, v in tags.items()},
            "origin": origin,
            "capture": str(mf.get("capture") or ""),
            # A version made from picks (dataset-extend): V1 and, per added item, where it came from.
            "extended_from": ds["extended_from"] if isinstance(ds.get("extended_from"), dict) else None,
        }

    def dataset_profile(self, dataset: str) -> dict | None:
        """data/profiles/<dataset>.json (`evh dataset-profile`), with "stale": True when the dataset's
        items no longer match the version it was computed on; None without one."""
        p = _json(model_datasets.profile_file(dataset, self.data_dir))
        if not isinstance(p, dict) or not p.get("rows"):
            return None
        ds = _json(self._dataset_file(dataset))
        now = items_digest(ds) if isinstance(ds, dict) else None
        return dict(p, stale=bool(now and p.get("items_sha256") and now != p["items_sha256"]))

    # -- runs, systems and spend ---------------------------------------------------------
    def arm_runs(self, arm: str) -> list[dict]:
        """The arm's runs, oldest first: when each was made, its items, what it cost, and how
        it was derived ("" for a measured run)."""
        out = []
        for d in self._dirs(arm):
            m = self._record(d)
            run_id = m.get("run_id") or self._run_id(d)
            frm = (m.get("derived") or {}).get("from", "")
            in_place, made = measured(m, bool(model_runs.meta(d).get("first")))
            out.append(
                {
                    "run_id": run_id,
                    "created_at": made,
                    "items": m.get("n_items"),
                    "cost_usd": (m.get("scores") or {}).get("total_cost_usd"),
                    "derived": (m.get("derived") or {}).get("kind", ""),
                    "from": frm,
                    "in_place": in_place,
                }
            )
        return sorted(out, key=lambda r: (r["created_at"], r["run_id"]))

    def arm_config(self, arm: str) -> dict:
        """The system behind the arm, as its latest run recorded it; params without credentials
        (`api_key_env` left out, a literal key shown as "(hidden)")."""
        from evaluation_harness._providers import shown_params  # noqa: PLC0415

        m = self._metrics(arm)
        params = m.get("params") or {}
        read_by = ""
        if params.get("provider") == "recorded":
            from evaluation_harness._adapter import adapter_module  # noqa: PLC0415

            hook = callable(getattr(adapter_module(m.get("adapter")), "recorded_output", None))
            read_by = (
                "the adapter's recorded_output(record)"
                if hook
                else f"the record's field {params.get('field')}"
            )
        return {
            "system_id": m.get("system_id") or arm.rsplit("/", 1)[-1],
            "params": shown_params(params),
            "adapter": m.get("adapter") or "",
            "deployment": m.get("deployment_id") or "",
            # A recorded arm (RFC-023): its outputs are the capture's records, read this way; no model was called.
            "recorded_by": read_by,
            # Only an arm whose system carried one (ADR-0025): the block, and whether it was committed before the run.
            **{k: m[k] for k in ("hypothesis", "hypothesis_in_advance") if m.get(k)},
        }

    @_memo
    def spend(self) -> list[dict]:
        """What was spent and when, in USD and in tokens: every measured run, once, by the score it made when it
        ran (a re-score reads stored outputs and calls nothing), and the judges' calls per judging set and day, from the
        stored verdicts (model.spend: what `evh cost-report` counts; `usd` is what the provider billed, `estimated_usd`
        what the scorer's price table says of the calls it did not bill). Either may be None: a local model bills
        nothing but still counts tokens when its adapter reports them; an unpriced call has tokens and no USD."""
        self._index()
        out = []
        for ds, d, m, arm in self._every:
            sc = m.get("scores") or {}
            usd = number(sc.get("total_cost_usd"))
            tokens = token_total(sc.get("total_tokens_in"), sc.get("total_tokens_out"))
            first = bool(model_runs.meta(d).get("first"))
            _in_place, at = measured(m, first)
            if not first or (usd is None and tokens is None):
                continue
            out.append(
                {
                    "at": at,
                    "usd": usd,
                    "tokens": tokens,
                    "kind": "arm",
                    "dataset": ds,
                    "what": self._run_id(d),
                    "arm": arm,
                }
            )
        out += model_spend.judge_spend(self.data_dir)
        out += smoke_spend(self.models())
        return sorted(out, key=lambda x: x["at"])

    # -- item fields (ADR-0003) -----------------------------------------------------------
    @_memo
    def item_fields(self, dataset: str) -> dict:
        """Return a dataset's declared fields and items' values."""
        ds = _json(self._dataset_file(dataset)) or {}
        fid = ds.get("fieldset")
        fs = load_fieldset(fid, model_datasets.FIELDSET.under(self.data_dir).base()) if fid else None
        # A field set that breaks its schema drives no page; validate (V15) names what is wrong.
        return {
            "fieldset": fs if fs and not fieldset_problems(str(fid), fs) else None,
            "values": {it["item_id"]: it.get("fields") or {} for it in ds.get("items") or []},
        }


def smoke_spend(models: list[dict]) -> list[dict]:
    """The arm smokes' spend entries (kind "smoke"), from the model records' smoke reports: paid calls no run
    record holds. A report's `spent_usd` counts the determinism check's repeat call; an older report has only its
    items' cost_usd, summed. A smoke belongs to no dataset's spend."""
    out = []
    for x in models:
        for system_id, sm in ((x.get("record") or {}).get("smokes") or {}).items():
            rep = (sm or {}).get("report") or {}
            usd = number(rep.get("spent_usd"))
            if usd is None:
                usd = sum(number(i.get("cost_usd")) or 0.0 for i in rep.get("items") or [])
            if usd:
                at = str((sm or {}).get("at") or "")[:10]
                out.append(
                    {"at": at, "usd": usd, "tokens": None, "kind": "smoke", "dataset": "", "what": system_id}
                )
    return out


def configured_spec() -> str | None:
    """The adapter the project's config.yaml names (`catalog.adapter`), None for the harness's own."""
    cfg = _common.ROOT / "config.yaml"
    if not _store.is_file(cfg):
        return None
    import yaml  # noqa: PLC0415

    doc = yaml.safe_load(_store.read_text(cfg, encoding="utf-8")) or {}
    spec: str | None = (doc.get("catalog") or {}).get("adapter")
    return spec


def load_catalog_adapter(spec: str | None = None) -> Adapter:
    """`path/to/file.py:Class` or `module:Class`, relative to the project root; else the
    project's config.yaml `catalog.adapter`; else HarnessAdapter."""
    root = _common.ROOT
    spec = spec or configured_spec()
    if not spec:
        return exposure_aware(HarnessAdapter())
    target, _, cls = spec.rpartition(":")
    if not target or not cls:
        from evaluation_harness._common import die  # noqa: PLC0415

        die(f"catalog adapter {spec!r}: expected 'path/to/file.py:Class' or 'module:Class'", "bad-argument")
    # The project's root is importable while its adapter loads (it may import its own helpers).
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if target.endswith(".py"):
        path = (root / target).resolve()
        try:
            # A name of its own: registered under its stem, a project file called `adapter.py`
            # or `stats.py` replaced the harness's module of that name in sys.modules.
            digest = hashlib.sha256(str(path).encode()).hexdigest()[:8]
            mod = load_module(path, f"evh_catalog_adapter_{path.stem}_{digest}")
        except ModuleNotLoadable:
            from evaluation_harness._common import die  # noqa: PLC0415

            die(f"catalog adapter: cannot load {path}", "failed")
    else:
        mod = importlib.import_module(target)
    return exposure_aware(getattr(mod, cls)())


def shared_adapter(spec: str | None = None, load=None):
    """The project's catalog adapter for a view, its scores read once per arm, and kept (model/view_cache) for as long
    as the data is what they were read from: a process that answers many views builds the adapter, indexes the runs
    and reads each arm's scores once, not for every view. A new one after any write, this process's or another's.
    `spec`: an adapter named on the command line is that adapter's own, as before (one view, one process). `load`: the
    loader a caller reads the adapter with when it is not `load_catalog_adapter` itself (a test's stand-in): its adapter
    is its own, never shared."""
    view_cache.begin()  # a view starts: the data is looked at before anything kept is reused
    if spec or (load is not None and load is not load_catalog_adapter) or not harness_own():
        return scores_once((load or load_catalog_adapter)(spec))
    return view_cache.get(("adapter",), lambda: scores_once(load_catalog_adapter(None), held=True))


def harness_own() -> bool:
    """Whether the views read the harness's own layout: no adapter named in config.yaml, and the server's, when it has
    one, is the harness's. What the view cache's key covers is the project's data/ (the data root and the goals); a
    project's own adapter may read anywhere, so nothing is kept of a view it answers (the server keeps its scores
    as it always has: until its own `refresh()`)."""
    from evaluation_harness import catalog_serve  # noqa: PLC0415

    served = getattr(catalog_serve, "A", None)
    if served is not None:
        return type(served) is HarnessAdapter
    return not view_cache.get(("spec",), configured_spec)


def exposure_aware(adapter):
    """The adapter, its `scores` leaving out a held-out side's read items (RFC-031 H1): every page, goal, round and
    inspector answer reads scores through it, a project's own adapter's too, so the read items count in none of them.
    The seal and the register are the adapter's own data directory's (`_exposure.aware`)."""
    from evaluation_harness import _exposure  # noqa: PLC0415

    return _exposure.aware(adapter)
