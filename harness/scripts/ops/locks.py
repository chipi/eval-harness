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


def sweep_locks(inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """A sweep runs each of its systems on the dataset: each system exclusive, the dataset shared."""
    dataset = _first(inputs.get("dataset"))
    out: list[tuple[str, bool]] = []
    for system in inputs.get("systems") or []:
        out.append((f"system:{system}", True))
        if dataset:
            out.append((f"dataset:{dataset}", False))
    return out


def model_locks(inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """What runs a system writes the record of the model it runs (a smoke, an onboarding, a replay's faithfulness): that
    model, exclusive, from the system's own record."""
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415
    from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

    system = _first(inputs.get("system"))
    if not system:
        return []
    try:
        record = SYSTEM.get(system)
    except Problem:
        return []
    model = record.get("model_record") or (record.get("params") or {}).get("model")
    return [(f"model:{model}", True)] if model else []


def rescore_locks(inputs: dict[str, Any]) -> list[tuple[str, bool]]:
    """A re-score writes onto a dataset's runs, or a round's arms: the dataset, and the round's goal; a round's own dataset
    when no dataset is named."""
    dataset = _first(inputs.get("dataset_id"))
    out: list[tuple[str, bool]] = [(f"dataset:{dataset}", True)] if dataset else []
    if inputs.get("round") and inputs.get("goal"):
        out.append((f"goal:{inputs['goal']}", True))
        if not dataset:
            from evaluation_harness import _rounds  # noqa: PLC0415

            rnd = _rounds.find(str(inputs["goal"]), str(inputs["round"])) or {}
            if rnd.get("dataset_id"):
                out.append((f"dataset:{rnd['dataset_id']}", True))
    return out
