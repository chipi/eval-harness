"""What the catalog and the run inspector need from a project's data, and the harness's own answer.

An ADAPTER answers questions about a project's runs: which arms exist, what each scored per
item, which way is better, what references exist, and what one arm wrote for one item. The
catalog builder (catalog_build.py) and the inspector server (catalog_serve.py) only ever ask
these questions, so a project with its own layout writes one adapter and gets both (ADR-0002).

    catalog:
      adapter: tools/my_adapter.py:Adapter     # in the project's config.yaml, or --adapter

Without one, HarnessAdapter reads the harness's own layout:

    <data>/runs*/<run_id>/{metrics.json, predictions.jsonl, outputs/<item_id>.txt}
    <data>/runs-judged/<scorer_id>/<run_id>/...        (evh judge-score, 0.3.0+)
    <data>/references/<tier>/<dataset_id>/<item_id>.txt

An ARM is a string id the adapter chooses. HarnessAdapter's is `<runs dir>/<dataset_id>/<config_id>`:
every repeat of a config on a dataset, averaged per item, exactly as `pair-test` and
`family-test` read them, so the inspector and the command line give the same p.

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
import json
import statistics
import sys
from functools import wraps
from pathlib import Path
from typing import Protocol

HERE = Path(__file__).resolve().parent

from evaluation_harness import _common  # noqa: E402
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
from evaluation_harness._runs import item_rows, lower_is_better_on, runs_on, score_of  # noqa: E402


def _memo(fn):
    """Cache a method's answers on its instance. `functools.lru_cache` on a method keys on
    `self` in a module-level cache, so every adapter ever made (one per test, per server
    start) stays alive with its data; this cache goes when the adapter does."""
    slot = f"_memo_{fn.__name__}"

    @wraps(fn)
    def wrapper(self, *args):
        cache = self.__dict__.setdefault(slot, {})
        if args not in cache:
            cache[args] = fn(self, *args)
        return cache[args]

    return wrapper


class Adapter(Protocol):
    """The questions the catalog and the inspector ask. Every method must be cheap to call
    twice. The server caches `scores` for as long as it runs, and the built-in adapter its
    index of runs: restart `catalog-serve` to see runs made after it started."""

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
        page: "items", "author" (the config that wrote it), "from_run", "model", "created_at",
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
    # Optional: the promoted baselines (run-promote), [{"baseline_id", "dataset", "run", "arm",
    # "reason", "promoted_at", "tier", "goal"}]; the pages lead with them, the answer so far.
    # def baselines(self) -> list[dict]: ...
    # Optional: the arm id of a config on a dataset (`evh rounds`, `evh inspect --round` and the
    # round pages build arm ids with it): `runs/<dataset>/<config_id>` when absent.
    # def arm_of(self, dataset: str, config_id: str) -> str: ...
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
    # Optional: experiment rounds (ADR-0004), each round's record with "arms", the arm ids in play;
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
    # Optional: what an arm was asked to do, {"config_id", "params", "adapter", "deployment"}, params
    # without credentials, "deployment" the model-record deployment its config named ("" for none);
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


def _number(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _tokens(tin, tout) -> int | None:
    """Tokens in plus out, or None when neither was reported (unknown is not 0)."""
    vals = [_number(x) for x in (tin, tout)]
    return int(sum(x for x in vals if x is not None)) if any(x is not None for x in vals) else None


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
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


class HarnessAdapter:
    """The harness's own data tree. Arms are configs on a dataset, repeats averaged per item."""

    item_word = "item"
    can_rescore = False

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir or _common.DATA)
        # The project's goals (EVAL_GOALS_DIR when set) unless a data directory is named.
        self.goals_dir = _common.GOALS if data_dir is None else self.data_dir / "goals"

    # -- arms ---------------------------------------------------------------------------
    @_memo
    def _index(self) -> dict[str, list[Path]]:
        """{arm id: [run dirs]}, from every runs* directory and runs-judged/<scorer>/."""
        out: dict[str, list[Path]] = {}
        bases = [p for p in sorted(self.data_dir.glob("runs*")) if p.is_dir() and p.name != "runs-judged"]
        bases += sorted(p for p in (self.data_dir / "runs-judged").glob("*") if p.is_dir())
        refs: dict[Path, str] = {}
        made: dict[Path, str] = {}
        # Every run seen, before any is set aside below: what was billed counts them all.
        self._every: list[tuple[str, Path, dict, str]] = []
        for base in bases:
            for d, m in runs_on(runs_dir=base):
                if not m.get("dataset_id"):
                    continue
                rel = base.relative_to(self.data_dir).as_posix()
                arm = f"{rel}/{m['dataset_id']}/{m['config_id']}"
                self._every.append((m["dataset_id"], d, m, arm))
                out.setdefault(arm, []).append(d)
                refs[d] = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id") or ""
                made[d] = m.get("created_at") or ""
        # ONE REFERENCE PER ARM: the one its latest run was scored against. An arm's runs were
        # averaged whatever they were scored against, so a run on silver and a run on gold read
        # as two repeats of one measurement. Runs on another reference are left out, and said so.
        self._stale: dict[str, list[str]] = {}
        for arm, dirs in out.items():
            # Latest by when it was measured, not by its directory name (a --run-id can be anything).
            ref = refs[max(dirs, key=lambda d: (made[d], d.name))]
            old = [d for d in dirs if refs[d] != ref]
            if old:
                out[arm] = [d for d in dirs if refs[d] == ref]
                was = sorted({refs[d] or "no reference" for d in old})
                self._stale[arm] = [
                    (
                        f"{len(old)} earlier run(s) scored against {', '.join(was)} left out: this arm is read "
                        f"against {ref or 'no reference'}, the reference of its latest run"
                    )
                ]
        return out

    def arms(self) -> list[str]:
        """Return all arm ids."""
        return list(self._index())

    def arms_of(self, path: str) -> list[str]:
        """The arm ids a path the caller selected yields; [] if none."""
        path = path.strip("/")
        if path in self._index():
            return [path]
        # a run directory selects the arm it belongs to
        return [
            a
            for a, ds in self._index().items()
            if any(d.relative_to(self.data_dir).as_posix() == path for d in ds)
        ]

    def _dirs(self, arm: str) -> list[Path]:
        return self._index().get(arm, [])

    def _metrics(self, arm: str) -> dict:
        ds = self._dirs(arm)
        return (_json(ds[-1] / "metrics.json") or {}) if ds else {}

    def describe(self, arm: str) -> dict:
        """Return arm metadata: id, label, dataset, task, etc."""
        base, _, rest = arm.rpartition("/")
        runs_dir, _, dataset = base.rpartition("/")
        m = self._metrics(arm)
        n = len(self._dirs(arm))
        label = rest + ("" if runs_dir == "runs" else f" · {runs_dir.removeprefix('runs-')}")
        label += f" ×{n}" if n > 1 else ""
        judged = derived_with(m, "judge").get("scorer_id")
        primary = m.get("primary_metric") or ""
        if judged:  # a judged run's headline is the judge's score, not the source run's metric
            keys = set(self.scores(arm))
            primary = next((k for k in ("judge_score", "judge_score_unvalidated") if k in keys), primary)
        ref = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id", "")
        author = next((r.get("author") for r in self.references() if r["id"] == ref), None)
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
            # Graded against its own outputs: the arm whose run (or config) wrote the reference.
            "wrote_reference": bool(author) and not judged and author == m.get("config_id"),
        }

    # -- scores -------------------------------------------------------------------------
    def scores(self, arm: str, rescore: bool = False) -> dict[str, dict]:
        """Return per-item scores for this arm: {metric: {source, values}}."""
        acc: dict[str, dict[str, list]] = {}
        for d in self._dirs(arm):
            # A page may show a run with a corrupt line; a statistical test may not (strict).
            for r in item_rows(d, strict=False):
                for k, v in _numeric(r).items():
                    acc.setdefault(k, {}).setdefault(r["item_id"], []).append(v)
        n = len(self._dirs(arm))
        src = "predictions.jsonl" + (f" (mean of {n} repeats)" if n > 1 else "")
        return {
            k: {"source": src, "values": {i: statistics.fmean(v) for i, v in items.items()}}
            for k, items in acc.items()
        }

    @property
    def preferred_metrics(self) -> tuple:
        """Every arm's primary metric, most common first: the inspector's default yardstick."""
        from collections import Counter  # noqa: PLC0415

        c = Counter(
            (_json(ds[-1] / "metrics.json") or {}).get("primary_metric") for ds in self._index().values()
        )
        return tuple(k for k, _ in c.most_common() if k)

    def recorded_means(self, arm: str) -> dict[str, float]:
        """Return run-level averages for arms with no per-item scores."""
        if any((d / "predictions.jsonl").is_file() for d in self._dirs(arm)):
            return {}
        return _numeric(self._metrics(arm).get("scores") or {})

    def input_hashes(self, arm: str) -> dict[str, str]:
        """Return per-item input hashes where recorded."""
        return {}  # the dataset's per-item sha256 is the input, for every arm alike

    def notes(self, arm: str) -> list[str]:
        """Return notes explaining why something could not be scored, or what was left out."""
        self._index()
        return list(getattr(self, "_stale", {}).get(arm, []))

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
            for m in [_json(d / "metrics.json") or {}]
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
            m = _json(ds[-1] / "metrics.json") or {}
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

    def arm_of(self, dataset: str, config_id: str) -> str:
        """The arm id of a config's runs on a dataset: `<runs dir>/<dataset>/<config_id>`, the
        runs directory as this project names it (EVAL_RUNS_DIR), relative to its data."""
        try:
            base = _common.RUNS.resolve().relative_to(self.data_dir.resolve()).as_posix()
        except ValueError:
            base = "runs"
        return f"{base}/{dataset}/{config_id}"

    @_memo
    def _kinds(self) -> dict:
        out: dict = {}
        for ds in self._index().values():
            out.update((_json(ds[-1] / "metrics.json") or {}).get("metric_kinds") or {})
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
        the set's manifest.json says (reference-create and reference-manifest write one): author,
        from_run, model, created_at, items, caveat, and "fetched" (its texts are not here: a
        reference the project does not redistribute, listed from its manifest)."""
        out = []
        for tier in ("gold", "silver"):
            for d in sorted((self.data_dir / "references" / tier).glob("*")):
                texts = d.is_dir() and any(d.glob("*.txt"))
                if d.is_dir() and (texts or (d / "manifest.json").is_file()):
                    mf = _json(d / "manifest.json") or {}
                    out.append(
                        {
                            "id": f"{tier}/{d.name}",
                            "tier": tier,
                            # The manifest names the dataset; the directory names the reference
                            # (a second gold for one dataset has a name of its own).
                            "dataset": mf.get("dataset_id") or d.name,
                            "task": "",
                            "archived": False,
                            "format": "",
                            "dir": d,
                            "items": len(list(d.glob("*.txt"))) if texts else mf.get("n_items"),
                            "fetched": not texts,
                            "source": mf.get("source"),
                            "author": mf.get("authored_by"),
                            "from_run": (mf.get("from_run") or {}).get("run_id"),
                            "model": mf.get("model"),
                            "created_at": mf.get("created_at"),
                            "caveat": mf.get("caveat"),
                        }
                    )
        return out

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
                m = _json(d / "metrics.json") or {}
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
            f = d / "outputs" / f"{item}.txt"
            if f.is_file():
                info = {"run": d.name}
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
                    "text": f.read_text(encoding="utf-8", errors="replace"),
                    "info": info,
                }
        return {"kind": "none", "note": "No stored output for this item (outputs/<item_id>.txt)."}

    def reference_view(self, ref: str, item: str) -> dict:
        """Return one reference's text for one item."""
        r = next((x for x in self.references() if x["id"] == ref), None)
        f = r["dir"] / f"{item}.txt" if r and _plain_name(item) else None
        if f and f.is_file():
            return {"kind": "text", "text": f.read_text(encoding="utf-8", errors="replace")}
        return {"kind": "none"}

    def item_text(self, dataset: str, item: str) -> dict:
        """The item every arm read, from the dataset's materialized copy (the local inspector
        only shows it)."""
        ds = _json(self.data_dir / "datasets" / f"{dataset}.json") or {}
        rel = next(
            (it.get("source_path") or it["item_id"] for it in ds.get("items") or [] if it["item_id"] == item),
            None,
        )
        f = self.data_dir / "materialized" / dataset / rel if rel else None
        if f and f.is_file():
            return {"kind": "text", "text": f.read_text(encoding="utf-8", errors="replace")}
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
        ds = _json(self.data_dir / "datasets" / f"{dataset}.json")
        return len(ds.get("items") or []) if isinstance(ds, dict) else None

    @_memo
    def conditions(self, arm: str) -> dict[str, str]:
        """What the arm's runs were measured under, flattened from their fingerprints: the
        machine, library versions, the harness, the scorer (adapter), the items and the
        reference's bytes. Not the arm's own params or model: those are what an arm varies. A
        field the arm's repeats disagree on reads "varies: a | b"."""
        seen: dict[str, list[str]] = {}
        for d in self._dirs(arm):
            fp = (_json(d / "metrics.json") or {}).get("fingerprint") or {}
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
        config names it (`model_record`, as its run recorded) or its run's params.model is one of the
        record's aliases."""
        from evaluation_harness import _models  # noqa: PLC0415

        recs = _models.load(self.data_dir)
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
        """Experiment rounds (ADR-0004, optional): each round's record, plus "arms" (the arm ids in
        play: runs in any runs directory that name it, and the configs carried in, less the retired)
        and "retired_arms" (the arm ids it retired: a retirement names a runs directory, else the
        project's)."""
        import yaml  # noqa: PLC0415

        out = []
        base = self.data_dir / "rounds"
        for f in sorted(base.glob("*/r*.yaml"), key=lambda p: (p.parent.name, int(p.stem[1:] or 0))):
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if not isinstance(doc, dict) or not doc.get("round_id"):
                continue
            ds = doc.get("dataset_id", "")
            ran = {
                arm
                for arm, dirs in self._index().items()
                if arm.split("/")[-2:-1] == [ds]
                and any(
                    (m := _json(d / "metrics.json") or {}).get("round") == doc["round_id"]
                    and m.get("goal") == doc.get("goal")
                    for d in dirs
                )
            }
            home = self.arm_of(ds, "").split("/", 1)[0]
            retired = {
                f"{r.get('runs_dir') or home}/{ds}/{r.get('config_id')}" for r in doc.get("retired") or []
            }
            carried = {self.arm_of(ds, c) for c in doc.get("carried") or []}
            in_play = sorted(a for a in (ran | carried) - retired if a in self._index())
            out.append(dict(doc, arms=in_play, retired_arms=sorted(retired)))
        return out

    @_memo
    def baselines(self) -> list[dict]:
        """The promoted baselines (data/baselines/*.json), each with the arm its run belongs to."""
        out = []
        for f in sorted((self.data_dir / "baselines").glob("*.json")):
            b = _json(f) or {}
            run = b.get("promoted_from")
            if not run or not b.get("dataset_id"):
                continue
            # A rescored copy keeps its source's run name; run-promote reads data/runs.
            hits = [a for a, ds in self._index().items() if any(d.name == run for d in ds)]
            arm = next((a for a in hits if a.startswith("runs/")), hits[0] if hits else None)
            out.append(
                {
                    "baseline_id": b.get("baseline_id", f.stem),
                    "dataset": b["dataset_id"],
                    "run": run,
                    "arm": arm,
                    "reason": b.get("reason", ""),
                    "promoted_at": b.get("promoted_at", ""),
                    "tier": b.get("reference_tier"),
                    "goal": b.get("goal"),
                }
            )
        return out

    def datasets(self) -> list[str]:
        """Every frozen dataset, run or not: a new version has a page before its first run."""
        return sorted(p.stem for p in (self.data_dir / "datasets").glob("*.json"))

    def dataset_lineage(self, dataset: str) -> dict | None:
        """The version this dataset was made from (`derived_from`), or None."""
        ds = _json(self.data_dir / "datasets" / f"{dataset}.json")
        got = ds.get("derived_from") if isinstance(ds, dict) else None
        return got if isinstance(got, dict) and got.get("dataset_id") else None

    def dataset_created(self, dataset: str) -> str:
        """When the dataset was frozen (`created_at`), or "" when its file does not say."""
        ds = _json(self.data_dir / "datasets" / f"{dataset}.json")
        got = ds.get("created_at") if isinstance(ds, dict) else None
        return got if isinstance(got, str) else ""

    def dataset_meta(self, dataset: str) -> dict:
        """The dataset's `tags`, and its origin in a few words: a capture it was made from (with the
        selection), or the version it was derived from; {} when its file says neither."""
        got = _json(self.data_dir / "datasets" / f"{dataset}.json")
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
            if mf.get("sample"):
                bits.append(f"a sample of {mf['sample']}")
            origin = ", ".join(bits)
        elif isinstance(ds.get("derived_from"), dict) and ds["derived_from"].get("dataset_id"):
            origin = f"version of {ds['derived_from']['dataset_id']}"
        return {"tags": {str(k): str(v) for k, v in tags.items()}, "origin": origin}

    def dataset_profile(self, dataset: str) -> dict | None:
        """data/profiles/<dataset>.json (`evh dataset-profile`), with "stale": True when the dataset's
        items no longer match the version it was computed on; None without one."""
        p = _json(self.data_dir / "profiles" / f"{dataset}.json")
        if not isinstance(p, dict) or not p.get("rows"):
            return None
        ds = _json(self.data_dir / "datasets" / f"{dataset}.json")
        now = items_digest(ds) if isinstance(ds, dict) else None
        return dict(p, stale=bool(now and p.get("items_sha256") and now != p["items_sha256"]))

    # -- runs, configs and spend ---------------------------------------------------------
    def arm_runs(self, arm: str) -> list[dict]:
        """The arm's runs, oldest first: when each was made, its items, what it cost, and how
        it was derived ("" for a measured run)."""
        out = []
        for d in self._dirs(arm):
            m = _json(d / "metrics.json") or {}
            out.append(
                {
                    "run_id": m.get("run_id") or d.name,
                    "created_at": m.get("created_at") or "",
                    "items": m.get("n_items"),
                    "cost_usd": (m.get("scores") or {}).get("total_cost_usd"),
                    "derived": (m.get("derived") or {}).get("kind", ""),
                    "from": (m.get("derived") or {}).get("from", ""),
                }
            )
        return sorted(out, key=lambda r: (r["created_at"], r["run_id"]))

    def arm_config(self, arm: str) -> dict:
        """The config behind the arm, as its latest run recorded it; params without credentials
        (`api_key_env` left out, a literal key shown as "(hidden)")."""
        from evaluation_harness._providers import shown_params  # noqa: PLC0415

        m = self._metrics(arm)
        return {
            "config_id": m.get("config_id") or arm.rsplit("/", 1)[-1],
            "params": shown_params(m.get("params") or {}),
            "adapter": m.get("adapter") or "",
            "deployment": m.get("deployment_id") or "",
        }

    @_memo
    def spend(self) -> list[dict]:
        """What was spent and when, in USD and in tokens: every measured run (a derived run re-reads
        stored outputs and calls nothing), and the judges' calls per judging set and day, from the
        stored verdicts. Either may be None: a local model bills nothing but still counts tokens
        when its adapter reports them; an unpriced call has tokens and no USD."""
        self._index()
        out = []
        for ds, d, m, arm in self._every:
            sc = m.get("scores") or {}
            usd = _number(sc.get("total_cost_usd"))
            tokens = _tokens(sc.get("total_tokens_in"), sc.get("total_tokens_out"))
            if m.get("derived") or (usd is None and tokens is None):
                continue
            out.append(
                {
                    "at": m.get("created_at") or "",
                    "usd": usd,
                    "tokens": tokens,
                    "kind": "arm",
                    "dataset": ds,
                    "what": d.name,
                    "arm": arm,
                }
            )
        sets = self.data_dir / "judging-sets"
        days: dict[tuple, list] = {}
        for f in sorted((self.data_dir / "judge-verdicts").glob("*/*/*/*.json")):
            v = _json(f) or {}
            usd = _number(v.get("cost_usd"))
            tokens = _tokens(v.get("tokens_in"), v.get("tokens_out"))
            if usd is None and tokens is None:
                continue
            key = ((v.get("created_at") or "")[:10], f.parts[-4], f.parts[-3])
            acc = days.setdefault(key, [None, None])
            acc[0] = usd if acc[0] is None else acc[0] + (usd or 0.0)
            acc[1] = tokens if acc[1] is None else acc[1] + (tokens or 0)
        for (day, scorer, set_id), (usd, tokens) in sorted(days.items()):
            ds = (_json(sets / f"{set_id}.json") or {}).get("dataset_id", "")
            out.append(
                {
                    "at": day,
                    "usd": round(usd, 8) if usd is not None else None,
                    "tokens": tokens,
                    "kind": "judge",
                    "dataset": ds,
                    "what": scorer,
                }
            )
        return sorted(out, key=lambda x: x["at"])

    # -- item fields (ADR-0003) -----------------------------------------------------------
    @_memo
    def item_fields(self, dataset: str) -> dict:
        """Return a dataset's declared fields and items' values."""
        ds = _json(self.data_dir / "datasets" / f"{dataset}.json") or {}
        fid = ds.get("fieldset")
        fs = load_fieldset(fid, self.data_dir / "fields") if fid else None
        # A field set that breaks its schema drives no page; validate (V15) names what is wrong.
        return {
            "fieldset": fs if fs and not fieldset_problems(str(fid), fs) else None,
            "values": {it["item_id"]: it.get("fields") or {} for it in ds.get("items") or []},
        }


def load_catalog_adapter(spec: str | None = None) -> Adapter:
    """`path/to/file.py:Class` or `module:Class`, relative to the project root; else the
    project's config.yaml `catalog.adapter`; else HarnessAdapter."""
    root = _common.ROOT
    if not spec:
        cfg = root / "config.yaml"
        if cfg.is_file():
            import yaml  # noqa: PLC0415

            spec = ((yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}).get("catalog") or {}).get(
                "adapter"
            )
    if not spec:
        return HarnessAdapter()
    target, _, cls = spec.rpartition(":")
    if not target or not cls:
        raise SystemExit(f"catalog adapter {spec!r}: expected 'path/to/file.py:Class' or 'module:Class'")
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
            raise SystemExit(f"catalog adapter: cannot load {path}") from None
    else:
        mod = importlib.import_module(target)
    return getattr(mod, cls)()
