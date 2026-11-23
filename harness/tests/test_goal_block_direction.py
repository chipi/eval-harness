#!/usr/bin/env python3
"""A goal that does not say which way its measure goes is read as every other reader reads it (RFC-041 F1).

  EVAL_STORE=files python tests/test_goal_block_direction.py        (and EVAL_STORE=sqlite)

`wer` on three arms, a goal whose primary is `{measure: wer}` with no `direction`: the table beside the goal's block
ranks `wer` lower (the name table), and the goal's block named the highest-`wer` arm its leader. Now the leaderboard's
goal block, `goal-leaderboard`, the goal's page, the goals table and the table all name the lowest-`wer` arm; a goal that
does say `higher` keeps its word (F1's precedence puts the goal first); and a source check lists every place that reads
a goal's own `direction` to rank by it.
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

proj = Path(tempfile.mkdtemp(prefix="evh-goal-block-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-goal-block", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    return SimpleNamespace(output=str(params["v"]), tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=None,
                           extra={}, meta={})

def score(output, reference):
    return {"wer": float(output)}
"""
ARMS = (("low", 0.1), ("mid", 0.3), ("high", 0.5))


def evh(*args):
    return _cli.run(proj, env, *args)


def result(r):
    return json.loads(r.stdout).get("result", {}) if r.returncode == 0 and r.stdout.strip() else {}


def write_goal(gid: str, primary: str, dataset: str) -> None:
    _runstore.write_text(
        proj,
        f"goals/{gid}.yaml",
        f'goal_id: {gid}\nschema_version: "0.1"\ntitle: {gid}\nstatement: {gid}\ndecision: {gid}\nstatus: active\n'
        f"datasets:\n  - dataset_id: {dataset}\nsuccess_criteria:\n  primary: {primary}\n",
    )


