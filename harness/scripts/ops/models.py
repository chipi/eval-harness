"""The model's and its deployments' operations (RFC-032 step 2): `evh model-*`, `evh deployment-*`, and the resources
under /api/v1/models. Onboarding a deployment is `evh model-onboard`, a job of its own until work moves onto the model
(step 4)."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_SET = {
    "type": "object",
    "description": "fields to set, by dotted key; the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}
_M = "evaluation_harness.ops.models"

OPS = (
    Op("model-list", "read", "every model: its kind, weights, deployments and state (vetted, onboarded, check, none)",
       "GET", "/models", f"{_M}:list_models", f"{_M}:say_list"),
    Op("model-show", "read", "one model and its deployments, each with its state", "GET", "/models/{model}",
       f"{_M}:show_model", f"{_M}:say_model"),
    Op("model-new", "edit", "make a model record, checked against its schema", "POST", "/models/{model}",
       f"{_M}:new_model", f"{_M}:say_saved", inputs={"set": _SET}, required=("set",)),
    Op("model-set", "edit", "change a model's fields, checked; its comments kept", "PATCH", "/models/{model}",
       f"{_M}:set_model", f"{_M}:say_saved", inputs={"set": _SET, "unset": _UNSET}),
    Op("deployment-show", "read", "one deployment: where it runs, its checks and its state", "GET",
       "/models/{model}/deployments/{deployment}", f"{_M}:show_deployment", f"{_M}:say_deployment"),
    Op("deployment-history", "read", "a deployment's saves, newest first: when, by whom, what it was", "GET",
       "/models/{model}/deployments/{deployment}/history", f"{_M}:deployment_history", f"{_M}:say_history"),
    Op("deployment-new", "edit", "make a deployment of a model (where it runs, its endpoint), checked", "POST",
       "/models/{model}/deployments/{deployment}", f"{_M}:new_deployment", f"{_M}:say_saved",
       inputs={"set": _SET}, required=("set",)),
    Op("deployment-set", "edit", "change a deployment's fields (not its checks: they are its history)", "PATCH",
       "/models/{model}/deployments/{deployment}", f"{_M}:set_deployment", f"{_M}:say_saved",
       inputs={"set": _SET, "unset": _UNSET}),
    Op("deployment-accept", "decision", "accept a flag kind as this deployment's own nature, with why: kept in its checks",
       "POST", "/models/{model}/deployments/{deployment}/accept", f"{_M}:accept", f"{_M}:say_saved",
       inputs={"flag": {"type": "string", "description": "the flag, or its kind (the words before its colon)"},
               "why": {"type": "string", "description": "why it is this deployment's nature, a sentence"}},
       required=("flag", "why")),
)  # fmt: skip


def _no_checks(sets: dict[str, Any] | None, unsets: list[str] | None) -> None:
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    touched = [k for k in [*(sets or {}), *(unsets or [])] if k.split(".")[0] == "checks"]
    if touched:
        raise Problem(
            "a deployment's checks are its history: onboard it, smoke an arm, or accept a flag", "not-allowed"
        )


def list_models() -> dict[str, Any]:
    """Every model with its deployments' count and its state."""
    from evaluation_harness.model.models import DEPLOYMENT, MODEL, status  # noqa: PLC0415

    deps = DEPLOYMENT.ids()
    return {
        "models": [
            {
                "model": m.get("model_id"),
                "name": m.get("name"),
                "kind": m.get("kind"),
                "weights": m.get("weights"),
                "deployments": sum(1 for d in deps if d.split("/")[0] == m.get("model_id")),
                "state": status(str(m.get("model_id"))),
            }
            for m in MODEL.all()
        ]
    }


def show_model(model: str) -> dict[str, Any]:
    """The model's record and each deployment's record with its state."""
    from evaluation_harness.model.models import DEPLOYMENT, MODEL, deployment_state, status  # noqa: PLC0415

    rec = MODEL.get(model)
    deps = [d for d in DEPLOYMENT.ids() if d.split("/")[0] == model]
    return {
        "model": model,
        "record": rec,
        "state": status(model),
        "deployments": [
            {"deployment": d.split("/")[1], "record": DEPLOYMENT.get(d), "state": deployment_state(d)}
            for d in deps
        ],
    }


