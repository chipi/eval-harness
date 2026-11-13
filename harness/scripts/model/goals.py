"""The goal (RFC-032's first entity): the decision an evaluation helps make, `data/goals/<goal_id>.yaml`, and the view of
where it stands, which every surface reads (the Workbench's home and hub, `evh goal-status`)."""

from __future__ import annotations

from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.entity import Entity


def _links(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Every dataset and reference the goal names exists."""
    out = []
    for i, d in enumerate(record.get("datasets") or []):
        ds = d.get("dataset_id") if isinstance(d, dict) else None
        if ds and not _store.is_file(_common.DATASETS / f"{ds}.json"):
            out.append(
                {"path": ["datasets", i, "dataset_id"], "message": f"no dataset {ds!r} in this project"}
            )
    for i, r in enumerate(record.get("references") or []):
        ref = r.get("reference_id") if isinstance(r, dict) else None
        if ref and ("/" not in ref or not _store.is_dir(_common.REFERENCES / ref)):
            out.append(
                {
                    "path": ["references", i, "reference_id"],
                    "message": f"no reference {ref!r} in this project",
                }
            )
    return out


GOAL = Entity(
    name="goal",
    plural="goals",
    folder="goals",
    id_field="goal_id",
    schema="goal.schema.json",
    skip=frozenset({"policy.yaml"}),
    links=_links,
)


def status(goal_id: str) -> dict[str, Any]:
    """Where a goal stands: each of its datasets (made, materialized, its reference, its runs and arms, its baseline),
    its rounds, the jobs working on it, and the next step, with the command that takes it."""
    from evaluation_harness import _baselines, _jobs, _rounds, _runs  # noqa: PLC0415

    g = GOAL.get(goal_id)
    refs = [r.get("reference_id") for r in g.get("references") or [] if isinstance(r, dict)]
    rounds = [
        {
            "round": r.get("round_id"),
            "status": r.get("status"),
            "dataset": r.get("dataset_id"),
            "question": r.get("hypothesis"),
        }
        for r in _rounds.load_rounds(goal_id)
    ]
    datasets, keys = [], {f"goal:{goal_id}"}
    for d in g.get("datasets") or []:
        ds = d.get("dataset_id")
        keys.add(f"dataset:{ds}")
        runs = _runs.runs_on(ds)
        base = _baselines.current(goal_id, ds)
        datasets.append(
            {
                "dataset": ds,
                "role": d.get("role"),
                "decides": d.get("decides", True) is not False,
                "made": _store.is_file(_common.DATASETS / f"{ds}.json"),
                "materialized": _store.is_dir(_common.MATERIALIZED / ds),
                "references": sorted(
                    {r for r in refs if r and r.endswith(f"/{ds}") and _store.is_dir(_common.REFERENCES / r)}
                    | {
                        f"{tier}/{ds}"
                        for tier in ("gold", "silver")
                        if _store.is_dir(_common.REFERENCES / tier / ds)
                    }
                ),
                "runs": len(runs),
                "arms": len({m["config_id"] for _, m in runs}),
                "baseline": {"version": base.get("version"), "run": base.get("promoted_from")}
                if base
                else None,
            }
        )
    running = [
        {"job": j.get("id") or j.get("job_id"), "command": j.get("command"), "state": j.get("state")}
        for j in _jobs.list_jobs()
        if str(j.get("state", "")).startswith(("running", "queued"))
        and any(k in keys for k, _ in j.get("locks") or [])
    ]
    return {
        "goal": goal_id,
        "title": g.get("title"),
        "measure": (g.get("success_criteria") or {}).get("primary"),
        "datasets": datasets,
        "rounds": rounds,
        "running": running,
        "next": _next(goal_id, datasets, rounds),
    }


def _next(goal_id: str, datasets: list[dict[str, Any]], rounds: list[dict[str, Any]]) -> dict[str, str]:
    """The first step not taken, on the datasets that decide: made, materialized, a reference, runs, a baseline; then
    the open round to close, or a round to open."""
    for d in (x for x in datasets if x["decides"]):
        ds = d["dataset"]
        if not d["made"]:
            return {"what": f"make the dataset {ds}", "command": f"evh dataset-create --dataset-id {ds} ..."}
        if not d["materialized"]:
            return {"what": f"fetch {ds}'s items", "command": f"evh dataset-materialize --dataset-id {ds}"}
        if not d["references"]:
            return {
                "what": f"promote a reference for {ds}",
                "command": f"evh reference-promote --dataset-id {ds} ...",
            }
        if not d["runs"]:
            return {
                "what": f"run an arm on {ds}",
                "command": f"evh run --system <a system> --dataset {ds} --goal {goal_id}",
            }
        if not d["baseline"]:
            return {
                "what": f"promote a baseline on {ds}",
                "command": 'evh run-promote --run <run id> --reason "..."',
            }
    open_ = [r for r in rounds if r["status"] == "open"]
    if open_:
        r = open_[-1]["round"]
        return {
            "what": f"read round {r}'s evidence, then close it",
            "command": f"evh rounds --goal {goal_id} --round {r}",
        }
    return {
        "what": "open a round with a question",
        "command": f'evh round-open --goal {goal_id} --hypothesis "..." ...',
    }
