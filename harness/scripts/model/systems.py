"""The system (RFC-032 step 3): what is evaluated, an adapter with its settings and the model it runs, with no dataset.
`evh run --system <id> --dataset <id>` runs it on a dataset; placed in a round it is an arm. Its record is
data/systems/<system_id>.yaml, or a folder validate.json's `systems` names (this repository's are in examples/)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.entity import Entity

#: A system id kept from a config id may carry capitals (`se_rougeL_n100_v1`).
SYSTEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _found() -> dict[str, Path]:
    """{system_id: its file} for every system of the project, by its file's name."""
    return {f.stem: f for f in _common.system_files()}


def _links(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The model and the deployment a system names exist."""
    out = []
    mid, dep = record.get("model_record"), record.get("deployment")
    if mid and not _store.is_file(_common.DATA / "models" / f"{mid}.yaml"):
        out.append({"path": ["model_record"], "message": f"no model {mid!r} in this project"})
    elif dep and not mid:
        out.append(
            {"path": ["deployment"], "message": "a deployment is a model's: name the model_record too"}
        )
    elif dep and not _store.is_file(_common.DATA / "deployments" / str(mid) / f"{dep}.yaml"):
        out.append({"path": ["deployment"], "message": f"no deployment {dep!r} of {mid!r}"})
    return out


SYSTEM = Entity(
    name="system",
    plural="systems",
    folder="systems",
    id_field="system_id",
    schema="system.schema.json",
    links=_links,
    finder=_found,
    id_pattern=SYSTEM_ID,
)


def where(system_id: str) -> str:
    """The system's file, relative to the project."""
    f = SYSTEM.path(system_id)
    try:
        return str(f.relative_to(_common.project_root()))
    except ValueError:
        return str(f)


def arm_of(
    system_id: str, dataset_id: str, goal: str | None = None, round_id: str | None = None
) -> tuple[dict[str, Any], Path]:
    """The system on a dataset, as a run reads it: the system's settings with the dataset, and the goal and round the
    run is for; and the system's file (an adapter is found relative to it). A system that does not exist is refused,
    naming those there are."""
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    try:
        rec = SYSTEM.get(system_id)
        path = SYSTEM.path(system_id)
    except Problem as exc:
        _common.die(str(exc), exc.kind)
    arm = {k: v for k, v in rec.items() if k != "system_id"}
    arm["config_id"] = (
        system_id  # the run records the system's id where it recorded the config's (until step 4)
    )
    arm["dataset_id"] = dataset_id
    if goal:
        arm["goal"] = goal
    if round_id:
        arm["round"] = round_id
    return arm, path
