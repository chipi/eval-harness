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

import importlib.util
import json
import statistics
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

try:
    from typing import Protocol
except ImportError:  # Python 3.7
    Protocol = object  # type: ignore[assignment,misc]

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import DATA, ROOT, is_descriptive, lower_is_better  # noqa: E402


class Adapter(Protocol):
    """The questions the catalog and the inspector ask. Every method must be cheap to call
    twice: the server caches nothing but `scores`."""

    #: What one item is called on the pages ("item", "episode", "article").
    item_word: str
    #: The data directory, served read-only by the inspector ("files" links open it).
    data_dir: Path
    #: Per-item facts that are never a default yardstick (length, latency): the scatter's x axis.
    shape_metrics: tuple
    #: Whether scores(arm, rescore=True) can compute what is not on record.
    can_rescore: bool

    def arms(self) -> List[str]:
        """Every arm id, for the catalog and the inspector's picker."""

    def arms_of(self, path: str) -> List[str]:
        """The arm ids a path the caller selected yields (often [path] itself); [] if none."""

    def describe(self, arm: str) -> dict:
        """{"id", "label", "dataset", "task"}; "dataset" is "" when none is recorded."""

    def scores(self, arm: str, rescore: bool = False) -> Dict[str, dict]:
        """{metric: {"source": str, "values": {item_id: float}}}."""

    @property
    def preferred_metrics(self) -> tuple:
        """Every arm's primary metric, most common first: the inspector's default yardstick."""

    def recorded_means(self, arm: str) -> Dict[str, float]:
        """Run-level averages, for arms with no per-item scores: shown, never tested."""

    def input_hashes(self, arm: str) -> Dict[str, str]:
        """{item_id: hash of the input the arm read}, where recorded."""

    def notes(self, arm: str) -> List[str]:
        """Why something could not be scored, in words."""

    def lower_is_better(self, metric: str) -> bool: ...

    def is_neutral(self, metric: str) -> bool:
        """A measurement with no better direction (length, counts)."""

    def references(self) -> List[dict]:
        """[{"id", "tier", "dataset", "task", "archived", "format"}]."""

    def reference_format(self, ref: str) -> str: ...

    def reference_archived(self, ref: str) -> bool: ...

    def output_format(self, arm: str) -> dict:
        """{"asked", "got", "how"}: the output format the arm was asked for and produced."""

    def item_view(self, arm: str, item: str) -> dict:
        """One arm's output for one item: {"kind": "text", "text": ...} or {"kind": "none"}."""

    def reference_view(self, ref: str, item: str) -> dict: ...

    def goals(self) -> List[dict]:
        """Every goal (goal.schema.json): what the evaluations are FOR. [] when there are none."""

    def goal_of(self, arm: str) -> str:
        """The goal an arm names ("" if none)."""

    # Optional (ADR-0003); `item_fields(A, dataset)` below answers for an adapter without it.
    # def item_fields(self, dataset: str) -> dict:
    #     {"fieldset": <fieldset.schema.json document> or None, "values": {item_id: {field: value}}}


def item_fields(A, dataset: str) -> dict:
    """A dataset's declared fields and its items' values, from the adapter if it answers, else
    none: the pages then show no fields."""
    fn = getattr(A, "item_fields", None)
    got = fn(dataset) if callable(fn) else None
    return got if isinstance(got, dict) and got.get("fieldset") else {"fieldset": None, "values": {}}


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rows(p: Path) -> list:
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _numeric(row: dict) -> dict:
    return {k: float(v) for k, v in row.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            and not k.startswith("self_family_")}


