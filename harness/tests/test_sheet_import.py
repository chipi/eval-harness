#!/usr/bin/env python3
"""A sheet filled elsewhere, read back (RFC-023): `inspect --sheet --csv --fill …` and `sheet-import`.

    python tests/test_sheet_import.py

In a throwaway project built from the tutorial ($0, offline), three arms on the six tickets:

- `--fill label`: the empty label columns; the filled sheet becomes a label set (a person's, or a model's with
  `--kind model`), `also right` joined, the allowed answers enforced, the `#` rows left out;
- `--fill pick`: the outputs as blind columns A, B, C…, shuffled per row by the seed (the same seed the same
  order), no arm named in the sheet, the rubric as its first row, the key beside it; the filled sheet becomes judged
  runs under data/runs-judged/<scorer>/, `judge_won_unvalidated` mapped back through the key (a shared pick split),
  unvalidated, with who filled it and the rubric's sha256; the inspector's sheet then shows them;
- `--fill scores`: `score: X` columns on the rubric's scale, the same way;
- every refusal, each writing nothing: no key, a key that is not the sheet's, an edited output, a row the key
  lacks, a pick naming a letter not on its row, a score off the scale or no number, nothing filled, a name already
  used, a missing --set or --scorer.
"""

import csv
import hashlib
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
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-sheet-import-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-sheet-import")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_PUBLIC"):
    env.pop(k, None)
D = "tickets_v1"
ARMS = {"lead1": "tickets_lead1_v1", "lead2": "tickets_lead2_v1", "author": "tickets_author_v1"}
RUNS = ",".join(ARMS.values())


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in out(r) and text in out(r)


def read(name):
    """(rows as dicts, header, raw bytes) of a CSV in the project."""
    raw = (proj / name).read_bytes()
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text, newline=""))), next(csv.reader(io.StringIO(text))), raw


def write(name, head, rows):
    with (proj / name).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows([[r.get(h, "") for h in head] for r in rows])


def tree():
    return sorted(
        str(p.relative_to(proj)) for p in proj.rglob("*") if p.is_file() and "runs-judged" in str(p)
    )


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fill(prefix, fill_, *extra, seed=None):
    name = f"{prefix}.csv"
    r = evh(
        "inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--csv", name, "--fill", fill_, *extra,
        *(["--seed", str(seed)] if seed is not None else []),
    )  # fmt: skip
    return r, name


def filled(prefix, how):
    """The blind sheet with its key, filled by `how(row, key_row)` -> {column: value}; written as <prefix>_f.csv
    (its key copied beside it)."""
    rows, head, _ = read(f"{prefix}.csv")
    key = json.loads((proj / f"{prefix}.key.json").read_text())
    mine = []
    for r in rows:
        if r["item_id"].startswith("#"):
            mine.append(r)
        else:
            mine.append({**r, **how(r, key["rows"][r["item_id"]], key)})
    write(f"{prefix}_f.csv", head, mine)
    shutil.copy(proj / f"{prefix}.key.json", proj / f"{prefix}_f.key.json")
    return head, mine, key


