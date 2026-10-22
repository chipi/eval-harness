#!/usr/bin/env python3
"""Assertions for goals (ADR-0002): config -> run -> baseline, validate V14, the goal pages.

    python scripts/test_goals.py

In a throwaway project built from the tutorial ($0, offline): a config naming an unknown goal
is refused before it runs; a known one is recorded on the run and carried to the baseline with
its format; V14 fails a dangling goal, a format the goal does not accept, a goal_id that is not
its file name and, once policy.yaml sets required_from, a new run with no goal; the catalog
gets a page per goal that ranks only arms on the goal's datasets.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent / "tutorial"
ok: list = []


def check(label, cond, detail=""):
    ok.append((label, bool(cond)))
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  ({detail})" if detail and not cond else ""))


proj = Path(tempfile.mkdtemp(prefix="evh-goals-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-goals")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def validate():
    r = evh("validate")
    line = next((ln for ln in r.stdout.splitlines() if "V14" in ln and ("ok" in ln or "FAIL" in ln)), "")
    return r, line


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")  # sources live inside the project
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is created and materialized", r.returncode == 0, r.stderr[-300:])
    shutil.copytree(KIT / "gold", data / "references" / "gold" / "tickets_v1")
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")

    cfg = (KIT / "configs" / "tickets_lead2.yaml").read_text()
    (data / "configs" / "bad.yaml").write_text(cfg + "goal: no_such_goal\n")
    r = evh("experiment-run", "--config", str(data / "configs" / "bad.yaml"))
    check(
        "run: a config naming an unknown goal is refused before it runs",
        r.returncode != 0 and "no_such_goal" in (r.stdout + r.stderr) and not (data / "runs").exists(),
        (r.stdout + r.stderr)[-200:],
    )
    (data / "configs" / "bad.yaml").unlink()

    (data / "configs" / "lead2.yaml").write_text(cfg + "goal: tickets_summary\nformat: paragraph\n")
    r = evh("experiment-run", "--config", str(data / "configs" / "lead2.yaml"))
    runs = sorted((data / "runs").glob("*/metrics.json"))
    m = json.loads(runs[0].read_text()) if runs else {}
    check(
        "run: the goal and format are recorded on the run",
        m.get("goal") == "tickets_summary" and m.get("format") == "paragraph",
        r.stderr[-200:],
    )
    check(
        "run: neither is in the fingerprint (they change what it answers, not what was measured)",
        "tickets_summary" not in json.dumps(m.get("fingerprint", {})),
    )

    r = evh(
        "run-promote",
        "--run",
        m.get("run_id", "?"),
        "--reason",
        "lead2 answers the triage goal on six tickets",
    )
    b = (
        json.loads(next((data / "baselines").glob("*.json")).read_text())
        if (data / "baselines").is_dir()
        else {}
    )
    check(
        "promote: the baseline carries the goal and the format",
        b.get("goal") == "tickets_summary" and b.get("format") == "paragraph",
        (r.stdout + r.stderr)[-200:],
    )

    r, line = validate()
    check(
        "V14: passes with one goal named by a config, a run and a baseline",
        "ok" in line and "1 goal(s)" in line,
        line,
    )

    (data / "configs" / "lead2.yaml").write_text(cfg + "goal: tickets_summary\nformat: bullets\n")
    r, line = validate()
    check(
        "V14: fails a format the goal's output contract does not accept",
        "FAIL" in line and "bullets" in r.stdout,
        line,
    )
    (data / "configs" / "lead2.yaml").write_text(cfg + "goal: tickets_summray\n")
    r, line = validate()
    check(
        "V14: fails a config naming a goal that does not exist",
        "FAIL" in line and "tickets_summray" in r.stdout,
        line,
    )
    (data / "configs" / "lead2.yaml").write_text(cfg + "goal: tickets_summary\n")

    g = data / "goals" / "tickets_summary.yaml"
    shutil.copy(g, data / "goals" / "renamed.yaml")
    r, line = validate()
    check(
        "V14: fails a goal_id that is not its file name", "FAIL" in line and "renamed.yaml" in r.stdout, line
    )
    (data / "goals" / "renamed.yaml").unlink()

    (data / "goals" / "policy.yaml").write_text("required_from: 2000-01-01\n")
    m.pop("goal", None)
    runs[0].write_text(json.dumps(m))
    r, line = validate()
    check(
        "V14: with required_from set, a run created since then that names no goal fails",
        "FAIL" in line and "names no goal" in r.stdout,
        line,
    )
    (data / "goals" / "policy.yaml").write_text("required_from: 2999-01-01\n")
    r, line = validate()
    check("V14: a run created before required_from is not held to it", "ok" in line, line)
    (data / "goals" / "policy.yaml").unlink()
    m["goal"] = "tickets_summary"
    runs[0].write_text(json.dumps(m))

    r = evh("catalog")
    page = proj / ".build" / "catalog" / "g" / "tickets_summary.html"
    html = page.read_text() if page.is_file() else ""
    check("catalog: a page per goal", r.returncode == 0 and page.is_file(), r.stderr[-300:])
    check(
        "catalog: the goal page lists the arm, marked as filed under the goal",
        "tickets_lead2_v1" in html and "filed" in html,
    )
    check(
        "catalog: the goals index links it",
        "g/tickets_summary.html" in (proj / ".build/catalog/goals.html").read_text(),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

bad = [lb for lb, c in ok if not c]
print(f"\n{len(ok) - len(bad)}/{len(ok)} assertions passed")
if bad:
    print("FAILED:", *bad, sep="\n  ")
    sys.exit(1)
