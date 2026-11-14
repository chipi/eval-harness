"""The model and its deployments (RFC-032 step 2): data/models/<model_id>.yaml and
data/deployments/<model_id>/<deployment_id>.yaml, each a record of its own; a deployment's checks (onboarding runs, arm
smokes, accepted flags) are its dated history, added to and never written over."""

from __future__ import annotations

import datetime as _dt
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.entity import Entity, Problem


def _deployment_links(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The model a deployment is of exists."""
    mid = record.get("model_id")
    if mid and not _store.is_file(_common.DATA / "models" / f"{mid}.yaml"):
        return [{"path": ["model_id"], "message": f"no model {mid!r} in this project"}]
    return []


MODEL = Entity(
    name="model", plural="models", folder="models", id_field="model_id", schema="model.schema.json"
)
DEPLOYMENT = Entity(
    name="deployment",
    plural="deployments",
    folder="deployments",
    id_field="deployment_id",
    schema="deployment.schema.json",
    parent_field="model_id",
    links=_deployment_links,
)


def status(model_id: str) -> str:
    """A model's state as the catalog names it (ADR-0021): vetted, onboarded, check or none, from its deployments'
    latest onboarding and its arms' latest smokes."""
    from evaluation_harness import _models, catalog_models  # noqa: PLC0415

    rec = _models.find(_common.DATA, model_id)
    return catalog_models.status_of(rec) if rec else "none"


def deployment_state(rid: str) -> dict[str, Any]:
    """A deployment's state from its checks: its latest onboarding, each arm's latest smoke, the flags accepted."""
    from evaluation_harness import _models  # noqa: PLC0415

    d = DEPLOYMENT.get(rid)
    checks = d.get("checks") or []
    arms = list(dict.fromkeys(c.get("system") for c in checks if c.get("kind") == "smoke"))
    return {
        "onboarding": _models.latest(checks, "onboarding"),
        "smokes": {cid: _models.latest(checks, "smoke", cid) for cid in arms},
        "accepted": d.get("accepted") or {},
        "checks": len(checks),
    }


def accept(rid: str, flag: str, why: str, by: str) -> dict[str, Any]:
    """Accept a flag kind as this deployment's own nature (a hosted gateway: no build to pin), with why: its
    `accepted`, and the decision kept in its checks with who made it."""
    if not why or len(why.split()) < 3:
        raise Problem("--why must be a sentence: why is this flag this deployment's nature?", "bad-argument")
    kind = flag.split(":", 1)[0].strip()
    if not kind:
        raise Problem(
            "--flag names the kind of flag (the words before its colon: reasoning, where it ran)",
            "bad-argument",
        )
    d = DEPLOYMENT.get(rid)
    when = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d["accepted"] = {**(d.get("accepted") or {}), kind: why}
    d["checks"] = [
        *(d.get("checks") or []),
        {"kind": "approval", "at": when, "accepted": [kind], "why": why, "by": by},
    ]
    return DEPLOYMENT.save(rid, d, by)
