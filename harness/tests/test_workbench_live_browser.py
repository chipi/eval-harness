#!/usr/bin/env python3
"""The Workbench on its server (RFC-032 step 1): catalog-serve serves it under /workbench/, and it reads the project
through the model's API.

    python tests/test_workbench_live_browser.py

In a project with a goal, a dataset, its reference and a run: the startup prints the link that signs in; through it the
home lists the project's goal with the next step its status names; the goal's screen shows its dataset as the API
says; a screen not wired yet says so instead of showing the mockup's data; a browser with no cookie is asked to sign
in; at a phone's width nothing scrolls sideways; and a public server has no /workbench/.

The models (step 2): a model brought in through the form is made by the model's API with who made it, and a bad id is
refused on the page; a deployment added on its page points at a fake OpenAI-shaped server; "Run the probes" starts
model-onboard as a job, the page follows it and shows the onboarding's flag; accepting it with why keeps the decision
in the deployment's checks; the model's page fits a phone.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wblive-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-wb-live",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)
env["OPENAI_API_KEY"] = "local"  # the fake server's; the onboarding job inherits the server's environment


class Fake(http.server.BaseHTTPRequestHandler):
    """An OpenAI-shaped server whose model reasons unless told not to: its onboarding is flagged."""

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
        msg = {"role": "assistant", "content": '{"answer": "yes", "reason": "17 has no divisors"}'}
        if body.get("reasoning_effort") != "none":
            msg["reasoning"] = "Let me think. 17 divided by 2, 3, 5 ... prime."
        self._send({"id": "x", "object": "chat.completion", "created": 0, "model": "fake:1b",
                    "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 60, "total_tokens": 100}})  # fmt: skip

    def log_message(self, *a):
        pass


fake = http.server.HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def serve(*extra: str) -> tuple[subprocess.Popen, int, list[str]]:
    """catalog-serve on a free port; its startup lines once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port), *extra], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    lines: list[str] = []
    assert p.stdout is not None
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    if "--public" in extra:
        return p, port, lines
    while line := p.stdout.readline():  # the startup's lines, up to its last
        lines.append(line.rstrip())
        if "reads the runs once" in line:
            break
    return p, port, lines


