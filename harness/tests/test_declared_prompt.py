#!/usr/bin/env python3
"""A system that points at a recorded prompt version sends that text (RFC-028; the Workbench's prompts): $0, offline.

    python tests/test_declared_prompt.py

A system on the bundled adapter declares its prompt as a recorded version (`prompts: {<name>: {version: <id>}}`), the
way the Workbench makes one and a study's trial does. Against a fake OpenAI-shaped server that keeps what it is sent:
the arm-smoke and the run each send the version's text before the item (they sent "Summarise:", the adapter reading
only `params.prompt`); the run records the version in its fingerprint and `prompt-show` names the run; a system that
declares two prompts is refused by the bundled adapter, which sends one.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SENT: list[str] = []


class Fake(http.server.BaseHTTPRequestHandler):
    """An OpenAI-shaped server: keeps each call's user message, answers one line."""

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SENT.append(body["messages"][-1]["content"])
        data = json.dumps({
            "id": "x", "object": "chat.completion", "created": 0, "model": "fake",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "a summary"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }).encode()  # fmt: skip
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a) -> None:
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
proj = Path(tempfile.mkdtemp(prefix="evh-declprompt-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), OPENAI_API_KEY="local")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
os.environ.setdefault("EVAL_STORE", "files")
env["EVAL_STORE"] = os.environ["EVAL_STORE"]


import _cli  # noqa: E402


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=600)


def last(r: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(r.stdout.splitlines()[-1]).get("result") or {}
    except (IndexError, ValueError):
        return {}


TEXT = "Write one line a support engineer can act on."
try:
    r = evh("init", "--store", env["EVAL_STORE"], "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason",
         "the kit's summaries, for the test", "--by", "t"),
        ("prompt-version", "--name", "tickets/summary", "--text", TEXT, "--note", "the first wording"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    vid = (last(evh("prompt-list", "--json")).get("prompts") or [{}])[0].get("latest") or ""
    if isinstance(vid, dict):
        vid = vid.get("id", "")
    check(
        "setup: a dataset with its reference, and a prompt version recorded",
        r.returncode == 0 and "/" in vid,
        (r.stderr[-300:], vid),
    )
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    params = f"params:\n  provider: openai\n  model: fake\n  base_url: {base}\n  usd_per_mtok_in: 0\n  usd_per_mtok_out: 0\n"
    _runstore.write_text(
        proj,
        "systems/ver_v1.yaml",
        f"system_id: ver_v1\n{params}prompts:\n  tickets/summary: {{version: {vid}}}\n",
    )
    SENT.clear()
    sm = evh("arm-smoke", "--system", "ver_v1", "--dataset", "tk_v1", "--items", "2")
    check(
        "arm-smoke sends the declared version's text before each item, not the adapter's default",
        sm.returncode == 0 and len(SENT) >= 2 and all(s.startswith(TEXT + "\n\n") for s in SENT),
        (sm.stderr[-300:], [s[:60] for s in SENT]),
    )
    SENT.clear()
    dry = evh("run", "--system", "ver_v1", "--dataset", "tk_v1", "--dry-run")
    check(
        "the run's dry run counts the declared prompt in its estimate, and calls nothing",
        dry.returncode == 0 and "item text + the system's prompt" in dry.stdout and not SENT,
        (dry.stdout[-600:], SENT[:1]),
    )
    SENT.clear()
    run = evh("run", "--system", "ver_v1", "--dataset", "tk_v1", "--json")
    run_id = ((last(run).get("values") or {}).get("runs") or [{}])[0].get("run_id")
    check(
        "the run sends it too, every item",
        run.returncode == 0 and len(SENT) >= 6 and all(s.startswith(TEXT + "\n\n") for s in SENT),
        (run.stderr[-300:], [s[:60] for s in SENT][:3]),
    )
    shown = last(evh("prompt-show", "--name", "tickets/summary", "--json"))
    check(
        "the run records the version, and prompt-show names the run that used it",
        bool(run_id) and run_id in json.dumps(shown),
        (run_id, json.dumps(shown)[:600]),
    )
    _runstore.write_text(
        proj,
        "systems/two_v1.yaml",
        f"system_id: two_v1\n{params}prompts:\n  tickets/summary: {{version: {vid}}}\n  tickets/other: {{version: {vid}}}\n",
    )
    two = evh("run", "--system", "two_v1", "--dataset", "tk_v1")
    check(
        "a system on the bundled adapter declaring two prompts is refused: it sends one",
        two.returncode != 0 and "one prompt" in (two.stdout + two.stderr),
        (two.stdout + two.stderr)[-400:],
    )
finally:
    server.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
