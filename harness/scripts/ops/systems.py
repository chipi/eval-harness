"""The systems' operations (RFC-032 step 3): `evh system-*`, and the resources under /api/v1/systems."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_SET = {
    "type": "object",
    "description": "fields to set, by dotted key; the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}
_S = "evaluation_harness.ops.systems"

OPS = (
    Op("system-list", "read", "every system: its adapter, the model it runs and where its file is", "GET", "/systems",
       f"{_S}:list_systems", f"{_S}:say_list"),
    Op("system-show", "read", "one system: its settings and the model it runs", "GET", "/systems/{system}",
       f"{_S}:show_system", f"{_S}:say_system"),
    Op("system-new", "edit", "make a system (data/systems/<id>.yaml), checked against its schema", "POST",
       "/systems/{system}", f"{_S}:new_system", f"{_S}:say_saved", inputs={"set": _SET}, required=("set",)),
    Op("system-set", "edit", "change a system's settings, checked; its comments kept", "PATCH", "/systems/{system}",
       f"{_S}:set_system", f"{_S}:say_saved", inputs={"set": _SET, "unset": _UNSET}),
)  # fmt: skip


def list_systems() -> dict[str, Any]:
    """Every system with what it runs."""
    from evaluation_harness.model.systems import SYSTEM, where  # noqa: PLC0415

    return {
        "systems": [
            {
                "system": s.get("system_id"),
                "adapter": s.get("adapter"),
                "model": s.get("model_record") or (s.get("params") or {}).get("model"),
                "deployment": s.get("deployment"),
                "file": where(str(s.get("system_id"))),
            }
            for s in SYSTEM.all()
        ]
    }


def show_system(system: str) -> dict[str, Any]:
    """The system's record and where its file is."""
    from evaluation_harness.model.systems import SYSTEM, where  # noqa: PLC0415

    return {"system": system, "record": SYSTEM.get(system), "file": where(system)}


def new_system(system: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the system from its fields."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

    return SYSTEM.save(
        system, _settings_form.set_values({"system_id": system}, list(set.items()), []), by, new=True
    )


def set_system(
    system: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Change the system's fields."""
    from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

    return SYSTEM.patch(system, list((set or {}).items()), list(unset or []), by)


def say_saved(r: dict[str, Any]) -> str:
    """A save's answer as text."""
    return f"{r['id']}: {'saved' if r['changed'] else 'unchanged (nothing to save)'}"


def say_list(r: dict[str, Any]) -> str:
    """system-list's answer as text: one system a line."""
    rows = r["systems"]
    if not rows:
        return (
            "no systems yet: evh system-new <id> --set params.provider=<provider> --set params.model=<model>"
        )
    w = max(len(str(s["system"])) for s in rows)
    return "\n".join(
        f"{s['system']:<{w}}  {s.get('model') or '':<28} {s.get('deployment') or '':<10} {s['file']}"
        for s in rows
    )


def say_system(r: dict[str, Any]) -> str:
    """system-show's answer as text: its settings, one a line."""
    rec = r["record"]
    lines = [f"{r['system']}  ({r['file']})"]
    for k in ("adapter", "model_record", "deployment"):
        if rec.get(k):
            lines.append(f"  {k:<13} {rec[k]}")
    for k, v in sorted((rec.get("params") or {}).items()):
        lines.append(f"  params.{k} = {v}")
    return "\n".join(lines)
