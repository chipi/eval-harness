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


def promote_locks(inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """A baseline's versions are written one at a time: `baselines:<goal or _dataset>/<dataset>`, the goal and dataset
    of the run promoted (or, for a rollback, named)."""
    from evaluation_harness.model import runs as model_runs  # noqa: PLC0415

    run = _first(inputs.get("run"))
    meta = (model_runs.run(run) or {}) if run else {}
    goal = None if inputs.get("no_goal") else (inputs.get("goal") or meta.get("goal"))
    dataset = meta.get("dataset_id") or _first(inputs.get("dataset"))
    return [(f"baselines:{goal or '_dataset'}/{dataset}", True)] if dataset else []


def split_locks(inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """A split writes two datasets beside the one it splits (and unsealing one opens them): all three, exclusive."""
    d = _first(inputs.get("dataset_id"))
    return [(f"dataset:{x}", True) for x in (d, f"{d}_validation", f"{d}_test")] if d else []


def run_dataset_locks(inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """What is made from a run is made on the run's own dataset: that dataset, exclusive."""
    from evaluation_harness.model import runs as model_runs  # noqa: PLC0415

    run = _first(inputs.get("run"))
    dataset = ((model_runs.run(run) or {}) if run else {}).get("dataset_id")
    return [(f"dataset:{dataset}", True)] if dataset else []
