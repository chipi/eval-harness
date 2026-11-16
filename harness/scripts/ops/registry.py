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
    when declared, the result's JSON Schema, which the API's description gives as the 200's.

    `printer`, when given, is a dotted `module:function` taking the same inputs that prints the answer as the command
    always printed it (a view whose text is not made from its result, as a table fitted to the terminal): the command
    line uses it for the text answer, every other surface the result. `tool_hidden` names inputs only the command line
    takes (they read or run a file of this machine's); `public_hidden` inputs a public server does not take (they answer
    with an item's text, an output or a label, or how long a test runs); `public_dropped`, when set, why a public server
    does not offer the operation at all; `status`, a dotted `module:function` of the result giving the command's exit code
    when the answer is also a verdict (`validate`: 1 when it found a problem); `positional` names inputs the command takes
    as positional words, after the route's parts (`evh search news summary`)."""

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
    printer: str = ""
    tool_hidden: tuple[str, ...] = ()
    public_hidden: tuple[str, ...] = ()
    public_dropped: str = ""
    status: str = ""
    positional: tuple[str, ...] = ()

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

    def print_text(self, **kwargs: Any) -> int:
        """Print its answer as the command always printed it (its `printer`), from the inputs; the printer's own exit
        code, when it gives one."""
        return _load(self.printer)(**kwargs) or 0

    def exit_code(self, result: dict[str, Any]) -> int:
        """The command's exit code for this answer: 0, unless the operation says an answer is also a verdict."""
        return int(_load(self.status)(result)) if self.status else 0

    def schema(self, public: bool = False) -> dict[str, Any]:
        """Its inputs (not the route's parts) as one JSON Schema object: what the API and the MCP tools take, so not
        what only the command line takes (`tool_hidden`), nor, for a public server, `public_hidden`."""
        hidden = {*self.tool_hidden, *(self.public_hidden if public else ())}
        return {
            "type": "object",
            "properties": {k: v for k, v in self.inputs.items() if k not in hidden},
            "required": [k for k in self.required if k not in hidden],
            "additionalProperties": False,
        }


#: The reads whose answers the view cache keeps (model/view_cache.result): the views computed from every arm's scores
#: and the listings of the data's records, ~0.1 to 2.5 s a call, which read nothing but the project's data/ and today's
#: date. A read not named here is computed every time; a new one is named only with a test that its answer is the same
#: with and without the cache (tests/test_view_cache_views.py).
CACHED_READS = frozenset({
    "overview-show", "arm-list", "dataset-arm-list", "goal-leaderboard", "metric-list", "activity-show", "dataset-list",
    "dataset-show", "goal-list", "model-list", "reference-list", "leaderboard", "capture-list",
})  # fmt: skip


def _load(dotted: str) -> Callable[..., Any]:
    mod, _, fn = dotted.partition(":")
    return getattr(importlib.import_module(mod), fn)


def _all() -> dict[str, Op]:
    from evaluation_harness.ops import (  # noqa: PLC0415
        datasets,
        goals,
        inspect,
        models,
        prompts,
        records,
        rounds,
        scorers,
        stats,
        studies,
        systems,
        views,
    )

    out: dict[str, Op] = {}
    for op in (
        *datasets.OPS,
        *goals.OPS,
        *inspect.OPS,
        *models.OPS,
        *rounds.OPS,
        *scorers.OPS,
        *stats.OPS,
        *views.OPS,
        *studies.OPS,
        *systems.OPS,
        *prompts.OPS,
        *records.OPS,
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
