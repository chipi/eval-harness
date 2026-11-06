#!/usr/bin/env python3
"""What a scoring change would move, before anything is written (RFC-022).

    evh score-preview --goal <goal_id> [--round rN] [--json]

Re-scores, in a temporary directory, every measured run the goal reads (or the round's arms), with the scorer in
this tree, and prints per arm its deciding measure as the goal reads it now and as it would read it, whether it is
still within the goal's limits, and then the decision before and after: the quality leader, how many contenders
with it, the recommendation. Nothing is written to the project and nothing is spent: the tool for developing a
scoring. Then `evh rescore --goal G --round rN --why "..."` applies it to a round, or `evh round-open --from rN
--scoring "..."` adopts it from the next one.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextlib
import io
import sys
import tempfile
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _jsonout, _rounds, _store
from evaluation_harness import catalog_build as cb
from evaluation_harness import rescore as rs
from evaluation_harness._common import die, load_goals
from evaluation_harness.catalog_adapter import HarnessAdapter, load_catalog_adapter


def decisions(A, goal: dict) -> dict[str, dict[str, Any]]:
    """{dataset: {"rows": {config_id: {"arm", "label", "mean", "out"}}, "leader", "contenders", "recommended"}}: the
    goal's decision on each dataset's gold group (else its first group), as `evh goals` reads it."""
    by_ds = cb.collect(A)
    retired_in = cb.retired_in_of(A, goal)
    out: dict[str, dict[str, Any]] = {}
    for ans in cb.goal_answers(goal, by_ds):
        ds = ans["dataset"]
        if not ans["groups"]:
            continue
        tiers = {r["id"]: r["tier"] for r in (by_ds.get(ds) or {}).get("refs", [])}
        grp = next((g for g in ans["groups"] if g["key"].startswith("gold/")), ans["groups"][0])
        gm = (grp["rows"][0].get("measure") if grp["rows"] else None) or ""
        dec = cb.group_decision(
            A,
            goal,
            ds,
            grp["rows"],
            gm,
            retired_in,
            cb.gold_beside(tiers, ans["groups"], grp["key"]),
        )
        rows = {}
        for r in grp["rows"]:
            key = r["arm"].rsplit("/", 1)[-1] + _set_of(r["arm"])
            rows[key] = {
                "arm": r["arm"],
                "label": r["label"],
                "mean": r["mean"],
                "out": dec["out"].get(r["arm"], []),
            }
        label = {r["arm"]: r["arm"].rsplit("/", 1)[-1] + _set_of(r["arm"]) for r in grp["rows"]}
        out[ds] = {
            "measure": gm,
            "rows": rows,
            "leader": label.get(dec.get("leader") or "", ""),
            # the contenders beside the leader, as `evh goals` counts them: the leader is not one of them
            "contenders": sorted(
                label.get(a, a) for a in dec.get("contenders") or [] if a != dec.get("leader")
            ),
            "recommended": label.get(dec.get("recommended") or "", ""),
        }
    return out


def _set_of(arm: str) -> str:
    """ " (repeats)" for an arm read from a repeat set, so a config's first pass and its later ones stay apart."""
    return " (repeats)" if "repeats" in arm.rsplit("/", 2)[0] else ""