def leaders(goal: str, dataset: str, out: Path) -> dict:
    """The arm each reader names the leader of `goal` on `dataset`, by reader."""
    got: dict = {}
    g = result(evh("goal-leaderboard", goal, "--json"))
    grp: dict = next((x for d in g.get("datasets", []) for x in d["groups"] if d["dataset"] == dataset), {})
    got["goal-leaderboard"] = str(grp.get("leader", "")).rpartition("/")[2]
    got["goal-leaderboard direction"] = grp.get("direction")
    lb = result(evh("leaderboard", dataset, "--goal", goal, "--json"))
    first = (lb.get("values", {}).get("groups") or [{}])[0]
    got["leaderboard table"] = (first.get("arms") or [{}])[0].get("system_id")
    got["leaderboard goal block"] = str((first.get("decision") or {}).get("leader", "")).rpartition("/")[2]
    text = " ".join(ln for b in lb.get("blocks", []) for ln in b.get("lines", []))
    m = re.search(rf"goal {goal}: leader (\S+?),", text)
    got["leaderboard goal line"] = m.group(1) if m else None
    page = (out / "g" / f"{goal}.html").read_text() if (out / "g" / f"{goal}.html").exists() else ""
    m = re.search(r"Quality leader: (\S+)", re.sub(r"<[^>]+>|\s+", " ", page))
    got["goal page"] = m.group(1) if m else None
    return got


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "wer_adapter.py").write_text(ADAPTER)
    for name, v in ARMS:
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: wer_adapter.py\nparams:\n  v: {v}\n",
        )
    for ds in ("tickets_v1", "tickets_b_v1"):
        r = evh("dataset-create", "--dataset-id", ds, "--source-dir", "tutorial/tickets")
        r = r if r.returncode else evh("dataset-materialize", "--dataset-id", ds)
        for name, _v in ARMS:
            r = (
                r
                if r.returncode
                else evh("run", "--system", f"{name}_v1", "--dataset", ds, "--run-id", f"{name}_{ds}")
            )
        check(f"setup: three arms on {ds}", r.returncode == 0, r.stderr[-300:])
    write_goal("g_open", "{measure: wer}", "tickets_v1")
    write_goal("g_higher", "{measure: wer, direction: higher}", "tickets_b_v1")
    out = proj / "catalog"
    r = evh("catalog", "--out", out)
    check("setup: the catalog builds", r.returncode == 0, r.stderr[-300:])

    got = leaders("g_open", "tickets_v1", out)
    readers = {k: v for k, v in got.items() if not k.endswith("direction")}
    check(
        "a goal with no direction on wer: every reader names the lowest-wer arm the leader",
        set(readers.values()) == {"low_v1"},
        readers,
    )
    check(
        "a goal with no direction on wer: goal-leaderboard says lower is better",
        got["goal-leaderboard direction"] == "lower",
        got["goal-leaderboard direction"],
    )
    glance = (out / "goals.html").read_text() if (out / "goals.html").exists() else ""
    row = glance[glance.find("g_open") :]
    row = row[: row.find("</tr>")]
    check(
        "a goal with no direction on wer: the goals table names low_v1 the leader",
        "low_v1" in row and "high_v1" not in row,
        re.sub(r"<[^>]+>", " ", row)[:300],
    )

    kept = leaders("g_higher", "tickets_b_v1", out)
    check(
        "a goal that says higher keeps it: the goal's block and page name the highest-wer arm",
        kept["goal-leaderboard"] == "high_v1"
        and kept["leaderboard goal block"] == "high_v1"
        and kept["goal page"] == "high_v1"
        and kept["goal-leaderboard direction"] == "higher",
        kept,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# -- the source: a goal's own `direction` ranks nothing but where it is listed -----------------------------------------
#: Each place that reads `direction` out of a goal's primary (or a decision's axis) and compares it with "lower". A goal's
#: block takes its direction from `_runs.direction` (`goal_views.lower_on`, `axes.axes_of`'s `direction_of`); these read the
#: goal's declaration for another reason, or a direction that was already decided.
READS = {
    ("_study.py", "decide"),  # a study's own trial: the direction stats.compare gave
    (
        "_study.py",
        "trial",
    ),  # a study's own `direction`, added to the rule's answer (`lower_is_better` or ...)
    ("_study.py", "weakest"),  # the same
    ("_study_cmd.py", "_confirm"),  # the same
    ("axes.py", "within"),  # an axis of a decision: already decided (`axes_of` asked `direction_of` for it)
    ("axes.py", "decide"),  # the same
    ("axes.py", "test"),  # the same
    ("axes.py", "shared"),  # the same
    ("axes.py", "axis_title"),  # the same
    ("catalog_build.py", "tradeoff_charts"),  # an axis of a decision: already decided
    ("charts.py", "intervals"),  # a group of the leaderboard: already decided
    ("charts.py", "items"),  # a group of the leaderboard: already decided
    ("charts.py", "ms_lower"),  # a study's own `direction`, added to the rule's answer
    ("model/goal_views.py", "baseline_gap"),  # a decision's axis: already decided
    (
        "promote_baseline.py",
        "evidence",
    ),  # passes the goal's declaration on to the pair test; none leaves it to the rule
}
PATTERN = re.compile(r"""(\.get\("direction"\)|\["direction"\])\s*(==|!=)\s*"(lower|higher)\"""")


def reads(src: str) -> list[tuple[str, int]]:
    out = []
    defs: list[tuple[int, str]] = []
    for n, line in enumerate(src.splitlines(), 1):
        m = re.match(r"(\s*)def (\w+)", line)
        if m:
            while defs and defs[-1][0] >= len(m.group(1)):
                defs.pop()
            defs.append((len(m.group(1)), m.group(2)))
        if PATTERN.search(line):
            out.append((defs[-1][1] if defs else "", n))
    return out


unlisted = []
for f in sorted((HARNESS / "scripts").rglob("*.py")):
    rel = f.relative_to(HARNESS / "scripts").as_posix()
    if rel.startswith("catalog_assets"):
        continue
    for fn, n in reads(f.read_text()):
        if (rel, fn) not in READS:
            unlisted.append(f"{rel}:{n} in {fn or 'module'}")
check(
    "source: a direction read out of a goal or a decision and compared with lower/higher only where listed",
    not unlisted,
    unlisted,
)

sys.exit(summary())
