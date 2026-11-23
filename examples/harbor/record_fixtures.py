#!/usr/bin/env python3
"""Record the example's fixtures: real Harbor job directories, from Harbor's own `oracle` and `nop` agents, scrubbed.

    python examples/harbor/record_fixtures.py        # from the repository root; needs Docker and `harbor`, costs $0

For each of the three tasks under `tasks/` it runs Harbor twice, with the agents that need no model and no key:

  oracle   runs the task's `solution/solve.sh`: the verifier should give reward 1       -> fixtures/jobs/oracle-<task>
  nop      does nothing: the verifier should give reward 0                              -> fixtures/jobs/nop-<task>

and a trial that fails for real: `fixtures/jobs/timeout-write-greeting` is the `oracle` agent on a copy of
`write-greeting` whose solution sleeps past its 3 s agent timeout, so Harbor records an `AgentTimeoutError` (and still runs
the verifier: reward 0). One fixture is NOT recorded: `fixtures/jobs/exception-write-greeting` is the `oracle` job with an
`EnvironmentStartTimeoutError` in its `exception_info` (the shape of Harbor's `ExceptionInfo`, harbor/models/trial/result.py)
and no verifier result, for a trial that never reached its verifier, which no run here produced. The README says so.

A job directory is kept without its `agent/` folder, its logs and its lock files (about 20 KB a job). Everything that
names this machine or a credential is scrubbed (`trial_uri`, the jobs folder's absolute path, `base_url`,
`model_api_key_name`), and the recorder refuses to write a fixture that still holds `/home/`, `/work/`, `http`, `_KEY`, the
scratch folder or the user's name. The tests (`test_harbor.py`) check the same of what is committed.
"""

from __future__ import annotations

import getpass
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
FIXTURES = HERE / "fixtures" / "jobs"
KEEP = ("config.json", "result.json")
VERIFIER = ("reward.txt", "ctrf.json", "test-stdout.txt")
#: What a fixture must not hold: a person's home, a checkout, a URL, a key's name.
FORBIDDEN = ("/home/", "/work/", "http", "_KEY")
NULLED = {"trial_uri", "base_url", "model_api_key_name"}
JOBS = "jobs"
EXCEPTION_ID = "Exc0001"


def scrub(value: object, scratch: str, renames: tuple[tuple[str, str], ...] = ()) -> object:
    """`value` (parsed JSON) with what names this machine or a credential removed; `renames` first (a place the run
    used, and the place the fixture says it was)."""
    if isinstance(value, dict):
        return {
            k: None
            if k in NULLED
            else (JOBS if k in ("trials_dir", "jobs_dir") else scrub(v, scratch, renames))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v, scratch, renames) for v in value]
    if isinstance(value, str):
        for old, new in renames:
            value = value.replace(old, new)
        # A traceback names where Harbor is installed: the home folder (and with it the user) goes.
        return re.sub(r"/home/[^/\s\"']+", "~", value.replace(scratch, JOBS))
    return value


def problems(path: Path, scratch: str) -> list[str]:
    """The forbidden strings a written file holds."""
    text = path.read_text(encoding="utf-8")
    bad = [f for f in (*FORBIDDEN, scratch, getpass.getuser()) if f and f in text]
    return [f"{path}: holds {b!r}" for b in bad]


