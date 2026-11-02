#!/usr/bin/env python3
"""The rows view (RFC-023 step 6, PRD-014 FR8): one row per item, its decisions, labels and signals.

    python tests/test_rows.py

In a throwaway project built from the tutorial ($0, offline): three arms run on the six tickets, a person labels
three of them, a smaller governed dataset stands for v1; `evh inspect --dataset-id D --rows` then shows every row,
and each signal (wrong, disagree, split, new, unlabelled) filters to exactly the items it should, together with
`--where`; rows are sorted by how many signals they carry; a picked row says so; the view prints the pick and
label-sheet commands for what it shows, writes nothing, and refuses what it cannot answer.
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
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-rows-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-rows")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_PUBLIC"):
    env.pop(k, None)
D = "tickets_v1"


def evh(*args, extra=None):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **(extra or {})},
        capture_output=True,
        text=True,
    )


def out(r):
    return r.stdout + r.stderr


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in out(r) and text in out(r)


def rows(*args):
    """The rows the view shows, in order, each {column: value}; [] when it failed."""
    r = evh("inspect", "--dataset-id", D, "--rows", "--runs", RUNS, *args, "--json")
    if r.returncode:
        return r, []
    blocks = json.loads(r.stdout)["result"]["blocks"]
    table = next((b for b in blocks if "columns" in b and b["columns"][0] == "item"), {"rows": []})
    return r, table["rows"]


def ids(rs):
    return [x["item"] for x in rs]


def n_signals(row):
    return sum(name in row["signals"] for name in ("wrong", "disagree", "split", "new", "unlabelled"))


def snapshot():
    return {str(p.relative_to(proj)): p.stat().st_mtime_ns for p in proj.rglob("*") if p.is_file()}


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "fields").mkdir()
    shutil.copy(KIT / "fields" / "tickets.yaml", data / "fields")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh(
        "dataset-create",
        "--dataset-id",
        D,
        "--source-dir",
        "tutorial/tickets",
        "--fieldset",
        "tickets",
        "--fields",
        str(KIT / "ticket_fields.csv"),
    )
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", D)
    check("setup: the tutorial dataset, with its fields", r.returncode == 0, out(r)[-300:])
    # The governed dataset v1 stands for: three tickets, so `api`, `mobile` and `enterprise` are new to it.
    gov = [x for x in csv.DictReader((KIT / "ticket_fields.csv").open()) if x["item_id"] < "t04"]
    with (proj / "gov_fields.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(gov[0]))
        w.writeheader()
        w.writerows(gov)
    r = evh(
        "dataset-create",
        "--dataset-id",
        "tickets_gov",
        "--source-dir",
        "tutorial/tickets",
        "--glob",
        "t0[123]_*",
        "--fieldset",
        "tickets",
        "--fields",
        "gov_fields.csv",
    )
    check("setup: the governed dataset (three tickets)", r.returncode == 0, out(r)[-300:])
    (data / "goals").mkdir()
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    # What each run decided, set per item (the first run stands for production; None: no output), so that every
    # signal has an item only it marks: t02 and t03 disagree with one candidate each (split), t04 with both (not
    # split), t06 with the one candidate that answered (not split).
    decided: dict[str, dict[str, str | None]] = {
        "lead1": {
            "t01_login": "A",
            "t02_invoice": "A",
            "t03_export": "A",
            "t04_api": "A",
            "t05_delete": "A",
            "t06_mobile": "A",
        },
        "author": {
            "t01_login": "A",
            "t02_invoice": "B",
            "t03_export": "A",
            "t04_api": "B",
            "t05_delete": "A",
            "t06_mobile": None,
        },
        "lead2_noisy": {
            "t01_login": "A",
            "t02_invoice": "A",
            "t03_export": "B",
            "t04_api": "B",
            "t05_delete": "A",
            "t06_mobile": "B",
        },
    }
    for arm, by_item in decided.items():
        cfg = data / "configs" / f"tickets_{arm}.yaml"
        cfg.write_text((KIT / "configs" / f"tickets_{arm}.yaml").read_text() + "goal: tickets_summary\n")
        r = evh("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
        run = next(p for p in (data / "runs").glob(f"tickets_{arm}_v1_*"))
        for item, text in by_item.items():
            (run / "outputs" / f"{item}.txt").unlink(missing_ok=True)
            if text is not None:
                (run / "outputs" / f"{item}.txt").write_text(text + "\n")
    RUNS = "tickets_lead1_v1,tickets_author_v1,tickets_lead2_noisy_v1"
    every = sorted(decided["lead1"])
    # A person labels three tickets: production right on t01 and t03, wrong on t02.
    with (proj / "sheet.csv").open("w", newline="") as f:
        sheet = csv.writer(f)
        sheet.writerow(["item_id", "label"])
        sheet.writerows([["t01_login", "A"], ["t02_invoice", "B"], ["t03_export", "A"]])
    r = evh("label-import", "sheet.csv", "--dataset-id", D, "--set", "owner", "--by", "owner")
    check("setup: a person labels three tickets", r.returncode == 0, out(r)[-300:])
    r = evh("pick", "--dataset-id", D, "--item", "t04_api", "--for", "tickets_gov", "--tag", "case=api")
    check("setup: one ticket is picked", r.returncode == 0, out(r)[-300:])
    r = evh("pick", "--dataset-id", D, "--item", "t05_delete")
    r = r if r.returncode else evh("pick", "--dataset-id", D, "--item", "t05_delete", "--drop")
    check("setup: another is picked, then dropped", r.returncode == 0, out(r)[-300:])
    before = snapshot()

    # ── every row, its columns ───────────────────────────────────────────────────────────────
    r, rs = rows()
    by = {x["item"]: x for x in rs}
    check(
        "--rows: one row per item, each run's decision, its labels with their source, picked, fields",
        r.returncode == 0
        and sorted(by) == every
        and by["t01_login"]["tickets_lead1_v1"]
        and "owner [person" in by["t01_login"]["labels"]
        and by["t05_delete"]["labels"] == ""
        and by["t04_api"]["picked"] == "for tickets_gov"
        and by["t05_delete"]["picked"] == by["t06_mobile"]["picked"] == ""
        and "area=account" in by["t01_login"]["fields"],
        out(r)[-600:],
    )
    check(
        "rows are sorted by how many signals they carry (most first), the dataset's order within",
        [n_signals(x) for x in rs] == sorted((n_signals(x) for x in rs), reverse=True),
        json.dumps(rs)[:600],
    )

    # ── each signal, a filter ────────────────────────────────────────────────────────────────
    r, rs = rows("--disagree")
    check(
        "--disagree: the items another run decided differently from the first (any of them)",
        sorted(ids(rs)) == ["t02_invoice", "t03_export", "t04_api", "t06_mobile"],
        out(r)[-300:],
    )
    r, rs = rows("--split")
    check(
        "--split: the items the candidates decided differently among themselves (not where both left production)",
        sorted(ids(rs)) == ["t02_invoice", "t03_export"],
        out(r)[-300:],
    )
    r, rs = rows("--disagree", "--split")
    check(
        "two signals together: an item needs both",
        sorted(ids(rs)) == ["t02_invoice", "t03_export"],
        out(r)[-300:],
    )
    want = ["t02_invoice"]
    r, rs = rows("--wrong-against", "owner")
    check(
        "--wrong-against SET: the items where the first run's decision is not the label's (unlabelled ones are not)",
        ids(rs) == want,
        out(r)[-300:],
    )
    r, rs = rows("--wrong-against", f"{D}/owner")
    check("--wrong-against DATASET/SET names the same set", sorted(ids(rs)) == want, out(r)[-300:])
    # A label accepting both answers on t02: production's A is one of them, so not wrong; the rows show both.
    (proj / "two.csv").write_text("item_id,label,also right\nt02_invoice,B,A\n")
    r = evh("label-import", "two.csv", "--dataset-id", D, "--set", "owner_two", "--by", "owner")
    r2, rs = rows("--wrong-against", "owner_two")
    _, every_row = rows()
    t02: dict = next((x for x in every_row if x["item"] == "t02_invoice"), {})
    check(
        "--wrong-against a label with several right answers: the decision is one of them, so not wrong; shown as A or B",
        r.returncode == 0 and r2.returncode == 0 and ids(rs) == [] and "A or B" in t02.get("labels", ""),
        out(r)[-200:] + out(r2)[-300:] + str(t02)[:300],
    )
    shutil.rmtree(proj / "data" / "labels" / D / "owner_two")
    (proj / "two.csv").unlink()  # the view-writes-nothing check compares the project to before
    r, rs = rows("--new-vs", "tickets_gov")
    by = {x["item"]: x for x in rs}
    check(
        "--new-vs V: the items with a field value V has never had, and which",
        sorted(by) == ["t04_api", "t05_delete", "t06_mobile"]
        and "area=api" in by["t04_api"]["signals"]
        and "plan=enterprise" in by["t05_delete"]["signals"],
        out(r)[-400:],
    )
    r, rs = rows("--unlabelled")
    check(
        "--unlabelled: the items no set labels",
        sorted(ids(rs)) == ["t04_api", "t05_delete", "t06_mobile"],
        out(r)[-300:],
    )
    r, rs = rows("--unlabelled", "--where", "area:account")
    check("signals and --where together: an item needs every one", ids(rs) == ["t05_delete"], out(r)[-300:])

    # ── the commands for what it shows, and --by ─────────────────────────────────────────────
    r = evh("inspect", "--dataset-id", D, "--rows", "--runs", RUNS, "--unlabelled", "--by", "area")
    check(
        "the view prints the pick and label-sheet commands for the rows it shows",
        r.returncode == 0
        and f"evh pick --dataset-id {D} --item t04_api --item t06_mobile --item t05_delete" in r.stdout
        and f"evh label-sheet --dataset-id {D} --item t04_api --item t06_mobile --item t05_delete"
        in r.stdout,
        out(r)[-600:],
    )
    check(
        "--by FIELD: the rows shown, counted per value",
        "by area" in r.stdout and "mobile" in r.stdout,
        out(r)[-600:],
    )
    check("the view writes nothing", snapshot() == before, "files changed")

    # ── --new-vs compares only the fields with few values in V (not a free text) ─────────────
    from evaluation_harness import _rows

    def fields_of(n_titles):
        decl = {"title": {"type": "text"}, "on": {"type": "date"}, "kind": {"type": "choice"}}

        def f(ds):
            if ds == "v":
                return decl, {
                    f"g{k}": {"title": f"title {k}", "on": "2026-10-01", "kind": "a"} for k in range(n_titles)
                }
            return decl, {"x1": {"title": "a title v never had", "on": "2026-11-02", "kind": "b"}}

        return f

    check(
        f"--new-vs: a text field with at most {_rows.NEW_MAX} values in V is compared, one with more is not",
        _rows._new_values(fields_of(_rows.NEW_MAX), "d", "v")
        == {"x1": ["title=a title v never had", "kind=b"]}
        and _rows._new_values(fields_of(_rows.NEW_MAX + 1), "d", "v") == {"x1": ["kind=b"]},
        str(_rows._new_values(fields_of(_rows.NEW_MAX), "d", "v")),
    )
    check(
        "--new-vs: a choice field is always compared, a date never (each new day is not a gap)",
        all("on=" not in x for xs in _rows._new_values(fields_of(3), "d", "v").values() for x in xs),
        "",
    )

    # ── --wrong-against: the adapter's verdict, where a label and an output are written differently ──
    (proj / "jsonish.py").write_text(
        "import json\n"
        "from evaluation_harness.adapter import Result\n"
        "def call_system(text, params):\n"
        "    return Result(output=json.dumps({'disposition': 'file' if len(text) % 2 else 'dismiss'}), cost_usd=0.0)\n"
        "def score(output, reference):\n"
        "    d = json.loads(output)['disposition']\n"
        "    return {} if reference is None else {'correct': float(d == reference.strip())}\n"
        "def same(a, b):\n"
        "    return json.loads(a)['disposition'] == json.loads(b)['disposition']\n"
    )
    (data / "configs" / "jsonish.yaml").write_text(
        "config_id: jsonish_v1\ndataset_id: tickets_v1\nadapter: jsonish.py\nparams:\n  provider: echo\n"
    )
    r = evh(
        "experiment-run",
        "--config",
        "data/configs/jsonish.yaml",
        "--run-id",
        "jsonish",
        extra={"PYTHONPATH": str(HERE.parent)},
    )
    jout = {
        p.stem: json.loads(p.read_text())["disposition"]
        for p in (data / "runs" / "jsonish" / "outputs").glob("t*.txt")
    }
    # Right on two, wrong on one, by construction: the label is the output's disposition, or the other one.
    flip = {"file": "dismiss", "dismiss": "file"}
    bare = {
        "t01_login": jout.get("t01_login", "file"),
        "t02_invoice": flip.get(jout.get("t02_invoice", "file"), "file"),
        "t03_export": jout.get("t03_export", "file"),
    }
    with (proj / "bare.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["item_id", "label"])
        wr.writerows(bare.items())
    r2 = evh("label-import", "bare.csv", "--dataset-id", D, "--set", "bare", "--by", "owner")
    r3 = evh(
        "inspect", "--dataset-id", D, "--rows", "--runs", "jsonish_v1", "--wrong-against", "bare", "--json",
        extra={"PYTHONPATH": str(HERE.parent)},
    )  # fmt: skip
    got = []
    if r3.returncode == 0:
        blocks = json.loads(r3.stdout)["result"]["blocks"]
        table: dict = next((b for b in blocks if "columns" in b and b["columns"][0] == "item"), {"rows": []})
        got = sorted(x["item"] for x in table["rows"])
    want = sorted(i for i, lab in bare.items() if jout.get(i) != lab)
    check(
        "--wrong-against: a bare label against an output's JSON, read by the adapter's score (correct 0), not as text",
        r.returncode == 0 and r2.returncode == 0 and got == want == ["t02_invoice"],
        f"got {got}, want {want}; {out(r3)[-300:]}",
    )

    # ── refusals ─────────────────────────────────────────────────────────────────────────────
    two = "tickets_lead1_v1,tickets_author_v1"
    for args, text, what in (
        (["--runs", two, "--split"], "--split needs 3", "--split with fewer than three runs"),
        (["--runs", "tickets_lead1_v1", "--disagree"], "--disagree needs 2", "--disagree with one run"),
        (["--wrong-against", "owner"], "--wrong-against needs 1", "--wrong-against with no run"),
        (["--runs", two, "--wrong-against", "no_such"], "no such label set", "an unknown label set"),
        (["--runs", two, "--new-vs", "no_such_dataset"], "no_such_dataset", "an unknown --new-vs dataset"),
        (["--runs", two, "--where", "nope:x"], "no field 'nope'", "a --where on no field"),
    ):
        r = evh("inspect", "--dataset-id", D, "--rows", *args)
        check(f"refused: {what}", refused(r, text), out(r)[-200:])
    r = evh("inspect", "--rows", "--runs", two)
    check("refused: --rows without --dataset-id", refused(r, "--dataset-id"), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--runs", two)
    check("refused: --dataset-id without --rows", refused(r, "--rows"), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--runs", two, "--unlabelled")
    check("refused: a rows filter without --rows", refused(r, "--rows"), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--rows", "--round", "r1")
    check("refused: --rows with --round", refused(r, "--runs"), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--rows", "--runs", two, extra={"EVH_PUBLIC": "1"})
    check(
        "refused publicly: the rows carry outputs and labels",
        refused(r, "not served publicly"),
        out(r)[-200:],
    )
    r = evh("inspect", "--baseline", "x")
    check("inspect still needs --runs, --round or --rows", refused(r, "--runs"), out(r)[-200:])

    # ── the decision, not the whole output (UXS-002): an adapter's decision(output) is what a row shows ───
    (proj / "decide.py").write_text(
        "from evaluation_harness.adapter import Result, score  # noqa: F401\n"
        "def call_system(text, params):\n"
        "    return Result(output='A because ' + text[:40], cost_usd=0.0)\n"
        "def decision(output):\n"
        "    return output.split()[0]\n"
    )
    (data / "configs" / "tickets_decider.yaml").write_text(
        "config_id: tickets_decider_v1\ndataset_id: tickets_v1\nadapter: decide.py\nparams:\n  provider: echo\n"
    )
    r = evh(
        "experiment-run",
        "--config",
        "data/configs/tickets_decider.yaml",
        extra={"PYTHONPATH": str(HERE.parent)},
    )
    check("setup: an arm whose adapter has decision()", r.returncode == 0, out(r)[-300:])
    r = evh("inspect", "--dataset-id", D, "--rows", "--runs", "tickets_decider_v1,tickets_lead1_v1", "--json")
    blocks = json.loads(r.stdout)["result"]["blocks"] if r.returncode == 0 else []
    table = next(
        (b for b in blocks if "columns" in b and b["columns"][0] == "item"), {"rows": [], "columns": []}
    )
    first = {x["item"]: x for x in table["rows"]}.get("t01_login", {})
    check(
        "rows: an arm's column is its adapter's decision(output), the signals second; an arm without one shows "
        "its output",
        first.get("tickets_decider_v1") == "A"
        and first.get("tickets_lead1_v1") == "A"
        and table["columns"][:2] == ["item", "signals"]
        and "disagree" not in str(first.get("signals")),
        out(r)[-400:] + json.dumps(table.get("columns")),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
