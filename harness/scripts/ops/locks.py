"""What a job holds (RFC-026 step 3, RFC-032 step 9 P3): the locks of a decision or a work operation, from its declaration
(`Op.locks`, `Op.locks_fn`) and the inputs of the call. The keys are the lock files' names (`.build/locks/<key>.lock`):
shared to read, exclusive to write, taken in key order by the job's supervisor. `project` is held by every job, shared; a
migration holds it exclusive, so each waits for the other."""

from __future__ import annotations

import string
from typing import Any

from evaluation_harness.ops.registry import Op, _load

PROJECT = "project"


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def fields(template: str) -> list[str]:
    """The inputs a lock template names (`"system:{system}"`: system)."""
    return [name for _lit, name, _spec, _conv in string.Formatter().parse(template) if name]


def locks_for(op: Op, inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """(key, exclusive) of a job of `op` with these inputs, `project` included, sorted by key. A template whose input
    the call does not give is left out (a first value stands for a list of them)."""
    if op.locks == PROJECT:
        return [(PROJECT, True)]
    out: dict[str, bool] = {PROJECT: False}
    for template, exclusive in op.locks or ():
        given = {n: _first(inputs.get(n)) for n in fields(template)}
        if any(v in (None, "") for v in given.values()):
            continue
        key = template.format(**given)
        out[key] = out.get(key, False) or bool(exclusive)
    if op.locks_fn:
        for key, exclusive in _load(op.locks_fn)(inputs):
            out[key] = out.get(key, False) or bool(exclusive)
    return sorted(out.items())
