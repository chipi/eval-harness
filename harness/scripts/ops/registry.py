"""The operations, one registry (RFC-032): the source the command line, the API and the MCP tools are made from."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

KINDS = ("read", "edit", "decision", "work")


@dataclass(frozen=True)
class Op:
    """One operation: `name` is its command (`evh goal-show`); `route` its resource, `{goal}` a part of the path and a
    positional of the command; `inputs` the rest, as JSON Schema properties; `run` a dotted `module:function` taking
    the inputs (and `by`, for a write), loaded only when called; `text` how the command prints its answer."""

    name: str
    kind: str
    about: str
    method: str
    route: str
    run: str
    text: str
    inputs: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()

    def path_params(self) -> list[str]:
        """The parts of the route the call names, in order."""
        return [p[1:-1] for p in self.route.split("/") if p.startswith("{") and p.endswith("}")]

    def call(self, **kwargs: Any) -> dict[str, Any]:
        """Run it."""
        return _load(self.run)(**kwargs)

    def say(self, result: dict[str, Any]) -> str:
        """Its answer as the command prints it."""
        return _load(self.text)(result)

    def schema(self) -> dict[str, Any]:
        """Its inputs (not the route's parts) as one JSON Schema object."""
        return {
            "type": "object",
            "properties": self.inputs,
            "required": list(self.required),
            "additionalProperties": False,
        }


def _load(dotted: str) -> Callable[..., Any]:
    mod, _, fn = dotted.partition(":")
    return getattr(importlib.import_module(mod), fn)


def _all() -> dict[str, Op]:
    from evaluation_harness.ops import goals, models  # noqa: PLC0415

    out: dict[str, Op] = {}
    for op in (*goals.OPS, *models.OPS):
        if op.kind not in KINDS:
            raise ValueError(f"{op.name}: kind {op.kind!r} is not one of {KINDS}")
        if op.name in out:
            raise ValueError(f"{op.name}: declared twice")
        out[op.name] = op
    return out


OPS: dict[str, Op] = _all()


def get(name: str) -> Op | None:
    """The operation of a command, or None."""
    return OPS.get(name)


def of_kind(*kinds: str) -> list[Op]:
    """The operations of these kinds."""
    return [op for op in OPS.values() if op.kind in kinds]
