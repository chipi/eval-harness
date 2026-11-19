#!/usr/bin/env python3
"""The Workbench's held-out test and studies (UXS-005; RFC-029, RFC-031): $0 and offline.

    python tests/test_workbench_heldout_browser.py

A git project with a goal over the tutorial's tickets (a time and a kind on each, and an alert id), a candidate system
whose hypothesis is committed, and twelve-item validation and test sets. Behind a real catalog-serve:

- the held-out test: a dataset split by time and sealed from the page, both sides joining the goal; the seal; a read
  recorded; the leak check finding an id in a public repo, recorded as a read; the counts for safety and a field
  allowed; the side opened for the candidate (one look); both arms run on it; the confirmation with the read items left
  out, as `evh pair-test --include-exposed` gives it;
- studies: a grid study written and checked on the page, run, its trials shown and its best confirmed on the test set
  (one look); an agent study asked and told from the page, then stopped; a past loop's results.tsv imported.

Every screen fits a phone's width.
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
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _signin
import _serve  # noqa: E402
import _signin  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbheld-"))
pub = Path(tempfile.mkdtemp(prefix="evh-wbheld-public-"))
env = dict(
    os.environ, EVH_ACTOR="person:tester", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-wb-held", GIT_AUTHOR_NAME="t",
    GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.org",
)  # fmt: skip
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_STORE", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)
WORDS = [
    "login",
    "invoice",
    "export",
    "api",
    "delete",
    "mobile",
    "crash",
    "slow",
    "sync",
    "email",
    "report",
    "refund",
]


import _cli  # noqa: E402


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return _cli.run(proj, env, *args, timeout=600)


def values(r: subprocess.CompletedProcess) -> dict:
    """A --json answer's values (the envelope is its last line)."""
    try:
        return (json.loads(r.stdout.splitlines()[-1]).get("result") or {}).get("values") or {}
    except (IndexError, ValueError):
        return {}


def git(where: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=where, env=env, check=True, capture_output=True)


