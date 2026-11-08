#!/usr/bin/env python3
"""The sheet (RFC-023, PRD-014 FR8): the items down, a column per arm, scores, labels, winners, signals, a footer.

    python tests/test_sheet.py

In a throwaway project built from the tutorial ($0, offline): three arms run on the six tickets, a person labels
three of them, a smaller governed dataset stands for v1; `evh inspect --sheet --dataset-id D` then shows every row,
and each signal (wrong, disagree, split, new, unlabelled) filters to exactly the items it should, together with
`--where`; rows are sorted by how many signals they carry; a picked row says so; the sheet carries each arm's
scores and the judge's, the winner per row on the chosen metric (ties named, the direction respected) and per
judging scorer, and per arm a mean, a win rate and a verdict (the goal's decision, else the paired test); the view
prints the pick and label-sheet commands for what it shows, writes nothing, and refuses what it cannot answer.
"""

import csv
import io
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
from evaluation_harness import _outputs, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402


def _set_output(run, item, text):
    """Change one output of a run in place (None removes it), as a hand edit of its outputs.jsonl would."""
    with _runstore._InProject(proj) as data:
        d = data / "runs" / run
        texts = _outputs.outputs(d)
        texts.pop(item, None)
        if text is not None:
            texts[item] = text
        _outputs.write_all(d, texts, list(texts))


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


def blocks_of(r):
    return json.loads(r.stdout)["result"]["blocks"] if r.returncode == 0 else []


def sheet_of(*args, runs=None):
    """The sheet's blocks: (the process, its rows in order each {column: value}, the footer {line: {arm: value}})."""
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", runs or RUNS, *args, "--json")
    blocks = blocks_of(r)
    table = next((b for b in blocks if "columns" in b and b["columns"][0] == "item_id"), {"rows": []})
    foot = next((b for b in blocks if "columns" in b and b["columns"][0] == "per arm"), {"rows": []})
    return r, table["rows"], {x["per arm"].split(" (")[0]: x for x in foot["rows"]}


def rows(*args, runs=None):
    """The rows the sheet shows, in order, each {column: value}; [] when it failed."""
    r, rs, _ = sheet_of(*args, runs=runs)
    return r, rs


def ids(rs):
    return [x["item_id"] for x in rs]


def label_col(row, name):
    """A label set's column on a row: the header names the set and its source."""
    return next((v for k, v in row.items() if k.startswith(f"label: {name} (")), None)


def n_signals(row):
    return sum(name in row["signals"] for name in ("wrong", "disagree", "split", "new", "unlabelled"))