def keep(job: Path, out: Path, scratch: str, renames: tuple[tuple[str, str], ...] = ()) -> None:
    """The job `job` as a fixture at `out`: its two JSON files, and each trial's two and its verifier's three."""
    for src in sorted(job.rglob("*")):
        rel = src.relative_to(job)
        parts = rel.parts
        wanted = (
            (len(parts) == 1 and src.name in KEEP)
            or (len(parts) == 2 and src.name in KEEP)
            or (len(parts) == 3 and parts[1] == "verifier" and src.name in VERIFIER)
        )
        if not wanted or not src.is_file():
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".json":
            dst.write_text(
                json.dumps(
                    scrub(json.loads(src.read_text(encoding="utf-8")), scratch, renames),
                    indent=4,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            dst.write_text(src.read_text(encoding="utf-8").replace(scratch, JOBS), encoding="utf-8")
        bad = problems(dst, scratch)
        if bad:
            raise SystemExit("refusing to record:\n  " + "\n  ".join(bad))


def record_timeout(root: Path, scratch: str) -> None:
    """`fixtures/jobs/timeout-write-greeting`: a trial Harbor itself ends with an `AgentTimeoutError`, recorded. The task is a
    copy of `write-greeting` whose solution sleeps and whose agent timeout is 3 s; the fixture says it ran on the real one."""
    copy = Path(scratch) / "tasks" / "write-greeting"
    shutil.copytree(TASKS / "write-greeting", copy)
    (copy / "task.toml").write_text(
        (copy / "task.toml")
        .read_text(encoding="utf-8")
        .replace("[agent]\ntimeout_sec = 120.0", "[agent]\ntimeout_sec = 3.0"),
        encoding="utf-8",
    )
    (copy / "solution" / "solve.sh").write_text(
        "#!/bin/bash\nsleep 30\necho hello > /app/greeting.txt\n", encoding="utf-8"
    )
    cmd = [
        "harbor", "run", "-p", str(copy), "-a", "oracle", "-o", scratch,
        "--job-name", "timeout-write-greeting", "-n", "1", "-r", "0", "-q", "-y",
    ]  # fmt: skip
    print(" ".join(cmd))
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False, encoding="utf-8")
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    out = FIXTURES / "timeout-write-greeting"
    shutil.rmtree(out, ignore_errors=True)
    keep(
        Path(scratch) / "timeout-write-greeting",
        out,
        scratch,
        ((str(copy), "examples/harbor/tasks/write-greeting"),),
    )


def synthetic_exception(out: Path) -> None:
    """The `exception-write-greeting` fixture: the oracle job with the trial's exception in place of its verifier result."""
    src = FIXTURES / "oracle-write-greeting"
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out)
    job_text = (out / "result.json").read_text(encoding="utf-8")
    for trial in list(out.glob("*__*")):
        name = f"write-greeting__{EXCEPTION_ID}"  # a trial of its own: a capture's record ids are trial names
        job_text = job_text.replace(trial.name, name)
        trial = trial.rename(trial.parent / name)
        result = json.loads((trial / "result.json").read_text(encoding="utf-8"))
        result["trial_name"] = name
        if isinstance(result.get("config"), dict):
            result["config"]["trial_name"] = name
        cfg = json.loads((trial / "config.json").read_text(encoding="utf-8"))
        cfg["trial_name"] = name
        (trial / "config.json").write_text(json.dumps(cfg, indent=4, sort_keys=True) + "\n", encoding="utf-8")
        result["verifier_result"] = None
        result["reward_valid"] = False
        result["exception_info"] = {
            "exception_type": "EnvironmentStartTimeoutError",
            "exception_message": "Environment start timed out after 300.0 seconds (a synthetic fixture, not recorded)",
            "exception_traceback": "(synthetic: the shape of harbor.models.trial.result.ExceptionInfo, edited in)",
            "occurred_at": result.get("finished_at"),
        }
        (trial / "result.json").write_text(
            json.dumps(result, indent=4, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.rmtree(trial / "verifier", ignore_errors=True)
    job = json.loads(job_text)
    job["n_errored_trials"] = 1  # the job's counts are not read; kept plausible
    (out / "result.json").write_text(json.dumps(job, indent=4, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    if sys.argv[1:] == [
        "--exception-only"
    ]:  # the synthetic job again, from the recorded oracle one, with no Docker
        synthetic_exception(FIXTURES / "exception-write-greeting")
        return 0
    if not shutil.which("harbor") or not shutil.which("docker"):
        print("needs `harbor` (uv tool install harbor) and Docker on PATH")
        return 1
    root = HERE.parents[1]
    scratch = tempfile.mkdtemp(prefix="evh-harbor-record-")
    try:
        for agent in ("oracle", "nop"):
            for task in sorted(p.name for p in TASKS.iterdir() if (p / "task.toml").is_file()):
                name = f"{agent}-{task}"
                cmd = [
                    "harbor", "run", "-p", f"examples/harbor/tasks/{task}", "-a", agent, "-o", scratch,
                    "--job-name", name, "-n", "1", "-r", "0", "-q", "-y",
                ]  # fmt: skip
                print(" ".join(cmd))
                r = subprocess.run(
                    cmd, cwd=root, capture_output=True, text=True, check=False, encoding="utf-8"
                )
                if r.returncode:
                    print(r.stdout + r.stderr)
                    return r.returncode
                out = FIXTURES / name
                shutil.rmtree(out, ignore_errors=True)
                keep(Path(scratch) / name, out, scratch)
        record_timeout(root, scratch)
        exc = FIXTURES / "exception-write-greeting"
        shutil.rmtree(exc, ignore_errors=True)
        synthetic_exception(exc)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"wrote {sum(1 for _ in FIXTURES.glob('*'))} job fixtures under {FIXTURES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
