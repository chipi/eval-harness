#!/usr/bin/env python3
"""A goal whose primary measure is prose (no run records it) does not stop a dataset from being read (RFC-041 F1: V14
warns about such a goal; this is what the readers do meanwhile).

    EVAL_STORE=files python tests/test_leaderboard_prose_measure.py
    EVAL_STORE=sqlite python tests/test_leaderboard_prose_measure.py

In a throwaway project ($0, offline: a stand-in adapter, three arms that record `wer`) whose goal reads
"WER vs human transcript (ascii-v1)", as the podcast project's goals do:

- `evh leaderboard <dataset>` read the dataset on that goal, found no arm that records the measure and refused:
  a whole project of imported runs could rank no dataset. It now says so in one NOTE line first (the measure, what the
  arms do record, that `evh validate` warns about it) and ranks the arms on their own headline, `wer`, lower first
  (the name table); the note is in --json too;
- with `--goal G` it still refuses, and says what the arms record and how to read the dataset without the goal;
- the goal's own page and `evh goal-leaderboard` (one table per dataset the goal decides on) say why the table is
  empty instead of leaving it blank;
- a dataset with a goal whose measure IS recorded is read as before: no note.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-prose-measure-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-prose", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

PROSE = "WER vs human transcript (ascii-v1)"
ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    return SimpleNamespace(output=str(params["v"]), tokens_in=10, tokens_out=5, cost_usd=0.0, latency_ms=None,
                           extra={}, meta={})

def score(output, reference):
    return {"wer": float(output)}

PRIMARY_METRIC = "wer"
"""
#: the arms by wer, lower first: the order the table must have
WER = {"a": 0.1, "c": 0.2, "b": 0.3}


def evh(*args):
    return _cli.run(proj, env, *args)


def goal(gid: str, measure: str, datasets: list[str], direction: str = "") -> None:
    ds = "".join(f"  - dataset_id: {d}\n" for d in datasets)
    _runstore.write_text(
        proj,
        f"goals/{gid}.yaml",
        f'goal_id: {gid}\nschema_version: "0.1"\ntitle: {gid}\nstatement: {gid}\ndecision: {gid}\nstatus: active\n'
        f"datasets:\n{ds}success_criteria:\n  primary: {{measure: {json.dumps(measure)}{', direction: ' + direction if direction else ''}}}\n",
    )