class HarnessAdapter:
    """The harness's own data tree. Arms are configs on a dataset, repeats averaged per item."""

    item_word = "item"
    can_rescore = False

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or DATA)

    # -- arms ---------------------------------------------------------------------------
    @lru_cache(maxsize=1)
    def _index(self) -> Dict[str, List[Path]]:
        """{arm id: [run dirs]}, from every runs* directory and runs-judged/<scorer>/."""
        out: Dict[str, List[Path]] = {}
        bases = [p for p in sorted(self.data_dir.glob("runs*")) if p.is_dir() and p.name != "runs-judged"]
        bases += sorted(p for p in (self.data_dir / "runs-judged").glob("*") if p.is_dir())
        for base in bases:
            for d in sorted(base.iterdir()):
                m = _json(d / "metrics.json") if d.is_dir() else None
                if not isinstance(m, dict) or not m.get("config_id") or not m.get("dataset_id"):
                    continue
                rel = base.relative_to(self.data_dir).as_posix()
                out.setdefault(f"{rel}/{m['dataset_id']}/{m['config_id']}", []).append(d)
        return out

    def arms(self) -> List[str]:
        return list(self._index())

    def arms_of(self, path: str) -> List[str]:
        path = path.strip("/")
        if path in self._index():
            return [path]
        # a run directory selects the arm it belongs to
        return [a for a, ds in self._index().items()
                if any(d.relative_to(self.data_dir).as_posix() == path for d in ds)]

    def _dirs(self, arm: str) -> List[Path]:
        return self._index().get(arm, [])

    def _metrics(self, arm: str) -> dict:
        ds = self._dirs(arm)
        return (_json(ds[-1] / "metrics.json") or {}) if ds else {}

    def describe(self, arm: str) -> dict:
        base, _, rest = arm.rpartition("/")
        runs_dir, _, dataset = base.rpartition("/")
        m = self._metrics(arm)
        n = len(self._dirs(arm))
        label = rest + ("" if runs_dir == "runs" else f" · {runs_dir.removeprefix('runs-')}")
        label += f" ×{n}" if n > 1 else ""
        judged = (m.get("judged_with") or {}).get("scorer_id")
        primary = m.get("primary_metric") or ""
        if judged:  # a judged run's headline is the judge's score, not the source run's metric
            keys = set(self.scores(arm))
            primary = next((k for k in ("judge_score", "judge_score_unvalidated") if k in keys), primary)
        return {"id": arm, "label": label, "dataset": dataset, "task": judged or primary,
                "primary": primary, "runs": n, "goal": m.get("goal", ""), "format": m.get("format", ""),
                "reference": ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id", "")}

    # -- scores -------------------------------------------------------------------------
    def scores(self, arm: str, rescore: bool = False) -> Dict[str, dict]:
        acc: Dict[str, Dict[str, list]] = {}
        for d in self._dirs(arm):
            for r in _rows(d / "predictions.jsonl"):
                if "item_id" not in r:
                    continue
                for k, v in _numeric(r).items():
                    acc.setdefault(k, {}).setdefault(r["item_id"], []).append(v)
        n = len(self._dirs(arm))
        src = "predictions.jsonl" + (f" (mean of {n} repeats)" if n > 1 else "")
        return {k: {"source": src, "values": {i: statistics.fmean(v) for i, v in items.items()}}
                for k, items in acc.items()}

    @property
    def preferred_metrics(self) -> tuple:
        """Every arm's primary metric, most common first: the inspector's default yardstick."""
        from collections import Counter
        c = Counter((_json(ds[-1] / "metrics.json") or {}).get("primary_metric") for ds in self._index().values())
        return tuple(k for k, _ in c.most_common() if k)

    def recorded_means(self, arm: str) -> Dict[str, float]:
        if any((d / "predictions.jsonl").is_file() for d in self._dirs(arm)):
            return {}
        return _numeric(self._metrics(arm).get("scores") or {})

    def input_hashes(self, arm: str) -> Dict[str, str]:
        return {}  # the dataset's per-item sha256 is the input, for every arm alike

    def notes(self, arm: str) -> List[str]:
        return []

    def lower_is_better(self, metric: str) -> bool:
        return lower_is_better(metric)

    @lru_cache(maxsize=None)
    def _descriptive(self) -> frozenset:
        kinds = set()
        for ds in self._index().values():
            m = _json(ds[-1] / "metrics.json") or {}
            kinds |= {k for k, v in (m.get("metric_kinds") or {}).items() if v == "descriptive"}
        return frozenset(kinds)

    def is_neutral(self, metric: str) -> bool:
        return is_descriptive(metric) or metric in self._descriptive()

    @property
    def shape_metrics(self) -> tuple:
        """Latency and the output's size (descriptive kinds measured in words or characters):
        the inspector's scatter axes, never a default yardstick."""
        size = sorted(k for k in self._descriptive() if "words" in k or "chars" in k)
        return ("latency_ms", *size)

    # -- references and outputs -----------------------------------------------------------
    @lru_cache(maxsize=1)
    def references(self) -> List[dict]:
        out = []
        for tier in ("gold", "silver"):
            for d in sorted((self.data_dir / "references" / tier).glob("*")):
                if d.is_dir() and any(d.glob("*.txt")):
                    out.append({"id": f"{tier}/{d.name}", "tier": tier, "dataset": d.name,
                                "task": "", "archived": False, "format": "", "dir": d})
        return out

    def reference_format(self, ref: str) -> str:
        return ""

    def reference_archived(self, ref: str) -> bool:
        return False

    def output_format(self, arm: str) -> dict:
        fmt = self._metrics(arm).get("format", "")
        return {"asked": fmt, "got": "", "how": "config" if fmt else ""}

    def item_view(self, arm: str, item: str) -> dict:
        for d in reversed(self._dirs(arm)):  # the latest repeat
            f = d / "outputs" / f"{item}.txt"
            if f.is_file():
                return {"kind": "text", "text": f.read_text(encoding="utf-8", errors="replace"),
                        "info": {"run": d.name}}
        return {"kind": "none", "note": "No stored output for this item (outputs/<item_id>.txt)."}

    def reference_view(self, ref: str, item: str) -> dict:
        r = next((x for x in self.references() if x["id"] == ref), None)
        f = r["dir"] / f"{item}.txt" if r else None
        if f and f.is_file():
            return {"kind": "text", "text": f.read_text(encoding="utf-8", errors="replace")}
        return {"kind": "none"}


    # -- goals --------------------------------------------------------------------------
    @lru_cache(maxsize=1)
    def goals(self) -> List[dict]:
        import yaml

        out = []
        for f in sorted((self.data_dir / "goals").glob("*.yaml")):
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) if f.name != "policy.yaml" else None
            if isinstance(doc, dict):
                out.append(dict(doc, goal_id=doc.get("goal_id") or f.stem))
        return out

    def goal_of(self, arm: str) -> str:
        return self._metrics(arm).get("goal", "")

    # -- item fields (ADR-0003) -----------------------------------------------------------
    @lru_cache(maxsize=None)
    def item_fields(self, dataset: str) -> dict:
        import yaml

        ds = _json(self.data_dir / "datasets" / f"{dataset}.json") or {}
        f = self.data_dir / "fields" / f"{ds.get('fieldset', '')}.yaml"
        fs = yaml.safe_load(f.read_text(encoding="utf-8")) if ds.get("fieldset") and f.is_file() else None
        return {"fieldset": fs if isinstance(fs, dict) else None,
                "values": {it["item_id"]: it.get("fields") or {} for it in ds.get("items") or []}}


def load_adapter(spec: Optional[str] = None) -> Adapter:
    """`path/to/file.py:Class` or `module:Class`, relative to the project root; else the
    project's config.yaml `catalog.adapter`; else HarnessAdapter."""
    if not spec:
        cfg = ROOT / "config.yaml"
        if cfg.is_file():
            import yaml
            spec = ((yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}).get("catalog") or {}).get("adapter")
    if not spec:
        return HarnessAdapter()
    target, _, cls = spec.rpartition(":")
    if not target or not cls:
        raise SystemExit(f"catalog adapter {spec!r}: expected 'path/to/file.py:Class' or 'module:Class'")
    if target.endswith(".py"):
        path = (ROOT / target).resolve()
        sys.path.insert(0, str(ROOT))
        mod_spec = importlib.util.spec_from_file_location(path.stem, path)
        if mod_spec is None or mod_spec.loader is None:
            raise SystemExit(f"catalog adapter: cannot load {path}")
        mod = importlib.util.module_from_spec(mod_spec)
        sys.modules[path.stem] = mod
        mod_spec.loader.exec_module(mod)
    else:
        sys.path.insert(0, str(ROOT))
        mod = importlib.import_module(target)
    return getattr(mod, cls)()