def main() -> int:
    """Print what the scorer in this tree would change in a goal's decision; write nothing."""
    argv, as_json = _jsonout.take_flag(sys.argv[1:])
    ap = argparse.ArgumentParser(prog="evh score-preview", description=__doc__.splitlines()[0])
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", dest="round_id", help="only this round's arms (its own and those it carried)")
    args = ap.parse_args(argv)
    goal = load_goals().get(args.goal)
    if goal is None:
        die(f"no goal {args.goal!r}", "not-found")
    datasets = [d["dataset_id"] for d in goal.get("datasets") or [] if d.get("dataset_id")]
    configs = None
    if args.round_id:
        rnd = _rounds.find(args.goal, args.round_id)
        if rnd is None:
            die(f"no round {args.round_id} of {args.goal}", "not-found")
        datasets, configs = [rnd["dataset_id"]], set(_rounds.arms_of(rnd))
    before = decisions(load_catalog_adapter(None), goal)
    with tempfile.TemporaryDirectory(prefix="evh-score-preview-") as tmp:
        root = Path(tmp)
        adapters: dict = {}
        n = 0
        per_ds: dict[str, int] = {}
        with contextlib.redirect_stdout(io.StringIO()):
            for ds in datasets:
                per_ds[ds] = 0
                for d, m in rs.measured_runs(ds, configs):
                    try:
                        rel = d.parent.resolve().relative_to(_common.DATA.resolve()).as_posix()
                    except ValueError:
                        rel = d.parent.name
                    if rs.rescore_one(d, m, out_dir=root / rel, adapters=adapters, quiet=True):
                        n += 1
                        per_ds[ds] += 1
        after = decisions(HarnessAdapter(runs_root=root), goal)
        scorer = next((rs.current_scorer({"adapter": k}, adapters) for k in adapters), "")
    if as_json:
        with _jsonout.collect("score-preview"):
            _print(args.goal, scorer, n, before, after, per_ds)
        return 0
    _print(args.goal, scorer, n, before, after, per_ds)
    return 0


def _derived_on(dataset_id: str) -> int:
    """How many re-scored (derived) runs on the dataset the goal can read: what score-preview leaves alone."""
    n = 0
    bases = [b for b in sorted(_common.DATA.glob("runs*")) if b.name != rs.RESCORED]
    bases += sorted(_store.glob(_common.DATA / rs.RESCORED, "*/*"))
    for base in bases:
        if _store.is_dir(base) and not _common.ignored_by_git(base):
            n += sum(1 for _d, m in rs.runs_on(dataset_id, runs_dir=base) if m.get("derived"))
    return n


def _print(goal: str, scorer: str, n: int, before: dict, after: dict, per_ds: dict[str, int]) -> None:
    from evaluation_harness.catalog_views import _fmt, _table  # noqa: PLC0415

    print(
        f"score-preview: {goal}, {n} run(s) re-scored in a temporary directory by {scorer}; nothing written\n"
        if n
        else f"score-preview: {goal}, no measured run to re-score; nothing written\n"
    )
    for ds in sorted(set(before) | set(after)):
        if per_ds.get(ds) == 0:
            print(
                f"{ds}: no measured runs to re-score here, so nothing was compared. The {_derived_on(ds)} run(s) "
                "this goal reads are themselves re-scores, and a re-score is not re-scored again by a preview.\n"
                f"  To check them against the scorer in this tree: evh rescore --dataset-id {ds} --out <a directory of "
                "your own>, then evh leaderboard --dataset-id "
                f"{ds} with EVAL_RUNS_DIR=<that directory>.\n"
            )
            continue
        b, a = before.get(ds) or {"rows": {}}, after.get(ds) or {"rows": {}}
        measure = a.get("measure") or b.get("measure") or ""
        print(f"{ds}  ({measure}, now -> with this scorer)")
        keys = sorted(set(b["rows"]) | set(a["rows"]))
        rows = []
        for k in keys:
            rb, ra = b["rows"].get(k) or {}, a["rows"].get(k) or {}
            mb, ma = rb.get("mean"), ra.get("mean")
            delta = "—" if mb is None or ma is None else f"{ma - mb:+.4f}"
            inb, ina = (
                ("out" if rb.get("out") else "in") if rb else "—",
                ("out" if ra.get("out") else "in") if ra else "—",
            )
            rows.append([k, _fmt(mb), _fmt(ma), delta, f"{inb} -> {ina}" if inb != ina else ina])
        _table(["arm", "now", "after", "moved", "limits"], rows)
        for what in ("leader", "recommended"):
            x, y = b.get(what) or "—", a.get(what) or "—"
            print(f"  {what:12} {x}" + ("" if x == y else f" -> {y}"))
        tb, ta = len(b.get("contenders") or []), len(a.get("contenders") or [])
        print(
            f"  {'contenders':12} {tb} arm(s) not significantly different from the leader"
            + ("" if tb == ta else f" -> {ta}")
        )
        print()
    if not n:
        return
    print(
        'Apply it: evh rescore --goal G --round rN --why "..." (re-score a round), or evh round-open --from rN '
        '--scoring "..." (adopt it from the next round).'
    )


if __name__ == "__main__":
    raise SystemExit(main())
