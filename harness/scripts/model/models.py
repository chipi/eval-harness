"""The model and its deployments (RFC-032 step 2): data/models/<model_id>.yaml and
data/deployments/<model_id>/<deployment_id>.yaml, each a record of its own; a deployment's checks (onboarding runs, arm
smokes, accepted flags) are its dated history, added to and never written over."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
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


#: The onboarding status a record's chip and `evh models --status` name, by the status it records.
STATUS = {"pass": "vetted", "check": "check"}


def deployments_of(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """A record's deployments, skipping any entry that is not a mapping."""
    return [d for d in rec.get("deployments") or [] if isinstance(d, dict)]


def status_of(rec: dict[str, Any]) -> str:
    """vetted: every deployment's onboarding passed and an arm that names the record passed its smoke (`evh
    arm-smoke`, on the task's own items); onboarded: the probes passed and no arm has (the probe is one toy
    question: it registers a model, it does not vet it); check: an onboarding flagged something; none: no
    onboarding ran. An arm whose smoke flagged something says so on its own badge: that is the arm's settings,
    not the model."""
    seen = [STATUS.get((d.get("onboarding") or {}).get("status", ""), "none") for d in deployments_of(rec)]
    if "check" in seen:
        return "check"
    if seen and all(x == "vetted" for x in seen):
        smokes = [(x or {}).get("status") for x in (rec.get("smokes") or {}).values() if isinstance(x, dict)]
        return "vetted" if "pass" in smokes else "onboarded"
    return "none"


def status(model_id: str, data: Path | None = None) -> str:
    """A model's state as the catalog names it (ADR-0021): vetted, onboarded, check or none, from its deployments'
    latest onboarding and its arms' latest smokes."""
    from evaluation_harness import _models  # noqa: PLC0415

    rec = _models.find(_common.DATA if data is None else Path(data), model_id)
    return status_of(rec) if rec else "none"


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
