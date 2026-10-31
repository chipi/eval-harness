#!/usr/bin/env python3
"""evh model-onboard (RFC-020), against a fake OpenAI-shaped server that reasons unless told not to.

python tests/test_model_onboard.py
"""

import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


class Fake(http.server.BaseHTTPRequestHandler):
    def _send(self, doc):
        data = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [{"name": "fake:1b", "model": "fake:1b", "digest": "abc123def456" + "0" * 52}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        off = body.get("reasoning_effort") == "none"
        msg = {"role": "assistant", "content": '{"answer": "yes", "reason": "17 has no divisors"}'}
        if not off:
            msg["reasoning"] = "Let me think. 17 divided by 2, 3, 5 ... prime."
        self._send(
            {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "fake:1b",
                "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 12 if off else 60, "total_tokens": 52},
            }
        )

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}/v1"

with tempfile.TemporaryDirectory() as td:
    data = Path(td) / "data"
    (data / "models").mkdir(parents=True)
    rec: dict[str, Any] = {
        "model_id": "fake-1b",
        "kind": "llm",
        "aliases": ["fake:1b"],
        "deployments": [
            {
                "id": "here",
                "where": "here",
                "tag": "fake:1b",
                "digest": "abc123def456",
                "endpoint": {"provider": "openai", "base_url": base, "model": "fake:1b"},
            }
        ],
        "settings": {"reasoning_effort": "none"},
    }
    f = data / "models" / "fake-1b.yaml"
    f.write_text(yaml.safe_dump(rec))
    env = {**os.environ, "EVAL_DATA_DIR": str(data), "OPENAI_API_KEY": "local"}
    run = subprocess.run(
        [sys.executable, str(HERE / "scripts" / "model_onboard.py"), "fake-1b", "--deployment", "here"],
        capture_output=True,
        text=True,
        env=env,
    )
    out = run.stdout + run.stderr
    check(
        "onboard: a model whose settings turn its reasoning off passes",
        run.returncode == 0 and "ONBOARD PASS" in out,
        out[-600:],
    )
    got = yaml.safe_load(f.read_text())
    caps = got.get("capabilities") or {}
    check(
        "onboard: it reasons by default, and the record's setting turns it off",
        caps.get("reasons") is True and caps.get("reasoning_off") == "reasoning_effort: none",
        caps,
    )
    report = (got["deployments"][0].get("onboarding") or {}).get("report") or {}
    check(
        "onboard: JSON mode is the model's; determinism and speed are the deployment's",
        caps.get("json_mode") is True
        and "deterministic" not in caps
        and "tokens_per_s" not in caps
        and report.get("deterministic") is True
        and isinstance(report.get("tokens_per_s"), float),
        (caps, report),
    )
    check("onboard: a digest the build extends is no change", not got.get("history"), got.get("history"))
    check(
        "onboard: the build's full digest and checked_at are written",
        got["deployments"][0]["digest"].startswith("abc123def456")
        and len(got["deployments"][0]["digest"]) == 64
        and got["deployments"][0].get("checked_at"),
        got["deployments"][0],
    )
    check(
        "onboard: the onboarding is recorded as pass, in the deployment",
        (got["deployments"][0].get("onboarding") or {}).get("status") == "pass" and "onboarding" not in got,
    )
    check("onboard: the settings are never changed", got["settings"] == rec["settings"])

    rec2 = {**rec, "settings": {}}
    f.write_text(yaml.safe_dump(rec2))
    run = subprocess.run(
        [sys.executable, str(HERE / "scripts" / "model_onboard.py"), "fake-1b", "--deployment", "here"],
        capture_output=True,
        text=True,
        env=env,
    )
    out = run.stdout + run.stderr
    check(
        "onboard: a reasoning model with no reasoning setting is flagged",
        run.returncode == 1
        and "reasoning: it reasons by default and the record sets no reasoning_effort" in out,
        out[-600:],
    )
    rec3 = {**rec, "deployments": [{**rec["deployments"][0], "digest": "ffffffffffff"}]}
    f.write_text(yaml.safe_dump(rec3))
    run = subprocess.run(
        [sys.executable, str(HERE / "scripts" / "model_onboard.py"), "fake-1b", "--deployment", "here"],
        capture_output=True,
        text=True,
        env=env,
    )
    check(
        "onboard: a build the server serves differently is flagged",
        run.returncode == 1 and "build: here serves abc123def456" in run.stdout,
        run.stdout[-600:],
    )
    got3 = yaml.safe_load(f.read_text())
    hist = got3.get("history") or []
    check(
        "onboard: the record takes the build it found, and its history keeps the one replaced",
        got3["deployments"][0]["digest"].startswith("abc123def456")
        and len(hist) == 1
        and hist[0]["what"] == "deployment here: digest"
        and hist[0]["from"] == "ffffffffffff"
        and hist[0]["to"].startswith("abc123def456"),
        hist,
    )

    other = {**rec["deployments"][0], "id": "there", "where": "there"}
    f.write_text(yaml.safe_dump({**rec, "deployments": [rec["deployments"][0], other]}))
    run = subprocess.run(
        [sys.executable, str(HERE / "scripts" / "model_onboard.py"), "fake-1b"],
        capture_output=True,
        text=True,
        env=env,
    )
    check(
        "onboard: with two deployments one must be named",
        run.returncode != 0 and "--deployment: one of here, there" in run.stdout + run.stderr,
        (run.stdout + run.stderr)[-400:],
    )
    run = subprocess.run(
        [sys.executable, str(HERE / "scripts" / "model_onboard.py"), "fake-1b", "--deployment", "there"],
        capture_output=True,
        text=True,
        env=env,
    )
    got = yaml.safe_load(f.read_text())
    deps = {d["id"]: d for d in got["deployments"]}
    check(
        "onboard: --deployment writes the onboarding into that deployment only",
        deps["there"].get("onboarding", {}).get("status") in ("pass", "check")
        and "onboarding" not in deps["here"]
        and "checked_at" in deps["there"]
        and "checked_at" not in deps["here"],
        {k: sorted(v) for k, v in deps.items()},
    )

srv.shutdown()
sys.exit(summary())
