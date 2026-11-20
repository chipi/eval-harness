"""Harbor trials as a system: one `harbor run` trial per item, called once.

    evh dataset-create --dataset-id harbor_tasks_v1 --source examples/harbor/source.py:Source \\
        --query '{"path": "examples/harbor/tasks"}'
    evh run --system harbor_oracle_v1 --dataset harbor_tasks_v1

An item is a Harbor task (`source.py`): `{"task", "path" or "dataset", "instruction"}`. The adapter runs

    harbor run (-p PATH | -d DATASET -i TASK) -a AGENT [-m MODEL] -o JOBS_DIR --job-name NAME -n 1 -r 0 -q -y

and reads the job directory Harbor wrote. It declares `CALL_ONCE` (RFC-038): a trial has side effects (an agent that
spent money, a container that ran) and the core must not retry it. `-r 0` says the same to Harbor. Its own timeout in
seconds (Harbor's flags are multipliers) ends a trial that hangs: the process group is sent SIGTERM, then SIGKILL after a
grace period.

What a call gives:

  output   the JSON {task, reward, pass, answered, tests, exception, trial}: what the verifier gave and the trial's name
  extra    {"reward": the verifier's reward}
  tokens   the agent's, as Harbor read them
  cost     0.0 for an agent that calls no model (`oracle`, `nop`), else the agent's own estimate (`cost_source` says which)
  meta     artifact (the trial's directory, which the inspector links), wall_s, harbor_job, agent, exception_type

A trial that ran and ended badly (Harbor wrote its `result.json`: the agent's exception, a wrong answer) is a scored 0,
with the exception in the output: the agent failed the task. A call that gave no trial result at all (Harbor crashed, the
trial timed out, no `result.json`) raises: a failed item, which `--resume` does not call again unless a person says so.

Params: `agent` (required), `model`, `jobs_dir` (default `artifacts/harbor`: under the project's `artifacts/`, which the
inspector serves), `timeout_s` (default: the task's agent, verifier and environment-build timeouts plus
`timeout_slack_s`, 120), `kill_grace_s` (20), `env_file`, `agent_env` ({NAME: value} passed as `--ae`; never put a key in a
system, name it in the env file), `harbor` (the command, `harbor`).
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation_harness.adapter import Result

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _toml  # noqa: E402

CALL_ONCE = True
PRIMARY_METRIC = "pass"
METRIC_KINDS = {
    "pass": "quality",
    "reward": "quality",
    "tests_passed_frac": "quality",
    "answered": "descriptive",
}
METRIC_DESCRIPTIONS = {
    "pass": "1 when the verifier's reward is 1.0: the agent solved the task. Averaged over the tasks, the share solved.",
    "reward": "The verifier's reward for the trial, 0 to 1 (the mean over the tasks).",
    "tests_passed_frac": "The share of the verifier's tests that passed, for the trials whose verifier wrote a ctrf.json.",
    "answered": "1 when the trial reached its verifier and a reward exists; 0 when it ended before that (an agent that crashed).",
}
#: Agents that call no model: their trials cost nothing, and say so.
NO_MODEL_AGENTS = ("oracle", "nop")
SLACK_S = 120.0
GRACE_S = 20.0


class HarborError(RuntimeError):
    """The call gave no trial result: Harbor failed, or the trial did not finish. `meta` and `cost_usd` ride on it, so the
    failed item keeps the trial's directory (the core reads them off the exception)."""

    def __init__(self, message: str, meta: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.meta = meta or {}


class HarborTimeout(HarborError):
    """The trial ran past this adapter's timeout and was killed."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rewards(result: dict[str, Any]) -> dict[str, float]:
    """The rewards the verifier gave: {name: number}; {} when it gave none."""
    got = (result.get("verifier_result") or {}).get("rewards")
    return {str(k): float(v) for k, v in got.items() if isinstance(v, (int, float))} if isinstance(got, dict) else {}


def reward(rs: dict[str, float]) -> float | None:
    """The trial's reward: the one named `reward`, else the only one there is, else None."""
    if "reward" in rs:
        return rs["reward"]
    return next(iter(rs.values())) if len(rs) == 1 else None


def tests(ctrf: Any) -> dict[str, int] | None:
    """The verifier's test counts, {passed, failed, total}, from its parsed ctrf.json; None when there are none."""
    s = ((ctrf or {}).get("results") or {}).get("summary") if isinstance(ctrf, dict) else None
    if not isinstance(s, dict) or not isinstance(s.get("tests"), int):
        return None
    return {"passed": int(s.get("passed") or 0), "failed": int(s.get("failed") or 0), "total": s["tests"]}


def verdict(task: str, trial: str, rs: dict[str, float], exception: str | None, counts: dict[str, int] | None) -> str:
    """The item's output, as one JSON document: the same for a trial this adapter ran and one read from a job directory."""
    r = reward(rs)
    return json.dumps(
        {
            "task": task,
            "reward": r,
            "pass": r is not None and r >= 1.0,
            "answered": r is not None,
            "tests": counts,
            "exception": exception,
            "trial": trial,
        },
        sort_keys=True,
    )


def recorded_output(record: dict[str, Any]) -> str:
    """A captured trial's output (`evh arm-from-capture`): what a live call of it gives, read from the importer's record."""
    out = record.get("outcome") or {}
    return verdict(
        str((record.get("fields") or {}).get("task") or (record.get("body") or {}).get("task") or ""),
        str(record["id"]),
        {str(k): float(v) for k, v in (out.get("rewards") or {}).items()},
        out.get("exception_type"),
        out.get("tests"),
    )


def score(output: str, reference: str | None = None) -> dict[str, float]:
    """`pass`, `answered`, `reward` and, when the verifier counted tests, the share that passed. The verifier decides, so no
    reference is read: a failed item (no output) scores 0 on all of them but the tests."""
    try:
        doc = json.loads(output)
    except ValueError:
        doc = {}
    doc = doc if isinstance(doc, dict) else {}
    r = doc.get("reward")
    got = {"answered": 1.0 if r is not None else 0.0, "pass": 1.0 if r is not None and r >= 1.0 else 0.0}
    if r is not None:
        got["reward"] = float(r)
    counts = doc.get("tests")
    if isinstance(counts, dict) and counts.get("total"):
        got["tests_passed_frac"] = counts["passed"] / counts["total"]
    return got


def score_failure(reference: str | None = None) -> dict[str, float]:
    """What an item that gave no trial result scores: it did not pass, and no reward exists."""
    return {"answered": 0.0, "pass": 0.0, "reward": 0.0}


def timeout_for(item: dict[str, Any], params: dict[str, Any]) -> float:
    """The seconds a trial may take: `timeout_s`, else the task's agent, verifier and environment-build timeouts plus the
    slack (Harbor has no flag in seconds; a task Harbor fetches by name has no `task.toml` here, so 3600 and the slack)."""
    if params.get("timeout_s"):
        return float(params["timeout_s"])
    slack = float(params.get("timeout_slack_s", SLACK_S))
    path = Path(item["path"]) if item.get("path") else None
    if path is not None and (path / "task.toml").is_file():
        t = _toml.read(path / "task.toml")
        parts = [_toml.get(t, s, k) for s, k in (("agent", "timeout_sec"), ("verifier", "timeout_sec"), ("environment", "build_timeout_sec"))]
        return sum(float(x) for x in parts if isinstance(x, (int, float))) + slack
    return 3600.0 + slack


def command(item: dict[str, Any], params: dict[str, Any], jobs_dir: str, job: str) -> list[str]:
    """The `harbor run` of one trial: one task, one attempt, no retry, nothing asked."""
    if item.get("dataset"):
        where = ["-d", str(item["dataset"]), "-i", str(item["task"])]
    elif item.get("path"):
        where = ["-p", str(item["path"])]
    else:
        raise ValueError(f"the item names neither a path nor a dataset: {sorted(item)}")
    cmd = [str(params.get("harbor") or "harbor"), "run", *where, "-a", str(params["agent"])]
    if params.get("model"):
        cmd += ["-m", str(params["model"])]
    cmd += ["-o", jobs_dir, "--job-name", job, "-n", "1", "-r", "0", "-q", "-y"]
    if params.get("env_file"):
        cmd += ["--env-file", str(params["env_file"])]
    for name, value in sorted((params.get("agent_env") or {}).items()):
        cmd += ["--ae", f"{name}={value}"]
    return cmd


def _stop(proc: subprocess.Popen[str], grace: float) -> None:
    """End `proc` and what it started: SIGTERM to its process group, SIGKILL when it has not gone after `grace` seconds."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 10.0)):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, sig)
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def _trial_dir(job_dir: Path) -> Path | None:
    """The one trial directory of a one-trial job, whether or not it finished."""
    found = sorted(p for p in job_dir.glob("*__*") if p.is_dir()) if job_dir.is_dir() else []
    return found[0] if found else None


def _left(job_dir: Path, job: str) -> dict[str, Any]:
    """What a call that gave no trial result leaves to open: the trial's directory if Harbor made one, else the job's."""
    trial = _trial_dir(job_dir)
    where = trial or (job_dir if job_dir.is_dir() else None)
    return {"harbor_job": job, **({"artifact": where.as_posix()} if where else {})}


def call_system(text: str, params: dict[str, Any]) -> Result:
    """Run the item's task as one Harbor trial and read what it left."""
    item = json.loads(text)
    if not params.get("agent"):
        raise ValueError("params.agent: the Harbor agent to run (oracle, nop, or an agent with its model)")
    jobs_dir = str(params.get("jobs_dir") or "artifacts/harbor")
    job = f"{item['task']}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    cmd = command(item, params, jobs_dir, job)
    limit = timeout_for(item, params)
    started = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603 - the user's own harbor, an argument list, no shell
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    job_dir = Path(jobs_dir) / job
    try:
        out, _ = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired as exc:
        _stop(proc, float(params.get("kill_grace_s", GRACE_S)))
        raise HarborTimeout(
            f"harbor run of {item['task']} ran past {limit:.0f} s and was stopped", _left(job_dir, job)
        ) from exc
    wall = time.monotonic() - started
    trial = _trial_dir(job_dir)
    result = _json(trial / "result.json") if trial else None
    if trial is None or not isinstance(result, dict):
        raise HarborError(
            f"harbor run of {item['task']} exited {proc.returncode} and wrote no trial result: {(out or '').strip()[-300:]}",
            _left(job_dir, job),
        )
    rs = rewards(result)
    exception = (result.get("exception_info") or {}).get("exception_type")
    counts = tests(_json(trial / "verifier" / "ctrf.json"))
    agent = str(params["agent"])
    usage = result.get("agent_result") or {}
    meta: dict[str, Any] = {
        "artifact": trial.as_posix(),
        "wall_s": round(wall, 3),
        "harbor_job": job,
        "agent": agent,
    }
    if exception:
        meta["exception_type"] = exception
    cost = usage.get("cost_usd")
    if agent in NO_MODEL_AGENTS:
        cost, meta["cost_source"] = 0.0, "no-model-agent"
    elif cost is not None:
        meta["cost_source"] = "harbor-agent-estimate"
    r = reward(rs)
    return Result(
        output=verdict(str(item["task"]), trial.name, rs, exception, counts),
        tokens_in=usage.get("n_input_tokens"),
        tokens_out=usage.get("n_output_tokens"),
        cost_usd=cost,
        extra={"reward": r} if r is not None else {},
        meta=meta,
    )
