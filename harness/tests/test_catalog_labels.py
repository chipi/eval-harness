#!/usr/bin/env python3
"""The catalog's RFC-023 pages (step 8): tier pills, source chips, the labels page, a dataset's labels, picks and
added items, where a reference was promoted from, production's recorded arm.

    python tests/test_catalog_labels.py

In a throwaway project built from the tutorial ($0, offline): a model's label set (a run's outputs) and a person's
(a sheet), the person's promoted to gold, an arm scored against the model's set, a capture with production's
recorded arm, a pick waiting for the governed dataset and a version made from another; then `evh catalog`. Every
page says what UXS-001 says it shows, and writes nothing a page could act on (the selection gives a command).
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-catlabels-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-catalog-labels")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_PUBLIC"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def page(rel):
    p = proj / "cat" / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def row_of(html, needle):
    """The <tr> holding `needle`, or ""."""
    return next((tr for tr in re.findall(r"<tr\b.*?</tr>", html, flags=re.S) if needle in tr), "")


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, out(r)[-300:])
    (data / "goals").mkdir()
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    for arm in ("lead1", "author"):
        cfg = data / "configs" / f"tickets_{arm}.yaml"
        cfg.write_text((KIT / "configs" / f"tickets_{arm}.yaml").read_text() + "goal: tickets_summary\n")
        r = evh("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
    author = next(p.name for p in (data / "runs").glob("tickets_author_v1_*"))
    r = evh("label-from-run", "--run", author, "--set", "author_v1")
    check("setup: a model's label set", r.returncode == 0, out(r)[-300:])
    with (proj / "sheet.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "label"])
        w.writerows(
            [["t01_login", "Login fails."], ["t02_invoice", "Invoice wrong."], ["t03_export", "Export."]]
        )
    r = evh("label-import", "sheet.csv", "--dataset-id", "tickets_v1", "--set", "owner_v1", "--by", "owner")
    check("setup: a person's label set", r.returncode == 0, out(r)[-300:])
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "gold",
        "--reason",
        "The owner's own answers are what we decide on.",
        "--by",
        "owner",
    )
    check("setup: the person's set promoted to gold", r.returncode == 0, out(r)[-300:])
    r = evh(
        "experiment-run", "--config", "data/configs/tickets_lead1.yaml", "--labels", "tickets_v1/author_v1"
    )
    check("setup: an arm scored against the model's label set", r.returncode == 0, out(r)[-300:])
    rows = [
        {
            "id": f"p{n}",
            "body": f"A new production ticket number {n}.",
            "channel": "email",
            "created_at": f"2026-11-0{n}T09:00:00Z",
        }
        for n in range(1, 4)
    ]
    (proj / "prod.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "prod.jsonl"}),
        "--capture",
        "prod_c1",
    )
    r = r if r.returncode else evh("dataset-from-capture", "prod_c1", "--dataset-id", "prod_v1")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "prod_v1")
    check("setup: a capture and its dataset", r.returncode == 0, out(r)[-300:])
    r = evh(
        "arm-from-capture",
        "--dataset-id",
        "prod_v1",
        "--capture",
        "prod_c1",
        "--as",
        "production_v1",
        "--field",
        "channel",
    )
    check("setup: production's recorded arm", r.returncode == 0, out(r)[-300:])
    r = evh(
        "pick", "--dataset-id", "prod_v1", "--item", "p1", "--for", "tickets_v1", "--note", "nothing like it"
    )
    r = r if r.returncode else evh("dataset-extend", "tickets_v1", "--dataset-id", "tickets_v2", "--picks")
    check("setup: a version made from a pick", r.returncode == 0, out(r)[-300:])
    r = evh(
        "pick",
        "--dataset-id",
        "prod_v1",
        "--item",
        "p2",
        "--for",
        "tickets_v1",
        "--tag",
        "case=new",
        "--by",
        "owner",
    )
    check("setup: a pick waiting", r.returncode == 0, out(r)[-300:])
    lead = sorted(p.name for p in (data / "runs").glob("tickets_lead1_v1_*"))[0]
    r = evh("run-promote", "--run", lead, "--reason", "The lead sentence is enough, for the catalog's test.")
    check("setup: a baseline promoted", r.returncode == 0, out(r)[-300:])
    r = evh("catalog", "--out", "cat")
    check("the catalog builds", r.returncode == 0, out(r)[-600:])

    cov = re.search(r'<table[^>]*id="coverage".*?</table>', page("index.html"), flags=re.S)
    cov_row = row_of(cov.group(0) if cov else "", ">tickets_v1<")
    check(
        "overview coverage: an arm scored against a label set counts as labels; the two run before any reference as none",
        "labels <b>1</b>" in cov_row and "none <b>2</b>" in cov_row,
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cov_row))[:400],
    )

    # ── the labels page ──────────────────────────────────────────────────────────────────────
    lp = page("labels.html")
    au, ow = row_of(lp, "author_v1"), row_of(lp, "owner_v1")
    check(
        "labels page: each set with its source chip, its dataset, coverage, who made it, whether it was promoted",
        'class="src src-model"' in au
        and "6 of 6" in au
        and "not promoted" in au
        and 'class="src src-person"' in ow
        and "3 of 6" in ow
        and "person · owner" in ow
        and 'class="pill tier-gold"' in ow
        and 'id="set-tickets_v1-owner_v1"' in ow,
        (au + ow)[:900],
    )
    check(
        "the menu names the labels page",
        'href="labels.html"' in page("index.html") or 'href="../labels.html"' in page("d/tickets_v1.html"),
        "",
    )

    # ── references: pills, promoted from ─────────────────────────────────────────────────────
    rp = page("references.html")
    rr = row_of(rp, "gold/tickets_v1")
    check(
        "references page: the tier a pill, promoted from the label set with its source chip",
        'class="pill tier-gold"' in rr and 'class="src src-person"' in rr and "owner_v1" in rr,
        rr[:600],
    )
    ref = page("r/gold-tickets_v1.html")
    check(
        "reference page: its pill in the hero; promoted from the set, by whom, why",
        'class="pill tier-gold"' in ref
        and "Promoted from" in ref
        and "by owner" in ref
        and "The owner&#x27;s own answers are what we decide on." in ref,
        re.sub(r"\s+", " ", ref)[:900],
    )

    # ── the dataset page ─────────────────────────────────────────────────────────────────────
    dp = page("d/tickets_v1.html")
    check(
        "dataset page: its label sets (chips, coverage, promoted) and how often two agree",
        'id="labels"' in dp
        and row_of(dp, "author_v1") != ""
        and "how often two sets agree" in dp
        and "the same label, on the items both label" in dp,
        "",
    )
    pick_row = row_of(dp, 'value="prod_v1:p2"')
    check(
        "dataset page: a pick waiting, its source, tags, who; a box per row and the command the boxes give",
        'class="cmdsel"' in pick_row
        and "prod_v1" in pick_row
        and "capture prod_c1" in pick_row
        and "case=new" in pick_row
        and "owner" in pick_row
        and 'data-prefix="evh dataset-extend tickets_v1 --dataset-id &lt;next&gt;"' in dp
        and 'data-flag="--pick"' in dp
        and "rows=1&item=p2" in pick_row,
        pick_row[:700],
    )
    arm_row = row_of(dp, "labels.html#set-tickets_v1-author_v1")
    check(
        "an arm scored against a label set: tinted t-labels, its source chip and set named, the row key says so",
        'class="t-labels"' in arm_row
        and 'class="src src-model"' in arm_row
        and "scored against a label set, not a reference" in dp,
        arm_row[:600],
    )
    gold_row = row_of(dp, "r/gold-tickets_v1.html")
    check(
        "an arm scored against a reference: its pill beside it",
        'class="pill tier-gold"' in gold_row,
        gold_row[:500],
    )
    v2 = page("d/tickets_v2.html")
    added = row_of(v2, "<code>p1</code>")
    check(
        "a version made from picks: each item it added, where it came from, the note",
        "added from production" in v2
        and "prod_v1" in added
        and "capture prod_c1" in added
        and "nothing like it" in added,
        (added or v2[:300])[:600],
    )

    check(
        "labels follow the item: v2's page counts the sets made on v1, and shows no pick that names only v1",
        "6 of 7" in row_of(v2, "author_v1") and 'value="prod_v1:p2"' not in v2,
        row_of(v2, "author_v1")[:400],
    )

    # ── production's recorded arm, the captures page ─────────────────────────────────────────
    pp = page("d/prod_v1.html")
    check(
        "a recorded arm is badged wherever it is named",
        'class="badge recorded"' in row_of(pp, "production_v1"),
        row_of(pp, "production_v1")[:400],
    )
    check(
        "a dataset with no labels says so, with the commands",
        "No labels yet" in pp and "evh label-sheet --dataset-id prod_v1" in pp,
        "",
    )
    cp = page("captures.html")
    crow = row_of(cp, "capture-prod_c1")
    check(
        "captures page: the rule-set words; its datasets; the recorded arm made from it",
        "a <code>rule</code> label set, promoted like any" in cp
        and "prod_v1" in crow
        and "production_v1" in crow,
        crow[:600],
    )
    ap = page("a/runs-prod_v1-production_v1.html")
    check(
        "recorded arm page: the badge, production's decisions from the capture (linked), no model called",
        'class="badge recorded"' in ap
        and "no model was called" in ap
        and 'href="../captures.html#capture-prod_c1"' in ap,
        re.sub(r"\s+", " ", ap)[:600],
    )
    check(
        "recorded arm page: cost and speed read recorded, no call; its config the capture and how it was read",
        "recorded, no call" in ap and "the record&#x27;s field channel" in ap and "production_v1" in ap,
        "",
    )
    check(
        "a recorded arm's row: its cost and speed read recorded, no call",
        "recorded, no call" in row_of(pp, "production_v1"),
        row_of(pp, "production_v1")[:500],
    )
    bp = page("a/runs-tickets_v1-tickets_lead1_v1.html")
    check(
        "a promoted arm's page: its deploy sheet (what was sent, the bookkeeping not sent, the command)",
        'id="deploy-sheet"' in bp
        and "settings sent" in bp
        and "evh deploy-sheet --config tickets_lead1_v1" in bp
        and "No capture here says what production ran" in bp,
        "",
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from evaluation_harness.catalog_adapter import load_catalog_adapter as L; A = L(None); "
                "print(json.dumps([A.deploy_sheet(a) is None for a in "
                "('runs/tickets_v1/tickets_author_v1', 'runs/tickets_v1/tickets_lead1_v1')]))"
            ),
        ],
        cwd=proj,
        env={**env, "PYTHONPATH": str(HERE.parent)},
        capture_output=True,
        text=True,
    )
    check(
        "the adapter's deploy_sheet: none for an arm never promoted, one for the promoted arm",
        probe.stdout.strip() == "[true, false]",
        out(probe)[-300:],
    )
    check(
        "an arm never promoted has no deploy sheet",
        'id="deploy-sheet"' not in page("a/runs-tickets_v1-tickets_author_v1.html"),
        "",
    )
    gp = page("g/tickets_summary.html")
    check(
        "goal page: a group scored against a label set is headed by its source chip and name; the baseline's sheet",
        re.search(r'<h3 class="sub">scored against <span class="src src-model">model</span>', gp) is not None
        and "deploy sheet: what production must match" in gp,
        "",
    )
    from evaluation_harness.catalog_build import deploy_verdicts

    ok = {"captures": [{"capture": "c1", "records": 4, "ok": True, "keys": {}}]}
    bad = {
        "captures": [
            {
                "capture": "c2",
                "records": 4,
                "ok": False,
                "keys": {
                    "model": {"match": 3, "differ": {"m-two": 1}, "missing": 0},
                    "prompt_sha": {"match": 2, "differ": {}, "missing": 2},
                },
            }
        ]
    }
    check(
        "the capture verdicts: every decision matched, or what differs and what is not recorded",
        "every one of its 4 decisions was made by the promoted model and prompt" in deploy_verdicts(ok)
        and "differ: m-two (1)" in deploy_verdicts(bad)
        and "not recorded: 2" in deploy_verdicts(bad),
        deploy_verdicts(bad),
    )

    # ── the inspector's rows view and item view (the server's functions, as /api/rows and /api/item answer) ──
    def serve_call(code):
        r = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json; from evaluation_harness import catalog_serve as cs; "
                    "from evaluation_harness.catalog_adapter import load_catalog_adapter as L; cs.set_adapter(L(None)); "
                    + code
                ),
            ],
            cwd=proj,
            env={**env, "PYTHONPATH": str(HERE.parent)},
            capture_output=True,
            text=True,
        )
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"error": out(r)[-400:]}

    arms = "runs/tickets_v1/tickets_lead1_v1,runs/tickets_v1/tickets_author_v1"
    rw = serve_call(
        f"print(json.dumps(cs.rows({{'dataset': ['tickets_v1'], 'runs': ['{arms}'], 'wrong': ['owner_v1']}})))"
    )
    by = {r["item"]: r for r in rw.get("rows", [])}
    check(
        "/api/rows: every item, each arm's decision, its labels, the signals and their counts, the sets to choose",
        len(by) == 6
        and set(by["t01_login"]["decisions"]) == set(arms.split(","))
        and any(
            x["set"] == "tickets_v1/owner_v1" and x["kind"] == "person" for x in by["t01_login"]["labels"]
        )
        and "unlabelled" not in by["t01_login"]["signals"]
        and rw["counts"]["unlabelled"] == 0
        and "tickets_v1/owner_v1" in rw["sets"]
        and "prod_v1" in rw["datasets"],
        json.dumps(rw)[:600],
    )
    pr = serve_call(
        "print(json.dumps(cs.rows({'dataset': ['prod_v1'], 'runs': ['runs/prod_v1/production_v1']})))"
    )
    pby = {r["item"]: r for r in pr.get("rows", [])}
    check(
        "/api/rows: a pick waiting says for which dataset; a refused arm is said in its own words",
        pby.get("p2", {}).get("picked") == ["tickets_v1"]
        and "not an arm on prod_v1"
        in serve_call(
            "print(json.dumps(cs.rows({'dataset': ['prod_v1'], 'runs': ['runs/tickets_v1/x_v1']})))"
        ).get("error", ""),
        json.dumps(pr)[:400],
    )
    pub = serve_call(
        "cs.LIMITS['hosts'] = ('public',); print(json.dumps(cs.rows({'dataset': ['tickets_v1']})))"
    )
    check("/api/rows is not served publicly", "not served publicly" in pub.get("error", ""), json.dumps(pub))
    it = serve_call("print(json.dumps(cs.item({'dataset': ['tickets_v1'], 'item': ['t01_login']})))")
    check(
        "/api/item for a dataset alone (the rows view): the item's fields and every label, with its source",
        it.get("views") == {}
        and any(
            x["set"] == "tickets_v1/owner_v1" and x["kind"] == "person" and x["text"]
            for x in it.get("labels", [])
        ),
        json.dumps(it)[:500],
    )
    ri = serve_call("print(json.dumps(cs.item({'arms': ['runs/prod_v1/production_v1'], 'item': ['p1']})))")
    check(
        "/api/item: production's recorded output is marked with its capture",
        ri.get("recorded") == {"runs/prod_v1/production_v1": "prod_c1"},
        json.dumps(ri)[:400],
    )
    check(
        "the dataset page's explore-rows button opens the rows view, production's recorded arm chosen first",
        'inspect.html?dataset=prod_v1&rows=1&runs=runs/prod_v1/production_v1"' in pp,
        "",
    )
    check(
        "the selection's script is in the catalog's assets (the page itself writes nothing)",
        ".cmdpick" in page("assets/catalog.js") and "<form" not in dp,
        "",
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
