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
            # step 3 (UXS-005): fetch, look inside, promote the answers the data came with; then label it here, the
            # sheet submitted when done (owner, 2026-11-17)
            page.goto(f"http://127.0.0.1:{port}/workbench/#prepare/notes_v1")
            page.wait_for_selector("h1:has-text('Prepare the dataset')", timeout=20000)
            page.fill("#pp-by", "tester")
            if page.locator("#pp-fetch").count():
                page.click("#pp-fetch")
                page.wait_for_selector("#pp-look:not([disabled])", timeout=60000)
            page.fill("#pp-by", "tester")
            page.click("#pp-look")
            page.wait_for_selector("a:has-text('Open its page in the catalog')", timeout=60000)
            check(
                "fetch and look inside: dataset-materialize and dataset-profile as jobs, each step then marked done",
                (proj / "data" / "materialized" / "notes_v1").is_dir()
                and (proj / "data" / "profiles" / "notes_v1.json").is_file(),
                page.locator("main").inner_text()[:400],
            )
            page.select_option("#pt-answers", "gold")
            page.fill("#pr-answers", "the labels the notes came with")
            page.fill("#pp-by", "tester")
            page.click("[data-promote=answers]")
            page.wait_for_selector("li:has-text('gold/notes_v1')", timeout=60000)
            check(
                "promote the answers the data came with: reference-promote as a job, the gold reference listed",
                any("notes_v1" in x.name for x in (proj / "data" / "references" / "gold").iterdir()),
                page.locator("main").inner_text()[:400],
            )
            page.click("text=Label it here")
            page.wait_for_selector("h1:has-text('Label the items')", timeout=20000)
            page.check("input[name=lb-items][value=all]")
            page.fill("#lb-by", "tester")
            page.click("#lb-make")
            page.wait_for_selector("[data-answer=n1]", timeout=60000)
            check(
                "a sheet with no answer yet holds nothing to lose: no mark, Submit off",
                not page.locator("[data-form=label-sheet] [data-unsent-mark]").is_visible()
                and page.locator("#lb-submit").is_disabled(),
                page.locator("#lb-submit").inner_text(),
            )
            page.fill("[data-answer=n1]", "a")
            page.fill("[data-answer=n2]", "b")
            page.fill("#lb-set", "tester_pass")
            page.reload()
            page.wait_for_selector("[data-answer=n1]", timeout=20000)
            check(
                "the sheet's answers are kept in this browser across a reload, counted, Submit naming what it writes",
                page.input_value("[data-answer=n1]") == "a"
                and page.locator("#lb-count").inner_text() == "2"
                and page.locator("#lb-submit").inner_text() == "Submit 2 answer(s) as label set tester_pass"
                and not (proj / "data" / "labels" / "notes_v1" / "tester_pass").exists(),
                (page.input_value("[data-answer=n1]"), page.locator("#lb-submit").inner_text()),
            )
            page.fill("#lb-by", "tester")
            page.click("#lb-submit")
            page.wait_for_selector("text=Written: label set", timeout=60000)
            lab = json.loads(
                (proj / "data" / "labels" / "notes_v1" / "tester_pass" / "labels.json").read_text()
            )
            check(
                "Submit: label-import writes the label set from the filled sheet (2 labels, a person's), the sheet dropped",
                lab.get("n_items") == 2
                and lab.get("source", {}).get("kind") == "person"
                and (proj / "data" / "labels" / "notes_v1" / "tester_pass" / "n2.txt").read_text().strip()
                == "b"
                and page.evaluate("localStorage.getItem('evh.draft.label.notes_v1')") is None,
                lab,
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#judge")
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
            # step 4 (UXS-005): a system made from a model where it runs, then checked on three items
            page.goto(f"http://127.0.0.1:{port}/workbench/#systems/tickets_summary")
            page.wait_for_selector("h1:has-text('Choose the systems')", timeout=20000)
            page.select_option("#sn-model", "fake-1b")
            page.wait_for_selector("#sn-dep", timeout=20000)
            page.fill("#sn-prompt", "Summarise the ticket in one line:")
            page.fill("#sn-max", "50")
            page.fill("#sn-by", "tester")
            check(
                "the system's id is made from the model and where it runs, the button names what it writes",
                page.input_value("#sn-id") == "fake-1b_here"
                and page.locator("#sn-make").inner_text() == "Make system fake-1b_here",
                (page.input_value("#sn-id"), page.locator("#sn-make").inner_text()),
            )
            page.click("#sn-make")
            page.wait_for_selector("td.mono:has-text('fake-1b_here')", timeout=20000)
            sysrec = yaml.safe_load((proj / "data" / "systems" / "fake-1b_here.yaml").read_text())
            check(
                "Make the system: system-new names the model record and the deployment, and carries its endpoint and settings",
                sysrec.get("model_record") == "fake-1b"
                and sysrec.get("deployment") == "here"
                and sysrec["params"].get("provider") == "openai"
                and sysrec["params"].get("base_url") == f"http://127.0.0.1:{fake.server_port}/v1"
                and sysrec["params"].get("prompt") == "Summarise the ticket in one line:"
                and sysrec["params"].get("max_tokens") == 50
                and sysrec["params"].get("temperature") == 0,
                sysrec,
            )
            check(
                "the system's prompt is recorded as a prompt version beside it, for its history (owner, 2026-11-17)",
                (proj / "data" / "prompts" / "fake-1b_here").is_dir()
                and any((proj / "data" / "prompts" / "fake-1b_here").iterdir()),
                sorted(x.name for x in (proj / "data" / "prompts").iterdir())
                if (proj / "data" / "prompts").is_dir()
                else [],
            )
            page.select_option("#sm-ds", "tk_v1")
            page.fill("#sm-cap", "0.01")
            page.fill("#sm-by", "tester")
            page.click("[data-smoke='fake-1b_here']")
            page.wait_for_selector("#sm-fake-1b_here details", timeout=120000)
            dep_doc = yaml.safe_load((proj / "data" / "deployments" / "fake-1b" / "here.yaml").read_text())
            check(
                "Check it on three items: arm-smoke as a job, its status, cost and projection, a reply per item; kept as the "
                "deployment's check",
                page.locator("#sm-fake-1b_here details").count() == 3
                and "all " in page.locator("#sm-fake-1b_here").inner_text()
                and any(
                    c.get("kind") == "smoke" and c.get("system") == "fake-1b_here"
                    for c in dep_doc.get("checks") or []
                ),
                (
                    page.locator("#sm-fake-1b_here").inner_text()[:400],
                    [c.get("kind") for c in dep_doc.get("checks") or []],
                ),
            )
            page.click("[data-clone='fake-1b_here']")
            page.fill("#cl-id-fake-1b_here", "fake-1b_here_t05")
            page.select_option("#cl-what-fake-1b_here", "temperature")
            page.fill("#cl-val-fake-1b_here", "0.5")
            page.click("#cl-go-fake-1b_here")
            page.wait_for_selector("td.mono:has-text('fake-1b_here_t05')", timeout=20000)
            clone = yaml.safe_load((proj / "data" / "systems" / "fake-1b_here_t05.yaml").read_text())
            check(
                "Clone it, change one thing: a new system, the temperature changed and everything else as the original's",
                clone["params"].get("temperature") == 0.5
                and {k: v for k, v in clone["params"].items() if k != "temperature"}
                == {k: v for k, v in sysrec["params"].items() if k != "temperature"}
                and clone.get("model_record") == "fake-1b"
                and clone.get("deployment") == "here",
                clone,
            )
            # W1 the eval (UXS-005 step 5): a round opened with its question, two arms run as one sweep, the evidence
            # read, one arm retired with its reason, the round closed with its conclusion and the leader promoted
            page.goto(f"http://127.0.0.1:{port}/workbench/#eval/tickets_summary")
            page.wait_for_selector("#ro-q", timeout=20000)
            page.fill("#ro-q", "Does the fake model summarise a ticket as well as the echo arm?")
            page.select_option("#ro-ds", "tk_v1")
            page.fill("#ro-by", "tester")
            page.click("#ro-open")
            page.wait_for_selector("[data-run]", timeout=60000)
            rnd = yaml.safe_load((proj / "data" / "rounds" / "tickets_summary" / "r1.yaml").read_text())
            check(
                "Open the round: round-open as a job, its question kept as the hypothesis, the round open",
                rnd.get("status") == "open"
                and rnd.get("hypothesis") == "Does the fake model summarise a ticket as well as the echo arm?"
                and "Does the fake model" in page.locator("main h2").first.inner_text(),
                rnd,
            )
            page.check("[data-run='one_v1']")
            page.check("[data-run='fake-1b_here']")
            page.click("#rn-est")
            page.wait_for_selector("#rn-out pre, #rn-out [role=alert]", timeout=60000)
            check(
                "See the cost first: the sweep's dry run (POST /estimate), nothing run",
                page.locator("#rn-out pre").count() == 1
                and not list((proj / "data" / "runs").glob("fake-1b_here_*")),
                page.locator("#rn-out").inner_text()[:300],
            )
            page.fill("#rn-cap", "0.05")
            page.fill("#ev-by", "tester")
            page.click("#rn-go")
            try:
                page.wait_for_selector("#arms li:has-text('fake-1b_here')", timeout=180000)
            except Exception:
                print(
                    "RUN-OUT",
                    page.locator("#rn-out").inner_text()[:600],
                    page.locator("main").inner_text()[:800],
                )
                raise
            rnd = yaml.safe_load((proj / "data" / "rounds" / "tickets_summary" / "r1.yaml").read_text())
            check(
                "Run them: one sweep job runs both in the round; each joins the round as an arm and the evidence reads them",
                {a["system"] for a in rnd.get("arms") or []} >= {"one_v1", "fake-1b_here"}
                and page.locator("main th:has-text('threshold')").count() == 1,
                (rnd.get("arms"), page.locator("main").inner_text()[:600]),
            )
            check(
                "the evidence's chart: each arm's mean against its cost, a point per arm",
                page.locator("figure.chart circle").count() == 2,
                page.locator("figure.chart").count(),
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#systems/tickets_summary")
            page.wait_for_selector("#sn-model", timeout=20000)
            offered = page.locator("#sn-model option[value='fake-1b']").inner_text()
            check(
                "a model whose arm is in play on the goal is offered with its rank there (a retired arm has none)",
                "on this goal" in offered and "#" in offered,
                offered,
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#eval/tickets_summary/r1")
            page.wait_for_selector("[data-retire='fake-1b_here']", timeout=20000)
            page.fill("#ev-by", "tester")
            page.click("[data-retire='fake-1b_here']")
            page.fill("#rt-why", "it repeats one fixed answer whatever the ticket says")
            page.click("#rt-go")
            page.wait_for_selector("li:has-text('fake-1b_here') .status:has-text('retired')", timeout=60000)
            rnd = yaml.safe_load((proj / "data" / "rounds" / "tickets_summary" / "r1.yaml").read_text())
            gone: dict = next((a for a in rnd["arms"] if a["system"] == "fake-1b_here"), {})
            check(
                "Retire: round-retire with its reason, final, kept on the arm",
                (gone.get("retired") or {}).get("reason")
                == "it repeats one fixed answer whatever the ticket says"
                and page.locator("[data-retire='fake-1b_here']").count() == 0,
                gone,
            )
            page.remove_listener("dialog", stay)
            page.once("dialog", lambda d: d.accept())
            page.fill(
                "#rc-text", "The echo arm is the one to keep for this test; the fake model was retired."
            )
            page.check("#rc-promote")
            page.fill("#ev-by", "tester")
            page.click("#rc-close")
            try:
                page.wait_for_selector(".answer .kicker:has-text('its conclusion')", timeout=60000)
            except Exception:
                print("RC-OUT", page.locator("#rc-out").inner_text()[:600])
                raise
            rnd = yaml.safe_load((proj / "data" / "rounds" / "tickets_summary" / "r1.yaml").read_text())
            base = list((proj / "data" / "baselines" / "tickets_summary" / "tk_v1").glob("*.json"))
            check(
                "Close the round: round-close with its conclusion, the leader's run promoted to the goal's baseline",
                rnd.get("status") == "closed"
                and (rnd.get("conclusion") or {})
                .get("text", "")
                .startswith("The echo arm is the one to keep")
                and bool(base),
                (rnd.get("status"), rnd.get("conclusion"), base),
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#eval/tickets_summary")
            page.wait_for_selector("#ro-q", timeout=20000)
            page.fill("#ro-q", "Is the echo arm as good when carried into the next round?")
            page.select_option("#ro-keep", "")
            page.fill("#ro-by", "tester")
            page.click("#ro-open")
            page.wait_for_selector("#cy-arm", timeout=60000)
            page.select_option("#cy-arm", "one_v1")
            page.fill("#ev-by", "tester")
            page.click("#cy-go")
            page.wait_for_selector("#arms li:has-text('one_v1')", timeout=60000)
            r2 = yaml.safe_load((proj / "data" / "rounds" / "tickets_summary" / "r2.yaml").read_text())
            carried: dict = next((a for a in r2.get("arms") or [] if a["system"] == "one_v1"), {})
            check(
                "Carry it in: round-carry brings an arm of the round before into the open round, unchanged",
                (carried.get("entered") or {}).get("how") == "carried",
                r2.get("arms"),
            )
            fake_run = sorted(x.name for x in (proj / "data" / "runs").glob("fake-1b_here_*"))[-1]
            r = evh(
                "run-promote",
                "--run",
                fake_run,
                "--goal",
                "tickets_summary",
                "--reason",
                "a second version for the rollback",
                "--by",
                "t",
                "--override-no-evidence",  # tk_v1 is a test set of 6 items: no promotion can be shown on it
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#eval/tickets_summary/r2")
            page.reload()  # the same address: reload, so the page reads the promotion made on the command line
            page.wait_for_selector("[data-rollback='1']", timeout=20000)
            page.fill("#rb-why-1", "the first baseline was the one the round decided")
            page.fill("#ev-by", "tester")
            page.click("[data-rollback='1']")
            page.wait_for_selector("li:has-text('v3') .status:has-text('current')", timeout=60000)
            vers = sorted(
                int(x.stem)
                for x in (proj / "data" / "baselines" / "tickets_summary" / "tk_v1").glob("*.json")
            )
            v3 = (
                json.loads((proj / "data" / "baselines" / "tickets_summary" / "tk_v1" / "3.json").read_text())
                if 3 in vers
                else {}
            )
            check(
                "Roll back: baseline-rollback restores v1 as a new version (v3) with its reason; the history kept",
                r.returncode == 0
                and vers == [1, 2, 3]
                and "the first baseline was the one" in json.dumps(v3),
                (r.stderr[-200:], vers, json.dumps(v3)[:300]),
            )
            # W2 (UXS-005): which is better, blind, on a sheet submitted when done; then what went wrong, with a new list
            page.goto(f"http://127.0.0.1:{port}/workbench/#review/tickets_summary")
            page.wait_for_selector("#rv-make", timeout=20000)
            page.select_option("#rv-ds", "tk_v1")
            page.wait_for_selector("#rv-a option[value='fake-1b_here']", state="attached", timeout=20000)
            page.select_option("#rv-a", "one_v1")
            page.select_option("#rv-b", "fake-1b_here")
            page.fill("#rv-by", "tester")
            page.click("#rv-make")
            page.wait_for_selector("[data-pick='t01_login']", timeout=60000)
            table = page.locator("main table").inner_text()
            check(
                "Make the sheet: a blind sheet-export job; the page shows outputs A and B, never which arm is which",
                "one_v1" not in table
                and "fake-1b_here" not in table
                and page.locator("[data-pick]").count() >= 3,
                table[:300],
            )
            page.check("[data-pick='t01_login'][value='A']")
            page.check("[data-pick='t02_invoice'][value='B']")
            page.fill("#rv-name", "tester_picks")
            page.reload()
            page.wait_for_selector("[data-pick='t01_login']", timeout=20000)
            check(
                "the picks are kept in this browser across a reload, counted, Submit naming what it writes",
                page.is_checked("[data-pick='t01_login'][value='A']")
                and page.locator("#rv-count").inner_text() == "2"
                and page.locator("#rv-submit").inner_text()
                == "Submit 2 answer(s) as judgements tester_picks",
                page.locator("#rv-submit").inner_text(),
            )
            page.fill("#rv-by", "tester")
            page.click("#rv-submit")
            page.wait_for_selector("text=Written: the judgements", timeout=60000)
            judged = [
                x for x in (proj / "data" / "runs").iterdir() if (x / "scores" / "tester_picks@none").exists()
            ]
            check(
                "Submit: sheet-import reads the key the sheet-export job kept and writes judged scores under both arms' runs",
                len(judged) == 2
                and page.evaluate("localStorage.getItem('evh.draft.review.tickets_summary')") is None,
                [x.name for x in judged],
            )
            page.click("[data-again]")
            page.wait_for_selector("#rv-make", timeout=20000)
            page.select_option("#rv-ds", "tk_v1")
            page.wait_for_selector("#rv-a option[value='fake-1b_here']", state="attached", timeout=20000)
            page.select_option("#rv-a", "one_v1")
            page.select_option("#rv-b", "fake-1b_here")
            page.check("input[name=rv-mode][value=tags]")
            page.select_option("#rv-modes", "")
            page.fill("#rv-new-id", "tk_modes")
            page.fill("#rv-new-modes", "too-short, off-topic")
            page.fill("#rv-by", "tester")
            page.click("#rv-make")
            page.wait_for_selector("[data-tag='t01_login']", timeout=60000)
            page.locator("[data-tag='t01_login'][value='too-short']").first.check()
            page.fill("#rv-name", "tester_tags")
            page.fill("#rv-by", "tester")
            page.click("#rv-submit")
            page.wait_for_selector("text=Written: the tag set", timeout=60000)
            tags_doc = proj / "data" / "tags" / "tk_v1" / "tester_tags" / "tags.json"
            check(
                "what went wrong: a failure-mode list made here (failure-modes-new), a tag sheet, the tags written as a tag set",
                (proj / "data" / "failure-modes" / "tk_modes.yaml").is_file()
                and tags_doc.is_file()
                and "too-short" in tags_doc.read_text(),
                tags_doc.read_text()[:300] if tags_doc.is_file() else "no tag set",
            )
            # W3 (UXS-005): production's records captured, made a dataset, its decisions scored as an arm, the rows where
            # it was wrong against a label set picked, and the next version of a dataset made with them
            prod_rows = [
                {
                    "id": f"p{i}",
                    "body": f"ticket {i}: the customer cannot export a report",
                    "decision": "export" if i % 2 else "login",
                    "outcome": {"resolved": "fixed" if i <= 4 else "wontfix"},
                }
                for i in range(1, 7)
            ]
            (proj / "prod.jsonl").write_text("".join(json.dumps(r) + "\n" for r in prod_rows))
            page.goto(f"http://127.0.0.1:{port}/workbench/#production/tickets_summary")
            page.wait_for_selector("#cp-go", timeout=20000)
            page.fill("#pd-by", "tester")
            page.fill("#cp-id", "prod_2026_11")
            page.fill("#cp-query", json.dumps({"path": "prod.jsonl"}))
            page.click("#cp-go")
            page.wait_for_selector("li:has-text('prod_2026_11')", timeout=60000)
            page.fill("#cd-id", "prod_v1")
            page.click("#cd-go")
            page.wait_for_selector("li:has-text('made into prod_v1')", timeout=60000)
            check(
                "Capture them, make a dataset of it: capture and dataset-from-capture as jobs, the capture listed with it",
                (proj / "data" / "captures" / "prod_2026_11" / "capture.json").is_file()
                and len(json.loads((proj / "data" / "datasets" / "prod_v1.json").read_text())["items"]) == 6,
                page.locator("main").inner_text()[:400],
            )
            page.select_option("#ca-cap", "prod_2026_11")
            page.select_option("#ca-ds", "prod_v1")
            page.fill("#ca-as", "prod_arm_v1")
            page.fill("#ca-field", "decision")
            page.click("#ca-go")
            page.wait_for_selector("#wr-run option[value='prod_arm_v1']", state="attached", timeout=60000)
            check(
                "Score its decisions: arm-from-capture makes production's decisions an arm with a run on the dataset",
                (proj / "data" / "systems" / "prod_arm_v1.yaml").is_file()
                and any((proj / "data" / "runs").glob("prod_arm_v1_*")),
                sorted(x.name for x in (proj / "data" / "runs").glob("prod_arm_*")),
            )
            labels_dir = proj / "prod_labels"
            labels_dir.mkdir()
            for i in range(1, 7):
                (labels_dir / f"p{i}.txt").write_text("export")
            lr = evh(
                "label-import",
                "--sheet",
                "prod_labels",
                "--dataset-id",
                "prod_v1",
                "--set",
                "truth",
                "--by",
                "t",
            )
            page.select_option("#wr-ds", "prod_v1")
            page.select_option("#wr-run", "prod_arm_v1")
            page.fill("#wr-set", "truth")
            page.click("#wr-show")
            page.wait_for_selector("[data-keep-item]", timeout=60000)
            shown_items = page.locator("[data-keep-item]").evaluate_all(
                "els => els.map(e => e.dataset.keepItem)"
            )
            check(
                "Show where it was wrong: sheet-show's rows as values, only the items production decided against the label set",
                lr.returncode == 0 and sorted(shown_items) == ["p2", "p4", "p6"],
                (lr.stderr[-200:], shown_items),
            )
            page.check("[data-keep-item='p2']")
            page.check("[data-keep-item='p4']")
            page.fill("#pk-for", "tk_v1")
            page.fill("#pk-note", "production said login where the customer could not export")
            page.click("#pk-go")
            page.wait_for_selector(
                "[data-keep-item]", state="detached", timeout=60000
            )  # the pick job ended: the rows go
            picks = evh("picks", "--json")
            check(
                "Pick them: the checked rows are picked for tk_v1 with the reason",
                picks.returncode == 0
                and "p2" in picks.stdout
                and "p4" in picks.stdout
                and "p6" not in picks.stdout,
                picks.stdout[-400:],
            )
            page.select_option("#ex-from", "tk_v1")
            page.fill("#ex-id", "tk_v2")
            page.fill("#pd-by", "tester")
            page.click("#ex-go")
            page.wait_for_function(
                "() => !document.querySelector('#ex-out') || !document.querySelector('#ex-out').textContent.includes('running')",
                timeout=60000,
            )
            page.wait_for_timeout(1000)
            v2 = (
                json.loads((proj / "data" / "datasets" / "tk_v2.json").read_text())
                if (proj / "data" / "datasets" / "tk_v2.json").is_file()
                else {}
            )
            check(
                "Make the next version: dataset-extend makes tk_v2 from tk_v1's items and the picks waiting for it",
                len(v2.get("items", []))
                == len(json.loads((proj / "data" / "datasets" / "tk_v1.json").read_text())["items"]) + 2,
                (
                    len(v2.get("items", [])),
                    page.locator("#ex-out").inner_text() if page.locator("#ex-out").count() else "",
                ),
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#production/tickets_summary")
            page.wait_for_selector("#ol-go", timeout=20000)
            page.select_option("#ol-cap", "prod_2026_11")
            page.select_option("#ol-ds", "prod_v1")
            page.fill("#ol-set", "outcomes_v1")
            page.fill(
                "#ol-rules",
                "- when: {resolved: fixed}\n  label: export\n- when: {resolved: wontfix}\n  label: login\n",
            )
            page.fill("#pd-by", "tester")
            page.click("#ol-go")
            page.wait_for_selector("#ol-out table", timeout=60000)
            out_doc = proj / "data" / "labels" / "prod_v1" / "outcomes_v1" / "labels.json"
            olab = json.loads(out_doc.read_text()) if out_doc.is_file() else {}
            check(
                "Labels from what happened later: label-from-capture with the rules typed here, a rule label set, then its "
                "coverage read from the rules the job kept",
                olab.get("source", {}).get("kind") == "rule"
                and olab.get("n_items") == 6
                and "Written: label set" in page.locator("#ol-out").inner_text()
                and "export" in page.locator("#ol-out").inner_text()
                and "rule 1: label export" in page.locator("#ol-out").inner_text()
                and "labelled\t6" in page.locator("#ol-out").inner_text(),
                (olab.get("source"), page.locator("#ol-out").inner_text()[:500]),
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
                ("goal-new", "Set the goal"),
                ("dataset/tickets_summary", "Add a dataset"),
                ("prepare/notes_v1", "Prepare the dataset"),
                ("label/notes_v1", "Label the items"),
                ("systems/tickets_summary", "Choose the systems"),
                ("eval/tickets_summary/r1", "Its rounds"),
                ("review/tickets_summary", "Review the outputs"),
                ("production/tickets_summary", "Learn from production"),
            ):
                phone.goto(f"http://127.0.0.1:{port}/workbench/#{screen}")
                phone.wait_for_selector(f"h1:has-text('{h1}')", timeout=20000)
                if shots := os.environ.get("EVH_WB_SHOTS"):
                    phone.screenshot(path=f"{shots}/phone-{screen.replace('/', '-')}.png", full_page=True)
                wide[screen] = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(
                "at a phone's width the models' screens and steps 1 to 4, the eval, the review and production do not scroll sideways",
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