try:
    r = evh("init", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "data" / "configs" / "one_v1.yaml").write_text(
        "config_id: one_v1\ndataset_id: tk_v1\nparams:\n  provider: echo\n  sentences: 1\n"
    )
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the test", "--by", "t"),
        ("run", "--config", "data/configs/one_v1.yaml"),
        ("goal-new", "tickets_summary", "--set", "title=Ticket summaries", "--set", "statement=A one-line summary of a ticket.",
         "--set", "decision=Which system writes it.", "--set", "success_criteria.primary.measure=overlap_f1",
         "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=tk_v1", "--set", "datasets.0.role=test"),
        ("catalog",),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    check(
        "setup: a goal, its dataset, reference and run, and the catalog",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = next(
            (
                m.group(0)
                for ln in lines
                if (m := re.search(r"http://\S+/api/v1/session\?token=\S+&next=/workbench/", ln))
            ),
            None,
        )
        check("the startup prints the Workbench's sign-in link", link is not None, lines)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("table >> text=Ticket summaries", timeout=20000)
            page.wait_for_function(
                "() => !document.querySelector('main').textContent.includes('…')", timeout=20000
            )
            home = page.locator("main").inner_text()
            check(
                "the home lists the project's goal and the next step its status names, read through the API",
                "Ticket summaries" in home
                and "promote a baseline on tk_v1" in home
                and "Nothing is running." in home
                and not errors,
                (home[:400], errors[:2]),
            )
            page.click("text=Ticket summaries")
            page.wait_for_selector("h1:has-text('Ticket summaries')", timeout=20000)
            goal = page.locator("main").inner_text()
            check(
                "the goal's screen shows its dataset, reference and run as the API says",
                "tk_v1" in goal
                and "gold/tk_v1" in goal
                and "1 run(s)" in goal
                and "promote a baseline on tk_v1" in goal,
                goal[:500],
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#dataset")
            page.wait_for_selector("h1", timeout=20000)
            check(
                "a screen not wired yet says so, and shows none of the mockup's data",
                "This screen comes later" in page.locator("main").inner_text()
                and "cnn_dailymail" not in page.content(),
                page.locator("main").inner_text()[:200],
            )
            # the models: bring one in, add where it runs, onboard it as a job, accept what it raises
            page.goto(f"http://127.0.0.1:{port}/workbench/#models")
            page.wait_for_selector("text=No models yet.", timeout=20000)
            page.click("text=Bring in a model")
            page.wait_for_selector("h1:has-text('Bring in a model')", timeout=20000)
            page.fill("#nm-id", "Bad Id")
            page.fill("#nm-aliases", "fake:1b")
            page.fill("#nm-by", "tester")
            page.click("#nm-save")
            page.wait_for_selector("#nm-out [role=alert]", timeout=20000)
            check(
                "a model id the model refuses is said on the page, and nothing is made",
                "is not a model id" in page.locator("#nm-out").inner_text()
                and not any((proj / "data" / "models").glob("*.yaml")),
                page.locator("#nm-out").inner_text()[:300],
            )
            page.fill("#nm-id", "fake-1b")
            page.check("input[name=nm-weights][value=open]")
            page.click("#nm-save")
            page.wait_for_selector("h1:has-text('fake-1b')", timeout=20000)
            hist = list((proj / "data" / "history" / "models").glob("fake-1b.jsonl"))
            check(
                "the form makes the model through the API, recorded as who made it",
                (proj / "data" / "models" / "fake-1b.yaml").is_file()
                and bool(hist)
                and '"person:tester"' in hist[0].read_text(),
                page.locator("main").inner_text()[:300],
            )
            page.fill("#dep-id", "here")
            page.fill("#dep-where", "here")
            page.fill("#dep-tag", "fake:1b")
            page.fill("#dep-url", f"http://127.0.0.1:{fake.server_port}/v1")
            page.click("#dep-add")
            page.wait_for_selector("h2:has-text('here')", timeout=20000)
            page.fill("#cap-here", "0.01")
            page.click("[data-onboard=here]")
            page.wait_for_selector("text=Accept what it raises", timeout=120000)
            shown = page.locator("main").inner_text()
            check(
                "Run the probes starts model-onboard as a job; the page follows it and shows the onboarding's flag",
                "reasoning" in shown and "The probes found something to read" in shown and not errors,
                (shown[:800], errors[:2]),
            )
            if shots := os.environ.get("EVH_WB_SHOTS"):
                page.screenshot(path=f"{shots}/desk-model.png", full_page=True)
            page.fill("#flag-here", "reasoning")
            page.fill("#why-here", "it reasons by default and this task is fine with it")
            page.fill("#by-here", "tester")
            page.click("[data-accept=here]")
            page.locator("text=Accepted as this deployment's nature").or_(
                page.locator("#acc-here [role=alert]")
            ).first.wait_for(timeout=20000)
            dep = yaml.safe_load((proj / "data" / "deployments" / "fake-1b" / "here.yaml").read_text())
            kinds = [c.get("kind") for c in dep.get("checks") or []]
            check(
                "accepting it with why keeps the decision in the deployment's checks, with who made it",
                kinds == ["onboarding", "approval"]
                and dep["checks"][-1].get("by") == "person:tester"
                and dep.get("accepted", {}).get("reasoning", "").startswith("it reasons by default"),
                (dep, page.locator("main").inner_text()[-600:]),
            )
            phone = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                storage_state=page.context.storage_state(),
            ).new_page()
            phone.goto(f"http://127.0.0.1:{port}/workbench/#home")
            phone.wait_for_selector("table >> text=Ticket summaries", timeout=20000)
            over = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check("at a phone's width the home does not scroll sideways", over <= 0, over)
            wide = {}
            for screen, h1 in (
                ("models", "Models in this project"),
                ("model/fake-1b", "fake-1b"),
                ("model-new", "Bring in a model"),
            ):
                phone.goto(f"http://127.0.0.1:{port}/workbench/#{screen}")
                phone.wait_for_selector(f"h1:has-text('{h1}')", timeout=20000)
                if shots := os.environ.get("EVH_WB_SHOTS"):
                    phone.screenshot(path=f"{shots}/phone-{screen.replace('/', '-')}.png", full_page=True)
                wide[screen] = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(
                "at a phone's width the models' screens do not scroll sideways",
                all(v <= 0 for v in wide.values()),
                wide,
            )
            stranger = browser.new_context().new_page()
            stranger.goto(f"http://127.0.0.1:{port}/workbench/")
            stranger.wait_for_selector("h1:has-text('Sign in')", timeout=20000)
            check(
                "a browser with no cookie is asked to sign in, and reads nothing",
                "Ticket summaries" not in stranger.content(),
            )
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)

    pub, pport, _ = serve("--public", "evals.example")
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{pport}/workbench/", headers={"Host": "evals.example"}
        )
        try:
            code = urllib.request.urlopen(req, timeout=30).status  # noqa: S310 - the test's own server  # nosec B310
        except urllib.error.HTTPError as exc:
            code = exc.code
        check("a public server has no /workbench/", code == 404, code)
    finally:
        pub.terminate()
        pub.wait(timeout=20)
finally:
    fake.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
