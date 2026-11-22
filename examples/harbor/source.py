"""Harbor tasks as a dataset: one item per task, read from a folder of task directories.

    evh dataset-create --dataset-id harbor_tasks_v1 --source examples/harbor/source.py:Source \\
        --query '{"path": "examples/harbor/tasks"}'
    evh dataset-create --dataset-id tb21_files_v1 --source examples/harbor/source.py:Source \\
        --query '{"dataset": "NovitaAI/tb21-file-recovery"}'

`path` is a folder of Harbor tasks (each a directory with `task.toml` and `instruction.md`): offline, nothing is
downloaded. `dataset` is a registry dataset, `name[@version]`: the source runs `harbor dataset download` into the
project's `.build/harbor/` to read its tasks, which needs the network and `harbor`, and the items name the dataset and the
task, so a run asks Harbor for that task by name. Neither needs Docker.

An item's id is the task's directory name; its text is one JSON document, the same the importer writes for a trial, so a
live arm and a recorded one read one shape:

    {"task": "write-greeting", "path": "examples/harbor/tasks/write-greeting", "instruction": "Create the file ..."}
    {"task": "...", "dataset": "name@version", "path": ".build/harbor/<dataset>/<task>", "instruction": "..."}

and its fields are the task's `difficulty` and `category` (`[metadata]`) and `agent_timeout_sec` (`[agent]`). A task's
author's name and email are never read.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _toml

DOWNLOADS = Path(".build") / "harbor"
DATASET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*(@[A-Za-z0-9._:+-]+)?")


def item_text(task: str, path: str, instruction: str, dataset: str | None = None) -> str:
    """The item's document as the importer's body is stored: canonical JSON, sorted keys."""
    doc = {"task": task, "path": path, "instruction": instruction}
    if dataset:
        doc["dataset"] = dataset
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class Source:
    """Harbor tasks, from a folder of them or a registry dataset."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def describe(self, query: dict) -> dict:
        """The tasks as a source block, with how many there are."""
        tasks = self._tasks(query, download=False)
        ref = query.get("dataset") or str(query.get("path"))
        return {
            "source": {"provider": "harbor", "ref": ref},
            "description": f"{len(tasks)} Harbor task(s) from {ref}: one item per task, its instruction as the item's text.",
        }

    def items(self, query: dict) -> Iterator[dict]:
        """One item per task directory, in name order."""
        dataset = query.get("dataset")
        for d in self._tasks(query, download=bool(dataset)):
            tables = _toml.read(d / "task.toml")
            instruction = (
                (d / "instruction.md").read_text(encoding="utf-8") if (d / "instruction.md").is_file() else ""
            )
            fields = {
                "difficulty": _toml.get(tables, "metadata", "difficulty"),
                "category": _toml.get(tables, "metadata", "category"),
                "agent_timeout_sec": _toml.get(tables, "agent", "timeout_sec"),
            }
            yield {
                "item_id": d.name,
                "text": item_text(d.name, d.as_posix(), instruction.strip(), dataset),
                "fields": {k: v for k, v in fields.items() if v is not None},
            }

    def _tasks(self, query: dict, download: bool) -> list[Path]:
        """The task directories: those of the folder, or of the dataset the registry gave (downloaded when `download`)."""
        if query.get("dataset"):
            return self._downloaded(str(query["dataset"]), download)
        if not query.get("path"):
            raise ValueError(
                'the harbor source needs a query with "path" (a folder of tasks) or "dataset" (a registry name)'
            )
        root = Path(query["path"])
        if not root.is_dir():
            raise ValueError(f"no folder {root}")
        return sorted(p for p in root.iterdir() if (p / "task.toml").is_file())

    def _downloaded(self, dataset: str, download: bool) -> list[Path]:
        if not DATASET.fullmatch(dataset):
            raise ValueError(f"dataset {dataset!r}: a registry name, name or name@version")
        folder = DOWNLOADS / dataset.split("@")[0].split("/")[-1]
        if download:
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                ["harbor", "dataset", "download", dataset, "-o", str(DOWNLOADS), "--overwrite"],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            if r.returncode:
                raise ValueError(f"harbor dataset download {dataset} failed: {(r.stdout + r.stderr)[-300:]}")
        return sorted(p for p in folder.iterdir() if (p / "task.toml").is_file()) if folder.is_dir() else []
