#!/usr/bin/env python3
"""Systems and prompt versions through the model (RFC-032 step 3), on both surfaces.

    python tests/test_model_systems.py

In a project `evh init` makes: a system made with `evh system-new` is its own file named by its id, with no dataset;
`system-set` changes one setting and keeps the file's comments; a key a system cannot hold (a dataset, a goal) and an id
that is taken are refused with nothing written; a run takes the system by its id on any dataset; a prompt version
recorded with `evh prompt-version` is listed and shown with the runs that used it; the API's resources give the command
line's answers, and a system made through the API records who sent it.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-systems-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-model-systems",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def result(r: subprocess.CompletedProcess) -> dict:
    """A --json command's result."""
    return json.loads(r.stdout)["result"]


def serve() -> tuple[subprocess.Popen, int]:
    """catalog-serve on a free port, once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError(f"the server did not start: {(p.communicate()[0] or '')[-500:]}")


def call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """One API call with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"}
    raw = json.dumps(body).encode() if body is not None else None
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"text": raw.decode(errors="replace")[-500:]}


SYSTEM = proj / "data" / "systems" / "lead1_v1.yaml"
try:
    r = evh("init")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("dataset-create", "--dataset-id", "tk_small_v1", "--source-dir", "tickets", "--limit", "3"),
        ("dataset-materialize", "--dataset-id", "tk_small_v1"),
    ):
        r = r if r.returncode else evh(*step)
    check("setup: a project with two datasets", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    made = evh("system-new", "lead1_v1", "--set", "params.provider=echo", "--set", "params.sentences=1")
    doc = yaml.safe_load(SYSTEM.read_text()) if SYSTEM.is_file() else {}
    check(
        "system-new makes the system's own file, named by its id, with no dataset",
        made.returncode == 0 and doc.get("system_id") == "lead1_v1" and "dataset_id" not in doc,
        (made.stdout + made.stderr)[-300:],
    )
    again = evh("system-new", "lead1_v1", "--set", "params.provider=echo")
    check(
        "system-new refuses an id that is taken",
        again.returncode == 1 and "ERROR (would-overwrite)" in again.stderr,
        again.stderr[-200:],
    )
    before = SYSTEM.read_text()
    bad = evh("system-set", "lead1_v1", "--set", "dataset_id=tk_v1")
    bad_goal = evh("system-set", "lead1_v1", "--set", "goal=g")
    check(
        "a system holds no dataset and no goal: both refused with their field, nothing written",
        bad.returncode == 1
        and "dataset_id" in bad.stderr
        and bad_goal.returncode == 1
        and "goal" in bad_goal.stderr
        and SYSTEM.read_text() == before,
        (bad.stderr[-200:], bad_goal.stderr[-200:]),
    )
    SYSTEM.write_text(SYSTEM.read_text().replace("system_id:", "# the terse one\nsystem_id:", 1))
    s = evh("system-set", "lead1_v1", "--set", "params.sentences=2")
    text = SYSTEM.read_text()
    check(
        "system-set changes one setting and keeps the file's comments",
        s.returncode == 0 and "# the terse one" in text and yaml.safe_load(text)["params"]["sentences"] == 2,
        (s.stderr[-200:], text),
    )
    runs = [evh("run", "--system", "lead1_v1", "--dataset", ds, "--json") for ds in ("tk_v1", "tk_small_v1")]
    ran = [result(x)["values"]["runs"][0] for x in runs if x.returncode == 0]
    check(
        "a run takes the system by its id, on any dataset: one system, two datasets, its id on both runs",
        len(ran) == 2
        and {x["dataset_id"] for x in ran} == {"tk_v1", "tk_small_v1"}
        and {x["config_id"] for x in ran} == {"lead1_v1"},
        [x.stderr[-200:] for x in runs],
    )
    nope = evh("run", "--system", "no_such_v1", "--dataset", "tk_v1")
    check(
        "a system that does not exist is refused, naming those there are",
        nope.returncode == 1 and "no system 'no_such_v1': one of lead1_v1" in nope.stderr,
        nope.stderr[-200:],
    )

    note = proj / "p.txt"
    note.write_text("Summarise the ticket in one sentence.\n")
    pv = evh("prompt-version", "tickets/summary", "--from-file", str(note), "--note", "the first wording")
    listed = result(evh("prompt-list", "--json"))
    shown = result(evh("prompt-show", "--name", "tickets/summary", "--json"))
    check(
        "prompt-list and prompt-show read the recorded version: its name, its count, its note",
        pv.returncode == 0
        and [x["name"] for x in listed["prompts"]] == ["tickets/summary"]
        and listed["prompts"][0]["versions"] == 1
        and shown["versions"][0]["note"] == "the first wording",
        (pv.stderr[-200:], listed, shown),
    )
    missing = evh("prompt-show", "--name", "no/such")
    check(
        "prompt-show refuses a name with no version, naming those there are",
        missing.returncode == 1 and "no prompt 'no/such': one of tickets/summary" in missing.stderr,
        missing.stderr[-200:],
    )

    cat = evh("catalog")
    check("setup: the catalog, which the server serves", cat.returncode == 0, cat.stderr[-300:])
    srv, port = serve()
    try:
        cli = {
            name: result(evh(name, *args, "--json"))
            for name, args in (
                ("system-list", ()),
                ("system-show", ("lead1_v1",)),
                ("prompt-list", ()),
                ("prompt-show", ("--name", "tickets/summary")),
            )
        }
        api = {
            "system-list": call(port, "GET", "/systems")[1].get("result"),
            "system-show": call(port, "GET", "/systems/lead1_v1")[1].get("result"),
            "prompt-list": call(port, "GET", "/prompts")[1].get("result"),
            "prompt-show": call(port, "GET", "/prompts/versions?name=tickets/summary")[1].get("result"),
        }
        check("the API's resources give the command line's answers", api == cli, (api, cli))
        code, body = call(
            port,
            "POST",
            "/systems/lead2_v1",
            {"set": {"params.provider": "echo", "params.sentences": 2}, "by": "person:api"},
        )
        hist = proj / "data" / "history" / "systems" / "lead2_v1.jsonl"
        check(
            "a system made through the API is checked by the same model and records who sent it",
            code == 200
            and (proj / "data" / "systems" / "lead2_v1.yaml").is_file()
            and '"person:api"' in (hist.read_text() if hist.is_file() else ""),
            (code, body),
        )
        bad_code, _ = call(
            port, "POST", "/systems/lead3_v1", {"set": {"dataset_id": "tk_v1"}, "by": "person:api"}
        )
        check(
            "the API refuses a system with a dataset; nothing written",
            400 <= bad_code < 500 and not (proj / "data" / "systems" / "lead3_v1.yaml").exists(),
            bad_code,
        )
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
