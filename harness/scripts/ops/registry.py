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
    the inputs (and `by`, for a write), loaded only when called; `text` how the command prints its answer; `output`,
    when declared, the result's JSON Schema, which the API's description gives as the 200's."""

    name: str
    kind: str
    about: str
    method: str
    route: str
    run: str
    text: str
    inputs: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    output: dict[str, Any] = field(default_factory=dict)

    def path_params(self) -> list[str]:
        """The parts of the route the call names, in order."""
        return [p[1:-1] for p in self.route.split("/") if p.startswith("{") and p.endswith("}")]

    def call(self, **kwargs: Any) -> dict[str, Any]:
        """Run it. A read in CACHED_READS is answered from what the view cache kept of it, when the data is what it was
        computed from and the views read the harness's own layout."""
        from evaluation_harness import catalog_adapter  # noqa: PLC0415
        from evaluation_harness.model import view_cache  # noqa: PLC0415

        # Whatever a view kept is looked at against the data, once, before it is used.
        with view_cache.operation():
            if self.name in CACHED_READS and catalog_adapter.harness_own():
                return view_cache.result(self.name, kwargs, lambda: _load(self.run)(**kwargs))
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


#: The reads whose answers the view cache keeps (model/view_cache.result): the views computed from every arm's scores
#: and the listings of the data's records, ~0.1 to 2.5 s a call, which read nothing but the project's data/ and today's
#: date. A read not named here is computed every time; a new one is named only with a test that its answer is the same
#: with and without the cache (tests/test_view_cache_views.py).
CACHED_READS = frozenset({
    "overview-show", "arm-list", "dataset-arm-list", "goal-leaderboard", "metric-list", "activity-show", "dataset-list",
    "dataset-show",
})  # fmt: skip


def _load(dotted: str) -> Callable[..., Any]:
    mod, _, fn = dotted.partition(":")
    return getattr(importlib.import_module(mod), fn)


def _all() -> dict[str, Op]:
    from evaluation_harness.ops import (  # noqa: PLC0415
        datasets,
        goals,
        models,
        prompts,
        rounds,
        scorers,
        studies,
        systems,
        views,
    )

    out: dict[str, Op] = {}
    for op in (
        *datasets.OPS,
        *goals.OPS,
        *models.OPS,
        *rounds.OPS,
        *scorers.OPS,
        *views.OPS,
        *studies.OPS,
        *systems.OPS,
        *prompts.OPS,
    ):
        if op.kind not in KINDS:
            raise ValueError(f"{op.name}: kind {op.kind!r} is not one of {KINDS}")
        if op.name in out:
            raise ValueError(f"{op.name}: declared twice")
        out[op.name] = op
    return out


OPS: dict[str, Op] = _all()
if bad := sorted(n for n in CACHED_READS if n not in OPS or OPS[n].kind != "read"):
    raise ValueError(f"CACHED_READS names operations that are not reads: {', '.join(bad)}")


def get(name: str) -> Op | None:
    """The operation of a command, or None."""
    return OPS.get(name)


def of_kind(*kinds: str) -> list[Op]:
    """The operations of these kinds."""
    return [op for op in OPS.values() if op.kind in kinds]
