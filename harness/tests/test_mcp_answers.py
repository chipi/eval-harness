#!/usr/bin/env python3
"""Answers written ahead: `evh mcp --write-answers` and `evh mcp --public --answers`.

    python tests/test_mcp_answers.py

A release that never changes can carry its tools' answers: each call to a public server was a fresh `evh`
process, several seconds of CPU, paid in tens of seconds where the deployment limits the server's CPU (the
evals server's first `goals` after each start took 33 s at cpus 0.5). In a throwaway project: the writer
answers every tool that takes no argument, never one whose default depends on the date or one that needs an
argument; the server serves a written answer without running the command (a marker put in the file comes
back), never reads a line another harness version wrote, and refuses --answers without --public.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
except ImportError as exc:
    print(f"  FAIL test_mcp_answers: {exc}: mcp is a dependency of the package")
    sys.exit(1)

tmp = Path(tempfile.mkdtemp(prefix="evh-mcp-answers-"))
(tmp / "data" / "datasets").mkdir(parents=True)
env = dict(os.environ, EVAL_HOME=str(tmp))
env.pop("EVAL_DATA_DIR", None)
answers = tmp / "answers.jsonl"


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=tmp, env=env, capture_output=True, text=True
    )


srv = None
try:
    # A relative EVAL_HOME, as render.sh passed it (`EVAL_HOME=_release/inspector`, run from the checkout): the
    # commands run inside the project, and from 0.6.2 to 0.7.1 they resolved it there and answered from nothing.
    (tmp / "data" / "goals").mkdir(parents=True)
    shutil.copy(
        Path(__file__).resolve().parents[1] / "tutorial" / "goals" / "tickets_summary.yaml",
        tmp / "data" / "goals",
    )
    rel_env = dict(env, EVAL_HOME=tmp.name)
    r = subprocess.run(
        [
            sys.executable,
            str(HERE / "cli.py"),
            "mcp",
            "--project",
            tmp.name,
            "--public",
            "--write-answers",
            str(tmp / "rel.jsonl"),
        ],
        cwd=tmp.parent,
        env=rel_env,
        capture_output=True,
        text=True,
    )
    rel = (
        {x["tool"]: x for x in map(json.loads, (tmp / "rel.jsonl").read_text().splitlines())}
        if r.returncode == 0
        else {}
    )
    goal_rows = json.loads(rel["goals"]["out"])["result"]["blocks"][0]["rows"] if "goals" in rel else []
    check(
        "--write-answers with a relative EVAL_HOME (from outside the project) answers from the project's data",
        [row.get("goal") for row in goal_rows] == ["tickets_summary"],
        (r.stderr[-300:], goal_rows),
    )
    (tmp / "rel.jsonl").unlink(missing_ok=True)
    shutil.rmtree(tmp / "data" / "goals")

    r = evh("mcp", "--public", "--write-answers", str(answers))
    lines = [json.loads(x) for x in answers.read_text().splitlines()] if answers.exists() else []
    tools = {x["tool"] for x in lines}
    check(
        "--write-answers: every tool that takes no argument, none whose default is dated or that needs an argument",
        r.returncode == 0
        and {"datasets", "goals", "arms", "metrics"} <= tools
        and not tools & {"overview", "activity", "search", "dataset-items", "deploy-sheet"},
        f"exit {r.returncode}: {sorted(tools)} {r.stdout[-200:]}{r.stderr[-300:]}",
    )
    version = next((x["harness"] for x in lines), "")

    # Per dataset: the writer asks leaderboard once for each dataset, with the argv a call builds.
    from evaluation_harness import mcp_server as ms

    (tmp / "data" / "datasets" / "toy_v1.json").write_text("{}")
    asked: list = []

    def fake_run(project, c, argv, timeout, public):
        asked.append((c, list(argv)))
        return (0, json.dumps({"command": c, "argv": argv}), "") if c == "leaderboard" else (1, "", "")

    real_run = ms.run_command
    ms.run_command = fake_run  # type: ignore[assignment]  # a stand-in for the test
    try:
        ms.write_answers(tmp, tmp / "ahead.jsonl", True)
    finally:
        ms.run_command = real_run
    want = ms.argv_of(ms.parser_of("leaderboard"), {"dataset-id": "toy_v1"})
    ahead = [json.loads(x) for x in (tmp / "ahead.jsonl").read_text().splitlines()]
    check(
        "--write-answers: leaderboard written ahead for each dataset, with the argv a call builds",
        ("leaderboard", want) in asked
        and any(x["tool"] == "leaderboard" and x["argv"] == want for x in ahead),
        (asked[-3:], ahead[-1:] if ahead else None),
    )

    # Markers: a written answer the command would never print, and a line from another harness version.
    out = [json.dumps({"tool": "leaderboard", "argv": want, "out": "LEADERBOARD-AHEAD", "harness": version})]
    for x in lines:
        if x["tool"] == "datasets":
            x = {**x, "out": json.dumps({"command": "datasets", "result": "WRITTEN-AHEAD"})}
        if x["tool"] == "goals":
            x = {**x, "out": json.dumps({"command": "goals", "result": "OLD-VERSION"}), "harness": "0.0.0"}
        out.append(json.dumps(x))
    answers.write_text("\n".join(out) + "\n")

    r = evh("mcp", "--answers", str(answers))
    check(
        "--answers without --public is refused (it serves a release that never changes)",
        r.returncode != 0 and "--public" in (r.stderr + r.stdout),
        (r.stderr + r.stdout)[-200:],
    )

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cmd = [sys.executable, str(HERE / "cli.py"), "mcp", "--http", "--port", str(port), "--public"]
    srv = subprocess.Popen(
        [*cmd, "--answers", str(answers)], cwd=tmp, env=env, stderr=subprocess.DEVNULL, start_new_session=True
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with urllib.request.urlopen(base + "/mcp/health", timeout=2) as resp:  # noqa: S310  # nosec B310
                if resp.status == 200:
                    break
        except OSError:
            time.sleep(0.2)

    async def calls():
        async with (
            streamable_http_client(base + "/mcp") as streams,
            ClientSession(streams[0], streams[1]) as s,
        ):
            await s.initialize()
            ds = await s.call_tool("datasets", {})
            goals = await s.call_tool("goals", {})
            lb = await s.call_tool("leaderboard", {"dataset-id": "toy_v1"})
            return ds.content[0].text, goals.content[0].text, goals.is_error, lb.content[0].text

    ds_text, goals_text, goals_error, lb_text = anyio.run(calls)
    check(
        "--answers: a leaderboard written ahead for a dataset is served for that dataset's call",
        "LEADERBOARD-AHEAD" in lb_text,
        lb_text[:200],
    )
    check(
        "--answers: a written answer is served without running the command",
        "WRITTEN-AHEAD" in ds_text,
        ds_text[:200],
    )
    check(
        "--answers: a line another harness version wrote is not read (the command runs)",
        not goals_error and "OLD-VERSION" not in goals_text and f'"version": "{version}"' in goals_text,
        goals_text[:200],
    )
finally:
    if srv is not None:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
