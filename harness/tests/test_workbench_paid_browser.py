#!/usr/bin/env python3
"""The Workbench's paid run, end to end (PLAN 0.8.1 T1): "Run them" against a local provider that bills.

    python tests/test_workbench_paid_browser.py

A git project with a goal and priced systems pointing at a fake OpenAI-shaped server that reports usage tokens, so
each call is billed. A round is opened on the page with a budget lower than the cap the page then sends. Checked:
the estimate on the page is the one `evh run --dry-run` prints; the cap the page typed is the job's EVAL_MAX_COST_USD;
the round's ledger holds the run to the lesser of its cap and the round's budget; a run made with an uncommitted system
file is recorded dirty and one made after a commit is not; `evh runs-list` stars the first and prints the legend; the
job's spent is the run's and the ledger's; at 390 px the commit notice sits above the button and nothing scrolls sideways.
No real provider is called: the base_url of every system is this process's fake.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _signin
import _cli  # noqa: E402
import _serve  # noqa: E402
import _signin  # noqa: E402
import _slow  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbpaid-"))
env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_HOME=str(proj), EVAL_STORE="files")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_BUILD_REF", "EVAL_MAX_COST_USD", "HF_TOKEN"):
    env.pop(
        k, None
    )  # EVAL_BUILD_REF would force build.dirty to null: the point here is that it is read from git
env["OPENAI_API_KEY"] = "local"  # the fake's; no real provider is reachable from this test
env.update(HF_HUB_OFFLINE="1", HF_HOME=str(proj / ".hf"))

#: What the fake reports per call, and the prices the systems declare: one call is 2000 x $5/M + 1000 x $10/M = $0.02.
PROMPT_TOKENS, COMPLETION_TOKENS, PRICE_IN, PRICE_OUT = 2000, 1000, 5.0, 10.0
CALLS: list[int] = []


class Fake(http.server.BaseHTTPRequestHandler):
    """An OpenAI-shaped server that answers and reports what the call used."""

    def _send(self, doc):
        data = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [{"name": "fake:1b", "model": "fake:1b"}]})

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        CALLS.append(1)
        self._send({"id": "x", "object": "chat.completion", "created": 0, "model": "fake:1b",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "a one-line summary"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": PROMPT_TOKENS, "completion_tokens": COMPLETION_TOKENS,
                              "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS}})  # fmt: skip

    def log_message(self, *a):
        pass


fake = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=600)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(proj), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
    )


def system_yaml(name: str) -> None:
    (proj / "data" / "systems" / f"{name}.yaml").write_text(
        f"system_id: {name}\nparams:\n  provider: openai\n  model: fake:1b\n  max_tokens: 400\n"
        f"  base_url: http://127.0.0.1:{fake.server_port}/v1\n"
        f"  usd_per_mtok_in: {PRICE_IN}\n  usd_per_mtok_out: {PRICE_OUT}\n",
        encoding="utf-8",
    )


def evidence(name: str, line: object) -> None:
    print(f"  EVIDENCE {name}: {line}")


def serve() -> tuple[subprocess.Popen, int, list[str]]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, encoding="utf-8",
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return p, port, _serve.startup(p, [])


def last_job(operation: str) -> tuple[Path, dict]:
    jobs = [
        (d, json.loads((d / "job.json").read_text(encoding="utf-8")))
        for d in sorted((proj / ".build" / "jobs").iterdir())
        if (d / "job.json").is_file()
    ]
    return [(d, j) for d, j in jobs if j.get("operation") == operation][-1]


def metrics_of(system: str) -> dict:
    """A run's record as the catalog reads it: its run.json with its score's metrics.json over it."""
    found = sorted((proj / "data" / "runs").glob(f"{system}_*"))
    if not found:
        return {}
    rec = json.loads((found[-1] / "run.json").read_text(encoding="utf-8"))
    for m in sorted(found[-1].rglob("metrics.json")):
        rec.update(json.loads(m.read_text(encoding="utf-8")))
    return rec


def dollars(text: str) -> str | None:
    m = re.search(r"ESTIMATE\s+~\$([0-9.]+)", text)
    return m.group(1) if m else None


#: Where a reader sees a line of #rn-out's answer: its text range's box, tested against the viewport and the client box of
#: every ancestor that clips (the .reply box scrolls), after the section is scrolled into view. Not seen: no box (inside a
#: closed <details>) or one outside a clipping ancestor.
SEEN_JS = """(re) => {
  const out = document.getElementById('rn-out');
  out.scrollIntoView({block: 'start'});
  const w = document.createTreeWalker(out, NodeFilter.SHOW_TEXT);
  const res = [];
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const m = new RegExp(re).exec(n.nodeValue);
    if (!m) continue;
    const rg = document.createRange(); rg.setStart(n, m.index); rg.setEnd(n, m.index + m[0].length);
    const r = rg.getBoundingClientRect();
    let ok = r.height > 0 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
    for (let e = n.parentElement; e && e !== document.body; e = e.parentElement) {
      const c = getComputedStyle(e);
      if (c.overflowY !== 'visible' || c.overflowX !== 'visible') {
        const b = e.getBoundingClientRect();
        if (r.top < b.top - 0.5 || r.bottom > b.bottom + 0.5) ok = false;
      }
    }
    res.push({text: m[0], ok});
  }
  return res;
}"""


def seen(page, rx: str) -> list:
    return page.evaluate(SEEN_JS, rx)


GOAL, DS, BUDGET, CAP1, CAP2 = "tickets_summary", "tk_v1", 0.30, 1.00, 0.50
try:
    r = evh("init", "--store", "files", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", DS, "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", DS),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", DS, "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", DS, "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the test", "--by", "t"),
        ("goal-new", GOAL, "--set", "title=Ticket summaries", "--set", "statement=A one-line summary of a ticket.",
         "--set", "decision=Which system writes it.", "--set", "success_criteria.primary.measure=overlap_f1",
         "--set", "success_criteria.primary.direction=higher", "--set", f"datasets.0.dataset_id={DS}", "--set", "datasets.0.role=pilot"),
        ("catalog",),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    git("init", "-q")
    git("config", "user.name", "tester")
    git("config", "user.email", "tester@example.invalid")
    git("add", "-A")
    c = git("commit", "-q", "-m", "the project, before any system of the round")
    check(
        "setup: a committed git project with a goal, its dataset and reference",
        r.returncode == 0 and c.returncode == 0,
        (r.stdout + r.stderr + c.stdout + c.stderr)[-400:],
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("table >> text=Ticket summaries", timeout=20000)
            page.goto(f"http://127.0.0.1:{port}/workbench/#eval/{GOAL}")
            page.wait_for_selector("#ro-q", timeout=20000)
            page.fill("#ro-q", "Does the billed fake model summarise a ticket?")
            page.select_option("#ro-ds", DS)
            page.fill("#ro-by", "tester")
            page.fill("#ro-budget", str(BUDGET))
            page.click("#ro-open")
            page.wait_for_selector("section.part:has(h2:has-text('Run arms in it'))", timeout=60000)

            def run_one(system: str, cap: float) -> dict:
                """The system's file is already in the project. Estimate, then Run them."""
                page.reload()
                page.wait_for_selector(f"[data-run='{system}']", timeout=30000)
                page.check(f"[data-run='{system}']")
                page.fill("#rn-cap", str(cap))
                page.click("#rn-est")
                page.wait_for_selector("#rn-out pre, #rn-out [role=alert]", state="attached", timeout=60000)
                shown = page.locator("#rn-out").inner_text()
                api_est = page.evaluate(
                    "(i) => fetch('/api/v1/estimate', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-EVH-Data': '1'}, body: JSON.stringify({operation: 'sweep', inputs: i})}).then((r) => r.json())",
                    {"systems": [system], "dataset": DS, "goal": GOAL, "round": "r1"},
                )
                evidence(
                    "1a",
                    f"estimate answer: result={json.dumps(api_est.get('result'))[:600]} text_lines={len(str(api_est.get('text')).splitlines())}",
                )
                reach = {}
                for w_, h_ in ((1280, 900), (390, 800)):
                    page.set_viewport_size({"width": w_, "height": h_})
                    reach[w_] = {
                        k: seen(page, rx)
                        for k, rx in (
                            ("estimate", r"ESTIMATE\s+~\$[0-9.]+"),
                            ("cap", rf"spend at most \${cap:g}\b"),
                        )
                    }
                figures = (
                    page.locator("#rn-figures").inner_text() if page.locator("#rn-figures").count() else ""
                )
                page.set_viewport_size({"width": 1280, "height": 900})
                page.fill("#ev-by", "tester")
                page.click("#rn-go")
                page.wait_for_selector(f"#arms li:has-text('{system}')", timeout=180000)
                jd, job = last_job("sweep")
                return {
                    "shown": shown,
                    "reach": reach,
                    "figures": figures,
                    "job_dir": jd,
                    "job": job,
                    "cap": cap,
                }

            # run 1: its system file is written after the commit and left uncommitted
            system_yaml("paid_a")
            a = run_one("paid_a", CAP1)
            ma = metrics_of("paid_a")
            cli = evh("run", "--system", "paid_a", "--dataset", DS, "--dry-run")
            page_est, cli_est = dollars(a["shown"]), dollars(cli.stdout)
            evidence("1", f"page={page_est!r} cli={cli_est!r}")
            check(
                "1 estimate: the page shows a positive dollar figure, equal to `evh run --dry-run`'s for the arm",
                page_est is not None and float(page_est) > 0 and page_est == cli_est,
                (a["shown"], cli.stdout[-600:], cli.stderr[-300:]),
            )

            figures = a["figures"]
            for w_, got in a["reach"].items():
                evidence("1b", f"{w_}px: {got}")
                check(
                    f"1b visible: at {w_} px the ESTIMATE line and the typed cap are in view without scrolling the reply box",
                    all(any(x["ok"] for x in got[k]) for k in ("estimate", "cap")),
                    (got, a["shown"]),
                )
            check(
                "1c the summary's cap is the one Run them uses, never the dry run's own (NONE: the estimate runs with no cap)",
                "NONE" not in figures and f"${CAP1:g}" in figures,
                figures,
            )

            jenv = a["job"].get("env") or {}
            evidence("2", f"typed={a['cap']} job.env={jenv}")
            check(
                "2 cap: the job's EVAL_MAX_COST_USD is the cap the test typed into #rn-cap",
                jenv.get("EVAL_MAX_COST_USD") is not None and float(jenv["EVAL_MAX_COST_USD"]) == a["cap"],
                a["job"],
            )

            ledger_f = proj / ".build" / "rounds" / GOAL / "r1.json"
            ledger = json.loads(ledger_f.read_text(encoding="utf-8")) if ledger_f.is_file() else {}
            ents = [e for e in ledger.get("entries", []) if e.get("job") == a["job_dir"].name]
            e1 = ents[0] if ents else {}
            lesser = min(BUDGET, CAP1)
            evidence("3", f"entry={e1} lesser={lesser}")
            check(
                "3 budget: the ledger holds the run to the lesser of its cap and the round's budget, and it spent within it",
                len(ents) == 1
                and abs(float(e1.get("reserved", -1)) - lesser) < 1e-9
                and e1.get("spent") is not None
                and 0 < float(e1["spent"]) <= lesser,
                ledger,
            )

            api = page.evaluate(
                "(id) => fetch('/api/v1/jobs/' + id, {credentials: 'same-origin'}).then((r) => r.json())",
                a["job_dir"].name,
            )
            billed = len(CALLS) * (PROMPT_TOKENS * PRICE_IN + COMPLETION_TOKENS * PRICE_OUT) / 1e6
            evidence(
                "7",
                f"job.spent_usd={api.get('spent_usd')} ledger.spent={e1.get('spent')} fake_billed={billed} metrics_keys={sorted(ma)}",
            )
            check(
                "7 spent: the job's spent_usd matches the ledger's spent and what the fake's calls billed",
                api.get("spent_usd")
                and abs(float(api["spent_usd"]) - float(e1.get("spent") or -1)) < 1e-6
                and abs(float(api["spent_usd"]) - billed) < 1e-6,
                (api, e1, len(CALLS)),
            )

            # run 2: the files are committed first
            dirty_a = (ma.get("build") or {}).get("dirty")
            git("add", "-A")
            git("commit", "-q", "-m", "paid_a and what the screen wrote")
            system_yaml("paid_b")
            git("add", "-A")
            git("commit", "-q", "-m", "paid_b")
            b = run_one("paid_b", CAP2)
            mb = metrics_of("paid_b")
            dirty_b = (mb.get("build") or {}).get("dirty")
            evidence("4", f"paid_a build={ma.get('build')} paid_b build={mb.get('build')}")
            check(
                "4 dirty: build.dirty is True for the run over an uncommitted system file, False for the one after a commit",
                dirty_a is True and dirty_b is False,
                (ma.get("build"), mb.get("build"), git("status", "--short").stdout),
            )

            rl = evh("runs-list")
            rows = {
                s: [ln for ln in rl.stdout.splitlines() if ln.startswith(f"{s}_")]
                for s in ("paid_a", "paid_b")
            }
            star = lambda ln: bool(re.search(r"\S\*\s", ln))  # noqa: E731  # the star follows the build ref directly
            evidence("5", rl.stdout)
            check(
                "5 runs-list: the dirty run's row has the star, the clean one's none, and the legend is printed",
                len(rows["paid_a"]) == 1
                and len(rows["paid_b"]) == 1
                and star(rows["paid_a"][0])
                and not star(rows["paid_b"][0])
                and "* = produced by a dirty tree; its build ref does not describe what ran" in rl.stdout,
                (rl.stdout, rl.stderr),
            )

            # 390 px: a third system the page can offer, nothing run
            system_yaml("paid_c")
            page.set_viewport_size({"width": 390, "height": 800})
            page.reload()
            page.wait_for_selector("[data-run='paid_c']", timeout=30000)
            geo = page.evaluate(
                """() => {
                  const n = [...document.querySelectorAll('section.part p')].find((p) => /Commit them/.test(p.textContent));
                  const b = document.getElementById('rn-go');
                  if (!n || !b) return {found: false};
                  const sec = n.closest('section.part'), nr = n.getBoundingClientRect(), br = b.getBoundingClientRect(),
                    sr = sec.getBoundingClientRect(), cs = getComputedStyle(n);
                  return {found: true, vw: window.innerWidth, scrollW: document.documentElement.scrollWidth,
                    noticeRight: nr.right, noticeBottom: nr.bottom, goTop: br.top, secRight: sr.right,
                    secScrollW: sec.scrollWidth, secClientW: sec.clientWidth, noticeW: nr.width, noticeH: nr.height,
                    visible: cs.display !== 'none' && cs.visibility !== 'hidden' && nr.width > 0 && nr.height > 0};
                }"""
            )
            evidence("6", geo)
            check(
                "6 390 px: the commit notice is visible, above #rn-go, and neither it nor its section overflows sideways",
                geo.get("found")
                and geo["visible"]
                and geo["noticeBottom"] <= geo["goTop"]
                and geo["vw"] == 390
                and geo["noticeRight"] <= geo["vw"]
                and geo["secRight"] <= geo["vw"]
                and geo["secScrollW"] <= geo["secClientW"]
                and geo["scrollW"] <= 390,
                geo,
            )
            check("no page error in the browser", not errors, errors)
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    fake.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