def snapshot():
    """Every file of the project with its mtime; the sqlite store's database changes on any write, so its files are
    compared by content instead."""
    db = _runstore.sqlite()
    snap = {
        str(p.relative_to(proj)): p.stat().st_mtime_ns
        for p in proj.rglob("*")
        if p.is_file() and not (db and p.name.startswith("project.sqlite"))
    }
    if db:
        snap.update({f"data/{f}": _runstore.read_bytes(proj, f) for f in _runstore.files_under(proj)})
        # a run's outputs and rows are rows of the database, not files: they are compared too
        with _runstore._InProject(proj) as data:
            for run in sorted({p.parent for p in _store.rglob(data, "metrics.json")}):
                key = run.relative_to(data).as_posix()
                snap[f"outputs:{key}"] = json.dumps(_outputs.outputs(run), sort_keys=True).encode()
                snap[f"rows:{key}"] = (_outputs.rows_text(run) or "").encode()
    return snap


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "fields").mkdir()
    _runstore.write_bytes(proj, "fields/tickets.yaml", (KIT / "fields" / "tickets.yaml").read_bytes())
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
    _runstore.write_bytes(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_bytes()
    )
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
        _runstore.write_text(
            proj,
            f"configs/tickets_{arm}.yaml",
            (KIT / "configs" / f"tickets_{arm}.yaml").read_text() + "goal: tickets_summary\n",
        )
        r = evh("run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
        run = next(n for n in _runstore.listdir(proj, "runs") if n.startswith(f"tickets_{arm}_v1_"))
        for item, text in by_item.items():
            _set_output(run, item, None if text is None else text + "\n")
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
    by = {x["item_id"]: x for x in rs}
    check(
        "--sheet: one row per item, its start, each run's decision, its labels with their source, picked, fields",
        r.returncode == 0
        and sorted(by) == every
        and by["t01_login"]["tickets_lead1_v1"]
        and by["t01_login"]["item"]
        and label_col(by["t01_login"], "owner") == "A"
        and label_col(by["t05_delete"], "owner") == ""
        and "label: owner (person · owner)" in by["t01_login"]
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
    # Another dataset holding the same tickets has a set of the same name that says otherwise on t02: a bare name
    # is two sets, and reading the first one found was a guess.
    with (proj / "gov.csv").open("w", newline="") as f:
        csv.writer(f).writerows([["item_id", "label"], ["t02_invoice", "A"]])
    r = evh("label-import", "gov.csv", "--dataset-id", "tickets_gov", "--set", "owner", "--by", "someone")
    amb = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--wrong-against", "owner")
    r2, rs = rows("--wrong-against", f"{D}/owner")
    check(
        "--wrong-against: a bare name two datasets' sets share is refused, naming both; DATASET/SET still reads one",
        r.returncode == 0
        and amb.returncode != 0
        and f"{D}/owner" in out(amb)
        and "tickets_gov/owner" in out(amb)
        and sorted(ids(rs)) == want,
        out(r)[-200:] + out(amb)[-300:],
    )
    _runstore.rmtree(proj, "labels/tickets_gov")
    (proj / "gov.csv").unlink()
    # A label accepting both answers on t02: production's A is one of them, so not wrong; the rows show both.
    (proj / "two.csv").write_text("item_id,label,also right\nt02_invoice,B,A\n")
    r = evh("label-import", "two.csv", "--dataset-id", D, "--set", "owner_two", "--by", "owner")
    r2, rs = rows("--wrong-against", "owner_two")
    _, every_row = rows()
    t02: dict = next((x for x in every_row if x["item_id"] == "t02_invoice"), {})
    check(
        "--wrong-against a label with several right answers: the decision is one of them, so not wrong; shown as A or B",
        r.returncode == 0
        and r2.returncode == 0
        and ids(rs) == []
        and label_col(t02, "owner_two") == "A or B",
        out(r)[-200:] + out(r2)[-300:] + str(t02)[:300],
    )
    _runstore.rmtree(proj, f"labels/{D}/owner_two")
    (proj / "two.csv").unlink()  # the view-writes-nothing check compares the project to before
    r, rs = rows("--new-vs", "tickets_gov")
    by = {x["item_id"]: x for x in rs}
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
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--unlabelled", "--by", "area")
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
    from evaluation_harness import _sheet

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
        f"--new-vs: a text field with at most {_sheet.NEW_MAX} values in V is compared, one with more is not",
        _sheet._new_values(fields_of(_sheet.NEW_MAX), "d", "v")
        == {"x1": ["title=a title v never had", "kind=b"]}
        and _sheet._new_values(fields_of(_sheet.NEW_MAX + 1), "d", "v") == {"x1": ["kind=b"]},
        str(_sheet._new_values(fields_of(_sheet.NEW_MAX), "d", "v")),
    )
    check(
        "--new-vs: a choice field is always compared, a date never (each new day is not a gap)",
        all("on=" not in x for xs in _sheet._new_values(fields_of(3), "d", "v").values() for x in xs),
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
    _runstore.write_text(
        proj,
        "configs/jsonish.yaml",
        "config_id: jsonish_v1\ndataset_id: tickets_v1\nadapter: jsonish.py\nparams:\n  provider: echo\n",
    )
    r = evh(
        "run",
        "--config",
        "data/configs/jsonish.yaml",
        "--run-id",
        "jsonish",
        extra={"PYTHONPATH": str(HERE.parent)},
    )
    with _runstore._InProject(proj) as data_:
        jsonish_out = _outputs.outputs(data_ / "runs" / "jsonish")
    jout = {k: json.loads(v)["disposition"] for k, v in jsonish_out.items() if k.startswith("t")}
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
        "inspect", "--sheet", "--dataset-id", D, "--runs", "jsonish_v1", "--wrong-against", "bare", "--json",
        extra={"PYTHONPATH": str(HERE.parent)},
    )  # fmt: skip
    got = []
    if r3.returncode == 0:
        table: dict = next(
            (b for b in blocks_of(r3) if "columns" in b and b["columns"][0] == "item_id"), {"rows": []}
        )
        got = sorted(x["item_id"] for x in table["rows"])
    want = sorted(i for i, lab in bare.items() if jout.get(i) != lab)
    check(
        "--wrong-against: a bare label against an output's JSON, read by the adapter's score (correct 0), not as text",
        r.returncode == 0 and r2.returncode == 0 and got == want == ["t02_invoice"],
        f"got {got}, want {want}; {out(r3)[-300:]}",
    )

    # ── scores, winners, the footer ──────────────────────────────────────────────────────────
    T = {"lead1": "tickets_lead1_v1", "author": "tickets_author_v1", "lead2": "tickets_lead2_noisy_v1"}
    #                  lead1 author lead2   (overlap_f1 higher is better; latency_ms lower is better)
    f1 = {
        "t01_login": (0.5, 0.5, 0.2),  # lead1 and author tie
        "t02_invoice": (0.4, 0.3, 0.1),
        "t03_export": (0.3, 0.6, 0.2),
        "t04_api": (0.2, 0.2, 0.2),  # all three tie
        "t05_delete": (0.6, 0.4, 0.5),
        "t06_mobile": (0.1, 0.3, 0.4),
    }
    lat = {
        "t01_login": (10, 20, 30),
        "t02_invoice": (10, 5, 30),
        "t03_export": (50, 20, 30),
        "t04_api": (10, 10, 30),  # lead1 and author tie
        "t05_delete": (10, 20, 5),
        "t06_mobile": (10, 20, 30),
    }
    run_names = {k: next(n for n in _runstore.listdir(proj, "runs") if n.startswith(f"{T[k]}_")) for k in T}
    with _runstore._InProject(proj) as data_:
        for n, k in enumerate(T):
            run_dir = data_ / "runs" / run_names[k]
            lines = []
            for row in _runstore.rows(run_dir):
                row["overlap_f1"], row["latency_ms"] = f1[row["item_id"]][n], lat[row["item_id"]][n]
                lines.append(json.dumps(row, sort_keys=True))
            _runstore.put_rows_text(run_dir, "\n".join(lines) + "\n")

    def footer_label(r, start):
        table = next((b for b in blocks_of(r) if b.get("columns", [""])[0] == "per arm"), {"rows": []})
        return next((x["per arm"] for x in table["rows"] if x["per arm"].startswith(start)), "")

    r, rs, foot = sheet_of()
    by = {x["item_id"]: x for x in rs}
    check(
        "scores in the cells: each run's metrics, the primary (the goal's) first, in its own column",
        r.returncode == 0
        and all(by[i][f"{T['lead1']}: overlap_f1"] == f1[i][0] for i in f1)
        and all(by[i][f"{T['lead2']}: overlap_f1"] == f1[i][2] for i in f1)
        and list(by["t01_login"]).index(f"{T['lead1']}: overlap_f1")
        == list(by["t01_login"]).index(T["lead1"]) + 1
        and f"{T['lead1']}: latency_ms" not in by["t01_login"],
        out(r)[-400:] + str(list(by["t01_login"])),
    )
    won = {i: by[i]["winner: overlap_f1"] for i in by}
    check(
        "winner on the goal's metric: the best arm, every arm tied for best named",
        won["t03_export"] == T["author"]
        and won["t06_mobile"] == T["lead2"]
        and won["t05_delete"] == T["lead1"]
        and sorted(won["t01_login"].split(" = ")) == sorted([T["lead1"], T["author"]])
        and sorted(won["t04_api"].split(" = ")) == sorted(T.values()),
        str(won),
    )
    rate = foot["win rate · winner: overlap_f1"]
    mean = foot["mean overlap_f1"]
    check(
        "footer: each arm's mean on the metric, and its win rate (the rows it wins, a shared win split)",
        abs(mean[T["lead1"]] - 0.35) < 1e-9
        and abs(mean[T["author"]] - 2.3 / 6) < 1e-9
        and abs(rate[T["lead1"]] - 2.8333333 / 6) < 1e-6
        and abs(rate[T["author"]] - 1.8333333 / 6) < 1e-6
        and abs(rate[T["lead2"]] - 1.3333333 / 6) < 1e-6
        and abs(sum(rate[t] for t in T.values()) - 1) < 1e-9
        and "higher is better" in footer_label(r, "mean"),
        json.dumps(foot)[:500],
    )
    verdict = foot["verdict"]
    check(
        "footer verdict with a goal naming the dataset: the goal's decision (the leader, who is not a contender and why)",
        verdict[T["author"]].startswith("leader")
        and verdict[T["lead1"]].startswith("not a contender: not significant")
        and "goal tickets_summary" in footer_label(r, "verdict"),
        json.dumps(verdict),
    )
    r, rs, foot = sheet_of("--metric", "latency_ms")
    by = {x["item_id"]: x for x in rs}
    won = {i: by[i]["winner: latency_ms"] for i in by}
    lrate = foot["win rate · winner: latency_ms"]
    check(
        "winner on a metric where lower is better (latency_ms): the smallest wins, ties named",
        r.returncode == 0
        and won["t03_export"] == T["author"]
        and won["t05_delete"] == T["lead2"]
        and won["t01_login"] == T["lead1"]
        and sorted(won["t04_api"].split(" = ")) == sorted([T["lead1"], T["author"]])
        and abs(lrate[T["lead2"]] - 1 / 6) < 1e-9
        and f"{T['lead1']}: latency_ms" in by["t01_login"]
        and "lower is better" in footer_label(r, "mean"),
        str(won) + out(r)[-200:],
    )
    r, rs, foot = sheet_of("--metric", "cost_usd")
    by = {x["item_id"]: x for x in rs}
    check(
        "identical scores: every arm tied for the winner, and a contender (nothing to test)",
        r.returncode == 0
        and all(sorted(by[i]["winner: cost_usd"].split(" = ")) == sorted(T.values()) for i in by)
        and sorted(foot["verdict"][t].split(",")[0] for t in T.values())
        == ["contender", "contender", "leader"],
        json.dumps(foot["verdict"]),
    )
    goal_rel = "goals/tickets_summary.yaml"
    goal_aside = _runstore.read_bytes(proj, goal_rel)
    _runstore.unlink(proj, goal_rel)
    r, rs, foot = sheet_of()
    _runstore.write_bytes(proj, goal_rel, goal_aside)
    check(
        "footer verdict with no goal: the paired test of each arm against the leader (the best mean)",
        r.returncode == 0
        and "paired test against the leader" in footer_label(r, "verdict")
        and foot["verdict"][T["author"]] == "leader"
        and foot["verdict"][T["lead1"]].startswith("not significant (p ")
        and "goal" not in footer_label(r, "verdict"),
        json.dumps(foot["verdict"]) + footer_label(r, "verdict"),
    )
    r, rs, foot = sheet_of("--unlabelled", "--where", "area:account")
    check(
        "the footer is over the rows shown (one row: the mean is that row's score)",
        ids(rs) == ["t05_delete"] and abs(foot["mean overlap_f1"][T["lead1"]] - 0.6) < 1e-9,
        json.dumps(foot)[:300],
    )

    # ── judged runs: the judge's scores in the cells, a winner per pick/pairwise scorer ─────────────
    def judged(scorer, metric, values):
        for k, name in run_names.items():
            m = _runstore.read_json(proj, f"runs/{name}/metrics.json")
            m["derived"] = {
                "kind": "judge",
                "from": name,
                "at": m["created_at"],
                "with": {"scorer_id": scorer},
            }
            m["primary_metric"] = metric
            with _runstore._InProject(proj) as data_:
                jd = data_ / "runs-judged" / scorer / name
                _store.mkdir(jd, parents=True)
                _store.write_text(jd / "metrics.json", json.dumps(m))
                _runstore.put_rows_text(
                    jd,
                    "".join(
                        json.dumps({"item_id": i, metric: v[list(T).index(k)]}) + "\n"
                        for i, v in values.items()
                    ),
                )

    grade = {i: (n % 5 + 1.0, (n * 2) % 5 + 1.0, (n * 3) % 5 + 1.0) for n, i in enumerate(f1)}
    judged("judge_a", "judge_score", grade)
    judged("judge_c", "judge_score", grade)
    picks = {
        "t01_login": (1, 0, 0),
        "t02_invoice": (0, 1, 0),
        "t03_export": (0, 1, 0),
        "t04_api": (0.5, 0, 0.5),  # a shared pick
        "t05_delete": (1, 0, 0),
        "t06_mobile": (0, 0, 1),
    }
    judged("judge_b", "judge_won", picks)
    r, rs, foot = sheet_of()
    by = {x["item_id"]: x for x in rs}
    cols = list(by["t01_login"])
    check(
        "judged scores: the judge's metric in the arm's cells, labelled by the scorer",
        r.returncode == 0
        and by["t02_invoice"][f"{T['lead1']}: judge_a/judge_score"] == grade["t02_invoice"][0]
        and by["t02_invoice"][f"{T['lead2']}: judge_c/judge_score"] == grade["t02_invoice"][2]
        and by["t03_export"][f"{T['author']}: judge_b/judge_won"] == 1,
        out(r)[-300:] + str(cols),
    )
    wb = {i: by[i]["winner: judge_b"] for i in by}
    check(
        "winner per judging scorer (judge_won): the arm(s) with the most, beside the metric's winner so a row where they differ shows",
        wb["t01_login"] == T["lead1"]
        and wb["t06_mobile"] == T["lead2"]
        and sorted(wb["t04_api"].split(" = ")) == sorted([T["lead1"], T["lead2"]])
        and "winner: overlap_f1" in cols
        and cols.index("winner: judge_b") < cols.index("winner: overlap_f1")
        and "winner: judge_a" not in cols,
        str(wb) + str(cols),
    )
    jr = foot["win rate · winner: judge_b"]
    check(
        "footer: the win rate on the judge's picks beside the metric's",
        abs(jr[T["lead1"]] - 2.5 / 6) < 1e-9
        and abs(jr[T["author"]] - 2 / 6) < 1e-9
        and abs(jr[T["lead2"]] - 1.5 / 6) < 1e-9,
        json.dumps(jr),
    )
    # Two of the three shown: t06_mobile's pick went to lead2, so neither shown arm won it.
    two_shown = f"{T['lead1']},{T['author']}"
    r, rs, foot = sheet_of(runs=two_shown)
    by = {x["item_id"]: x for x in rs}
    jr = foot.get("win rate · winner: judge_b", {})
    check(
        "a pick that went to an arm not shown is nobody's win, and a shared pick credits each arm its share (t04: half): the judge's own win rate",
        r.returncode == 0
        and by["t06_mobile"]["winner: judge_b"] in ("", None)
        and abs(jr.get(T["lead1"], 0) - 2.5 / 6) < 1e-9
        and abs(jr.get(T["author"], 0) - 2 / 6) < 1e-9,
        json.dumps(jr) + str(by.get("t06_mobile", {}).get("winner: judge_b")),
    )
    r, rs, foot = sheet_of("--from", "runs-judged/judge_b", runs=two_shown)
    by = {x["item_id"]: x for x in rs}
    jr = foot.get("win rate · winner: judge_won", {})
    check(
        "the same when the judged runs are the arms (read on judge_won): a row where every shown arm has 0 has no winner",
        r.returncode == 0
        and by["t06_mobile"].get("winner: judge_won") in ("", None)
        and abs(jr.get(T["lead1"], 0) - 2.5 / 6) < 1e-9
        and abs(jr.get(T["author"], 0) - 2 / 6) < 1e-9,
        json.dumps(jr) + json.dumps(by.get("t06_mobile", {}))[:300],
    )
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--metric", "judge_score")
    check("refused: a metric two scorers judged, naming them", refused(r, "judge_a, judge_c"), out(r)[-300:])
    r, rs, foot = sheet_of("--metric", "judge_a/judge_score")
    check(
        "--metric SCORER/metric reads the sheet on a judge's score",
        r.returncode == 0
        and "mean judge_a/judge_score" in foot
        and foot["mean judge_a/judge_score"][T["lead1"]] is not None,
        out(r)[-300:],
    )
    r, rs, foot = sheet_of("--metric", "judge_won")
    cols = list(rs[0]) if rs else []
    check(
        "--metric judge_won (one scorer judged it): read on it, and its winners not repeated as a metric winner",
        r.returncode == 0
        and "winner: judge_b" in cols
        and not any(c.startswith("winner: judge_b/") for c in cols),
        out(r)[-300:] + str(cols),
    )
    r, rs, _ = sheet_of("--scores-only")
    cols = list(rs[0]) if rs else []
    check(
        "--scores-only leaves the outputs out, keeps the scores",
        r.returncode == 0 and T["lead1"] not in cols and f"{T['lead1']}: overlap_f1" in cols,
        str(cols),
    )

    # ── the CSV: Excel opens it, the footer is marked, the empty columns to fill ──────────────────
    def read_sheet(name):
        text = (proj / name).read_text("utf-8-sig") if (proj / name).is_file() else ""
        return list(csv.DictReader(io.StringIO(text, newline=""))), next(csv.reader(io.StringIO(text)), [])

    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--csv", "out.csv")
    raw = (proj / "out.csv").read_bytes() if (proj / "out.csv").is_file() else b""
    body, head = read_sheet("out.csv")
    items_ = [x for x in body if not x["item_id"].startswith("#")]
    foot_ = [x for x in body if x["item_id"].startswith("#")]
    check(
        "--csv: UTF-8 with the mark Excel needs, a column per field, the footer rows marked #",
        r.returncode == 0
        and raw.startswith(b"\xef\xbb\xbf")
        and head[:3] == ["item_id", "item", "signals"]
        and "field: area" in head
        and len(items_) == 6
        and foot_[0]["item_id"].startswith("#mean")
        and any(x["item_id"] == "#verdict" for x in foot_)
        and foot_[0][f"{T['author']}: overlap_f1"]
        and items_[0]["item"]
        and items_[0][T["lead1"]],
        out(r)[-300:] + str(head),
    )
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--csv", "out.csv")
    check(
        "--csv never overwrites a sheet (it may have been filled)",
        refused(r, "not overwritten"),
        out(r)[-200:],
    )
    r = evh(
        "inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--csv", "lab.csv", "--fill", "label",
        "--choices", "A,B",
    )  # fmt: skip
    lab_rows, lab_head = read_sheet("lab.csv")
    check(
        "--csv --fill label: the empty label (the allowed answers in its header), also right and note columns; no footer",
        r.returncode == 0
        and lab_head[-3:] == ["label [A|B]", "also right", "note"]
        and len(lab_rows) == 6
        and not any(x["item_id"].startswith("#") for x in lab_rows),
        out(r)[-300:] + str(lab_head[-4:]),
    )
    r = evh(
        "inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--csv", "sc.csv", "--scores-only", "--unlabelled"
    )  # fmt: skip
    sc_rows, sc_head = read_sheet("sc.csv")
    check(
        "--csv takes the filters and --scores-only",
        r.returncode == 0
        and T["lead1"] not in sc_head
        and f"{T['lead1']}: overlap_f1" in sc_head
        and sorted(x["item_id"] for x in sc_rows if not x["item_id"].startswith("#"))
        == ["t04_api", "t05_delete", "t06_mobile"],
        out(r)[-200:],
    )
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--seed", "3")
    check("refused: --seed without a blind fill", refused(r, "--fill pick or scores"), out(r)[-200:])
    for made in ("out.csv", "lab.csv", "sc.csv"):
        (proj / made).unlink(missing_ok=True)
    r, rs, foot = sheet_of("--from", "runs-judged/judge_a", runs=T["lead1"])
    check(
        "--from DIR looks the config ids up there: a judging pass read as the run itself, its score the primary",
        r.returncode == 0
        and rs
        and "mean judge_score" in foot
        and f"{T['lead1']}: judge_score" in rs[0]
        and f"{T['lead1']}: overlap_f1" not in rs[0],
        out(r)[-300:],
    )
    r2, rs2, foot2 = sheet_of(runs=f"runs-judged/judge_a/{D}/{T['lead1']}")
    check(
        "an arm id as the catalog names it, under a nested folder (runs-judged/<scorer>/<dataset>/<config>): the same sheet as --from",
        r2.returncode == 0
        and rs2
        and "mean judge_score" in foot2
        and [x["item_id"] for x in rs2] == [x["item_id"] for x in rs],
        out(r2)[-300:],
    )
    r2 = evh("inspect", "--sheet", "--dataset-id", D, "--runs", f"runs-judged/judge_a/other_v1/{T['lead1']}")
    check("refused: a nested arm id on another dataset", refused(r2, f"not an arm on {D}"), out(r2)[-200:])
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", T["lead1"], "--from", "runs-judged/no_such")
    check("refused: a --from that holds no such run", refused(r, "no run of that config"), out(r)[-200:])
    # A metric an arm has on some rows only: its win rate is over the rows it was scored on, and an arm scored on
    # none has no win rate (it was never compared, not always beaten).
    part: dict[str, tuple] = dict.fromkeys(f1, (None, 2.0, None))
    part["t01_login"], part["t02_invoice"] = (3.0, 1.0, None), (1.0, 3.0, None)
    judged("judge_p", "judge_score", part)
    r, rs, foot = sheet_of("--metric", "judge_p/judge_score")
    pr: dict = next((v for k, v in foot.items() if k.startswith("win rate") and "judge_score" in k), {})
    check(
        "win rate on a metric: over the rows each arm was scored on; '—' for one scored on none",
        r.returncode == 0
        and abs(pr.get(T["lead1"], 0) - 1 / 2) < 1e-9
        and abs(pr.get(T["author"], 0) - 5 / 6) < 1e-9
        and pr.get(T["lead2"]) in (None, "", "—"),
        json.dumps(pr) + out(r)[-200:],
    )
    vr: dict = next((v for k, v in foot.items() if k.startswith("verdict")), {})
    check(
        "verdict: an arm with no score on the metric gets none, and takes no part in the decision",
        "no judge_p/judge_score in this run" in str(vr.get(T["lead2"], ""))
        and "leader" in str(vr.get(T["author"], "")),
        json.dumps(vr),
    )
    r, rs, foot = sheet_of("--metric", "judge_p/judge_score", runs=f"{T['lead1']},{T['lead2']}")
    vr = next((v for k, v in foot.items() if k.startswith("verdict")), {})
    check(
        "verdict: one scored arm beside an unscored one is compared with nothing, never 'leader, recommended'",
        "nothing to compare" in str(vr.get(T["lead1"], "")) and "recommended" not in json.dumps(vr),
        json.dumps(vr),
    )
    _runstore.rmtree(proj, "runs-judged")

    # ── refusals ─────────────────────────────────────────────────────────────────────────────
    two = "tickets_lead1_v1,tickets_author_v1"
    for args, text, what in (
        (["--runs", two, "--split"], "--split needs 3", "--split with fewer than three runs"),
        (["--runs", "tickets_lead1_v1", "--disagree"], "--disagree needs 2", "--disagree with one run"),
        (["--wrong-against", "owner"], "--wrong-against needs 1", "--wrong-against with no run"),
        (["--runs", two, "--wrong-against", "no_such"], "no such label set", "an unknown label set"),
        (["--runs", two, "--new-vs", "no_such_dataset"], "no_such_dataset", "an unknown --new-vs dataset"),
        (["--runs", two, "--where", "nope:x"], "no field 'nope'", "a --where on no field"),
        (["--runs", two, "--metric", "no_such_metric"], "no run in --runs records it", "an unknown --metric"),
        (["--runs", two, "--item", "t01_login"], "not with --sheet", "--item with --sheet"),
        (["--runs", two, "--fill", "pick"], "with --csv", "--fill without --csv"),
        (
            ["--runs", two, "--csv", "x.csv", "--fill", "scores", "--scale", "5"],
            "LO..HI",
            "a --scale that is no range",
        ),
        (["--runs", "no_such_run_v1"], "no run with that id", "a run that does not exist"),
    ):
        r = evh("inspect", "--sheet", "--dataset-id", D, *args)
        check(f"refused: {what}", refused(r, text), out(r)[-200:])
    r = evh("inspect", "--sheet", "--runs", two)
    check("refused: --sheet without --dataset-id", refused(r, "--dataset-id"), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--runs", two)
    check("refused: --dataset-id without --sheet", refused(r, "--sheet"), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--runs", two, "--unlabelled")
    check("refused: a sheet filter without --sheet", refused(r, "--sheet"), out(r)[-200:])
    r = evh("inspect", "--runs", two, "--scores-only")
    check("refused: --scores-only without --sheet", refused(r, "--sheet"), out(r)[-200:])
    r = evh("inspect", "--sheet", "--dataset-id", D, "--round", "r1")
    check("refused: --sheet with --round", refused(r, "--runs"), out(r)[-200:])
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", two, extra={"EVH_PUBLIC": "1"})
    check(
        "refused publicly: the sheet carries outputs and labels",
        refused(r, "not served publicly"),
        out(r)[-200:],
    )
    r = evh("inspect", "--baseline", "x")
    check("inspect still needs --runs, --round or --sheet", refused(r, "--runs"), out(r)[-200:])
    r = evh("inspect", "--runs", two, "--items")
    check("--items is gone (the sheet replaces it)", r.returncode != 0 and "--items" in out(r), out(r)[-200:])
    r = evh("inspect", "--dataset-id", D, "--rows", "--runs", two)
    check("--rows is gone (the sheet replaces it)", r.returncode != 0 and "--rows" in out(r), out(r)[-200:])

    # ── the decision, not the whole output (UXS-002): an adapter's decision(output) is what a row shows ───
    (proj / "decide.py").write_text(
        "from evaluation_harness.adapter import Result, score  # noqa: F401\n"
        "def call_system(text, params):\n"
        "    return Result(output='A because ' + text[:40], cost_usd=0.0)\n"
        "def decision(output):\n"
        "    return output.split()[0]\n"
        "def title(item):\n"
        "    return 'TITLE ' + item.split()[0]\n"
    )
    _runstore.write_text(
        proj,
        "configs/tickets_decider.yaml",
        "config_id: tickets_decider_v1\ndataset_id: tickets_v1\nadapter: decide.py\nparams:\n  provider: echo\n",
    )
    r = evh(
        "run",
        "--config",
        "data/configs/tickets_decider.yaml",
        extra={"PYTHONPATH": str(HERE.parent)},
    )
    check("setup: an arm whose adapter has decision()", r.returncode == 0, out(r)[-300:])
    r = evh(
        "inspect", "--sheet", "--dataset-id", D, "--runs", "tickets_decider_v1,tickets_lead1_v1", "--json"
    )
    table = next(
        (b for b in blocks_of(r) if "columns" in b and b["columns"][0] == "item_id"),
        {"rows": [], "columns": []},
    )
    first = {x["item_id"]: x for x in table["rows"]}.get("t01_login", {})
    check(
        "rows: an arm's column is its adapter's decision(output), the signals second; an arm without one shows "
        "its output",
        first.get("tickets_decider_v1") == "A"
        and first.get("tickets_lead1_v1") == "A"
        and table["columns"][:3] == ["item_id", "item", "signals"]
        and "disagree" not in str(first.get("signals")),
        out(r)[-400:] + json.dumps(table.get("columns")),
    )
    rest = evh(
        "inspect", "--sheet", "--dataset-id", D, "--runs", "tickets_lead1_v1,tickets_decider_v1", "--json"
    )
    rest_rows: list = next(
        (b for b in blocks_of(rest) if "columns" in b and b["columns"][0] == "item_id"), {"rows": []}
    )["rows"]
    check(
        "the item's start is the first arm's adapter's title(item) when it has one, else the item's own start",
        str(first.get("item", "")).startswith("TITLE ")
        and rest_rows
        and not str(rest_rows[0].get("item", "")).startswith("TITLE "),
        str(first.get("item")) + " | " + str(rest_rows[0].get("item") if rest_rows else None),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