def serve() -> tuple[subprocess.Popen, int, list[str]]:
    """catalog-serve on a free port; its startup lines once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
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
    return p, port, _serve.startup(p, lines)  # its start-up lines, the rest read as it comes


try:
    r = evh("init", "--store", "files", "--tutorial")
    # the baseline points at a recorded version of the goal's prompt: the agent study may change it
    r = (
        r
        if r.returncode
        else evh(
            "prompt-version",
            "--name",
            "g/prompt",
            "--text",
            "Keep what support needs.",
            "--note",
            "the first wording",
        )
    )
    base_ver = (
        values(evh("prompt-list", "--json"))
        or json.loads(evh("prompt-list", "--json").stdout.splitlines()[-1])["result"]
    )
    base_ver = ((base_ver.get("prompts") or [{}])[0]).get("latest") or ""
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "data" / "fields" / "t.yaml").write_text(
        "fieldset_id: t\nfields:\n  - name: opened\n    type: date\n    required: true\n"
        "  - name: kind\n    type: choice\n    values: [bug, question, access]\n  - name: alert\n    type: text\n"
    )
    names = sorted(x.stem for x in (proj / "tickets").glob("*.txt"))
    dates = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-08", "2026-11-09", "2026-11-10"]
    kinds = ["bug", "question", "bug", "access", "bug", "question"]
    (proj / "f.csv").write_text(
        "item_id,opened,kind,alert\n"
        + "".join(
            f"{n},{d},{k},ALERT-{i}\n" for i, (n, d, k) in enumerate(zip(names, dates, kinds, strict=True))
        )
    )
    for side, rng in (("val", range(12)), ("test", range(12, 24))):
        src, gold = proj / f"src_{side}", proj / f"gold_{side}"
        src.mkdir()
        gold.mkdir()
        for i in rng:
            s = [
                f"Ticket{i} " + " ".join(WORDS[(i + j * 3 + w) % len(WORDS)] for w in range(5)) + "."
                for j in range(4)
            ]
            (src / f"t{i:02d}.txt").write_text(" ".join(s) + "\n")
            (gold / f"t{i:02d}.txt").write_text(" ".join(s[:2]) + "\n")
    for sid, n, hyp in (
        ("sup_base_v1", 1, ""),
        ("sup_cand_v1", 2, ("hypothesis:\n  against: sup_base_v1\n  measure: overlap_f1\n  direction: better\n"
                           "  statement: two sentences keep what support needs\n")),
    ):  # fmt: skip
        (proj / "data" / "systems" / f"{sid}.yaml").write_text(
            f"system_id: {sid}\nparams:\n  provider: echo\n  sentences: {n}\n{hyp}"
            + (f"prompts:\n  g/prompt: {{version: {base_ver}}}\n" if sid == "sup_base_v1" else "")
        )
    steps = [
        ("dataset-create", "--dataset-id", "sup_v1", "--source-dir", "tickets", "--fieldset", "t", "--fields", "f.csv"),
        *[step for ds, side in (("tk_val", "val"), ("tk_test", "test")) for step in (
            ("dataset-create", "--dataset-id", ds, "--source-dir", f"src_{side}"),
            ("dataset-materialize", "--dataset-id", ds),
            ("label-import", "--sheet", f"gold_{side}", "--dataset-id", ds, "--set", "g", "--by", "person:owner"),
            ("reference-promote", "--dataset-id", ds, "--labels", "g", "--tier", "gold", "--reason",
             "the first two sentences of each ticket", "--by", "person:owner"),
        )],
        ("goal-new", "g", "--set", "title=Ticket summaries", "--set", "statement=A ticket's summary keeps what support needs.",
         "--set", "decision=Which summariser support uses.", "--set", "success_criteria.primary.measure=overlap_f1",
         "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=sup_v1",
         "--set", "datasets.0.role=validation", "--set", "datasets.1.dataset_id=tk_val", "--set", "datasets.1.role=validation",
         "--set", "datasets.2.dataset_id=tk_test", "--set", "datasets.2.role=test"),
        ("catalog",),
    ]  # fmt: skip
    for step in steps:
        r = r if r.returncode else evh(*step)
    (proj / "config.yaml").write_text(
        (proj / "config.yaml").read_text() + f"exposure:\n  public_repos: [{pub}]\n  ids: [alert]\n"
    )
    git(proj, "init", "-q")
    git(proj, "add", "-A")
    git(
        proj,
        "commit",
        "-q",
        "-m",
        "the project, its candidate and its hypothesis, before any item is held out",
    )
    git(pub, "init", "-q")
    (pub / "plan.md").write_text("we read ALERT-4 while fixing the gate\n")
    git(pub, "add", "-A")
    git(pub, "commit", "-q", "-m", "a plan that names a held-out alert")
    check(
        "setup: a git project with the goal, its datasets and a candidate whose hypothesis is committed",
        r.returncode == 0,
        (r.stdout + r.stderr)[-400:],
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("h1", timeout=20000)
            base = f"http://127.0.0.1:{port}/workbench/"

            def again(box: str) -> None:
                """The box's "Read it again", then the screen read fresh."""
                said = page.locator(box).inner_text()
                if not page.locator(f"{box} button:has-text('Read it again')").count():
                    raise AssertionError(f"{box} did not end well: {said[:800]}")
                page.click(f"{box} button:has-text('Read it again')")

            # ── the held-out test ──
            page.goto(f"{base}#goal/g")
            page.click("text=The held-out test")
            page.wait_for_selector("#sp-go", timeout=20000)
            page.fill("#ho-by", "tester")
            page.select_option("#sp-ds", "sup_v1")
            page.fill("#sp-key", "opened")
            page.fill("#sp-at", "2026-11-02T00:00:00Z")
            page.fill("#sp-count", "kind")
            page.click("#sp-go")
            page.wait_for_selector(
                "#sp-out:has-text('Both sides joined the goal'), #sp-out [role=alert]", timeout=60000
            )
            goal = yaml.safe_load((proj / "data" / "goals" / "g.yaml").read_text())
            test_doc = json.loads((proj / "data" / "datasets" / "sup_v1_test.json").read_text())
            check(
                "Hold some items out: dataset-split by time, sealed, its counts fixed; both sides join the goal with their roles",
                {(d["dataset_id"], d["role"]) for d in goal["datasets"]}
                >= {("sup_v1_validation", "validation"), ("sup_v1_test", "test")}
                and (test_doc.get("sealed") or {}).get("count_by") == ["kind"],
                (page.locator("#sp-out").inner_text()[:400], goal.get("datasets")),
            )
            again("#sp-out")
            page.wait_for_selector("#rd-go", timeout=20000)
            seal = page.locator("main").inner_text()
            check(
                "the seal: its held-out items, when it was sealed, what its counts may show, the side to tune on",
                "5" in seal and "sealed" in seal and "sup_v1_validation" in seal and "kind" in seal,
                seal[:600],
            )
            page.fill("#rd-items", names[1])
            page.fill("#rd-what", "decision and reason")
            page.fill("#rd-who", "agent:homelab")
            page.click("#rd-go")
            page.wait_for_selector("#rd-out:has-text('Done.'), #rd-out [role=alert]", timeout=60000)
            again("#rd-out")
            page.wait_for_selector("#lk-go", timeout=20000)
            ex = evh("exposure", "--dataset", "sup_v1_test", "--json")
            side = (json.loads(ex.stdout.splitlines()[-1])["result"]["sides"] or [{}])[0]
            check(
                "Record a read (exposure-add): who read what, counted as evh exposure counts it",
                side.get("exposed") == 1
                and side.get("by") == {"agent:homelab": 1}
                and "1 of 5" in page.locator("main").inner_text(),
                (side, page.locator("main").inner_text()[:500]),
            )
            page.click("#lk-go")
            page.wait_for_selector(
                "#lk-out button:has-text('Record them as reads'), #lk-out [role=alert]", timeout=60000
            )
            found = page.locator("#lk-out").inner_text()
            if page.locator("#lk-add").count():
                page.click("#lk-add")
                page.wait_for_selector("#lk-out:has-text('Done.'), #lk-out [role=alert]", timeout=60000)
            side = (
                json.loads(evh("exposure", "--dataset", "sup_v1_test", "--json").stdout.splitlines()[-1])[
                    "result"
                ]["sides"]
                or [{}]
            )[0]
            check(
                "the leak check (exposure-check, its finds a job's file) finds an id in a public repo; recorded as a read",
                side.get("exposed") == 2,
                (side, found[:600], page.locator("#lk-out").inner_text()[:400]),
            )
            again("#lk-out")
            page.wait_for_selector("#sc-go", timeout=20000)
            counts = page.locator("main").inner_text()
            check(
                "the counts, for safety only (sealed-counts): per day, by the fields fixed at the seal",
                "2026-11-03" in counts and "kind=bug" in counts.lower(),
                counts[counts.find("Counts") :][:600],
            )
            page.fill("#sc-add", "alert")
            page.fill("#sc-why", "the alerts tell which incidents the side holds")
            page.click("#sc-go")
            page.wait_for_selector("#sc-out:has-text('Done.'), #sc-out [role=alert]", timeout=60000)
            check(
                "allow one more field in the counts (dataset-seal-counts, a person's decision with why)",
                [
                    e.get("field")
                    for e in (
                        (
                            json.loads((proj / "data" / "datasets" / "sup_v1_test.json").read_text()).get(
                                "sealed"
                            )
                            or {}
                        ).get("count_by_added")
                        or []
                    )
                ]
                == ["alert"],
                page.locator("#sc-out").inner_text()[:300],
            )
            git(
                proj, "add", "-A"
            )  # the person commits the split before naming a candidate: a dirty tree is refused
            git(proj, "commit", "-q", "-m", "the split, sealed")
            page.select_option("#us-sys", "sup_cand_v1")
            page.fill("#us-why", "the two-sentence candidate, named before the side is read")
            page.click("#us-go")
            page.wait_for_selector("#us-out:has-text('Done.'), #us-out [role=alert]", timeout=60000)
            looks = json.loads(evh("looks", "--dataset", "sup_v1_test", "--json").stdout.splitlines()[-1])[
                "result"
            ]["sets"][0]
            check(
                "Open it for one candidate (dataset-unseal): its committed hypothesis, one look recorded",
                len(looks.get("looks") or []) == 1 and "look 1" in page.locator("#us-out").inner_text(),
                (page.locator("#us-out").inner_text()[:400], looks),
            )
            # the side's reference, now that a candidate is named (the prepare screen's work, done here by command)
            gold = proj / "gold_sup"
            gold.mkdir()
            for f in (KIT / "gold").iterdir():
                if f.stem in names[1:]:
                    shutil.copy(f, gold / f.name)
            r = evh(
                "label-import",
                "--sheet",
                str(gold),
                "--dataset-id",
                "sup_v1_test",
                "--set",
                "g",
                "--by",
                "person:owner",
            )
            r = r if r.returncode else evh("reference-promote", "--dataset-id", "sup_v1_test", "--labels", "g", "--tier", "gold",
                                           "--reason", "the kit's summaries for the held-out side", "--by", "person:owner")  # fmt: skip
            check(
                "setup: the held-out side's reference, after the candidate was named",
                r.returncode == 0,
                r.stderr[-300:],
            )
            again("#us-out")
            page.wait_for_selector("#hr-go", timeout=20000)
            page.click("#hr-go")
            page.wait_for_selector("#hr-out:has-text('Done.'), #hr-out [role=alert]", timeout=120000)
            again("#hr-out")
            page.wait_for_selector("text=the number that counts", timeout=30000)
            cli = values(evh("pair-test", "sup_v1_test", "--a", "sup_cand_v1", "--b", "sup_base_v1", "--metric", "overlap_f1",
                             "--include-exposed", "--json"))  # fmt: skip
            conf = page.locator("main").inner_text()
            check(
                "Run both on it, then the confirmation: the paired test with the read items left out, the number with them kept "
                "beside it, as evh pair-test --include-exposed gives it",
                cli.get("n") == 3
                and f"{cli['delta']:+.3f}" in conf
                and "2 read item(s) left out" in conf
                and "with the read items kept" in conf,
                (conf[-700:], {k: cli.get(k) for k in ("n", "delta", "p", "verdict", "with_exposed")}),
            )

            # ── studies ──
            page.goto(f"{base}#goal/g")
            page.click("text=Studies")
            page.wait_for_selector("#sn6-go", timeout=20000)
            check(
                "the studies: none yet",
                # "study" is a glossary word: underlined once, with its ? after it
                "No study" in page.locator("main").inner_text()
                and "yet." in page.locator("main").inner_text(),
                page.locator("main").inner_text()[:300],
            )
            page.fill("#st6-by", "tester")
            page.fill("#sn6-id", "s1")
            page.select_option("#sn6-ds", "tk_val")
            page.select_option("#sn6-base", "sup_base_v1")
            page.click("#sn6-fill")
            page.click("#sn6-dry")
            page.wait_for_selector("#sn6-out pre, #sn6-out [role=alert]", timeout=60000)
            check(
                "Check it, before its baseline has run on the validation set: refused, saying to run it first",
                "sup_base_v1 has no run on tk_val" in page.locator("#sn6-out").inner_text(),
                page.locator("#sn6-out").inner_text()[:400],
            )
            r = evh("run", "--system", "sup_base_v1", "--dataset", "tk_val")
            check(
                "setup: the baseline run on the validation set (the eval's work, done here by command)",
                r.returncode == 0,
                r.stderr[-300:],
            )
            page.click("#sn6-dry")
            page.wait_for_selector(
                "#sn6-out:has-text('Nothing was called'), #sn6-out [role=alert]:not(:has-text('no run on'))",
                timeout=60000,
            )
            check(
                "Check it: study-run's dry run through the spec written here, nothing called, nothing written",
                "Nothing was called" in page.locator("#sn6-out").inner_text()
                and not (proj / "data" / "studies").exists(),
                page.locator("#sn6-out").inner_text()[:400],
            )
            page.click("#sn6-go")
            page.wait_for_selector("#sn6-out a:has-text('Open it'), #sn6-out [role=alert]", timeout=120000)
            page.click("#sn6-out a:has-text('Open it')")
            page.wait_for_selector("h1:has-text('The study s1')", timeout=20000)
            page.wait_for_selector("#cf-go", timeout=20000)
            shown = (
                values(evh("study-show", "g", "s1", "--json"))
                or json.loads(evh("study-show", "g", "s1", "--json").stdout.splitlines()[-1])["result"]
            )
            one = page.locator("main").inner_text()
            check(
                "Run it: the study as a job under a cap; its trials, each with how it was decided, and the best so far, as "
                "study-show says",
                len(shown.get("rows") or []) == 3
                and "t3" in one
                and "kept" in one
                and f"Best so far: {shown.get('best')}" in one,
                (one[:900], shown.get("best")),
            )
            # RFC-034: the trials drawn above their table, the best so far as a line, and each against its cost.
            page.wait_for_selector("[data-chart='study-progress'] svg", timeout=60000)
            page.wait_for_selector("[data-chart='gain-cost'] svg", timeout=60000)
            check(
                "its trials drawn: kept filled, dropped hollow, the best so far from the baseline; each trial's gain "
                "against its cost",
                page.locator("[data-chart='study-progress'] svg polyline").count() == 1
                and page.locator("[data-chart='study-progress'] svg circle").count() >= 3
                and page.locator("[data-chart='gain-cost'] svg circle").count() >= 1,
                page.locator("[data-chart='study-progress']").inner_text()[:300],
            )
            page.select_option("#cf-test", "tk_test")
            page.click("#cf-dry")
            page.wait_for_selector("#cf-out pre, #cf-out [role=alert]", timeout=60000)
            check(
                "Confirm it, first what it would read (the dry run): its items and its look, nothing run",
                "look 1" in page.locator("#cf-out").inner_text()
                and not (
                    json.loads(evh("looks", "--dataset", "tk_test", "--json").stdout.splitlines()[-1])[
                        "result"
                    ]["sets"][0].get("looks")
                ),
                page.locator("#cf-out").inner_text()[:400],
            )
            page.click("#cf-go")
            page.wait_for_selector(
                "#cf-out button:has-text('Read it again'), #cf-out [role=alert]", timeout=120000
            )
            again("#cf-out")
            page.wait_for_selector("#cf-go", timeout=20000)
            check(
                "Confirm it (study-confirm, a decision): one look at the test set; its outcome listed with the study",
                "better" in page.locator("main").inner_text()
                and "1 confirmed" in page.locator("main").inner_text(),
                page.locator("main").inner_text()[-900:],
            )
            page.goto(f"{base}#study/g")
            page.wait_for_selector("#sn6-go", timeout=20000)
            page.fill("#sn6-id", "s2")
            page.select_option("#sn6-ds", "tk_val")
            page.select_option("#sn6-base", "sup_base_v1")
            page.select_option("#sn6-sampler", "agent")
            page.click("#sn6-fill")
            page.wait_for_function(
                "() => document.querySelector('#sn6-spec').value.includes('prompts: [g/prompt]')",
                timeout=20000,
            )
            page.click("#sn6-go")
            page.wait_for_selector("#sn6-out a:has-text('Open it'), #sn6-out [role=alert]", timeout=120000)
            page.click("#sn6-out a:has-text('Open it')")
            page.wait_for_selector("#sa-go", timeout=20000)
            page.click("#sa-go")
            page.wait_for_selector("#tl-go", timeout=60000)
            offered = json.loads(page.input_value("#tl-json"))
            check(
                "an agent study whose baseline points at a prompt version: its spec lets the agent change that prompt, and "
                "a proposal starts from the best so far's text",
                offered.get("prompts") == {"g/prompt": "Keep what support needs."},
                offered,
            )
            page.fill(
                "#tl-json",
                json.dumps(
                    {
                        "params": {"sentences": 2},
                        "prompts": {"g/prompt": "Keep what support needs, in two sentences."},
                        "hypothesis": "two keep more",
                        "rationale": "the gold keeps two",
                    }
                ),
            )
            page.click("#tl-go")
            page.wait_for_selector(
                "#tl-out button:has-text('Read it again'), #tl-out [role=alert]", timeout=120000
            )
            again("#tl-out")
            page.wait_for_selector("#so-stop", timeout=20000)
            check(
                "an agent study from the page: its state asked (study-ask), a proposal told (study-tell) and run as its trial, "
                "its prompt a new version made from the baseline's",
                "two keep more" in page.locator("main").inner_text()
                and "kept" in page.locator("main").inner_text()
                and len(
                    pvs := json.loads(
                        evh("prompt-show", "--name", "g/prompt", "--json").stdout.splitlines()[-1]
                    )["result"]["versions"]
                )
                == 2
                and pvs[1].get("parent") == base_ver
                and any(r["run_id"].startswith("s2-t1") for r in pvs[1]["runs"]),
                (
                    page.locator("main").inner_text()[:600],
                    evh("prompt-show", "--name", "g/prompt").stdout[-600:],
                ),
            )
            page.click("#so-stop")
            page.wait_for_selector(
                "#so-out button:has-text('Read it again'), #so-out [role=alert]", timeout=60000
            )
            again("#so-out")
            page.wait_for_function(
                "() => /ended/.test(document.querySelector('main').textContent)", timeout=20000
            )
            check(
                "Stop it (study-stop): the study ends",
                "ended" in page.locator("main").inner_text(),
                page.locator("main").inner_text()[:400],
            )
            tsv = proj / "results.tsv"
            tsv.write_text(
                "commit\tval_bpb\tmemory_gb\tstatus\tdescription\n"
                "a1b2c3d\t0.997\t44.0\tkeep\tbaseline\nb2c3d4e\t0.993\t44.2\tkeep\tbigger lr\nc3d4e5f\t1.005\t44.0\tdiscard\tswiglu\n"
            )  # fmt: skip
            page.goto(f"{base}#study/g")
            page.wait_for_selector("#si-go", timeout=20000)
            page.fill("#si-id", "karpathy")
            page.set_input_files("#si-file", str(tsv))
            page.click("#si-go")
            page.wait_for_selector(
                "#si-out button:has-text('Read it again'), #si-out [role=alert]", timeout=60000
            )
            again("#si-out")
            page.wait_for_selector("text=g/karpathy", timeout=20000)
            check(
                "Import a past loop (study-import, the results.tsv an upload): a closed study, listed with the others",
                "g/karpathy" in page.locator("main").inner_text()
                and "g/s1" in page.locator("main").inner_text()
                and not errors,
                (page.locator("main").inner_text()[:600], errors[:2]),
            )
            phone = browser.new_context(
                viewport={"width": 390, "height": 844}, storage_state=page.context.storage_state()
            ).new_page()
            wide = {}
            for screen, h1 in (
                ("heldout/g", "The held-out test"),
                ("study/g", "Studies"),
                ("study/g/s1", "The study s1"),
            ):
                phone.goto(f"{base}#{screen}")
                phone.wait_for_selector(f"h1:has-text('{h1}')", timeout=20000)
                # measured once every chart on the screen is drawn: a chart lands after the screen, and measured
                # before it, a chart that widened the page passed (review, 2026-11-19)
                phone.wait_for_function(
                    "() => !document.querySelector('.chart-box [role=status]')", timeout=30000
                )
                wide[screen] = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(
                "at a phone's width the held-out test and the studies do not scroll sideways",
                all(v <= 0 for v in wide.values()),
                wide,
            )
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(pub, ignore_errors=True)
sys.exit(summary())
