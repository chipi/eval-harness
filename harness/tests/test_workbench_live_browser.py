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
env.pop("HF_TOKEN", None)
env.update(
    HF_HUB_OFFLINE="1", HF_HOME=str(proj / ".hf")
)  # W8's publish is refused offline, with no token of this machine


#: Seconds the fake waits before it answers: a run the jobs page stops is still running when it is stopped.
SLOW = {"s": 0.0}
#: What each call sent as its user message: a system pointing at a prompt version sends that text.
SENT: list[str] = []


class Fake(http.server.BaseHTTPRequestHandler):
    """An OpenAI-shaped server whose model reasons unless told not to: its onboarding is flagged."""

    def _send(self, doc):
        data = json.dumps(doc).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except BrokenPipeError:
            pass  # a run the jobs page stopped is killed mid-call: nobody reads this answer

    def do_GET(self):
        self._send({"models": [{"name": "fake:1b", "model": "fake:1b", "digest": "abc123def456" + "0" * 52}]})

    def do_POST(self):
        time.sleep(SLOW["s"])
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SENT.append(str(((body.get("messages") or [{}])[-1]).get("content") or ""))
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
            served = page.evaluate(
                "() => Promise.all(['mock.js', 'mockup.html', 'workflows.js', 'round5.js', 'live.js'].map((n) =>"
                " fetch('/workbench/' + n, {credentials: 'same-origin'}).then((r) => [n, r.status])))"
            )
            import tomllib
            from evaluation_harness.catalog_serve import WORKBENCH_FILES

            shipped = tomllib.loads((HARNESS / "pyproject.toml").read_text())["tool"]["setuptools"][
                "package-data"
            ]["evaluation_harness.workbench"]
            beside = sorted(
                x.name
                for x in (HARNESS / "workbench").iterdir()
                if x.is_file() and x.suffix in (".js", ".html", ".css", ".py")
            )
            check(
                "the package ships the live Workbench's files, the ones the server serves and nothing else of the folder: "
                "the frozen mockup is in workbench/mockup/, outside the package (D7)",
                set(shipped) == set(WORKBENCH_FILES) == set(beside),
                (shipped, sorted(WORKBENCH_FILES), beside),
            )
            check(
                "the live Workbench loads no mockup data and the server serves none of the frozen mockup's files (D7)",
                page.evaluate("() => typeof window.MOCK") == "undefined"
                and dict(served)
                == {
                    "mock.js": 404,
                    "mockup.html": 404,
                    "workflows.js": 404,
                    "round5.js": 404,
                    "live.js": 200,
                },
                served,
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
            seen = {}
            for route, h1 in (("hub", "Your goals"), ("dataset-hf/tickets_summary", "Add a dataset"),
                              ("dataset-src-kaggle/tickets_summary", "Your goals"), ("catalog", "The catalog")):  # fmt: skip
                page.goto(f"http://127.0.0.1:{port}/workbench/#{route}")
                page.wait_for_selector(f"h1:has-text('{h1}')", timeout=20000)
                seen[route] = "cnn_dailymail" not in page.content()
            check(
                "a route of the mockup's own opens the live screen it stands for (one the live page lacks, the home), never mock data",
                all(seen.values()),
                seen,
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
                and "prompt" not in sysrec["params"]
                and list(sysrec.get("prompts") or {}) == ["tickets_summary/prompt"]
                and sysrec["params"].get("max_tokens") == 50
                and sysrec["params"].get("temperature") == 0,
                sysrec,
            )
            pv1 = sysrec["prompts"]["tickets_summary/prompt"]["version"]
            v1_text = proj / "data" / "prompts" / "tickets_summary" / "prompt" / f"{pv1.split('/')[-1]}.txt"
            check(
                "the prompt is recorded as a version of the goal's prompt, and the system points at it (RFC-028; owner, "
                "2026-11-17: a manual eval and a study both make versions)",
                v1_text.is_file() and v1_text.read_text() == "Summarise the ticket in one line:",
                (pv1, sorted(x.name for x in v1_text.parent.iterdir()) if v1_text.parent.is_dir() else []),
            )
            SENT.clear()
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
                and len(SENT) >= 3
                and all(x.startswith("Summarise the ticket in one line:\n\n") for x in SENT)
                and any(
                    c.get("kind") == "smoke" and c.get("system") == "fake-1b_here"
                    for c in dep_doc.get("checks") or []
                ),
                (
                    page.locator("#sm-fake-1b_here").inner_text()[:400],
                    [c.get("kind") for c in dep_doc.get("checks") or []],
                    [x[:50] for x in SENT[:3]],
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
            page.click("[data-clone='fake-1b_here']")
            page.fill("#cl-id-fake-1b_here", "fake-1b_here_p2")
            page.select_option("#cl-what-fake-1b_here", "prompt")
            page.fill(
                "#cl-val-fake-1b_here", "Summarise the ticket in one line a support engineer can act on:"
            )
            page.click("#cl-go-fake-1b_here")
            page.wait_for_selector("td.mono:has-text('fake-1b_here_p2')", timeout=30000)
            p2 = yaml.safe_load((proj / "data" / "systems" / "fake-1b_here_p2.yaml").read_text())
            pv2 = (p2.get("prompts") or {}).get("tickets_summary/prompt", {}).get("version", "")
            v2_doc = proj / "data" / "prompts" / "tickets_summary" / "prompt" / f"{pv2.split('/')[-1]}.json"
            check(
                "Clone it with a changed prompt: a new version of the goal's prompt, made from the source's, the clone "
                "pointing at it and otherwise as the original",
                bool(pv2)
                and pv2 != pv1
                and v2_doc.is_file()
                and json.loads(v2_doc.read_text()).get("parent") == pv1
                and p2["params"] == sysrec["params"],
                (p2, v2_doc.read_text() if v2_doc.is_file() else None),
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
            # Prompts (RFC-028): the goal's prompt with its versions, each with its text and the runs that sent it; two
            # versions compared; a new version recorded from the latest; one written out as a file
            page.goto(f"http://127.0.0.1:{port}/workbench/#home")
            page.click("text=Prompts")
            page.wait_for_selector("h1:has-text('Prompts')", timeout=20000)
            page.click("a:has-text('tickets_summary/prompt')")
            page.wait_for_selector("#pd-go", timeout=20000)
            pshown = evh("prompt-show", "--name", "tickets_summary/prompt", "--json")
            vers = json.loads(pshown.stdout.splitlines()[-1])["result"]["versions"]
            text = page.locator("main").inner_text()
            check(
                "a prompt's versions with their text, who made each, what it was made from and the runs that sent it, as "
                "evh prompt-show says",
                [v["id"] for v in vers][:2] == [pv1, pv2]
                and "Summarise the ticket in one line a support engineer" in text
                and len(vers[0]["runs"]) >= 1
                and vers[0]["runs"][0]["run_id"] in page.content(),
                ([(v["id"], len(v["runs"])) for v in vers], text[:600]),
            )
            page.select_option("#pd-a", pv1)
            page.select_option("#pd-b", pv2)
            page.click("#pd-go")
            page.wait_for_selector("#pd-out pre", timeout=20000)
            diff = page.locator("#pd-out").inner_text()
            check(
                "What changed between two: prompt-diff's unified diff",
                "-Summarise the ticket in one line:" in diff
                and "+Summarise the ticket in one line a support engineer can act on:" in diff,
                diff[:400],
            )
            page.fill("#pp6-by", "tester")
            page.fill("#pn-text", "Summarise the ticket in one line; name the product area first:")
            page.fill("#pn-note", "the area first, so triage can route it")
            check(
                "A new version is a form with unsent changes",
                page.locator("#pn-go").inner_text() == "Record a new version of tickets_summary/prompt"
                and page.locator("[data-form=prompt-new] [data-unsent-mark]").is_visible(),
                page.locator("#pn-go").inner_text(),
            )
            page.click("#pn-go")
            page.wait_for_selector("summary:has-text('v3')", timeout=30000)
            vers = json.loads(
                evh("prompt-show", "--name", "tickets_summary/prompt", "--json").stdout.splitlines()[-1]
            )["result"]["versions"]
            check(
                "Record it (prompt-version): the third version, made from the latest, with its note",
                len(vers) == 3
                and vers[2].get("parent") == pv2
                and vers[2].get("note") == "the area first, so triage can route it",
                [(v["id"], v.get("parent"), v.get("note")) for v in vers],
            )
            page.click("#px-go")
            page.wait_for_selector("#px-out a, #px-out [role=alert]", timeout=30000)
            got = page.evaluate(
                "(u) => fetch(u, {credentials: 'same-origin'}).then((r) => r.text())",
                page.locator("#px-out a").get_attribute("href"),
            )
            check(
                "Write one out (prompt-export as a job): the version's text as a file to commit",
                got == "Summarise the ticket in one line; name the product area first:",
                (page.locator("#px-out").inner_text()[:200], got[:200]),
            )
            # W6 (UXS-005): a second label set's moves read before promoting it ($0, under its own label), then
            # promoted with why and the arms re-scored against it; the scorer in this tree previewed on the goal, then a
            # round re-scored with why
            short = proj / "short"
            short.mkdir()
            for f in sorted((KIT / "gold").iterdir()):
                (short / f.name).write_text(f.read_text().split(".")[0] + ".\n")
            r = evh(
                "label-import", "--sheet", str(short), "--dataset-id", "tk_v1", "--set", "short", "--by", "t"
            )
            check("setup: a second label set on tk_v1", r.returncode == 0, r.stderr[-300:])
            page.goto(f"http://127.0.0.1:{port}/workbench/#reference/tk_v1")
            page.wait_for_selector("#mv-go", timeout=20000)
            now = page.locator("main").inner_text()
            check(
                "W6 reads its reference sets and label sets (reference-list, label-set-list), with how often two agree",
                "gold/tk_v1" in now and "tk_v1/short" in now and "tk_v1/g" in now and "in both" in now,
                now[:600],
            )
            page.fill("#rf6-by", "tester")
            page.select_option("#mv-set", "short")
            page.click("#mv-go")
            page.wait_for_selector("#mv-out table, #mv-out [role=alert]", timeout=60000)
            moves = page.locator("#mv-out").inner_text()
            scored = sorted(x.name for x in (proj / "data" / "runs").glob("*/scores/*@labels.tk_v1.short"))
            check(
                "What it moves: the arms scored against the label set under its own label ($0, rescore --labels), "
                "ranked beside their rank on the reference now",
                "labels/tk_v1/short" in moves
                and "one_v1" in moves
                and "gold/tk_v1" in moves
                and bool(scored)
                and bool(rows := [r.split("\t") for r in page.locator("#mv-out tbody tr").all_inner_texts()])
                and all(len(r) == 6 and r[0].strip().isdigit() and r[3].strip().isdigit() for r in rows)
                and not (proj / "data" / "references" / "silver").exists(),
                (moves[:600], scored, page.locator("#mv-out tbody tr").all_inner_texts()),
            )
            page.select_option("#rp6-set", "short")
            page.select_option("#rp6-tier", "silver")
            page.fill("#rp6-why", "the first sentence of each answer, to see the order it gives")
            check(
                "Promote is a form with unsent changes until sent: its button says what it will write",
                page.locator("#rp6-go").inner_text() == "Promote short as silver/tk_v1"
                and page.locator("[data-form=ref-promote] [data-unsent-mark]").is_visible(),
                page.locator("#rp6-go").inner_text(),
            )
            page.click("#rp6-go")
            page.wait_for_selector("#rp6-out:has-text('Promoted'), #rp6-out [role=alert]", timeout=60000)
            man = proj / "data" / "references" / "silver" / "tk_v1"
            silver_scored = sorted(x.name for x in (proj / "data" / "runs").glob("*/scores/*@silver.tk_v1"))
            check(
                "Promote it: reference-promote with who and why, then the arms re-scored against it (rescore --reference-id)",
                man.is_dir() and bool(silver_scored) and "rescored" in page.locator("#rp6-out").inner_text(),
                (
                    sorted(x.name for x in man.iterdir()) if man.is_dir() else None,
                    silver_scored,
                    page.locator("#rp6-out").inner_text()[:400],
                ),
            )
            page.click("#rp6-out button")
            page.wait_for_selector("#mv-go", timeout=20000)
            check(
                "read again, the new reference set is listed",
                "silver/tk_v1" in page.locator("main").inner_text(),
                page.locator("main").inner_text()[:500],
            )
            before = sorted(str(x) for x in (proj / "data").rglob("*"))
            page.click("#sp-go")
            page.wait_for_selector("#sp-out table, #sp-out [role=alert]", timeout=60000)
            prev = page.locator("#sp-out").inner_text()
            check(
                "When the scoring changes: score-preview as a job, each arm now and after, the leader and contenders; nothing written",
                "one_v1" in prev
                and "now" in prev
                and "contenders" in prev
                and "nothing written" in prev
                and sorted(str(x) for x in (proj / "data").rglob("*")) == before,
                prev[:600],
            )
            page.select_option("#rr-round", "r2")
            page.fill("#rr-why", "the scorer's tokenizer changed, so the round reads the new numbers")
            page.click("#rr-go")
            page.wait_for_selector("#rr-out:has-text('Re-scored'), #rr-out [role=alert]", timeout=60000)
            r2t = (proj / "data" / "rounds" / "tickets_summary" / "r2.yaml").read_text()
            check(
                "Apply it to a round: rescore with the goal, the round and why, the reason kept on the round",
                "the scorer's tokenizer changed" in r2t,
                (page.locator("#rr-out").inner_text()[:400], r2t[-600:]),
            )
            # W7 (UXS-005): a judge scorer made on the page from systems; the tutorial's fake-judge scorer shown with its
            # judges, guards and (stored) validation, changed while it has judged nothing, its cost read first (the dry
            # run through POST /estimate), the arms judged as a job under a cap, then kept as it judged; what it cost
            (proj / "tutorial").mkdir(exist_ok=True)
            shutil.copy2(KIT / "judge_prompt.txt", proj / "tutorial" / "judge_prompt.txt")
            (proj / "data" / "scorers").mkdir(exist_ok=True)
            (proj / "data" / "scorers" / "tickets-judge-v1.yaml").write_text(
                (KIT / "scorers" / "tickets-judge-v1.yaml")
                .read_text()
                .replace("dataset_id: tickets_v1", "dataset_id: tk_v1")
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#eval/tickets_summary/r2")
            page.click("text=A judge for this goal")
            page.wait_for_selector("h1:has-text('A judge for this goal')", timeout=20000)
            page.wait_for_selector("#js-est", timeout=20000)
            shown = page.locator("main").inner_text()
            check(
                "W7 lists the goal's judge scorers (scorer-list) and shows one: its judges and families, its guards, not "
                "validated with the reasons, as stored (scorer-show)",
                "tickets-judge-v1" in shown
                and "judge_a" in shown
                and "vendor_b" in shown
                and "re-asked in another order" in shown
                and "not validated" in shown
                and "can never be validated" in shown,
                shown[:900],
            )
            page.fill("#jd-by", "tester")
            page.fill("#ss-cap", "0.02")
            check(
                "changing it is a form with unsent changes",
                page.locator("#ss-go").inner_text() == "Save tickets-judge-v1"
                and page.locator("[data-form=scorer-set] [data-unsent-mark]").is_visible(),
                page.locator("#ss-go").inner_text(),
            )
            page.click("#ss-go")
            page.wait_for_function(
                "() => document.querySelector('#js-cap') && document.querySelector('#js-cap').value === '0.02'",
                timeout=20000,
            )
            sc = yaml.safe_load((proj / "data" / "scorers" / "tickets-judge-v1.yaml").read_text())
            check(
                "Save sends only what changed (scorer-set): the cap, the rest of the record as it was",
                sc.get("cost_cap_usd") == 0.02
                and sc["protocol"]["outputs_per_call"] == 16
                and "mode" not in sc,
                sc,
            )
            page.click("#js-est")
            page.wait_for_selector("#js-out pre, #js-out [role=alert]", timeout=60000)
            est = page.locator("#js-out").inner_text()
            check(
                "The cost first: judge-score's dry run through POST /estimate refuses an unvalidated judge unless asked",
                "not validated" in est or "unvalidated" in est.lower(),
                est[:500],
            )
            page.check("#js-unval")
            page.click("#js-est")
            page.wait_for_selector("#js-out:has-text('DRY RUN'), #js-out [role=alert]", timeout=60000)
            est = page.locator("#js-out").inner_text()
            check(
                "asked to run it unvalidated, the dry run says its calls and cost, and the cap; nothing judged",
                "DRY RUN" in est and "cap $0.02" in est and not (proj / "data" / "judge-summaries").exists(),
                est[:600],
            )
            page.click("#js-go")
            page.wait_for_selector("#js-out:has-text('Judged.'), #js-out [role=alert]", timeout=120000)
            sums = (
                sorted(x.name for x in (proj / "data" / "judge-summaries").glob("*.json"))
                if (proj / "data" / "judge-summaries").is_dir()
                else []
            )
            check(
                "Judge the arms: judge-score as a job under the cap, labelled unvalidated; its summary written",
                "Judged." in page.locator("#js-out").inner_text()
                and any(x.startswith("tickets-judge-v1@") for x in sums),
                (page.locator("#js-out").inner_text()[:600], sums),
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#goal/tickets_summary")
            page.wait_for_selector("h1:has-text('Ticket summaries')", timeout=20000)
            page.goto(f"http://127.0.0.1:{port}/workbench/#judge/tickets_summary")
            page.wait_for_selector("#ss-new", timeout=20000)
            check(
                "read again, a scorer that has judged stays as it judged, and what it judged is listed",
                "stays as it judged" in page.locator("main").inner_text()
                and "verdict(s)" in page.locator("main").inner_text()
                and not page.locator("#ss-go").count(),
                page.locator("main").inner_text()[:900],
            )
            page.click("#ss-new")
            page.wait_for_function(
                "() => document.querySelector('#jn-id').value === 'tickets-judge-v1-v2'", timeout=20000
            )
            check(
                "a new version starts from the one it supersedes: its prompt, guards, cap and judges (its fake judges kept as they are)",
                page.input_value("#jn-prompt") == "tutorial/judge_prompt.txt"
                and page.input_value("#jn-cap") == "0.02"
                and page.locator("input[name=jn-keep]:checked").count() == 2,
                (page.input_value("#jn-prompt"), page.input_value("#jn-cap")),
            )
            page.check("input[name=jn-judge][value=one_v1]")
            page.check("input[name=jn-judge][value=fake-1b_here]")
            page.click("#jn-go")
            page.wait_for_selector("[data-scorer='tickets-judge-v1-v2'], #jn-out [role=alert]", timeout=20000)
            v2f = proj / "data" / "scorers" / "tickets-judge-v1-v2.yaml"
            v2 = (
                yaml.safe_load(v2f.read_text())
                if v2f.is_file()
                else {"page": page.locator("#jn-out").inner_text()}
            )
            check(
                "Make a new version: scorer-new with supersedes, the judges kept and the systems chosen, the prompt, guards and cap",
                v2.get("supersedes") == "tickets-judge-v1"
                and [j.get("id") for j in v2.get("judges", [])]
                == ["judge_a", "judge_b", "fake-1b_here", "one_v1"]
                and v2["judges"][0].get("params", {}).get("model") == "fake-a"
                and v2.get("cost_cap_usd") == 0.02
                and v2.get("prompt", {}).get("file") == "tutorial/judge_prompt.txt"
                and v2.get("protocol", {}).get("outputs_per_call") == 16,
                v2,
            )
            page.click("#cr-go")
            page.wait_for_selector("#cr-out pre, #cr-out [role=alert]", timeout=60000)
            check(
                "What it cost: cost-report as a job, each arm's billed cost and the judging",
                "billed" in page.locator("#cr-out").inner_text(),
                page.locator("#cr-out").inner_text()[:500],
            )
            # W8 (UXS-005): the settings, one row each: where the data is kept (the move refused until config.yaml names
            # the store), this release's formats, the project checked (validate, its failures as `evh validate` says),
            # a policy file checked and saved (data-put), publishing refused offline
            page.goto(f"http://127.0.0.1:{port}/workbench/#home")
            page.click("text=Settings")
            page.wait_for_selector("h1:has-text('Govern and maintain')", timeout=20000)
            page.wait_for_selector("#vd-go", timeout=20000)
            check(
                "W8 says where the project keeps its data, the store config.yaml names (data-ls's overview)",
                "config.yaml names files: every run, label and score a file under data/"
                in page.locator("main").inner_text(),
                page.locator("main").inner_text()[:400],
            )
            page.fill("#st-by", "tester")
            page.click("#mv-dry")
            page.wait_for_selector("#mv-st-out pre, #mv-st-out [role=alert]", timeout=60000)
            page.wait_for_function(
                "() => document.querySelector('#mv-st-out').textContent.includes('Nothing to move')",
                timeout=20000,
            )
            check(
                "the store's move goes into the store config.yaml names: its dry run as a job counts nothing to move into "
                "files, so Move it stays off (tests/test_workbench_store_browser.py moves one)",
                "0 file(s)" in page.locator("#mv-st-out").inner_text()
                and page.locator("#mv-run").is_disabled(),
                page.locator("#mv-st-out").inner_text()[:300],
            )
            page.click("#mg-check")
            page.wait_for_selector("#mg-out pre, #mg-out [role=alert]", timeout=60000)
            check(
                "this release's formats: migrate --check as a job, the data's format against the release's",
                "this release reads" in page.locator("#mg-out").inner_text(),
                page.locator("#mg-out").inner_text()[:300],
            )
            page.click("#vd-go")
            page.wait_for_selector("#vd-out details", timeout=120000)
            cli = evh("validate").stdout
            fails = [x.strip() for x in cli.splitlines() if x.strip().startswith("FAIL")]
            listed = page.locator("#vd-out li").all_inner_texts()
            check(
                "Check the project: validate read through the API, its failures listed as evh validate prints them",
                [x.strip() for x in listed] == fails
                and (
                    f"{len(fails)} check(s) failed" in page.locator("#vd-out").inner_text()
                    if fails
                    else "Every check passed" in page.locator("#vd-out").inner_text()
                ),
                (listed, fails),
            )
            page.select_option("#sf-path", "goals/policy.yaml")
            page.wait_for_selector("#sf-text", timeout=20000)
            page.fill("#sf-text", "required_from: 17/11/2026\n")
            page.click("#sf-check")
            page.wait_for_selector("#sf-out [role=alert], #sf-out .note", timeout=60000)
            bad = page.locator("#sf-out").inner_text()
            page.fill("#sf-text", "required_from: 2000-01-01\n")
            check(
                "a policy is a form with unsent changes; Check (data-put --check) shows what is wrong with it, nothing saved",
                "does not pass" in bad
                and "required_from" in bad
                and not (proj / "data" / "goals" / "policy.yaml").exists()
                and page.locator("#sf-save").inner_text() == "Save goals/policy.yaml",
                bad[:500],
            )
            page.click("#sf-save")
            page.wait_for_function(
                "() => /Saved|Not saved/.test(document.querySelector('#sf-out').textContent)", timeout=60000
            )
            pol = proj / "data" / "goals" / "policy.yaml"
            check(
                "Save refuses a policy the project would fail (a run since then names no goal), and says which run",
                "Not saved" in page.locator("#sf-out").inner_text()
                and "names no goal" in page.locator("#sf-out").inner_text()
                and not pol.exists(),
                page.locator("#sf-out").inner_text()[:400],
            )
            pol.parent.mkdir(parents=True, exist_ok=True)
            pol.write_text(
                "required_from: 2098-01-01\n"
            )  # made elsewhere after the page read that there was none
            page.fill("#sf-text", "required_from: 2099-01-01\n")
            page.click("#sf-save")
            page.wait_for_function(
                "() => /Not saved/.test(document.querySelector('#sf-out').textContent) && !/names no goal/.test(document.querySelector('#sf-out').textContent) || /Saved\\./.test(document.querySelector('#sf-out').textContent)",
                timeout=60000,
            )
            check(
                "a file made elsewhere after the page read that there was none is not overwritten (data-put new): refused",
                "exists" in page.locator("#sf-out").inner_text()
                and pol.read_text() == "required_from: 2098-01-01\n",
                (page.locator("#sf-out").inner_text()[:300], pol.read_text()),
            )
            page.once("dialog", lambda d: d.accept())  # the unsent policy asks before leaving: leave
            page.goto(f"http://127.0.0.1:{port}/workbench/#home")
            page.wait_for_selector("h1:has-text('Your goals')", timeout=20000)
            page.goto(f"http://127.0.0.1:{port}/workbench/#settings")
            page.wait_for_selector("#sf-path", timeout=20000)
            page.select_option("#sf-path", "goals/policy.yaml")
            page.wait_for_function(
                "() => document.querySelector('#sf-text') && document.querySelector('#sf-text').value.includes('2098')",
                timeout=20000,
            )
            page.fill("#sf-text", "required_from: 2099-01-01\n")
            page.click("#sf-save")
            page.wait_for_function(
                "() => /Saved\\./.test(document.querySelector('#sf-out').textContent) || /Not saved/.test(document.querySelector('#sf-out').textContent) && !/names no goal/.test(document.querySelector('#sf-out').textContent)",
                timeout=60000,
            )
            check(
                "Save (data-put with the file, new): the policy written as typed",
                pol.is_file() and pol.read_text() == "required_from: 2099-01-01\n",
                (page.locator("#sf-out").inner_text()[:300], pol.read_text() if pol.is_file() else None),
            )
            page.select_option("#pb-ds", "tk_v1")
            page.fill("#pb-repo", "someone/tk")
            page.click("#pb-go")
            page.wait_for_selector("#pb-out [role=alert], #pb-out pre", timeout=60000)
            check(
                "Publish: dataset-publish as a job with the repo; offline and with no token it is refused, and says why",
                page.locator("#pb-out [role=alert]").count() == 1,
                page.locator("#pb-out").inner_text()[:400],
            )
            # Jobs (UXS-005): every job a page at a time, filtered; one job's record, result, files (a blind sheet's key not
            # among them) and log; a run stopped while it runs, then resumed as a new job with what it left of its cap
            page.once("dialog", lambda d: d.accept())  # the publish form, refused, is still unsent: leave
            page.goto(f"http://127.0.0.1:{port}/workbench/#home")
            page.click("text=Every job")
            page.wait_for_selector("h1:has-text('Jobs')", timeout=20000)
            page.wait_for_selector("text=of ", timeout=20000)
            every = evh("jobs-status", "--json")
            total = len(json.loads(every.stdout.splitlines()[-1])["result"]["values"]["jobs"])
            check(
                "the jobs: the newest page of them (GET /jobs), counted as evh jobs-status counts them",
                f"of {total}" in page.locator("main").inner_text()
                and page.locator("main tbody tr").count() == min(total, 50),
                (page.locator("main").inner_text()[-300:], total),
            )
            page.select_option("#jf-state", "succeeded")
            page.wait_for_function(
                "() => document.querySelector('#jf-state')?.value === 'succeeded' && document.querySelectorAll('main tbody tr').length",
                timeout=20000,
            )
            page.select_option("#jf-op", "sheet-export")
            page.wait_for_function(
                "() => [...document.querySelectorAll('main tbody tr')].every((r) => r.children[1].textContent === 'sheet-export')"
                " && document.querySelectorAll('main tbody tr').length > 0",
                timeout=20000,
            )
            check(
                "filtered by state and operation (state, operation)",
                all("succeeded" in r for r in page.locator("main tbody tr").all_inner_texts()),
                page.locator("main tbody tr").all_inner_texts()[:3],
            )
            page.click("main tbody tr >> nth=-1 >> a")
            page.wait_for_selector("h1:has-text('sheet-export')", timeout=20000)
            page.wait_for_function(
                "() => !document.querySelector('#jb-log').textContent.startsWith('reading')", timeout=20000
            )
            jid = page.url.rsplit("/", 1)[-1]
            names = page.locator("main ul a.mono").all_inner_texts()
            on_disk = sorted(x.name for x in (proj / ".build" / "jobs" / jid).iterdir())
            got = page.evaluate(
                "(u) => fetch(u, {credentials: 'same-origin'}).then((r) => r.status)",
                f"/api/v1/jobs/{jid}/files/{names[0]}" if names else "/none",
            )
            said = evh("jobs-status", jid).stdout
            check(
                "one job: its record, its result and its log, its files (a link each, which answers), the blind sheet's key "
                "not among them (GET /jobs/{id}, its files, its log); evh jobs-status names the same files",
                names == ["review.csv"]
                and any(n.endswith(".key.json") for n in on_disk)
                and got == 200
                and "inputs" in page.locator("main").inner_text()
                and page.locator("#jb-log").inner_text().strip() != ""
                and f"files: {', '.join(names)}" in said,
                (names, on_disk, got, said[-300:]),
            )
            SLOW["s"] = 1.5

            def start_run() -> dict:
                """A run of the fake system as a job: each call waits 1.5 s, so it is still running when stopped."""
                return page.evaluate(
                    """() => fetch('/api/v1/jobs', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type':
                    'application/json', 'X-EVH-Data': '1'}, body: JSON.stringify({operation: 'run', inputs: {system:
                    'fake-1b_here', dataset: 'tk_v1'}, by: 'person:tester', max_cost_usd: 1})}).then((r) => r.json())"""
                )

            def done_items(jid: str) -> int:
                f = proj / ".build" / "jobs" / jid / "progress.json"
                return (json.loads(f.read_text()).get("done") or 0) if f.is_file() else 0

            early = start_run()
            page.goto(f"http://127.0.0.1:{port}/workbench/#jobs/{early.get('id')}")
            page.wait_for_selector("#jb-stop", timeout=20000)
            page.click("#jb-stop")
            page.wait_for_selector(
                "#jb-resume, #jb-out [role=alert]", timeout=30000
            )  # the page draws the job again after a stop
            stopped = json.loads((proj / ".build" / "jobs" / early["id"] / "state.json").read_text())
            jobs_before = len(list((proj / ".build" / "jobs").iterdir()))
            if page.locator("#jb-resume").count():
                page.click("#jb-resume")
                page.wait_for_function(
                    f"() => !location.hash.endsWith('{early['id']}') || document.querySelector('#jb-out [role=alert], #jb-out .note')",
                    timeout=20000,
                )
            check(
                "a run stopped from its page before it wrote anything (POST /jobs/{id}/stop): cancelled; Resume refuses it "
                "with why, and starts no job",
                stopped.get("state") == "cancelled"
                and done_items(early["id"]) == 0
                and "nothing to resume" in page.locator("#jb-out").inner_text()
                and len(list((proj / ".build" / "jobs").iterdir())) == jobs_before,
                (stopped, page.locator("#jb-out").inner_text()[:300]),
            )
            started = start_run()
            page.goto(f"http://127.0.0.1:{port}/workbench/#jobs/{started.get('id')}")
            page.wait_for_selector("#jb-stop", timeout=20000)
            deadline = time.monotonic() + 60
            while done_items(started["id"]) < 1 and time.monotonic() < deadline:
                time.sleep(0.2)
            page.click("#jb-stop")
            page.wait_for_selector("#jb-resume, #jb-out [role=alert]", timeout=30000)
            stopped = json.loads((proj / ".build" / "jobs" / started["id"] / "state.json").read_text())
            check(
                "a running run stopped after it wrote something: cancelled, and Resume the run offered",
                stopped.get("state") == "cancelled" and page.locator("#jb-resume").count() == 1,
                (stopped, page.locator("main").inner_text()[:300]),
            )
            SLOW["s"] = 0.0
            page.click("#jb-resume")
            page.wait_for_function(
                f"() => location.hash.startsWith('#jobs/') && !location.hash.endsWith('{started['id']}')",
                timeout=20000,
            )
            page.wait_for_selector(
                "h1 ~ p.lead:has-text('succeeded'), h1 ~ p.lead:has-text('failed')", timeout=120000
            )
            again = json.loads(
                (proj / ".build" / "jobs" / page.url.rsplit("/", 1)[-1] / "job.json").read_text()
            )
            check(
                "Resume the run: a new job continues the stopped run (run --resume its run id) with what it left of its cap, "
                "and its page follows it to its end",
                "succeeded" in page.locator("h1 ~ p.lead").inner_text()
                and again["inputs"].get("resume") == started.get("run_id")
                and float(again["env"]["EVAL_MAX_COST_USD"]) <= 1.0,
                (
                    page.locator("h1 ~ p.lead").inner_text(),
                    again.get("inputs"),
                    again.get("env"),
                    started.get("run_id"),
                    page.locator("#jb-log").inner_text()[-600:],
                ),
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
                ("reference/tk_v1", "Change the reference set"),
                ("judge/tickets_summary", "A judge for this goal"),
                ("settings", "Govern and maintain"),
                ("jobs", "Jobs"),
                ("prompts/tickets_summary/prompt", "tickets_summary/prompt"),
                ("review/tickets_summary", "Review the outputs"),
                ("production/tickets_summary", "Learn from production"),
            ):
                phone.goto(f"http://127.0.0.1:{port}/workbench/#{screen}")
                phone.wait_for_selector(f"h1:has-text('{h1}')", timeout=20000)
                if shots := os.environ.get("EVH_WB_SHOTS"):
                    phone.screenshot(path=f"{shots}/phone-{screen.replace('/', '-')}.png", full_page=True)
                wide[screen] = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(
                "at a phone's width the models' screens and steps 1 to 4, the eval, the review, production, the reference set, the judge, the settings, the jobs and the prompts do not scroll sideways",
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