def letter_of(key_row, key, arm_token):
    k = next(i for i, a in enumerate(key["arms"]) if a["arm"] == arm_token)
    return next(letter for letter, info in key_row.items() if info["arm"] == k)


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "fields").mkdir()
    shutil.copy(KIT / "fields" / "tickets.yaml", data / "fields")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh(
        "dataset-create", "--dataset-id", D, "--source-dir", "tutorial/tickets", "--fieldset", "tickets",
        "--fields", str(KIT / "ticket_fields.csv"),
    )  # fmt: skip
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", D)
    check("setup: the tutorial dataset, materialized", r.returncode == 0, out(r)[-300:])
    for arm in ARMS:
        shutil.copy(KIT / "configs" / f"tickets_{arm}.yaml", data / "configs")
        r = evh("run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
    items = sorted(p.stem for p in (data / "materialized" / D).glob("*.txt")) or sorted(
        p.stem for p in (KIT / "tickets").glob("*.txt")
    )
    check("setup: six tickets", len(items) == 6, str(items))

    # ── labels: --fill label, then sheet-import --set ────────────────────────────────────────
    r, name = fill("lab", "label", "--choices", "file,dismiss,escalate")
    rows, head, raw = read(name)
    check(
        "--fill label: the item, what each arm decided, and the empty label (its choices in the header), also right, note",
        r.returncode == 0
        and raw.startswith(b"\xef\xbb\xbf")
        and head[-3:] == ["label [file|dismiss|escalate]", "also right", "note"]
        and len(rows) == 6
        and all(not x["label [file|dismiss|escalate]"] for x in rows)
        and not (proj / "lab.key.json").exists(),
        out(r)[-300:] + str(head),
    )
    col = "label [file|dismiss|escalate]"
    mine = [{**x, col: "file"} for x in rows]
    mine[1][col], mine[1]["also right"] = "escalate", "file"
    mine[2][col] = ""
    mine.append({"item_id": "#a footer", col: "dismiss"})
    write("lab_f.csv", head, mine)
    r = evh("sheet-import", "lab_f.csv", "--dataset-id", D, "--by", "owner", "--set", "owner_sheet")
    labels_dir = data / "labels" / D / "owner_sheet"
    doc = (
        json.loads((labels_dir / "labels.json").read_text()) if (labels_dir / "labels.json").is_file() else {}
    )
    got = {p.stem: p.read_text().strip() for p in labels_dir.glob("*.txt")}
    check(
        "sheet-import: a filled label column becomes a person's label set (also right joined, an empty row and the # rows left out)",
        r.returncode == 0
        and doc.get("source", {}).get("kind") == "person"
        and doc["source"]["by"] == "owner"
        and doc["source"]["sheet_sha256"] == sha((proj / "lab_f.csv").read_bytes())
        and len(got) == 5
        and json.loads(got[items[1]]) == {"accept": ["escalate", "file"]}
        and got[items[0]] == "file"
        and items[2] not in got,
        out(r)[-300:] + str(got),
    )
    r = evh(
        "sheet-import",
        "lab_f.csv",
        "--dataset-id",
        D,
        "--by",
        "claude",
        "--kind",
        "model",
        "--set",
        "claude_sheet",
    )
    doc = json.loads((data / "labels" / D / "claude_sheet" / "labels.json").read_text())
    check(
        "sheet-import --kind model: the same sheet as a model's label set, the tool named",
        r.returncode == 0 and doc["source"]["kind"] == "model" and doc["source"]["by"] == "claude",
        out(r)[-300:],
    )
    bad = [{**x, col: "maybe"} for x in rows]
    write("lab_bad.csv", head, bad)
    r = evh("sheet-import", "lab_bad.csv", "--dataset-id", D, "--by", "owner", "--set", "never")
    check(
        "refused: an answer outside the sheet's choices, nothing written",
        refused(r, "not among the sheet's choices") and not (data / "labels" / D / "never").exists(),
        out(r)[-300:],
    )
    r = evh("sheet-import", "lab_f.csv", "--dataset-id", D, "--by", "owner")
    check("refused: labels without --set", refused(r, "--set"), out(r)[-200:])
    r = evh("sheet-import", "lab_f.csv", "--dataset-id", D, "--by", "owner", "--set", "owner_sheet")
    check("refused: a label set that exists is never edited", refused(r, "never edited"), out(r)[-200:])
    r = evh("sheet-import", "lab.csv", "--dataset-id", D, "--by", "owner", "--set", "empty_one")
    check("refused: nothing filled", refused(r, "nothing filled"), out(r)[-200:])

    # ── pick: blind columns, the key, the round trip ─────────────────────────────────────────
    r, name = fill("pick", "pick", seed=7)
    rows, head, raw = read(name)
    text = raw.decode("utf-8-sig")
    key = json.loads((proj / "pick.key.json").read_text())
    rub = next(x for x in rows if x["item_id"] == "#rubric")
    body = [x for x in rows if not x["item_id"].startswith("#")]
    check(
        "--fill pick: blind columns A, B, C and an empty pick; the rubric the first row; no arm named in the sheet",
        r.returncode == 0
        and head[:5] == ["item_id", "item", "A", "B", "C"]
        and "pick" in head
        and rows[0]["item_id"] == "#rubric"
        and len(body) == 6
        and all(x["A"] and x["B"] and x["C"] and not x["pick"] for x in body)
        and not any(a in text for a in ARMS.values())
        and key["fill"] == "pick"
        and key["rubric"] == rub["item"]
        and key["rubric_sha256"] == hashlib.sha256(rub["item"].encode()).hexdigest()
        and sorted(key["rows"]) == sorted(items),
        out(r)[-300:] + str(head),
    )
    orders = {tuple(letter_of(key["rows"][i], key, a) for a in ARMS.values()) for i in items}
    check(
        "the arms' order is shuffled per row (their letters differ from row to row)",
        len(orders) > 1,
        str(orders),
    )
    r2, _ = fill("pick_again", "pick", seed=7)
    r3, _ = fill("pick_other", "pick", seed=8)
    again = json.loads((proj / "pick_again.key.json").read_text())["rows"]
    other = json.loads((proj / "pick_other.key.json").read_text())["rows"]
    check(
        "the same seed gives the same order; another seed another",
        r2.returncode == r3.returncode == 0 and again == key["rows"] and other != key["rows"],
        "",
    )
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--csv", "pick.csv", "--fill", "pick")
    check(
        "refused: a sheet that exists is not overwritten (it may be filled)",
        refused(r, "not overwritten"),
        out(r)[-200:],
    )
    r = evh(
        "inspect", "--sheet", "--dataset-id", D, "--runs", ARMS["lead1"], "--csv", "one.csv", "--fill", "pick"
    )
    check(
        "refused: a pick needs two runs",
        refused(r, "two runs or more") and not (proj / "one.csv").exists(),
        out(r)[-200:],
    )

    # The filler picks the author's output everywhere but on the second row (a tie with lead1) and the third (skipped).
    def pick_author(row, key_row, key):
        i = row["item_id"]
        if i == items[2]:
            return {}
        if i == items[1]:
            return {
                "pick": "|".join(
                    sorted([letter_of(key_row, key, ARMS["author"]), letter_of(key_row, key, ARMS["lead1"])])
                )
            }
        return {"pick": letter_of(key_row, key, ARMS["author"]).lower()}

    filled("pick", pick_author)
    r = evh("sheet-import", "pick_f.csv", "--dataset-id", D, "--by", "owner", "--scorer", "owner_picks")
    after_import = tree()
    jroot = data / "runs-judged" / "owner_picks"
    recs = {}
    metrics = {}
    for arm, cid in ARMS.items():
        d = next(iter(jroot.glob(f"{cid}_*")), None)
        if d is not None:
            recs[arm] = {
                json.loads(ln)["item_id"]: json.loads(ln)
                for ln in (d / "predictions.jsonl").read_text().splitlines()
            }
            metrics[arm] = json.loads((d / "metrics.json").read_text())
    check(
        "sheet-import pick: judged runs under data/runs-judged/<scorer>/, one per arm, named as the source run",
        r.returncode == 0
        and sorted(recs) == sorted(ARMS)
        and all(
            m["derived"]["from"] == next((data / "runs").glob(f"{ARMS[a]}_*")).name
            for a, m in metrics.items()
        ),
        out(r)[-400:],
    )
    won = {a: {i: v["judge_won_unvalidated"] for i, v in recs[a].items()} for a in recs} if recs else {}
    check(
        "the key maps every pick back to its arm, through the shuffle (a lower-case letter, a shared pick split, an empty row skipped)",
        all(
            won["author"][i] == 1.0 and won["lead1"][i] == 0.0 and won["lead2"][i] == 0.0
            for i in items
            if i not in items[1:3]
        )
        and won["author"][items[1]] == won["lead1"][items[1]] == 0.5
        and won["lead2"][items[1]] == 0.0
        and items[2] not in won["author"],
        json.dumps(won),
    )
    m = metrics.get("author", {})
    w = m.get("derived", {}).get("with", {})
    check(
        "the judged runs are unvalidated, say who filled the sheet, the rubric's and the sheet's sha256",
        m.get("derived", {}).get("kind") == "judge"
        and m.get("primary_metric") == "judge_won_unvalidated"
        and w.get("source") == "sheet"
        and w.get("scorer_id") == "owner_picks"
        and w.get("filled_by") == "owner"
        and w.get("kind") == "person"
        and w.get("unvalidated") is True
        and w.get("validated") is False
        and w.get("rubric_sha256") == key["rubric_sha256"]
        and w.get("sheet_sha256") == sha((proj / "pick_f.csv").read_bytes())
        and set(m.get("scores", {})) >= {"judge_won_unvalidated"}
        and abs(m["scores"]["judge_won_unvalidated"] - (4 + 0.5) / 5) < 1e-9,
        json.dumps(w)[:400],
    )
    r = evh("inspect", "--sheet", "--dataset-id", D, "--runs", RUNS, "--json")
    blocks = json.loads(r.stdout)["result"]["blocks"] if r.returncode == 0 else []
    table: dict = next(
        (b for b in blocks if "columns" in b and b["columns"][0] == "item_id"), {"rows": [], "columns": []}
    )
    byi = {x["item_id"]: x for x in table["rows"]}
    check(
        "the inspector's sheet shows them: the judge's picks in the cells and a winner column for the scorer",
        r.returncode == 0
        and byi[items[0]]["winner: owner_picks"] == ARMS["author"]
        and sorted(byi[items[1]]["winner: owner_picks"].split(" = "))
        == sorted([ARMS["author"], ARMS["lead1"]])
        and byi[items[2]]["winner: owner_picks"] == ""
        and byi[items[0]][f"{ARMS['author']}: owner_picks/judge_won_unvalidated"] == 1.0,
        out(r)[-300:] + str(table["columns"]),
    )
    r = evh("sheet-import", "pick_f.csv", "--dataset-id", D, "--by", "owner", "--scorer", "owner_picks")
    check("refused: judged runs are never overwritten", refused(r, "never overwritten"), out(r)[-200:])
    r = evh("sheet-import", "pick_f.csv", "--dataset-id", D, "--by", "owner")
    check("refused: judgements without --scorer", refused(r, "--scorer"), out(r)[-200:])
    check("refusing wrote nothing more", tree() == after_import and after_import != [], str(tree()))

    # ── refusals of a pick sheet, each leaving nothing written ───────────────────────────────
    def refuses(what, mutate, text, scorer, key_from=None, drop_key=False):
        rows_, head_, _ = read("pick_f.csv")
        rows_ = mutate(rows_)
        write("bad.csv", head_, rows_)
        (proj / "bad.key.json").unlink(missing_ok=True)
        if not drop_key:
            shutil.copy(proj / (key_from or "pick.key.json"), proj / "bad.key.json")
        r_ = evh("sheet-import", "bad.csv", "--dataset-id", D, "--by", "owner", "--scorer", scorer)
        check(
            f"refused: {what}, nothing written",
            refused(r_, text) and not (data / "runs-judged" / scorer).exists(),
            out(r_)[-300:],
        )

    first_row = lambda rs: next(x for x in rs if not x["item_id"].startswith("#"))  # noqa: E731
    refuses("no key beside the sheet", lambda rs: rs, "no key at", "r1", drop_key=True)
    refuses(
        "a key that is another sheet's (another seed)",
        lambda rs: rs,
        "outputs are not the key's",
        "r2",
        key_from="pick_other.key.json",
    )

    def edit_output(rs):
        first_row(rs)["B"] += " and a word more"
        return rs

    refuses("an edited output", edit_output, "outputs are not the key's", "r3")

    def foreign_row(rs):
        return [*rs, {"item_id": "t99_nope", "pick": "A"}]

    refuses("a row the key does not have", foreign_row, "not in the key", "r4")

    def off_letter(rs):
        first_row(rs)["pick"] = "D"
        return rs

    refuses("a pick naming a letter that is not on the row", off_letter, "no D on the row", "r5")

    def nothing(rs):
        for x in rs:
            x["pick"] = ""
        return rs

    refuses("nothing filled", nothing, "nothing filled", "r6")

    # ── scores: the rubric file, the scale, the round trip ───────────────────────────────────
    (proj / "rubric.md").write_text("Score the summary for what a person triaging needs to know.\n")
    r, name = fill("sc", "scores", "--scale", "1..10", "--rubric", "rubric.md", seed=3)
    rows, head, _ = read(name)
    key = json.loads((proj / "sc.key.json").read_text())
    rub = next(x for x in rows if x["item_id"] == "#rubric")
    check(
        "--fill scores: blind columns and a score column each, the rubric file's words, the scale in the key",
        r.returncode == 0
        and head[:5] == ["item_id", "item", "A", "B", "C"]
        and {"score: A", "score: B", "score: C"} <= set(head)
        and rub["item"] == "Score the summary for what a person triaging needs to know."
        and key["scale"] == [1, 10]
        and key["fill"] == "scores"
        and key["rubric_sha256"] == hashlib.sha256(rub["item"].encode()).hexdigest(),
        out(r)[-300:] + str(head),
    )
    value = {"author": "9", "lead1": "5", "lead2": "3"}

    def score_by_arm(row, key_row, key_):
        got = {f"score: {letter_of(key_row, key_, ARMS[a])}": v for a, v in value.items()}
        if row["item_id"] == items[1]:  # a spreadsheet in a comma-decimal locale
            got[f"score: {letter_of(key_row, key_, ARMS['author'])}"] = "7,5"
        if row["item_id"] == items[2]:  # one arm left unscored
            got[f"score: {letter_of(key_row, key_, ARMS['lead2'])}"] = ""
        return got

    filled("sc", score_by_arm)
    r = evh(
        "sheet-import",
        "sc_f.csv",
        "--dataset-id",
        D,
        "--by",
        "claude",
        "--kind",
        "model",
        "--scorer",
        "claude_scores",
    )
    sroot = data / "runs-judged" / "claude_scores"
    srecs = {}
    smet = {}
    for arm, cid in ARMS.items():
        d = next(iter(sroot.glob(f"{cid}_*")), None)
        if d is not None:
            srecs[arm] = {
                json.loads(ln)["item_id"]: json.loads(ln)["judge_score_unvalidated"]
                for ln in (d / "predictions.jsonl").read_text().splitlines()
            }
            smet[arm] = json.loads((d / "metrics.json").read_text())
    check(
        "sheet-import scores: judge_score_unvalidated per arm per item, mapped back through the shuffle; a comma decimal read; an empty cell skipped",
        r.returncode == 0
        and sorted(srecs) == sorted(ARMS)
        and all(srecs["author"][i] == 9.0 for i in items if i != items[1])
        and srecs["author"][items[1]] == 7.5
        and all(srecs["lead1"][i] == 5.0 for i in items)
        and items[2] not in srecs["lead2"]
        and all(srecs["lead2"][i] == 3.0 for i in items if i != items[2]),
        out(r)[-300:] + json.dumps(srecs)[:400],
    )
    w = smet.get("author", {}).get("derived", {}).get("with", {})
    check(
        "scored runs: unvalidated, filled by a model (named), the rubric's sha256, the scale",
        smet.get("author", {}).get("primary_metric") == "judge_score_unvalidated"
        and w.get("kind") == "model"
        and w.get("filled_by") == "claude"
        and w.get("unvalidated") is True
        and w.get("rubric_sha256") == key["rubric_sha256"]
        and w.get("scale") == [1, 10],
        json.dumps(w)[:300],
    )

    def refuses_scores(what, edit, text, scorer):
        rows_, head_, _ = read("sc_f.csv")
        edit(first_row(rows_), key)
        write("bad2.csv", head_, rows_)
        shutil.copy(proj / "sc.key.json", proj / "bad2.key.json")
        r_ = evh("sheet-import", "bad2.csv", "--dataset-id", D, "--by", "owner", "--scorer", scorer)
        check(
            f"refused: {what}, nothing written",
            refused(r_, text) and not (data / "runs-judged" / scorer).exists(),
            out(r_)[-300:],
        )

    refuses_scores(
        "a score above the scale", lambda x, k: x.update({"score: A": "11"}), "outside the scale 1..10", "s1"
    )
    refuses_scores(
        "a score below the scale", lambda x, k: x.update({"score: B": "0"}), "outside the scale 1..10", "s2"
    )
    refuses_scores(
        "a score that is no number", lambda x, k: x.update({"score: C": "good"}), "is not a number", "s3"
    )
    r = evh(
        "sheet-import",
        "pick_f.csv",
        "--dataset-id",
        D,
        "--by",
        "owner",
        "--scorer",
        "mixed",
        "--key",
        "sc.key.json",
    )
    check(
        "refused: picks with a scores key (the key says which fill made the sheet)",
        refused(r, "--fill scores") and not (data / "runs-judged" / "mixed").exists(),
        out(r)[-300:],
    )
    r = evh("sheet-import", "sc_f.csv", "--dataset-id", "no_such_dataset", "--by", "owner", "--scorer", "s9")
    check(
        "refused: a dataset that does not exist",
        r.returncode != 0 and "Traceback" not in out(r),
        out(r)[-200:],
    )
    r = evh("sheet-import", "sc_f.csv", "--dataset-id", D, "--by", "owner", "--scorer", "has/slash")
    check("refused: a scorer name that is no folder name", refused(r, "--scorer"), out(r)[-200:])
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
