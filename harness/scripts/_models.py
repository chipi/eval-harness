"""Model records (RFC-020) and their deployments (RFC-032 step 2), optional.

A model is data/models/<model_id>.yaml: what it is (its aliases: the ids runs record for it), what it can do and the
settings chosen for it. Each place and build it runs is a deployment, a record of its own,
data/deployments/<model_id>/<deployment_id>.yaml, with the dated history of its checks: each onboarding run, each arm
smoke, each approval, never overwritten.

`find` and `load` give a model as the commands read it: with its deployments, each with its latest onboarding, and its
arms' latest smokes (`smokes`, by system id), worked out from the checks. A project that keeps no records has none of
this; `facts()` is then empty.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from collections.abc import Callable
from pathlib import Path
from typing import Any

from evaluation_harness import _store

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

#: What a deployment record holds that the joined view leaves out (the view names it `id`, its latest onboarding
#: `onboarding`).
_OWN = ("model_id", "deployment_id", "order", "checks")


def records_dir(data_dir: Path) -> Path:
    """Where a project's model records live: data_dir/models/."""
    return data_dir / "models"


def deployments_dir(data_dir: Path, model_id: str | None = None) -> Path:
    """Where the deployments live: data_dir/deployments/, or one model's."""
    base = data_dir / "deployments"
    return base / model_id if model_id else base


def _read(f: Path) -> dict[str, Any] | None:
    doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) if yaml else None
    return doc if isinstance(doc, dict) else None


def deployments(data_dir: Path, model_id: str) -> list[dict[str, Any]]:
    """A model's deployment records, as stored, by id."""
    base = deployments_dir(data_dir, model_id)
    if not _store.is_dir(base):
        return []
    found = [d for f in sorted(_store.glob(base, "*.yaml")) if (d := _read(f)) is not None]
    return sorted(found, key=lambda d: (d.get("order", len(found)), str(d.get("deployment_id"))))


def latest(checks: list[dict[str, Any]], kind: str, system: str | None = None) -> dict[str, Any] | None:
    """The last check of a kind (of one system, for a smoke), without its kind, system and dataset."""
    hit = [c for c in checks or [] if c.get("kind") == kind and (system is None or c.get("system") == system)]
    if not hit:
        return None
    return {k: v for k, v in hit[-1].items() if k not in ("kind", "system", "dataset")}


def joined(rec: dict[str, Any], deps: list[dict[str, Any]]) -> dict[str, Any]:
    """A model with its deployments as the commands read them: each with its id and latest onboarding; the arms'
    latest smokes by system id."""
    out = dict(rec)
    view, smokes = [], {}
    for d in deps:
        v = {"id": d.get("deployment_id"), **{k: x for k, x in d.items() if k not in _OWN}}
        if (on := latest(d.get("checks") or [], "onboarding")) is not None:
            v["onboarding"] = on
        view.append(v)
        for cid in dict.fromkeys(c.get("system") for c in d.get("checks") or [] if c.get("kind") == "smoke"):
            smokes[cid] = latest(d["checks"], "smoke", cid)
    if view:
        out["deployments"] = view
    if smokes:
        out["smokes"] = smokes
    return out


def load(data_dir: Path) -> list[dict[str, Any]]:
    """Every model, with its deployments, sorted by id; a file that is not a mapping is skipped."""
    from evaluation_harness import _format  # noqa: PLC0415

    base = records_dir(data_dir)
    if yaml is None or not _store.is_dir(base):
        return []
    _format.require(data_dir)
    out = []
    for f in sorted(_store.glob(base, "*.yaml")):
        doc = _read(f)
        if doc is not None:
            out.append(joined(doc, deployments(data_dir, str(doc.get("model_id") or f.stem))))
    return out