def new_model(model: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the model from its fields."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.models import MODEL  # noqa: PLC0415

    return MODEL.save(
        model, _settings_form.set_values({"model_id": model}, list(set.items()), []), by, new=True
    )


def set_model(
    model: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Change the model's fields."""
    from evaluation_harness.model.models import MODEL  # noqa: PLC0415

    return MODEL.patch(model, list((set or {}).items()), list(unset or []), by)


def show_deployment(model: str, deployment: str) -> dict[str, Any]:
    """The deployment's record and its state."""
    from evaluation_harness.model.models import DEPLOYMENT, deployment_state  # noqa: PLC0415

    rid = f"{model}/{deployment}"
    return {
        "model": model,
        "deployment": deployment,
        "record": DEPLOYMENT.get(rid),
        "state": deployment_state(rid),
    }


def deployment_history(model: str, deployment: str) -> dict[str, Any]:
    """The deployment's saves."""
    from evaluation_harness.model.models import DEPLOYMENT  # noqa: PLC0415

    rid = f"{model}/{deployment}"
    DEPLOYMENT.get(rid)
    return {"model": model, "deployment": deployment, "saves": DEPLOYMENT.history(rid)}


def new_deployment(model: str, deployment: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the deployment from its fields."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.models import DEPLOYMENT  # noqa: PLC0415

    _no_checks(set, None)
    rec = _settings_form.set_values({"model_id": model, "deployment_id": deployment}, list(set.items()), [])
    return DEPLOYMENT.save(f"{model}/{deployment}", rec, by, new=True)


def set_deployment(
    model: str, deployment: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Change the deployment's fields, never its checks."""
    from evaluation_harness.model.models import DEPLOYMENT  # noqa: PLC0415

    _no_checks(set, unset)
    return DEPLOYMENT.patch(f"{model}/{deployment}", list((set or {}).items()), list(unset or []), by)


def accept(model: str, deployment: str, flag: str, why: str, by: str) -> dict[str, Any]:
    """Accept a flag kind on the deployment, with why."""
    from evaluation_harness.model import models  # noqa: PLC0415

    return models.accept(f"{model}/{deployment}", flag, why, by)


def say_list(r: dict[str, Any]) -> str:
    """model-list's answer as text: one model a line."""
    rows = r["models"]
    if not rows:
        return "no model records yet: evh model-new <id> --set kind=llm --set aliases.0=<the id runs record>"
    w = max(len(str(m["model"])) for m in rows)
    return "\n".join(
        f"{m['model']:<{w}}  {m.get('kind') or '':<5} {m.get('weights') or '':<12} {m['deployments']} deployment(s)  {m['state']}"
        for m in rows
    )


def say_model(r: dict[str, Any]) -> str:
    """model-show's answer as text: the record's facts, then each deployment and its state."""
    rec = r["record"]
    lines = [
        f"{r['model']}: {rec.get('name') or ''} ({rec.get('kind')}, {rec.get('weights') or 'weights unknown'}) {r['state']}"
    ]
    for d in r["deployments"]:
        on = (d["state"]["onboarding"] or {}).get("status", "not onboarded")
        lines.append(
            f"  {d['deployment']:<14} {d['record'].get('where', '')}: onboarding {on}, {d['state']['checks']} check(s)"
        )
    if not r["deployments"]:
        lines.append("  no deployments: evh deployment-new <model> <id> --set where=...")
    return "\n".join(lines)


def say_deployment(r: dict[str, Any]) -> str:
    """deployment-show's answer as text."""
    rec, st = r["record"], r["state"]
    on = st["onboarding"]
    lines = [f"{r['model']}/{r['deployment']}: {rec.get('where', '')}"]
    lines.append(
        f"  onboarding  {on['status']} at {on['at']}" if on else "  onboarding  none yet: evh model-onboard"
    )
    for cid, s in st["smokes"].items():
        lines.append(f"  smoke       {cid}: {s['status']} at {s['at']}")
    for kind, why in st["accepted"].items():
        lines.append(f"  accepted    {kind}: {why}")
    return "\n".join(lines)


def say_history(r: dict[str, Any]) -> str:
    """deployment-history's answer as text."""
    if not r["saves"]:
        return f"{r['model']}/{r['deployment']}: no saves recorded (made by evh migrate or by hand)"
    return "\n".join(f"{s['at']}  {s['by']}  {'made' if s['was'] is None else 'changed'}" for s in r["saves"])


def say_saved(r: dict[str, Any]) -> str:
    """A save's answer as text."""
    return f"{r['id']}: {'saved' if r['changed'] else 'unchanged (nothing to save)'}"
