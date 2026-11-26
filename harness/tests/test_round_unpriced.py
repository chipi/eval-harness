#!/usr/bin/env python3
"""A round with a budget does not run an arm whose price is unknown, unless a person says it may (--allow-unpriced).

    python tests/test_round_unpriced.py

In a throwaway project, $0 and offline: `evh run` and `evh arm-smoke` of an arm in a budgeted round whose system
declares no usd_per_mtok_in / usd_per_mtok_out are refused before a call, naming the arm, its model and where the price
goes; the arm runs through a project's own adapter (one that passes to the bundled echo), because a project adapter's
provider says nothing of what it spends. A bundled provider that makes no paid call (echo) costs nothing, priced or not
(tutorial 4's round r2 runs one). A declared price of 0 is a price; a round without a budget never asks;
--allow-unpriced lets the arm through and the round records that it did, so round-show and round-evidence say its
budget leaves the arm out.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

KIT = HARNESS / "tutorial"
proj = Path(tempfile.mkdtemp(prefix="evh-unpriced-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-unpriced")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_SPENT_TO"):
    env.pop(k, None)
GOAL = "tickets_summary"


def evh(*args):
    return _cli.run(proj, env, *args)


def system(system_id: str, adapter: str | None = None, **params) -> list[str]:
    body = "".join(f"\n  {k}: {v}" for k, v in params.items())
    head = f"system_id: {system_id}\n" + (f"adapter: {adapter}\n" if adapter else "")
    _runstore.write_text(proj, f"systems/{system_id}.yaml", f"{head}params:\n  provider: echo{body}\n")
    return ["--system", system_id, "--dataset", "tickets_v1", "--goal", GOAL, "--round", "r1"]


def runs_of(prefix: str) -> list[str]:
    return [n for n in _runstore.listdir(proj, "runs") if n.startswith(prefix)]


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "data" / "systems").mkdir(parents=True, exist_ok=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    _runstore.write_text(
        proj, f"goals/{GOAL}.yaml", (KIT / "goals" / f"{GOAL}.yaml").read_text(encoding="utf-8")
    )
    r = r if r.returncode else evh("round-open", "--goal", GOAL, "--dataset", "tickets_v1",
                                   "--hypothesis", "unpriced arms", "--budget-usd", "1")  # fmt: skip
    check(
        "setup: a dataset, the goal and round r1 with a $1 budget",
        r.returncode == 0,
        (r.stdout + r.stderr)[-400:],
    )

    # A project's own adapter: it passes to the bundled echo, but a project adapter's provider proves nothing of cost.
    (proj / "own_adapter.py").write_text(
        '"""Passes to the bundled adapter."""\n\nfrom evaluation_harness.adapter import call_system, score  # noqa: F401\n',
        encoding="utf-8",
    )
    up = system("up_v1", adapter="own_adapter.py", model="tiny-1b")
    r = evh("run", *up)
    err = r.stderr
    check(
        "run: an arm with no price in a round with a budget is refused (not-configured), before any run is written",
        r.returncode != 0
        and "ERROR (not-configured)" in err
        and not runs_of("up_v1")
        and not (proj / ".build" / "rounds" / GOAL / "r1.json").exists(),
        (r.returncode, err[-500:]),
    )
    check(
        "run: the refusal names the arm and its model, says what the budget cannot count, and where the price goes",
        "up_v1" in err
        and "tiny-1b" in err
        and "r1" in err
        and "usd_per_mtok_in" in err
        and "usd_per_mtok_out" in err
        and "0 is a price" in err
        and "--allow-unpriced" in err,
        err[-600:],
    )

    r = evh("run", *up, "--dry-run")
    check(
        "dry run: an unpriced arm in a budgeted round is costed, not refused",
        r.returncode == 0,
        r.stderr[-400:],
    )

    r = evh("arm-smoke", *up)
    check(
        "arm-smoke: refused the same way, before a call",
        r.returncode != 0 and "ERROR (not-configured)" in r.stderr and "--allow-unpriced" in r.stderr,
        (r.returncode, (r.stdout + r.stderr)[-500:]),
    )

    r = evh("run", *up, "--allow-unpriced")
    check(
        "run --allow-unpriced: the arm runs",
        r.returncode == 0 and len(runs_of("up_v1")) == 1,
        (r.returncode, (r.stdout + r.stderr)[-500:]),
    )
    shown = evh("round-show", GOAL, "r1", "--json")
    doc = json.loads(shown.stdout)["result"] if shown.returncode == 0 else {}
    allowed = (doc.get("round") or {}).get("unpriced_allowed") or []
    check(
        "the round records that the arm was let through unpriced: round-show has it, with the model and who",
        len(allowed) == 1
        and allowed[0].get("system") == "up_v1"
        and allowed[0].get("model") == "tiny-1b"
        and (allowed[0].get("actor") or {}).get("name") == "test",
        (shown.returncode, shown.stdout[:200], shown.stderr[-300:]),
    )
    said = evh("round-show", GOAL, "r1")
    check(
        "round-show (text): says the budget excludes the unpriced arm",
        "budget excludes up_v1 (model tiny-1b)" in said.stdout,
        said.stdout[-600:],
    )
    ev = evh("round-evidence", GOAL, "r1")
    check(
        "round-evidence: the budget line says it leaves the unpriced arm out",
        "up_v1" in ev.stdout and "not counted" in ev.stdout and "--allow-unpriced" in ev.stdout,
        ev.stdout[-700:] + ev.stderr[-300:],
    )

    echo = system("echo_v1", model="tiny-1b")
    r = evh("run", *echo)
    check(
        "run: the bundled echo provider costs nothing, so a budgeted round runs it with no price declared",
        r.returncode == 0 and len(runs_of("echo_v1")) == 1,
        (r.returncode, (r.stdout + r.stderr)[-500:]),
    )

    free = system("free_v1", model="local-1b", usd_per_mtok_in=0, usd_per_mtok_out=0)
    r = evh("run", *free)
    check(
        "run: a declared price of 0 is a price: the arm runs without the flag",
        r.returncode == 0 and len(runs_of("free_v1")) == 1,
        (r.returncode, (r.stdout + r.stderr)[-500:]),
    )

    r = evh(
        "round-close",
        "--goal",
        GOAL,
        "--round",
        "r1",
        "--conclusion",
        "the unpriced arm needed the flag and the free one did not.",
    )
    r = r if r.returncode else evh("round-open", "--goal", GOAL, "--dataset", "tickets_v1", "--from", "r1",
                                   "--hypothesis", "no budget")  # fmt: skip
    check("setup: round r2 with no budget", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    nb = system("nb_v1", adapter="own_adapter.py", model="tiny-1b")
    nb[-1] = "r2"
    r = evh("run", *nb)
    check(
        "run: a round without a budget never asks about a price",
        r.returncode == 0 and len(runs_of("nb_v1")) == 1,
        (r.returncode, (r.stdout + r.stderr)[-400:]),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