def by_alias(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Each alias a run may record (params.model), to its record."""
    return {a: r for r in load(data_dir) for a in r.get("aliases") or []}


def lock_path(record: Path) -> Path:
    """The lock a record is written under: keyed by the record's own path, not the model's id, so two projects
    with a model of one name never wait on each other (ADR-0024)."""
    import hashlib  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    key = hashlib.sha256(str(record.resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"evh-model-{key}.lock"


def _locked_write(
    f: Path, change: Callable[[dict[str, Any]], None], start: dict[str, Any], stamp: bool = True
) -> dict[str, Any]:
    """Apply `change` to the record as it is on disk NOW, under its lock, and write it: two commands writing one
    record (model-onboard on two machines, two arm-smokes) each keep their own change. Read at the start and written
    at the end, the slower one wrote back the whole record it had read and the other's result was lost. `stamp`: the
    record names who changed it last (a model record); a deployment's checks each name who made them instead."""
    import fcntl  # noqa: PLC0415

    from evaluation_harness import _common  # noqa: PLC0415
    from evaluation_harness._actor import actor  # noqa: PLC0415

    with _store.open_file(lock_path(f), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            doc = (_read(f) if _store.is_file(f) else None) or dict(start)
            change(doc)
            if stamp:
                doc["actor"] = actor()  # who changed the record last (RFC-027)
            _store.mkdir(f.parent, parents=True, exist_ok=True)
            _common.write_text_atomic(f, yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    return doc


def update_record(data_dir: Path, model_id: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Change a model's own record (its capabilities, history, versions), under its lock. Its deployments and their
    checks are records of their own (`update_deployment`, `add_check`): a change that puts them back is refused."""

    def guarded(doc: dict[str, Any]) -> None:
        change(doc)
        back = [k for k in ("deployments", "smokes") if k in doc]
        if back:
            raise ValueError(
                f"{model_id}: {', '.join(back)} are records of their own (deployments/{model_id}/)"
            )

    return _locked_write(records_dir(data_dir) / f"{model_id}.yaml", guarded, {"model_id": model_id})


def update_deployment(
    data_dir: Path,
    model_id: str,
    deployment_id: str,
    change: Callable[[dict[str, Any]], None],
    where: str = "local",
) -> dict[str, Any]:
    """Change a deployment's record under its lock; one that does not exist yet is made (`where` it runs)."""
    f = deployments_dir(data_dir, model_id) / f"{deployment_id}.yaml"
    start = {
        "model_id": model_id,
        "deployment_id": deployment_id,
        "order": len(deployments(data_dir, model_id)),
        "where": where,
    }
    return _locked_write(f, change, start, stamp=False)


def check_by() -> str:
    """This process's actor as a check's `by`: person:NAME, or agent:NAME for person:NAME."""
    from evaluation_harness._actor import actor  # noqa: PLC0415

    a = actor()
    return f"{a['type']}:{a['name']}" + (f" for person:{a['for']}" if a.get("for") else "")


def add_check(data_dir: Path, model_id: str, deployment_id: str, check: dict[str, Any]) -> dict[str, Any]:
    """Add a check (an onboarding run, an arm smoke, an approval) to a deployment's history: kept, never replaced."""
    if check.get("kind") not in ("onboarding", "smoke", "approval") or not check.get("at"):
        raise ValueError(f"a check has a kind (onboarding, smoke, approval) and a time: {check}")
    check = {**check, "by": check.get("by") or check_by()}
    return update_deployment(
        data_dir, model_id, deployment_id, lambda d: d.setdefault("checks", []).append(check)
    )


def split_accepted(
    rec: dict[str, Any] | None, flags: list[str], deployment: str | None = None
) -> tuple[list[str], list[str]]:
    """(flags still to look at, flags accepted): a flag whose kind (the words before its colon, "reasoning",
    "where it ran") the record's `accepted` names, or the named deployment's, is a known property a person
    accepted, with why: of the model (gpt-oss cannot stop reasoning) or of one deployment (a hosted gateway has no
    build to pin, and its repeats vary). Accepted flags are reported, never hidden."""
    dep = deployment_of(rec or {}, deployment) if deployment else None
    kinds = set((rec or {}).get("accepted") or {}) | set((dep or {}).get("accepted") or {})
    left = [f for f in flags if f.split(":", 1)[0] not in kinds]
    return left, [f for f in flags if f.split(":", 1)[0] in kinds]


def find(data_dir: Path, model_id: str) -> dict[str, Any] | None:
    """The model with this id, with its deployments, or None when there is none."""
    from evaluation_harness import _format  # noqa: PLC0415

    f = records_dir(data_dir) / f"{model_id}.yaml"
    if yaml is None or not _store.is_file(f):
        return None
    _format.require(data_dir)
    doc = _read(f)
    return joined(doc, deployments(data_dir, model_id)) if doc is not None else None


def facts(data_dir: Path) -> dict[str, dict[str, str]]:
    """{alias: {weights, licence}} for the arms page's open / proprietary filter: the records that say."""
    out = {}
    for alias, rec in by_alias(data_dir).items():
        if rec.get("weights"):
            out[alias] = {k: rec[k] for k in ("weights", "licence") if rec.get(k)}
    return out


def deployment_of(rec: dict[str, Any], deployment_id: str) -> dict[str, Any] | None:
    """The model's deployment with this id (as `find` gives it), or None."""
    return next((d for d in rec.get("deployments") or [] if d.get("id") == deployment_id), None)


def resolve(cfg: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    """A system with the model record it names (`model_record: <id>`) applied: the record's settings
    under the system's own params (the system wins), `model` from the record's first alias when the system
    gives none, and `model_record` kept so the run records which record it ran with. `deployment: <id>`
    (kept too) names one of the record's deployments. A system naming no record is returned as it is; one
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
    """What the records get wrong beyond their schemas: a file named other than its id, an alias two records claim,
    a deployment under a folder its model_id does not name or of no model, a code record's version listed twice."""
    out = []
    seen: dict[str, str] = {}
    base = records_dir(data_dir)
    models = set()
    for f in sorted(_store.glob(base, "*.yaml")) if _store.is_dir(base) else []:
        doc = _read(f)
        if doc is None:
            out.append(f"{f.name}: not a mapping")
            continue
        models.add(f.stem)
        if doc.get("model_id") != f.stem:
            out.append(f"{f.name}: model_id {doc.get('model_id')!r} is not the file's name")
        for a in doc.get("aliases") or []:
            if a in seen and seen[a] != f.stem:
                out.append(f"alias {a!r} is claimed by {seen[a]} and {f.stem}")
            seen.setdefault(a, f.stem)
        commits = [v.get("commit") for v in doc.get("versions") or [] if isinstance(v, dict)]
        for c in sorted({c for c in commits if commits.count(c) > 1}, key=str):
            out.append(f"{f.name}: version {c!r} is listed more than once")
        if doc.get("kind") == "code":
            # A replay runs each item at the version deployed then (RFC-030): no two versions at one moment.
            from evaluation_harness import _coderec  # noqa: PLC0415

            out += [f"{f.name}: {x}" for x in _coderec.periods(doc)[1]]
    dbase = deployments_dir(data_dir)
    for f in sorted(_store.glob(dbase, "*/*.yaml")) if _store.is_dir(dbase) else []:
        rel = f"deployments/{f.parent.name}/{f.name}"
        doc = _read(f)
        if doc is None:
            out.append(f"{rel}: not a mapping")
            continue
        if f.parent.name not in models:
            out.append(f"{rel}: no model {f.parent.name!r} (models/{f.parent.name}.yaml)")
        if doc.get("model_id") != f.parent.name or doc.get("deployment_id") != f.stem:
            out.append(f"{rel}: model_id and deployment_id must be its folder's and its file's names")
    return out
