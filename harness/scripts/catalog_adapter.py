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

Item text (outputs, references) is only ever returned by item_view / reference_view, which
only the local inspector server calls. The static catalog never embeds it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import statistics
import sys
from functools import wraps
from pathlib import Path
from typing import Protocol

HERE = Path(__file__).resolve().parent

import _common  # noqa: E402
from _common import (  # noqa: E402
    BOOKKEEPING_PREFIXES,
    ModuleNotLoadable,
    is_descriptive,
    load_goals,
    load_module,
)
from _record import derived_with  # noqa: E402
from _runs import item_rows, lower_is_better_on, runs_on, score_of  # noqa: E402


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

    def is_neutral(self, metric: str) -> bool:
        """A measurement with no better direction (length, counts)."""

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
        """One arm's output for one item: {"kind": "text", "text": ...} or {"kind": "none"}."""

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
    # "harness.version": ..., "scorer.sha256": ..., "data.items_sha256": ...,
    # "reference.sha256": ...}; the inspector lists what differs between the arms it compares.
    # def conditions(self, arm: str) -> dict[str, str]: ...
    # Optional: the promoted baselines (run-promote), [{"baseline_id", "dataset", "run", "arm",
    # "reason", "promoted_at", "tier", "goal"}]; the pages lead with them, the answer so far.
    # def baselines(self) -> list[dict]: ...
    # Optional: experiment rounds (ADR-0004), each round's record with "arms", the arm ids in play;
    # a goal page shows them as its history.
    # def rounds(self) -> list[dict]: ...
    # Optional: every dataset id, including those no arm has run on yet.
    # def datasets(self) -> list[str]: ...
    # Optional: the version a dataset was made from, {"dataset_id", "added", "removed",
    # "changed"} (item id lists), or None; the dataset pages link the versions both ways.
    # def dataset_lineage(self, dataset: str) -> Optional[dict]: ...


def item_fields(A, dataset: str) -> dict:
    """A dataset's declared fields and its items' values, from the adapter if it answers, else
    none: the pages then show no fields."""
    fn = getattr(A, "item_fields", None)
    got = fn(dataset) if callable(fn) else None
    return got if isinstance(got, dict) and got.get("fieldset") else {"fieldset": None, "values": {}}


def _flat_conditions(fp: dict) -> dict[str, str]:
    """A run fingerprint's conditions as {group.field: value} (see HarnessAdapter.conditions)."""
    out: dict[str, str] = {}
    for k, v in (fp.get("host") or {}).items():
        if v is not None:
            out[f"machine.{k}"] = str(v)
    for k, v in ((fp.get("system_under_test") or {}).get("libraries") or {}).items():
        out[f"library.{k}"] = str(v)
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
        for base in bases:
            for d, m in runs_on(runs_dir=base):
                if not m.get("dataset_id"):
                    continue
                rel = base.relative_to(self.data_dir).as_posix()
                out.setdefault(f"{rel}/{m['dataset_id']}/{m['config_id']}", []).append(d)
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
    def _descriptive(self) -> frozenset:
        kinds = set()
        for ds in self._index().values():
            m = _json(ds[-1] / "metrics.json") or {}
            kinds |= {k for k, v in (m.get("metric_kinds") or {}).items() if v == "descriptive"}
        return frozenset(kinds)

    def is_neutral(self, metric: str) -> bool:
        """Return whether this metric is descriptive (neither better nor worse)."""
        return is_descriptive(metric) or metric in self._descriptive()

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
        the set's manifest.json says (reference-create writes one): author, from_run, model,
        created_at, n_items, caveat."""
        out = []
        for tier in ("gold", "silver"):
            for d in sorted((self.data_dir / "references" / tier).glob("*")):
                if d.is_dir() and any(d.glob("*.txt")):
                    mf = _json(d / "manifest.json") or {}
                    out.append(
                        {
                            "id": f"{tier}/{d.name}",
                            "tier": tier,
                            "dataset": d.name,
                            "task": "",
                            "archived": False,
                            "format": "",
                            "dir": d,
                            "items": len(list(d.glob("*.txt"))),
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
        """{metric: what it measures}, as the runs record it (the adapter's
        METRIC_DESCRIPTIONS). Two runs that describe one metric differently: the one read last."""
        out: dict[str, str] = {}
        for ds in self._index().values():
            for d in ds:
                out.update((_json(d / "metrics.json") or {}).get("metric_descriptions") or {})
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
                return {
                    "kind": "text",
                    "text": f.read_text(encoding="utf-8", errors="replace"),
                    "info": info,
                }
        return {"kind": "none", "note": "No stored output for this item (outputs/<item_id>.txt)."}

    def reference_view(self, ref: str, item: str) -> dict:
        """Return one reference's text for one item."""
        r = next((x for x in self.references() if x["id"] == ref), None)
        f = r["dir"] / f"{item}.txt" if r else None
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
    def rounds(self) -> list[dict]:
        """Experiment rounds (ADR-0004, optional): each round's record, plus "arms" (the arm ids in
        play: configs whose runs in data/runs name it, and those carried in, less the retired)."""
        import yaml  # noqa: PLC0415

        out = []
        base = self.data_dir / "rounds"
        for f in sorted(base.glob("*/r*.yaml"), key=lambda p: (p.parent.name, int(p.stem[1:] or 0))):
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if not isinstance(doc, dict) or not doc.get("round_id"):
                continue
            ds = doc.get("dataset_id", "")
            ran = {
                arm.rsplit("/", 1)[-1]
                for arm, dirs in self._index().items()
                if arm.startswith(f"runs/{ds}/")
                and any(
                    (m := _json(d / "metrics.json") or {}).get("round") == doc["round_id"]
                    and m.get("goal") == doc.get("goal")
                    for d in dirs
                )
            }
            retired = {r.get("config_id") for r in doc.get("retired") or []}
            in_play = sorted((ran | set(doc.get("carried") or [])) - retired)
            out.append(
                dict(doc, arms=[f"runs/{ds}/{c}" for c in in_play if f"runs/{ds}/{c}" in self._index()])
            )
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

    # -- item fields (ADR-0003) -----------------------------------------------------------
    @_memo
    def item_fields(self, dataset: str) -> dict:
        """Return a dataset's declared fields and items' values."""
        from _fields import fieldset_problems, load_fieldset  # noqa: PLC0415

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
