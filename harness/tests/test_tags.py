#!/usr/bin/env python3
"""Failure modes and tags on outputs, through the commands (PLAN_0.8.0 D1, owner 2026-11-05).

    python tests/test_tags.py

In a throwaway project with the tutorial's tickets and two arms: a failure-mode list; `inspect --sheet --fill tags`
writes a sheet with a `failure_modes:` column per arm and its key; filled as a person would (modes, `ok`, a blank),
`sheet-import --tags` reads it back into a tag set and `evh tags` counts each arm's modes. A blank cell is not
recorded, `ok` is; an edited output, an unknown mode and a second import under the same name are refused.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-tags-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-tags")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def read(path):
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.reader(fh))


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "failure-modes").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    for arm in ("lead1", "lead2"):
        (data / "configs" / f"{arm}.yaml").write_text((KIT / "configs" / f"tickets_{arm}.yaml").read_text())
        r = r if r.returncode else evh("run", "--config", str(data / "configs" / f"{arm}.yaml"))
    check("setup: the dataset and two runs", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    (data / "failure-modes" / "summaries.yaml").write_text(
        "failure_modes_id: summaries\n"
        "modes:\n"
        "  - {id: misses-ask, description: does not say what the customer asks for}\n"
        "  - {id: too-long, description: more than two sentences}\n"
    )
    sheet = proj / "tags.csv"
    r = evh(
        "inspect",
        "--sheet",
        "--dataset-id",
        "tickets_v1",
        "--runs",
        "tickets_lead1_v1,tickets_lead2_v1",
        "--csv",
        str(sheet),
        "--fill",
        "tags",
        "--modes",
        "summaries",
    )
    rows = read(sheet) if sheet.is_file() else []
    head = rows[0] if rows else []
    cols = [h for h in head if h.startswith("failure_modes: ")]
    check(
        "inspect --fill tags: a failure_modes column per arm, the modes listed in the first row, a key beside it",
        r.returncode == 0
        and len(cols) == 2
        and rows[1][0] == "#modes"
        and (proj / "tags.key.json").is_file(),
        (r.stdout + r.stderr)[-400:] + str(head),
    )
    # Fill: lead1 misses the ask on t02, lead2 is too long on t01 and t02 (two modes), ok elsewhere on lead2;
    # lead1's other cells left blank (not read).
    c1, c2 = head.index(cols[0]), head.index(cols[1])
    for row in rows[2:]:
        if row[0] == "t02_invoice":
            row[c1], row[c2] = "misses-ask", "too-long|misses-ask"
        elif row[0] == "t01_login":
            row[c2] = "too-long"
        else:
            row[c2] = "ok"
    filled = proj / "filled.csv"
    write(filled, rows)
    shutil.copy(proj / "tags.key.json", proj / "filled.key.json")
    r = evh(
        "sheet-import",
        str(filled),
        "--dataset-id",
        "tickets_v1",
        "--by",
        "owner",
        "--tags",
        "first",
        "--modes",
        "summaries",
    )
    check(
        "sheet-import --tags: the set is written",
        r.returncode == 0 and (data / "tags" / "tickets_v1" / "first" / "tags.json").is_file(),
        (r.stdout + r.stderr)[-400:],
    )
    r = evh("tags", "--dataset-id", "tickets_v1", "--json")
    arms = json.loads(r.stdout).get("arms", {}) if r.returncode == 0 else {}
    l1: dict = next((v for k, v in arms.items() if "lead1" in k), {})
    l2: dict = next((v for k, v in arms.items() if "lead2" in k), {})
    check(
        "evh tags: lead1 read once (blank cells are not recorded), lead2 six times, its modes counted",
        l1.get("outputs") == 1
        and l1.get("modes") == {"misses-ask": 1}
        and l2.get("outputs") == 6
        and l2.get("tagged") == 2
        and l2.get("modes") == {"too-long": 2, "misses-ask": 1},
        r.stdout[-600:],
    )
    shown = proj / "shown.csv"
    r = evh(
        "inspect",
        "--sheet",
        "--dataset-id",
        "tickets_v1",
        "--runs",
        "tickets_lead1_v1,tickets_lead2_v1",
        "--csv",
        str(shown),
    )
    srows = read(shown) if shown.is_file() else []
    fm = [h for h in (srows[0] if srows else []) if h.endswith(": failure modes")]
    t02: list = next((x for x in srows if x and x[0] == "t02_invoice"), [])
    t03: list = next((x for x in srows if x and x[0] == "t03_export"), [])
    cells = [(srows[0].index(h), h) for h in fm] if srows else []
    check(
        "inspect's sheet: a failure-modes column per tagged arm, an item's modes, `ok`, blank when not read",
        r.returncode == 0
        and len(fm) == 2
        and sorted(t02[c] for c, _ in cells) == ["misses-ask", "too-long|misses-ask"]
        and sorted(t03[c] for c, _ in cells) == ["", "ok"],
        (r.stdout + r.stderr)[-300:] + str(fm) + str(t02) + str(t03),
    )
    r = evh(
        "sheet-import",
        str(filled),
        "--dataset-id",
        "tickets_v1",
        "--by",
        "owner",
        "--tags",
        "first",
        "--modes",
        "summaries",
    )
    check(
        "a tag set is never edited: the same name again is refused",
        r.returncode == 1 and "would-overwrite" in r.stderr,
        r.stderr[-200:],
    )
    bad = [list(x) for x in rows]
    bad[2][c1] = "invented"
    write(proj / "bad.csv", bad)
    shutil.copy(proj / "tags.key.json", proj / "bad.key.json")
    r = evh(
        "sheet-import",
        str(proj / "bad.csv"),
        "--dataset-id",
        "tickets_v1",
        "--by",
        "owner",
        "--tags",
        "second",
        "--modes",
        "summaries",
    )
    check(
        "a mode not in the list is refused",
        r.returncode == 1 and "name no mode of summaries" in r.stderr,
        r.stderr[-300:],
    )
    edited = [list(x) for x in rows]
    edited[2][head.index("output: " + cols[0].split(": ", 1)[1])] = (
        "an output edited after the sheet was written"
    )
    write(proj / "edited.csv", edited)
    shutil.copy(proj / "tags.key.json", proj / "edited.key.json")
    r = evh(
        "sheet-import",
        str(proj / "edited.csv"),
        "--dataset-id",
        "tickets_v1",
        "--by",
        "owner",
        "--tags",
        "third",
        "--modes",
        "summaries",
    )
    check(
        "an output edited since the sheet was written is refused (mismatch)",
        r.returncode == 1 and "ERROR (mismatch)" in r.stderr,
        r.stderr[-300:],
    )
    (data / "goals").mkdir()
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    r = evh("catalog", "--out", "cat")
    gp = proj / "cat" / "g" / "tickets_summary.html"
    html = gp.read_text() if gp.is_file() else ""
    check(
        "the goal page counts each tagged arm's failure modes on its dataset",
        r.returncode == 0
        and "failure modes" in html
        and "1 of 1 output(s) read have a failure: misses-ask 1" in html
        and "2 of 6 output(s) read have a failure: too-long 2, misses-ask 1" in html,
        (r.stdout + r.stderr)[-400:] + html[html.find("failure modes") - 200 :][:800],
    )
    r = evh("validate")
    v21 = [ln for ln in r.stdout.splitlines() if "V21" in ln]
    check(
        "validate V21: the list and the set agree",
        bool(v21) and v21[0].lstrip().startswith("ok"),
        "\n".join(v21) or r.stdout[-600:],
    )
    (data / "failure-modes" / "summaries.yaml").write_text(
        "failure_modes_id: summaries\nmodes:\n  - {id: misses-ask}\n"
    )
    r = evh("validate")
    check(
        "validate V21: a mode removed from the list after it was used fails, naming it",
        r.returncode != 0 and "too-long not a mode of summaries" in r.stdout,
        r.stdout[-600:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