def order(text: str) -> list[str]:
    """The arms in the order their rows appear."""
    seen = [(m.start(), m.group(1)) for m in re.finditer(r"^\s*([abc])_v1\b", text, re.MULTILINE)]
    return [s for _, s in sorted(seen)]


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
    src = proj / "tutorial" / "items"
    src.mkdir(parents=True)
    for n in range(6):
        (src / f"t{n:02d}.txt").write_text(f"item {n}\n")
    (proj / "prose_adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "prose_v1", "--source-dir", "tutorial/items")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "prose_v1")
    check("setup: a frozen dataset", r.returncode == 0, r.stderr[-300:])
    for name, v in WER.items():
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: prose_adapter.py\nparams:\n  v: {v}\n",
        )
        r = evh("run", "--system", f"{name}_v1", "--dataset", "prose_v1", "--run-id", name)
        check(f"setup: the run {name} (wer {v})", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    goal("g_prose", PROSE, ["prose_v1"])

    # -- evh leaderboard <dataset>: the goal's measure is recorded by no arm -----------------------------------------
    r = evh("leaderboard", "prose_v1")
    text = r.stdout
    lines = text.splitlines()
    notes = [ln for ln in lines if "NOTE" in ln]
    check("leaderboard: exits 0 (it refused)", r.returncode == 0, (r.stdout + r.stderr)[-500:])
    check(
        "leaderboard: one NOTE, before the table, names the goal, its measure, what the arms record and V14",
        len(notes) == 1
        and lines.index(notes[0])
        < min((i for i, ln in enumerate(lines) if re.match(r"\s*[abc]_v1\b", ln)), default=0)
        and "g_prose" in text
        and PROSE in notes[0]
        and "wer" in notes[0]
        and "V14" in text
        and "validate" in text,
        notes,
    )
    check("leaderboard: ranked on wer, lower first", order(text)[:3] == ["a", "c", "b"], order(text))
    r = evh("leaderboard", "prose_v1", "--json")
    res = json.loads(r.stdout).get("result", {}) if r.returncode == 0 and r.stdout.strip() else {}
    note = (res.get("values") or {}).get("note") or ""
    check(
        "leaderboard --json: exits 0 and carries the note, no goal",
        r.returncode == 0
        and PROSE in note
        and "V14" in note
        and (res.get("values") or {}).get("goal") is None,
        (r.stdout + r.stderr)[-500:],
    )
    rows = [x.get("system_id") for b in res.get("blocks", []) for x in b.get("rows", [])]
    check(
        "leaderboard --json: the rows are ranked on wer, lower first",
        rows[:3] == ["a_v1", "c_v1", "b_v1"],
        rows,
    )

    # -- --goal G keeps the refusal, and says more -----------------------------------------------------------------
    r = evh("leaderboard", "prose_v1", "--goal", "g_prose")
    err = r.stdout + r.stderr
    check(
        "--goal: still refuses (not-found), naming the measure, what the arms record and how to read without the goal",
        r.returncode != 0
        and "not-found" in err
        and PROSE in err
        and "which goal g_prose reads" in err
        and "wer" in err
        and "evh leaderboard prose_v1" in err
        and "--goal" in err,
        err[-500:],
    )

    # -- the goal's own readers say why its table is empty ---------------------------------------------------------
    r = evh("goal-leaderboard", "g_prose", "--json")
    res = json.loads(r.stdout).get("result", {}) if r.returncode == 0 and r.stdout.strip() else {}
    dnotes = " ".join(d.get("notes", "") for d in res.get("datasets", []))
    check(
        "goal-leaderboard --json: the dataset's notes say the measure is recorded by no arm, what they record, V14",
        r.returncode == 0 and PROSE in dnotes and "wer" in dnotes and "V14" in dnotes,
        dnotes or (r.stdout + r.stderr)[-400:],
    )
    r = evh("goal-leaderboard", "g_prose")
    check("goal-leaderboard: the text says so too", r.returncode == 0 and "V14" in r.stdout, r.stdout[-500:])
    out = proj / "catalog"
    r = evh("catalog", "--out", out)
    pages = {p.name: p.read_text() for p in out.rglob("*.html")} if r.returncode == 0 else {}
    goal_page = next((t for n, t in pages.items() if "g_prose" in n), "")
    check(
        "catalog: builds, and the goal's page says why it has no table",
        r.returncode == 0 and "V14" in goal_page and "wer" in goal_page,
        (r.stdout + r.stderr)[-400:],
    )
    r = evh("pair-test", "prose_v1", "--a", "a_v1", "--b", "b_v1")
    check(
        "pair-test with no --metric reads the runs' own (wer), not the goal's prose",
        r.returncode == 0 and "wer" in r.stdout,
        (r.stdout + r.stderr)[-400:],
    )

    # -- a goal whose measure is recorded is read as before -------------------------------------------------------
    goal("g_prose", "wer", ["prose_v1"], "lower")
    r = evh("leaderboard", "prose_v1")
    check(
        "a recorded measure: no note, the same ranking",
        r.returncode == 0
        and PROSE not in r.stdout
        and "V14" not in r.stdout
        and order(r.stdout)[:3] == ["a", "c", "b"],
        r.stdout[:900] + r.stderr[-300:],
    )
    r = evh("leaderboard", "prose_v1", "--goal", "g_prose")
    check(
        "a recorded measure: --goal reads it",
        r.returncode == 0 and order(r.stdout)[:3] == ["a", "c", "b"],
        r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

summary()
