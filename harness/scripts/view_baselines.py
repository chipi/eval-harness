#!/usr/bin/env python3
"""The baselines: each goal's on each dataset, and each dataset's own, with their evidence and history (RFC-027 D4).

    evh baselines
    evh baselines --goal triage_orrery --all-versions
    evh baselines --json > registry/baselines.json

Per line (a goal on a dataset, or a dataset's own): the current version, who promoted it and why, the comparison
that justified it (frozen at promotion), how to reproduce it (the `deploy-sheet` block of its run) and, with
`--all-versions`, every version. `--json` is the export a production system reads: sorted, with no timestamp or
harness version of its own, so two exports with no new promotion are the same bytes.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from typing import Any

from evaluation_harness import _baselines
from evaluation_harness._common import BOOKKEEPING_PREFIXES, load_goals

SCHEMA = "evh-baselines/1"


def _reproduce(run_id: str) -> dict[str, Any] | None:
    """How to reproduce the baseline: the deploy sheet of its run (one definition), less what it says of promotion."""
    from evaluation_harness.deploy_sheet import sheet  # noqa: PLC0415
    from evaluation_harness.promote_baseline import run_record  # noqa: PLC0415

    rec = run_record(run_id)
    if rec is None:
        return None
    try:
        s = sheet(str(rec.get("system_id")))
    except SystemExit:  # the sheet refused (its run unreadable): the baseline still lists, without it
        return None
    if (
        s.get("run_id") != run_id
    ):  # the arm's sheet names another of its runs: describe this one by its record
        return {"run_id": run_id, "system_id": rec.get("system_id")}
    return {k: v for k, v in s.items() if k != "promoted"}


def _scores(v: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
    """The scores the baseline is read by, and how many repeats they are the mean of: an arm run with --repeat is
    read as the mean over its repeats everywhere else, so here too (the run's own scores stay in the record)."""
    rep = v.get("repeats") or {}
    sc = rep.get("mean_scores") or v.get("scores") or {}
    shown = {k: x for k, x in sorted(sc.items()) if not k.startswith(BOOKKEEPING_PREFIXES)}
    return shown, (len(rep.get("runs") or []) or None) if rep.get("mean_scores") else None


def _entry(v: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "version",
        "promoted_from",
        "promoted_at",
        "actor",
        "reason",
        "replaces",
        "restores",
        "evidence",
        "migrated",
    )
    return {k: v.get(k) for k in keep if v.get(k) is not None}


def lines(goal: str | None, no_goal: bool, dataset: str | None, all_versions: bool) -> list[dict[str, Any]]:
    """Every selected line with its current version, how to reproduce it and its history."""
    goals = load_goals()
    out = []
    for g, ds in _baselines.lines():
        if (goal and g != goal) or (no_goal and g is not None) or (dataset and ds != dataset):
            continue
        vs = _baselines.versions(g, ds)
        cur = vs[-1]
        gdoc = goals.get(g or "") or {}
        out.append(
            {
                "goal": g,
                "dataset": ds,
                "current": cur["version"],
                **_entry(cur),
                "scores": _scores(cur)[0],
                "repeats": _scores(cur)[1],
                "reference_tier": cur.get("reference_tier"),
                "reproduce": _reproduce(str(cur.get("promoted_from"))),
                "intended_use": {"context": gdoc.get("context"), "decision": gdoc.get("decision")}
                if gdoc
                else None,
                "history": [_entry(v) for v in (vs if all_versions else vs[:-1])],
            }
        )
    return out
