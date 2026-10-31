"""Model records (RFC-020), optional: data/models/<model_id>.yaml, one file per model the project uses.

A record says what a model is (its aliases: the ids runs record for it), its deployments (each place and
build it runs, with its own onboarding), what it can do and the settings chosen for it. A project that keeps none has none of
this; `facts()` is then empty, as `data/models.yaml` was before the records replaced it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def records_dir(data_dir: Path) -> Path:
    return data_dir / "models"


def load(data_dir: Path) -> list[dict[str, Any]]:
    """Every record under data_dir/models/, sorted by id; a file that is not a mapping is skipped."""
    base = records_dir(data_dir)
    if yaml is None or not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            out.append(doc)
    return out


def by_alias(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Each alias a run may record (params.model), to its record."""
    return {a: r for r in load(data_dir) for a in r.get("aliases") or []}


def find(data_dir: Path, model_id: str) -> dict[str, Any] | None:
    f = records_dir(data_dir) / f"{model_id}.yaml"
    if yaml is None or not f.is_file():
        return None
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else None


def facts(data_dir: Path) -> dict[str, dict[str, str]]:
    """{alias: {weights, licence}} for the arms page's open / proprietary filter: the records that say."""
    out = {}
    for alias, rec in by_alias(data_dir).items():
        if rec.get("weights"):
            out[alias] = {k: rec[k] for k in ("weights", "licence") if rec.get(k)}
    return out


def deployment_of(rec: dict[str, Any], deployment_id: str) -> dict[str, Any] | None:
    """The record's deployment with this id, or None."""
    return next((d for d in rec.get("deployments") or [] if d.get("id") == deployment_id), None)


def resolve(cfg: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    """A config with the model record it names (`model_record: <id>`) applied: the record's settings
    under the config's own params (the config wins), `model` from the record's first alias when the config
    gives none, and `model_record` kept so the run records which record it ran with. `deployment: <id>`
    (kept too) names one of the record's deployments. A config naming no record is returned as it is; one
    naming a record or deployment that does not exist, or a deployment without a record, raises ValueError."""
    rid = cfg.get("model_record")
    if not rid:
        if cfg.get("deployment"):
            raise ValueError(f"deployment {cfg['deployment']!r} names no model_record")
        return cfg
    rec = find(data_dir, rid)
    if rec is None:
        raise ValueError(f"model_record {rid!r}: no {records_dir(data_dir) / (rid + '.yaml')}")
    if cfg.get("deployment") and deployment_of(rec, cfg["deployment"]) is None:
        known = ", ".join(d.get("id", "?") for d in rec.get("deployments") or []) or "none"
        raise ValueError(f"deployment {cfg['deployment']!r}: {rid} has no such deployment (known: {known})")
    params = {**(rec.get("settings") or {}), **(cfg.get("params") or {})}
    if "model" not in params and rec.get("aliases"):
        params["model"] = rec["aliases"][0]
    return {**cfg, "params": params}


def problems(data_dir: Path) -> list[str]:
    """What a record set gets wrong beyond its schema: a file named other than its id, an alias two records
    claim, a deployment id used twice in one record."""
    out = []
    seen: dict[str, str] = {}
    base = records_dir(data_dir)
    for f in sorted(base.glob("*.yaml")) if base.is_dir() else []:
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) if yaml else None
        if not isinstance(doc, dict):
            out.append(f"{f.name}: not a mapping")
            continue
        if doc.get("model_id") != f.stem:
            out.append(f"{f.name}: model_id {doc.get('model_id')!r} is not the file's name")
        for a in doc.get("aliases") or []:
            if a in seen and seen[a] != f.stem:
                out.append(f"alias {a!r} is claimed by {seen[a]} and {f.stem}")
            seen.setdefault(a, f.stem)
        ids = [d.get("id") for d in doc.get("deployments") or []]
        for dep in sorted({i for i in ids if ids.count(i) > 1}, key=str):
            out.append(f"{f.name}: deployment id {dep!r} is used more than once")
    return out
