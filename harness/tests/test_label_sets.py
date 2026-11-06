#!/usr/bin/env python3
"""Label sets (RFC-023 step 2): what is right for an item, and who said it.

    python tests/test_label_sets.py

In a throwaway project built from the tutorial ($0, offline): a run's outputs become a `model` set, with the
refusals of a reference's provenance (a clean, finished run); a sheet of the items to label (unlabelled, all, where two runs disagree, chosen
ones, with a proposal) and its import as a `person` set (`yes` takes the proposal, notes kept); a set is never
edited; a capture's outcomes become a `rule` set by the mapping; `evh labels` lists the sets, their coverage and
how often two agree; and labels follow an item by its sha256 into another dataset holding it.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def _set_output(d, item, text):
    """Change one output of a run in place (None removes it), as a hand edit of its outputs.jsonl would."""
    texts = _outputs.outputs(d)
    texts.pop(item, None)
    if text is not None:
        texts[item] = text
    _outputs.write_all(d, texts, list(texts))


proj = Path(tempfile.mkdtemp(prefix="evh-labels-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-labels")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in out(r) and text in out(r)


LABELS = proj / "data" / "labels"

try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    shutil.copytree(KIT / "production", proj / "tutorial" / "production")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, out(r)[-300:])
    (data / "goals").mkdir()
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    for arm in ("lead1", "author"):
        cfg = data / "configs" / f"tickets_{arm}.yaml"
        cfg.write_text((KIT / "configs" / f"tickets_{arm}.yaml").read_text() + "goal: tickets_summary\n")
        r = evh("run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
    author = next(p.name for p in (data / "runs").glob("tickets_author_v1_*"))
    lead = next(p.name for p in (data / "runs").glob("tickets_lead1_v1_*"))

    # ── label-from-run ──────────────────────────────────────────────────────────────────────
    (proj / "author_prompt.txt").write_text("Summarise the ticket for the support lead.\n")
    r = evh("label-from-run", "--run", author, "--set", "author_v1", "--guideline", "author_prompt.txt")
    doc = (
        json.loads((LABELS / "tickets_v1" / "author_v1" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-from-run: the run's outputs as a model set, its source the run, its guideline hashed",
        doc.get("n_items") == 6
        and doc["source"]["kind"] == "model"
        and doc["source"]["run_id"] == author
        and doc["guideline"]["path"] == "author_prompt.txt"
        and len(doc["guideline"]["sha256"]) == 64
        and all(len(v["item_sha256"]) == 64 for v in doc["items"].values())
        and (LABELS / "tickets_v1" / "author_v1" / "t01_login.txt").read_text()
        == (_outputs.output(data / "runs" / author, "t01_login") or "").strip() + "\n",
        out(r)[-300:],
    )
    r = evh("label-from-run", "--run", author, "--set", "author_v1")
    check("a set is never edited: the same name again is refused", refused(r, "never edited"), out(r)[-300:])
    r = evh("label-from-run", "--run", author, "--set", "../escape")
    check("a set's name cannot leave data/labels/", refused(r, "lowercase"), out(r)[-200:])
    r = evh("label-from-run", "--run", "no_such_run", "--set", "x")
    check("label-from-run: an unknown run is refused", refused(r, "no finished run"), out(r)[-200:])

    # ── label-sheet ───────────────────────────────────────────────────────────────────────
    def sheet(name, *args):
        p = proj / name
        r = evh("label-sheet", "--dataset-id", "tickets_v1", "--out", name, *args)
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig"))) if r.returncode == 0 else []
        return r, rows

    r, rows = sheet("s_unlabelled.csv")
    check(
        "label-sheet: by default only the unlabelled items (the model set covers all six)",
        r.returncode == 0 and rows == [],
        out(r)[-200:],
    )
    r, rows = sheet("s_all.csv", "--items", "all", "--runs", f"{lead},{author}", "--propose", "author_v1")
    check(
        "label-sheet --items all: every item, the start of the item, each run's decision, the proposal, empty label",
        len(rows) == 6
        and rows[0]["item"]
        and rows[0][f"decided: {lead}"]
        and rows[0]["proposal"]
        == (LABELS / "tickets_v1" / "author_v1" / f"{rows[0]['item_id']}.txt").read_text().strip()
        and rows[0]["label"] == "",
        out(r)[-300:],
    )
    r, rows = sheet("s_dis.csv", "--items", "disagree", "--runs", f"{lead},{author}")
    lo = {k: v.strip() for k, v in _outputs.outputs(data / "runs" / lead).items()}
    au = {k: v.strip() for k, v in _outputs.outputs(data / "runs" / author).items()}
    check(
        "label-sheet --items disagree: exactly the items the two runs decided differently",
        r.returncode == 0
        and sorted(x["item_id"] for x in rows) == sorted(i for i in lo if lo[i] != au.get(i)),
        out(r)[-300:],
    )
    r, rows = sheet("s_pick.csv", "--item", "t02_invoice", "--item", "t04_api", "--runs", "tickets_lead1_v1")
    check(
        "label-sheet --item: exactly those; a config names its latest run",
        [x["item_id"] for x in rows] == ["t02_invoice", "t04_api"],
        out(r)[-300:],
    )
    r, _ = sheet("s_pick.csv", "--items", "all")
    check("label-sheet: an existing sheet is never overwritten", refused(r, "not overwritten"), out(r)[-200:])
    r, _ = sheet("s_bad.csv", "--items", "disagree", "--runs", lead)
    check("label-sheet --items disagree needs two runs", refused(r, "two runs"), out(r)[-200:])

    # ── label-import ──────────────────────────────────────────────────────────────────────
    filled = proj / "filled.csv"
    with (proj / "s_all.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rows[0]["label"], rows[0]["note"] = "needs-engineering", "a real bug"
    rows[1]["label"] = "yes"
    rows[2]["label"] = "support-only"
    with filled.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    r = evh("label-import", "filled.csv", "--dataset-id", "tickets_v1", "--set", "owner_v1", "--by", "owner")
    doc = (
        json.loads((LABELS / "tickets_v1" / "owner_v1" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-import: the filled rows as a person set; `yes` takes the proposal; a note kept; empty rows left out",
        doc.get("n_items") == 3
        and doc["source"]
        == {
            "kind": "person",
            "by": "owner",
            "sheet": "filled.csv",
            "sheet_sha256": doc["source"].get("sheet_sha256"),
        }
        and (LABELS / "tickets_v1" / "owner_v1" / f"{rows[1]['item_id']}.txt").read_text().strip()
        == rows[1]["proposal"]
        and doc.get("notes") == {rows[0]["item_id"]: "a real bug"},
        out(r)[-300:],
    )
    answers = proj / "answers"
    answers.mkdir()
    (answers / "t01_login.txt").write_text("Login fails after SSO change.\n")
    (answers / "t04_api.txt").write_text("Rate limit lower than documented.\n")
    r = evh("label-import", "answers", "--dataset-id", "tickets_v1", "--set", "owner_files", "--by", "owner")
    fdoc = (
        json.loads((LABELS / "tickets_v1" / "owner_files" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-import: a folder of <item_id>.txt as a person set, its files hashed",
        fdoc.get("n_items") == 2
        and fdoc["source"].get("kind") == "person"
        and fdoc["source"].get("folder") == "answers"
        and len(fdoc["source"].get("folder_sha256", "")) == 64
        and (LABELS / "tickets_v1" / "owner_files" / "t04_api.txt").read_text()
        == "Rate limit lower than documented.\n",
        out(r)[-300:],
    )
    # 2026-11-04 (a beta agent): a refusal found late (a --guideline file that does not exist) left the set's
    # .txt files written and no labels.json, and the half set then blocked its own name.
    r = evh(
        "label-import", "answers", "--dataset-id", "tickets_v1", "--set", "half_set", "--by", "owner",
        "--guideline", "no_such_guideline.md",
    )  # fmt: skip
    half = LABELS / "tickets_v1" / "half_set"
    check(
        "label-import: a refusal writes nothing, so the name stays free",
        r.returncode != 0
        and "--guideline" in out(r)
        and not (half.exists() and any(half.iterdir()))
        and not any(p.name.startswith(".half_set") for p in (LABELS / "tickets_v1").iterdir()),
        out(r)[-300:],
    )
    (proj / "guide.md").write_text("Summarise the ticket's problem in one sentence.\n")
    r = evh(
        "label-import", "answers", "--dataset-id", "tickets_v1", "--set", "half_set", "--by", "owner",
        "--guideline", "guide.md",
    )  # fmt: skip
    check(
        "label-import: after a refusal, the same name imports",
        r.returncode == 0 and (half / "labels.json").is_file() and (half / "t01_login.txt").is_file(),
        out(r)[-300:],
    )
    shutil.rmtree(half)  # this throwaway set is not one the checks below count
    (proj / "empty").mkdir()
    r = evh("label-import", "empty", "--dataset-id", "tickets_v1", "--set", "none_v1", "--by", "owner")
    check("label-import: an empty folder is refused", refused(r, "no <item_id>.txt"), out(r)[-200:])
    # ── a sheet opened in Excel and saved back (owner, 2026-11-02: CSV only, Excel-friendly) ──────────────────────
    r = evh(
        "label-sheet",
        "--dataset-id",
        "tickets_v1",
        "--items",
        "all",
        "--choices",
        "file,dismiss,escalate",
        "--out",
        "excel.csv",
    )
    raw = (proj / "excel.csv").read_bytes() if (proj / "excel.csv").is_file() else b""
    check(
        "label-sheet: UTF-8 with the mark Excel needs; the allowed answers in the label column's header",
        r.returncode == 0
        and raw.startswith(b"\xef\xbb\xbf")
        and "label [file|dismiss|escalate]" in raw.decode("utf-8-sig").splitlines()[0],
        out(r)[-300:] + raw[:200].decode("utf-8", "replace"),
    )
    # As Excel saves it where the comma is the decimal mark: the mark kept, `;` between columns, CRLF lines.
    (proj / "excel_saved.csv").write_bytes(
        "\ufeffitem_id;item;proposal;label [file|dismiss|escalate];also right;note\r\n"
        "t01_login;Login fails;;file;escalate;\r\nt02_invoice;Invoice wrong;;dismiss;;\r\n".encode()
    )
    r = evh(
        "label-import", "excel_saved.csv", "--dataset-id", "tickets_v1", "--set", "excel_v1", "--by", "owner"
    )
    check(
        "label-import: Excel's own CSV (the mark, `;`, CRLF) reads back, also right included",
        r.returncode == 0
        and (LABELS / "tickets_v1" / "excel_v1" / "t01_login.txt").read_text()
        == '{"accept": ["escalate", "file"]}\n'
        and (LABELS / "tickets_v1" / "excel_v1" / "t02_invoice.txt").read_text() == "dismiss\n",
        out(r)[-300:],
    )
    (proj / "excel_typo.csv").write_bytes(
        "\ufeffitem_id;label [file|dismiss|escalate]\r\nt01_login;dismis\r\nt02_invoice;file\r\n".encode()
    )
    r = evh(
        "label-import", "excel_typo.csv", "--dataset-id", "tickets_v1", "--set", "typo_v1", "--by", "owner"
    )
    check(
        "label-import: an answer not among the sheet's choices is refused, naming the row; nothing is written",
        refused(r, "t01_login: 'dismis'") and not (LABELS / "tickets_v1" / "typo_v1").exists(),
        out(r)[-300:],
    )
    (proj / "book.xlsx").write_bytes(b"PK\x03\x04 a workbook")
    r = evh("label-import", "book.xlsx", "--dataset-id", "tickets_v1", "--set", "book_v1", "--by", "owner")
    check(
        "label-import: a workbook is refused, saying how to save it as CSV",
        refused(r, "Save As > CSV UTF-8"),
        out(r)[-300:],
    )
    shutil.rmtree(LABELS / "tickets_v1" / "excel_v1", ignore_errors=True)

    # ── an item with more than one right answer (owner, 2026-11-02: a label can accept several) ───────────────────
    (proj / "several.csv").write_text(
        "item_id,label,also right,note\nt01_login,file,escalate | file,\nt02_invoice,dismiss,,\n"
    )
    r = evh(
        "label-import", "several.csv", "--dataset-id", "tickets_v1", "--set", "several_v1", "--by", "owner"
    )
    several = LABELS / "tickets_v1" / "several_v1"
    check(
        "label-import: `also right` adds the other right answers; one meaning, one text (sorted, no repeats)",
        r.returncode == 0
        and (several / "t01_login.txt").read_text() == '{"accept": ["escalate", "file"]}\n'
        and (several / "t02_invoice.txt").read_text() == "dismiss\n",
        out(r)[-300:],
    )
    (answers / "t01_login.txt").write_text('{"accept": ["file", "escalate", "file"]}\n')
    (answers / "t04_api.txt").unlink()
    r = evh(
        "label-import", "answers", "--dataset-id", "tickets_v1", "--set", "several_files", "--by", "owner"
    )
    check(
        "label-import: a folder's {\"accept\": [...]} is the same label as the sheet's",
        r.returncode == 0
        and (LABELS / "tickets_v1" / "several_files" / "t01_login.txt").read_text()
        == (several / "t01_login.txt").read_text(),
        out(r)[-300:],
    )
    (proj / "notalist.csv").write_text('item_id,label\nt01_login,"{""accept"": ""file""}"\n')
    r = evh(
        "label-import", "notalist.csv", "--dataset-id", "tickets_v1", "--set", "bad_accept", "--by", "owner"
    )
    check(
        'label-import: {"accept": ...} that is not a list of answers is refused, saying how to write one',
        refused(r, "not a list of answers") and not (LABELS / "tickets_v1" / "bad_accept").exists(),
        out(r)[-300:],
    )
    (proj / "one.csv").write_text("item_id,label\nt01_login,escalate\nt02_invoice,file\n")
    evh("label-import", "one.csv", "--dataset-id", "tickets_v1", "--set", "one_v1", "--by", "owner")
    r = evh("labels", "--dataset-id", "tickets_v1", "--json")
    pairs = {
        frozenset((p["a"], p["b"])): p
        for p in (json.loads(r.stdout) if r.returncode == 0 else {}).get("agreement", [])
    }
    p = pairs.get(frozenset(("tickets_v1/one_v1", "tickets_v1/several_v1")), {})
    check(
        "labels: agreeing is accepting the same answers; sharing one (escalate, of escalate or file) is counted apart",
        p.get("both") == 2 and p.get("same") == 0 and p.get("share") == 1 and "agree" not in p,
        str(p) + r.stdout[-300:],
    )
    r = evh("labels", "--dataset-id", "tickets_v1", "--confusion")
    check(
        "labels --confusion: each pair's matrix, the first set's labels down",
        r.returncode == 0 and "escalate or file" in r.stdout and "Cohen's kappa" in r.stdout,
        r.stdout[-600:],
    )
    from evaluation_harness._label_sets import _masi, compare, label_line, label_text
    from evaluation_harness._label_sets import answers as accepted

    # Cohen's kappa on a textbook table: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no gives 0.4.
    table = [("yes", "yes")] * 20 + [("yes", "no")] * 5 + [("no", "yes")] * 10 + [("no", "no")] * 15
    c = compare(table)
    check(
        "compare: Cohen's kappa 0.40 on the textbook table; the confusion matrix counts it",
        c["kind"] == "categories"
        and c["kappa"] == 0.4
        and c["same"] == 35
        and c["confusion"] == {"yes": {"yes": 20, "no": 5}, "no": {"yes": 10, "no": 15}}
        and c["alpha_distance"] == "nominal",
        str(c),
    )
    check(
        "compare: MASI distance (Passonneau 2006): the same 0, a subset in between, nothing shared 1",
        _masi(frozenset("ab"), frozenset("ab")) == 0.0
        and abs(_masi(frozenset("ab"), frozenset("abcd")) - (1 - 0.5 * 2 / 3)) < 1e-9
        and _masi(frozenset("ab"), frozenset("cd")) == 1.0,
    )
    every_same = compare([("file", "file")] * 4)
    free = compare([("The login fails after the SSO change.", "Login is broken since SSO moved.")])
    check(
        "compare: a coefficient is undefined when every label is the same; free text is not compared as text",
        every_same["kappa"] is None
        and every_same["alpha"] is None
        and free == {"both": 1, "kind": "free text"},
        str(every_same) + str(free),
    )

    check(
        "answers / label_text / label_line: a bare label is its one answer; a set reads, writes and shows",
        accepted("Login fails.\n") == ["Login fails."]
        and accepted('{"accept": ["escalate", "file"]}') == ["escalate", "file"]
        and label_text(["file"]) == "file"
        and label_text(["file", "escalate"]) == '{"accept": ["escalate", "file"]}'
        and label_line('{"accept": ["escalate", "file"]}') == "escalate or file"
        and accepted('{"accept": "file"}') == ['{"accept": "file"}'],
    )
    from evaluation_harness.adapter import score as default_score

    both = '{"accept": ["login fails after sso", "the export is empty"]}'
    check(
        "the bundled adapter scores an output against the right answer it is closest to",
        default_score("the export is empty", both)["overlap_f1"] == 1.0
        and default_score("login fails after sso", both)["overlap_f1"] == 1.0
        and default_score("nothing alike", both)["overlap_f1"] == 0.0,
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "several_v1",
        "--tier",
        "silver",
        "--name",
        "several_check",
        "--reason",
        "a check of what promotion says",
        "--by",
        "owner",
    )
    check(
        "reference-promote names the labels that accept several answers, each to be fully right",
        r.returncode == 0 and "1 label(s) accept more than one answer (escalate or file: 1)" in out(r),
        out(r)[-400:],
    )
    shutil.rmtree(proj / "data" / "references" / "silver" / "several_check", ignore_errors=True)
    for s in ("several_v1", "several_files", "one_v1"):
        shutil.rmtree(LABELS / "tickets_v1" / s)
    shutil.rmtree(LABELS / "tickets_v1" / "owner_files")  # the later checks count the sets on tickets_v1
    (proj / "bad.csv").write_text("id,answer\nt01_login,x\n")
    r = evh("label-import", "bad.csv", "--dataset-id", "tickets_v1", "--set", "bad_v1", "--by", "owner")
    check(
        "label-import: a file without item_id and label is refused",
        refused(r, "item_id and label"),
        out(r)[-200:],
    )
    (proj / "ghost.csv").write_text("item_id,label\nno_such_item,x\n")
    r = evh("label-import", "ghost.csv", "--dataset-id", "tickets_v1", "--set", "ghost_v1", "--by", "owner")
    check(
        "label-import: an item not in the dataset is refused", refused(r, "not in tickets_v1"), out(r)[-200:]
    )

    # ── labels ───────────────────────────────────────────────────────────────────────────
    r = evh("labels", "--dataset-id", "tickets_v1", "--json")
    v = json.loads(r.stdout) if r.returncode == 0 else {}
    pair: dict = next(
        (
            p
            for p in v.get("agreement", [])
            if {p["a"], p["b"]} == {"tickets_v1/author_v1", "tickets_v1/owner_v1"}
        ),
        {},
    )
    check(
        "labels --dataset-id: each set's coverage; two sets of written summaries are free text, not compared as text",
        sorted((s["set"], len(s["items"])) for s in v.get("sets", [])) == [("author_v1", 6), ("owner_v1", 3)]
        and pair == {"a": pair.get("a"), "b": pair.get("b"), "both": 3, "kind": "free text"},
        r.stdout[-400:],
    )
    r = evh("labels")
    check(
        "labels: every set, with its source",
        "tickets_v1/owner_v1: person · owner" in r.stdout and "model · " in r.stdout,
        r.stdout[-300:],
    )

    # ── labels follow the item ─────────────────────────────────────────────────────────────
    r = evh(
        "dataset-create",
        "--dataset-id",
        "tickets_v2",
        "--source-dir",
        "tutorial/tickets",
        "--from",
        "tickets_v1",
    )
    r2 = evh("labels", "--dataset-id", "tickets_v2", "--json")
    v2 = json.loads(r2.stdout) if r2.returncode == 0 else {}
    check(
        "labels follow the item: a new version with the same items has v1's labels",
        r.returncode == 0
        and sorted((s["set"], len(s["items"])) for s in v2.get("sets", []))
        == [("author_v1", 6), ("owner_v1", 3)],
        out(r)[-200:] + r2.stdout[-300:],
    )
    edited = proj / "tutorial" / "tickets_edited"
    shutil.copytree(proj / "tutorial" / "tickets", edited)
    first = sorted(edited.iterdir())[0]
    first.write_text(first.read_text() + "\nEdited.\n")
    evh(
        "dataset-create",
        "--dataset-id",
        "tickets_v3",
        "--source-dir",
        "tutorial/tickets_edited",
        "--from",
        "tickets_v1",
    )
    r = evh("labels", "--dataset-id", "tickets_v3", "--json")
    v3 = json.loads(r.stdout) if r.returncode == 0 else {}
    cover = {s["set"]: s["items"] for s in v3.get("sets", [])}
    check(
        "an edited item's labels do not follow it",
        len(cover.get("author_v1", [])) == 5 and first.stem not in cover.get("author_v1", []),
        r.stdout[-300:],
    )

    # ── label-from-capture ─────────────────────────────────────────────────────────────────
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "tutorial/production/desk_export.jsonl"}),
        "--capture",
        "desk_c1",
    )
    r = r if r.returncode else evh("dataset-from-capture", "desk_c1", "--dataset-id", "desk_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-from-capture",
            "--dataset-id",
            "desk_v1",
            "--capture",
            "desk_c1",
            "--map",
            "tutorial/production/outcomes.yaml",
            "--set",
            "outcomes_c1",
        )
    )
    doc = (
        json.loads((LABELS / "desk_v1" / "outcomes_c1" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-from-capture: the mapping's labels as a rule set, the capture and the mapping hashed, the counts",
        doc.get("n_items") == 5
        and doc["source"]["kind"] == "rule"
        and doc["source"]["capture"] == "desk_c1"
        and doc["source"]["skipped"] == 1
        and len(doc["source"]["mapping_sha256"]) == 64
        and doc["guideline"]["path"].endswith("outcomes.yaml"),
        out(r)[-300:],
    )

    # ── reference-promote (step 3): a reference set is labels you promote ─────────────────────────
    REF = proj / "data" / "references"
    reason = "the owner's labels of three tickets, for this test"
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "gold",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    m = json.loads((REF / "gold" / "tickets_v1" / "manifest.json").read_text()) if r.returncode == 0 else {}
    owner_ids = sorted(json.loads((LABELS / "tickets_v1" / "owner_v1" / "labels.json").read_text())["items"])
    check(
        "reference-promote: the set's labels as the dataset's gold, recording the set, its source, the reason and who",
        sorted(p.stem for p in (REF / "gold" / "tickets_v1").glob("*.txt")) == owner_ids
        and m.get("tier") == "gold"
        and m["promoted_from"]
        == {"labels": "owner_v1", "dataset_id": "tickets_v1", "source": m["promoted_from"]["source"]}
        and m["promoted_from"]["source"]["kind"] == "person"
        and m["reason"] == reason
        and m["promoted_by"] == "owner"
        and "promoted as gold from tickets_v1/owner_v1 (person · owner)" in m["caveat"]
        and "authored_by" not in m,
        out(r)[-300:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "gold",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check("reference-promote: never overwrites a reference", refused(r, "never overwritten"), out(r)[-200:])
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "silver",
        "--name",
        "x1",
        "--by",
        "owner",
        "--reason",
        "fine",
    )
    check("reference-promote: a reason is a sentence", refused(r, "a sentence"), out(r)[-200:])
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "no_such_set",
        "--tier",
        "silver",
        "--name",
        "x2",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check(
        "reference-promote: an unknown set is refused",
        refused(r, "no labels of tickets_v1/no_such_set"),
        out(r)[-200:],
    )
    unlabelled = next(i for i in au if i not in owner_ids)
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--items",
        unlabelled,
        "--tier",
        "silver",
        "--name",
        "x3",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check(
        "reference-promote --items: an item the set does not label is refused",
        refused(r, "has no label for"),
        out(r)[-200:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "author_v1",
        "--tier",
        "silver",
        "--name",
        "tickets_v1_author",
        "--by",
        "owner",
        "--reason",
        "the author model's answers, to rank the arms",
    )
    m = (
        json.loads((REF / "silver" / "tickets_v1_author" / "manifest.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "a model set promoted keeps who authored it (the fingerprint hashes it): its config, model and run",
        m.get("authored_by") == "tickets_author_v1" and (m.get("from_run") or {}).get("run_id") == author,
        out(r)[-300:] + json.dumps(m)[:300],
    )
    r = evh(
        "rescore",
        "--dataset-id",
        "tickets_v1",
        "--reference-id",
        "silver/tickets_v1_author",
        "--out",
        "data/runs-author",
    )
    r = (
        r
        if r.returncode
        else subprocess.run(
            [sys.executable, str(HERE / "cli.py"), "leaderboard", "--dataset-id", "tickets_v1"],
            cwd=proj,
            env={**env, "EVAL_RUNS_DIR": "data/runs-author"},
            capture_output=True,
            text=True,
        )
    )
    check(
        "scored against it, the author arm is marked as graded against its own answers",
        r.returncode == 0
        and any(
            line.strip().startswith("tickets_author_v1") and "*" in line for line in r.stdout.splitlines()
        ),
        out(r)[-500:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v2",
        "--labels",
        "tickets_v1/owner_v1",
        "--tier",
        "gold",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check(
        "reference-promote from a set on another dataset: labels follow the item",
        r.returncode == 0
        and sorted(p.stem for p in (REF / "gold" / "tickets_v2").glob("*.txt")) == owner_ids,
        out(r)[-300:],
    )

    # ── production's recorded decisions as an arm (step 5) ─────────────────────────────────────
    evh("dataset-materialize", "--dataset-id", "desk_v1")
    r = evh(
        "arm-from-capture",
        "--dataset-id",
        "desk_v1",
        "--capture",
        "desk_c1",
        "--as",
        "desk_production_v1",
        "--field",
        "channel",
    )
    cfg_text = (data / "configs" / "desk_production_v1.yaml").read_text() if r.returncode == 0 else ""
    rec_run = next((p for p in (data / "runs").glob("desk_production_v1_*")), None)
    rec_m = json.loads((rec_run / "metrics.json").read_text()) if rec_run else {}
    cap_recs = {
        json.loads(p.read_text())["id"]: json.loads(p.read_text())
        for p in (data / "captures" / "desk_c1" / "records").glob("*.json")
    }
    check(
        "arm-from-capture: a config with provider recorded, run: each output the record's field, no call, no cost",
        "provider: recorded" in cfg_text
        and rec_run is not None
        and all(_outputs.output(rec_run, i) == str(cap_recs[i]["fields"]["channel"]) for i in cap_recs)
        and not (rec_m.get("scores") or {}).get("total_cost_usd")
        and len(rec_m["fingerprint"]["settings"].get("capture_sha256", "")) == 64
        and "no system called" in out(r),
        out(r)[-400:],
    )
    r = evh(
        "arm-from-capture",
        "--dataset-id",
        "desk_v1",
        "--capture",
        "desk_c1",
        "--as",
        "desk_production_v1",
        "--field",
        "channel",
    )
    check(
        "arm-from-capture: an existing config is never overwritten",
        refused(r, "not overwritten"),
        out(r)[-200:],
    )
    r = evh("arm-from-capture", "--dataset-id", "desk_v1", "--capture", "desk_c1", "--as", "desk_nofield_v1")
    check(
        "a recorded arm needs the adapter's recorded_output or a --field; refused before anything is written",
        r.returncode != 0
        and "recorded_output" in out(r)
        and not (data / "configs" / "desk_nofield_v1.yaml").exists(),
        out(r)[-300:],
    )

    # ── agreement: --disagree keeps the items the arms decided differently (step 5) ──────────────
    alt = data / "runs-alt" / lead
    shutil.copytree(data / "runs" / lead, alt)
    changed = sorted(_outputs.outputs(alt))[:2]
    for i in changed:
        _set_output(alt, i, "a different decision")

    def inspected(*extra):
        r = evh(
            "inspect",
            "--runs",
            "tickets_lead1_v1,runs-alt/tickets_v1/tickets_lead1_v1",
            "--metric",
            "output_words",
            "--json",
            *extra,
        )
        rows = [
            x
            for b in (json.loads(r.stdout)["result"]["blocks"] if r.returncode == 0 else [])
            for x in b.get("rows", [])
        ]
        return r, rows

    r, dis_rows = inspected("--disagree")
    check(
        "inspect --disagree: only the items where the arms' outputs are not the same decision",
        r.returncode == 0 and [x["n"] for x in dis_rows] == [len(changed)],
        out(r)[-400:],
    )
    r, dis_rows = inspected()
    check(
        "inspect without --disagree: every item",
        r.returncode == 0 and [x["n"] for x in dis_rows] == [6],
        out(r)[-300:],
    )
    from evaluation_harness import _adapter

    check(
        "same(a, b): the adapter's when it has one, else the same text",
        _adapter.same_of(None)("a decision ", "a decision") and not _adapter.same_of(None)("a", "b"),
    )
    shutil.rmtree(data / "runs-alt")

    # ── scoring against labels (step 4) ───────────────────────────────────────────────────
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "author_v1")
    lab_dir = data / "runs-labels-tickets_v1-author_v1"
    ms = (
        [json.loads(p.read_text()) for p in sorted(lab_dir.glob("*/metrics.json"))]
        if r.returncode == 0
        else []
    )
    check(
        "rescore --labels: every run scored against the set, beside the runs, never in the re-score goals read",
        len(ms) == 2
        and all(
            m["fingerprint"]["data"]["reference_id"] == "labels/tickets_v1/author_v1"
            and m["fingerprint"]["data"]["reference_tier"] == "labels"
            and len(m["fingerprint"]["data"]["references_sha256"] or "") == 64
            for m in ms
        )
        and not (data / "runs-rescored").exists(),
        out(r)[-300:],
    )
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "tickets_v2/owner_v1")
    check(
        "rescore --labels: a set on another dataset is refused (promote it, or label this one)",
        refused(r, "a set on tickets_v2"),
        out(r)[-300:],
    )
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "no_such_set")
    check("rescore --labels: an unknown set is refused", refused(r, "no label set at"), out(r)[-200:])
    before_lab = set((data / "runs-labels-tickets_v1-author_v1").glob("tickets_lead1_v1_*"))
    before_runs = sorted((data / "runs").glob("tickets_lead1_v1_*"))
    r = subprocess.run(
        [
            sys.executable,
            str(HERE / "cli.py"),
            "run",
            "--config",
            "data/configs/tickets_lead1.yaml",
            "--labels",
            "author_v1",
        ],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
    )
    made = sorted(set((data / "runs-labels-tickets_v1-author_v1").glob("tickets_lead1_v1_*")) - before_lab)
    run_m: dict = json.loads((made[-1] / "metrics.json").read_text()) if made else {}
    check(
        "evh run --labels: an arm of its own, beside the runs (data/runs-labels-<dataset>-<set>/), never one more"
        " run of the config's arm in data/runs; the run records the set",
        r.returncode == 0
        and "the label set labels/tickets_v1/author_v1" in out(r)
        and run_m.get("reference_tier") == "labels"
        and run_m["fingerprint"]["data"]["reference_id"] == "labels/tickets_v1/author_v1"
        and sorted((data / "runs").glob("tickets_lead1_v1_*")) == before_runs,
        out(r)[-300:],
    )
    for d in made:
        shutil.rmtree(d, ignore_errors=True)
    r = evh("goals", "--goal", "tickets_summary")
    group = (
        out(r).split("labels/tickets_v1/author_v1", 1)[1] if "labels/tickets_v1/author_v1" in out(r) else ""
    )
    check(
        "the goal groups the arms scored against the set, flags the arm that made its labels, recommends another",
        r.returncode == 0
        and group
        and "[recommended]" in group.split("\n\n", 1)[0]
        and not any(
            "tickets_author_v1" in line and "[recommended]" in line
            for line in group.split("\n\n", 1)[0].splitlines()
        ),
        out(r)[-1500:],
    )

    # ── V19: a set's labels are the ones it recorded ──────────────────────────────────────────
    # validate checks the run folders git tracks: commit the project, as a real one would be.
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t"],
    ):
        subprocess.run(cmd, cwd=proj, env=env, capture_output=True)
    r = evh("validate")
    check(
        "validate V19: every label set matches its hashes",
        "V19 label sets" in out(r) and "FAIL V19" not in out(r),
        out(r)[-400:],
    )
    check(
        "validate V1: a run scored against a label set (reference_tier labels) is a valid run",
        "FAIL V1 " not in out(r) and any(data.glob("runs-labels-*/*/metrics.json")),
        out(r)[-600:],
    )
    (LABELS / "tickets_v1" / "owner_v1" / f"{rows[0]['item_id']}.txt").write_text("edited by hand\n")
    r = evh("validate")
    check(
        "validate V19: an edited label fails",
        r.returncode != 0 and "FAIL V19" in out(r) and "never edited" in out(r),
        out(r)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
