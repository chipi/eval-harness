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

import hashlib
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
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
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
        if "rebuilt when the data changes" in line:
            break
    return p, port, lines


try:
    r = evh("init", "--store", "files", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    notes = "id,text,label,words\nn1,first note,a,2\nn2,second note,b,2\nn3,third note,a,2\n"
    (proj / "notes.csv").write_text(notes)
    col = lambda c: {"fileObject": {"@id": "notes.csv"}, "extract": {"column": c}}  # noqa: E731
    (proj / "croissant.json").write_text(json.dumps({
        "@type": "sc:Dataset", "name": "notes",
        "distribution": [{"@type": "cr:FileObject", "@id": "notes.csv", "contentUrl": "notes.csv",
                          "encodingFormat": "text/csv", "sha256": hashlib.sha256(notes.encode()).hexdigest()}],
        "recordSet": [{"@type": "cr:RecordSet", "name": "default", "field": [
            {"name": f"default/{c}", "dataType": t, "source": col(c)}
            for c, t in (("id", "sc:Text"), ("text", "sc:Text"), ("label", "sc:Text"), ("words", "sc:Integer"))
        ]}],
    }))  # fmt: skip
    (proj / "data" / "systems" / "one_v1.yaml").write_text(
        "system_id: one_v1\nparams:\n  provider: echo\n  sentences: 1\n"
    )
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the test", "--by", "t"),
        ("run", "--system", "one_v1", "--dataset", "tk_v1"),
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
            # step 2 (UXS-005): a dataset from a source (a Croissant description in the project, offline), previewed with
            # its answers, its fields proposed and kept, made as a job with its field set and its answers' label set,
            # added to the goal with its role
            page.click("text=Add a dataset")
            page.wait_for_selector("h1:has-text('Add a dataset')", timeout=20000)
            page.select_option("#ds-source", "croissant")
            page.wait_for_selector("#dsq-path", timeout=20000)
            for k, v in (
                ("path", "croissant.json"),
                ("record_set", "default"),
                ("text", "text"),
                ("id", "id"),
                ("answer", "label"),
            ):
                page.fill(f"#dsq-{k}", v)
            page.fill("#ds-by", "tester")
            page.click("#ds-read")
            page.wait_for_selector("#ds-read-out td:has-text('n1')", timeout=60000)
            check(
                "Read it: a source-preview job shows the source's first items with their answers, nothing written",
                "first note" in page.locator("#ds-read-out").inner_text()
                and page.locator("#ds-read-out tbody tr:first-child td:last-child").inner_text().strip()
                == "a"
                and not (proj / "data" / "datasets" / "notes_v1.json").exists(),
                page.locator("#ds-read-out").inner_text()[:300],
            )
            page.click("#ds-fields")
            page.wait_for_selector("#ds-fields-out td:has-text('words')", timeout=60000)
            check(
                "Propose its fields: a fieldset-propose job proposes words (an integer); the text, id and answer are not fields",
                [t.strip() for t in page.locator("#ds-fields-out td.mono").all_inner_texts()] == ["words"],
                page.locator("#ds-fields-out").inner_text(),
            )
            page.fill("#ds-id", "notes_v1")
            page.check("input[name=ds-role][value=validation]")
            page.reload()
            page.wait_for_selector("#dsq-path", timeout=20000)
            check(
                "the dataset's choices are longer work: marked, and kept across a reload in this browser (the fields too)",
                page.input_value("#dsq-path") == "croissant.json"
                and page.input_value("#ds-id") == "notes_v1"
                and page.locator("#ds-fields-out td:has-text('words')").count() == 1
                and page.locator("[data-form=dataset-new] [data-unsent-mark]").is_visible()
                and page.locator("#ds-make").inner_text() == "Make dataset notes_v1",
                (
                    page.input_value("#dsq-path"),
                    page.input_value("#ds-id"),
                    page.locator("#ds-make").inner_text(),
                ),
            )
            page.click("#ds-make")
            page.wait_for_selector("h1:has-text('Ticket summaries')", timeout=60000)
            g = yaml.safe_load((proj / "data" / "goals" / "tickets_summary.yaml").read_text())
            made = (
                json.loads((proj / "data" / "datasets" / "notes_v1.json").read_text())
                if (proj / "data" / "datasets" / "notes_v1.json").is_file()
                else {}
            )
            check(
                "Make the dataset: its field set (the kept fields), dataset-create with them and its answers' label set, then the "
                "goal names it with its role; the draft is gone",
                (proj / "data" / "fields" / "notes_v1.yaml").is_file()
                and [it.get("fields") for it in made.get("items", [])][:1] == [{"words": 2}]
                and (proj / "data" / "labels" / "notes_v1" / "answers" / "labels.json").is_file()
                and {"dataset_id": "notes_v1", "role": "validation"} in (g.get("datasets") or [])
                and page.evaluate("localStorage.getItem('evh.draft.dataset.tickets_summary')") is None
                and "notes_v1" in page.locator("main").inner_text(),
                (g.get("datasets"), made.get("items", [])[:1], page.locator("main").inner_text()[:300]),
            )
            # step 1 (UXS-005): a goal made from the home, a bad id refused on the page, then changed
            page.goto(f"http://127.0.0.1:{port}/workbench/#home")
            page.click("text=New goal")
            page.wait_for_selector("h1:has-text('Set the goal')", timeout=20000)
            page.fill("#gf-title", "Notes triage")
            id_from_title = page.input_value("#gf-id")
            page.fill("#gf-id", "Bad Id")
            page.fill("#gf-statement", "Sort a note into its kind, for the person reading the queue.")
            page.fill("#gf-decision", "Which system sorts notes well enough to use.")
            page.fill("#gf-measure", "overlap_f1")
            page.fill("#gf-by", "tester")
            page.click("#gf-save")
            page.wait_for_selector("#gf-out [role=alert]", timeout=20000)
            check(
                "the goal's id is made from its title; one the model refuses is said on the page, nothing made",
                id_from_title == "notes_triage"
                and not (proj / "data" / "goals" / "Bad Id.yaml").exists()
                and page.locator("h1:has-text('Set the goal')").is_visible(),
                (id_from_title, page.locator("#gf-out").inner_text()[:300]),
            )
            page.fill("#gf-id", "notes_triage")
            check(
                "the goal form's button names what it will write",
                page.locator("#gf-save").inner_text() == "Make goal notes_triage",
                page.locator("#gf-save").inner_text(),
            )
            page.click("#gf-save")
            page.wait_for_selector("h1:has-text('Notes triage')", timeout=20000)
            made = yaml.safe_load((proj / "data" / "goals" / "notes_triage.yaml").read_text())
            check(
                "Make the goal: goal-new with its five things, no dataset yet, the winner rule balanced",
                made.get("title") == "Notes triage"
                and made["success_criteria"]["primary"] == {"measure": "overlap_f1", "direction": "higher"}
                and made["success_criteria"].get("strategy") == "balanced"
                and made.get("datasets") == [],
                made,
            )
            page.click("text=Edit the goal")
            page.wait_for_selector("h1:has-text('The goal')", timeout=20000)
            page.fill("#gf-decision", "Which system sorts notes well enough to use, at what cost.")
            page.fill("#gf-by", "tester")
            page.click("#gf-save")
            page.wait_for_selector("h1:has-text('Notes triage')", timeout=20000)
            changed = yaml.safe_load((proj / "data" / "goals" / "notes_triage.yaml").read_text())
            goal_hist = (proj / "data" / "history" / "goals" / "notes_triage.jsonl").read_text().splitlines()
            last = json.loads(goal_hist[-1])
            check(
                "Edit the goal: goal-set saves the change (the decision), the rest kept, recorded with who made it",
                changed.get("decision") == "Which system sorts notes well enough to use, at what cost."
                and changed.get("title") == "Notes triage"
                and last.get("by") == "person:tester"
                and (last.get("was") or {}).get("decision") == "Which system sorts notes well enough to use.",
                (changed.get("decision"), last),
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#prepare")
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
            # unsent changes (UXS-005, owner 2026-11-17): marked, the button says what it writes, leaving asks
            unsent_mark = page.locator("[data-form=model-new] [data-unsent-mark]")
            check(
                "a form with unsent changes is marked, and its button names what it will write",
                unsent_mark.is_visible() and page.locator("#nm-save").inner_text() == "Make model Bad Id",
                (unsent_mark.is_visible(), page.locator("#nm-save").inner_text()),
            )
            dialogs: list[str] = []

            def stay(d) -> None:
                dialogs.append(d.message)
                d.dismiss()

            page.on("dialog", stay)
            page.click("a.btn:has-text('The models')")
            page.wait_for_timeout(500)
            check(
                "leaving it asks first, naming what is not saved; staying keeps the screen and what was typed",
                len(dialogs) == 1
                and "Make model Bad Id" in dialogs[0]
                and page.locator("h1:has-text('Bring in a model')").is_visible()
                and page.input_value("#nm-aliases") == "fake:1b",
                (dialogs, page.url),
            )
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
            check(
                "once saved the form holds nothing: going on to the model's page asked nothing more",
                len(dialogs) == 1 and not unsent_mark.count(),
                dialogs,
            )
            page.fill("#dep-id", "here")
            page.evaluate("window.WB.render()")  # a redraw, as a job's poll or a read coming back does
            check(
                "a form with unsent changes is not redrawn under the person: what was typed stays",
                page.input_value("#dep-id") == "here"
                and page.locator("[data-form=dep-add] [data-unsent-mark]").is_visible()
                and page.locator("#dep-add").inner_text() == "Add deployment here",
                (page.input_value("#dep-id"), page.locator("#dep-add").inner_text()),
            )
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
