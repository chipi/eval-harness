"""The operations, one registry (RFC-032): the source the command line, the API and the MCP tools are made from."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

KINDS = ("read", "edit", "decision", "work")
#: The kinds that run as jobs (P3): their route is a POST that answers 202 with the job.
JOB_KINDS = ("decision", "work")


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
    as positional words, after the route's parts (`evh search news summary`); `one_of`, inputs of which a call names at
    least one (`comparison-show`: runs or round), said in the schema so a caller knows before it calls; `exclusive`,
    groups of inputs of which a call names at most one.

    A decision or a work operation is a job (P3): `run` is its `body`, a function that prints and returns the exit code,
    `text` is empty, `printer` unused. Its route's parts are inputs too (required, named flags on the command line, never
    positionals): `parts` maps a part of the route to the input it fills (default: the input of the same name), `parts_fn`
    (dotted, taking the parts by name) builds the inputs of a part that is composite; a route's request body is the inputs
    the parts do not fill. `locks` are what the job holds: templates `("system:{system}", True)` (the key, exclusive or
    shared; an input the call does not give leaves its lock out), `"project"` for a migration (the whole project,
    exclusive), `()` for a job that writes nothing another job writes (the project, shared, which every job holds), and
    `locks_fn` (dotted, taking the inputs) for locks the inputs do not name by themselves; `locks` is None only until one
    is declared. `spends`: the job calls models, so a call carries `max_cost_usd`. `why`: the input a decision's reason
    is (it is required), empty for a decision with none. `resume`: (the input that names the run to continue, the input
    that names the run a job writes), for a job that can be resumed. An input says more in its schema: `x-ref: "system"`
    (a system of the project), `x-file: "upload"` (a file the call carries) or `"artifact"` (a file the job writes in its
    folder; `"no"`: it is named like a file and is not one), `pattern` (what a text may be), `x-short`, `x-flag`, `x-metavar` and `x-nargs: "+"` for the command line, `default`.
    `in_process`: a decision quick enough to answer in the server's process (RFC-032: "in-process when quick"), as an
    edit is: it is not a job, and none of the above applies to it (`deployment-accept`)."""

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
    one_of: tuple[str, ...] = ()
    exclusive: tuple[tuple[str, ...], ...] = ()
    locks: Any = None
    locks_fn: str = ""
    spends: bool = False
    why: str = ""
    resume: tuple[str, ...] = ()
    parts: dict[str, str] = field(default_factory=dict)
    parts_fn: str = ""
    in_process: bool = False

    def path_params(self) -> list[str]:
        """The parts of the route the call names, in order."""
        return [p[1:-1] for p in self.route.split("/") if p.startswith("{") and p.endswith("}")]

    def is_job(self) -> bool:
        """Whether it runs as a job: a work operation, or a decision that is not answered in the server's process."""
        return self.kind in JOB_KINDS and not self.in_process

    def part_inputs(self) -> dict[str, str]:
        """For a job: the input each part of the route fills."""
        return {p: self.parts.get(p, p) for p in self.path_params()}

    def route_inputs(self, parts: dict[str, str]) -> dict[str, Any]:
        """For a job: the inputs the route's parts give (`parts_fn` builds a composite one)."""
        if self.parts_fn:
            return dict(_load(self.parts_fn)(**parts))
        mapped = self.part_inputs()
        return {mapped[p]: v for p, v in parts.items()}

    def with_defaults(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """The inputs with every default the schema declares filled in, so a job's record holds the whole call."""
        return {**{k: s["default"] for k, s in self.inputs.items() if "default" in s}, **inputs}

    def call(self, **kwargs: Any) -> dict[str, Any]:
        """Run it. A read in CACHED_READS is answered from what the view cache kept of it, when the data is what it was
        computed from and the views read the harness's own layout."""
        from evaluation_harness import catalog_adapter  # noqa: PLC0415
        from evaluation_harness.model import view_cache  # noqa: PLC0415

        if self.is_job():
            raise ValueError(
                f"{self.name} is a {self.kind}: it runs as a job (`evh {self.name}`, or POST {self.route})"
            )
        # Whatever a view kept is looked at against the data, once, before it is used.
        with view_cache.operation():
            if self.name in CACHED_READS and catalog_adapter.harness_own():
                return view_cache.result(self.name, kwargs, lambda: _load(self.run)(**kwargs))
            return _load(self.run)(**kwargs)

    def body(self, **inputs: Any) -> int:
        """A job's body run in this process: it prints, and answers the command's exit code."""
        return int(_load(self.run)(**inputs) or 0)

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
        if self.is_job():
            hidden |= set(self.part_inputs().values())
        return self._schema(hidden)

    def job_schema(self) -> dict[str, Any]:
        """For a job: every input a call may give, the route's parts too, as the API takes it (a file is an upload)."""
        return self._schema(set(self.tool_hidden))

    def _schema(self, hidden: set[str]) -> dict[str, Any]:
        one_of = [k for k in self.one_of if k not in hidden]
        pairs = [
            {"not": {"required": [a, b]}}
            for group in self.exclusive
            for i, a in enumerate(group)
            for b in group[i + 1 :]
            if a not in hidden and b not in hidden
        ]
        return {
            "type": "object",
            "properties": {k: api_spec(v) for k, v in self.inputs.items() if k not in hidden},
            "required": [k for k in self.required if k not in hidden],
            **({"anyOf": [{"required": [k]} for k in one_of]} if one_of else {}),
            **({"allOf": pairs} if pairs else {}),
            "additionalProperties": False,
        }


#: What the API takes for an input that is a file the call carries (`x-file: "upload"`); the job is given its path.
UPLOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "a file the call carries (at most 50 MB in all)",
    "properties": {
        "name": {"type": "string", "description": "the file's name: letters, digits, '.', '_' or '-'"},
        "content_base64": {"type": "string", "description": "the file's bytes, base64"},
    },
    "required": ["name", "content_base64"],
    "additionalProperties": False,
}


def api_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """An input's schema as the API takes it: a file is an upload object."""
    if spec.get("x-file") != "upload":
        return spec
    one = {**UPLOAD_SCHEMA, **({"description": spec["description"]} if "description" in spec else {})}
    return {"type": "array", "items": one} if spec.get("type") == "array" else one


def input_problem(exc: Any) -> str:
    """A jsonschema ValidationError of a call's inputs in words: an unmet `one_of` names the inputs (jsonschema says
    only that the call 'is not valid under any of the given schemas')."""
    if exc.validator == "anyOf" and all(set(s) == {"required"} for s in exc.validator_value):
        return "one of " + ", ".join(k for s in exc.validator_value for k in s["required"]) + " is needed"
    return str(exc.message)


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
        charts,
        dataset_jobs,
        datasets,
        goals,
        inspect,
        models,
        project_jobs,
        prompts,
        records,
        records_work,
        reports,
        rounds,
        run_jobs,
        scorers,
        stats,
        studies,
        study_jobs,
        systems,
        views,
    )

    out: dict[str, Op] = {}
    for op in (
        *dataset_jobs.OPS,
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
        *project_jobs.OPS,
        *records.OPS,
        *records_work.OPS,
        *reports.OPS,
        *run_jobs.OPS,
        *study_jobs.OPS,
        *charts.OPS,
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
