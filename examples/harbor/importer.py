"""Harbor job directories as a capture: one record per trial, read from the files Harbor wrote. Neither Docker nor Harbor
is needed: a job directory is plain JSON and text.

    evh capture --importer examples/harbor/importer.py:Importer \\
        --query '{"jobs_dir": "artifacts/harbor_oracle_v1"}' --capture harbor_2026_11
    evh dataset-from-capture --capture harbor_2026_11 --dataset-id harbor_hist_v1
    evh dataset-materialize --dataset-id harbor_hist_v1
    evh arm-from-capture --dataset-id harbor_hist_v1 --capture harbor_2026_11 --as harbor_recorded_v1 \\
        --like harbor_oracle_v1

A record per trial directory that holds a `result.json` (`<jobs_dir>/<job>/<task>__<id>/`):

  id          the trial's name (`write-greeting__o6yqqmR`)
  body        {task, path, instruction}: the item the live adapter reads (the instruction when the task's folder is found
              from the trial's config, else empty)
  fields      task, agent, model, difficulty and category (the last two from the task's `task.toml`, when found)
  created_at  the trial's `started_at`
  source      {system: "harbor", url: "<job>/<trial>"}
  outcome     {reward, rewards, exception_type, tests}: what the verifier gave, the trial's exception if it had one, and
              the verifier's test counts (`verifier/ctrf.json`)

Query keys: `jobs_dir` (a folder of jobs, or one job's folder), `job` (one job of it), `pick` (`first` or `last`: one
trial per task, the earliest or the latest; without it a task run in several trials is several records, and so several
items). A trial's agent directory, its logs and its credentials are never read.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _toml


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tests_of(trial: Path) -> dict[str, int] | None:
    """The verifier's test counts, {passed, failed, total}, from its `ctrf.json`; None when it wrote none."""
    summary = ((_json(trial / "verifier" / "ctrf.json") or {}).get("results") or {}).get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("tests"), int):
        return None
    return {
        "passed": int(summary.get("passed") or 0),
        "failed": int(summary.get("failed") or 0),
        "total": summary["tests"],
    }


def rewards_of(result: dict[str, Any]) -> dict[str, float]:
    """The rewards the verifier gave: {name: number}; {} when it gave none."""
    got = (result.get("verifier_result") or {}).get("rewards")
    return (
        {str(k): float(v) for k, v in got.items() if isinstance(v, (int, float))}
        if isinstance(got, dict)
        else {}
    )


def reward_of(rewards: dict[str, float]) -> float | None:
    """The trial's reward: the one named `reward`, else the only one there is; None when there is no single one."""
    if "reward" in rewards:
        return rewards["reward"]
    return next(iter(rewards.values())) if len(rewards) == 1 else None


class Importer:
    """Harbor trials, from job directories on disk."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def records(self, query: dict) -> Iterator[dict]:
        """One record per trial, oldest first; with `pick`, one per task."""
        root = Path(query.get("jobs_dir") or "")
        if not query.get("jobs_dir") or not root.is_dir():
            raise ValueError(
                f'the harbor importer needs "jobs_dir" (a folder of Harbor jobs): {query.get("jobs_dir")!r}'
            )
        pick = query.get("pick")
        if pick not in (None, "first", "last"):
            raise ValueError('"pick" is "first" or "last"')
        found = [*root.glob("result.json"), *root.glob("*/result.json"), *root.glob("*/*/result.json")]
        # A trial's result.json names the trial; a job's does not (and sits beside the trials').
        trials = sorted(
            {p.parent for p in found if isinstance(_json(p), dict) and _json(p).get("trial_name")}
        )
        if query.get("job"):
            trials = [t for t in trials if query["job"] in t.relative_to(root).parts[:-1]]
            if not trials:
                raise ValueError(f"no trial under the job {query['job']!r} of {root}")
        records = sorted(
            (self._record(root, t) for t in trials), key=lambda r: (r["created_at"] or "", r["id"])
        )
        if pick:
            by_task: dict[str, dict] = {}
            for r in records:
                if pick == "last" or r["fields"]["task"] not in by_task:
                    by_task[r["fields"]["task"]] = r
            records = sorted(by_task.values(), key=lambda r: (r["created_at"] or "", r["id"]))
        yield from records

    def _record(self, root: Path, trial: Path) -> dict:
        result = _json(trial / "result.json") or {}
        config = result.get("config") or _json(trial / "config.json") or {}
        agent = (config.get("agent") or {}).get("name") or (result.get("agent_info") or {}).get("name")
        model = (config.get("agent") or {}).get("model_name") or (
            (result.get("agent_info") or {}).get("model_info") or {}
        ).get("name")
        task = str(result.get("task_name") or trial.name.rsplit("__", 1)[0])
        task_path = (config.get("task") or {}).get("path")
        folder = Path(task_path) if task_path else None
        tables = _toml.read(folder / "task.toml") if folder and (folder / "task.toml").is_file() else {}
        instruction = (
            (folder / "instruction.md").read_text(encoding="utf-8").strip()
            if folder and (folder / "instruction.md").is_file()
            else ""
        )
        rewards = rewards_of(result)
        exception = (result.get("exception_info") or {}).get("exception_type")
        fields = {
            "task": task,
            "agent": agent,
            "model": model,
            "difficulty": _toml.get(tables, "metadata", "difficulty"),
            "category": _toml.get(tables, "metadata", "category"),
        }
        return {
            "id": trial.name,
            "body": {"task": task, "path": task_path or "", "instruction": instruction},
            "fields": {k: v for k, v in fields.items() if v is not None},
            "created_at": result.get("started_at"),
            "source": {"system": "harbor", "url": trial.relative_to(root).as_posix()},
            "outcome": {
                "reward": reward_of(rewards),
                "rewards": rewards,
                "exception_type": exception,
                "tests": tests_of(trial),
            },
        }
