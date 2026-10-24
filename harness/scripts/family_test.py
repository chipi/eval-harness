#!/usr/bin/env python3
"""One arm against a declared family of opponents, Holm step-down over the whole family.

    python scripts/family_test.py --dataset-id cnn_dailymail_200 \
        --a cnn_bart_l_n200_v1 --against _n200_v1 --metric coverage

WHY THIS AND NOT k(k-1)/2
  `leaderboard.py --significance` asks "which of all 325 pairs differ?" and pays Nemenyi's
  multiplicity price for every one of them. That is the right price for that question. But
  "how does the local model compare to the hosted field?" is 25 comparisons, not 325, and
  correcting for 300 nobody made throws away the power to answer the one that was asked.

  `pair_test.py` handles ONE pre-registered pair and applies Bonferroni (alpha/m) because a
  single pair cannot do better: Holm's step-down needs every p-value in the family at once.
  This script has them all, so it runs the real thing.

HOLM, AND WHY IT IS STRICTLY BETTER THAN BONFERRONI HERE
  Sort the family's p-values ascending. Compare the smallest to alpha/m, the next to
  alpha/(m-1), ... the largest to alpha/1. Stop at the first failure; everything from there
  down is not-separated. Every step after the first is LOOSER than Bonferroni's alpha/m, so
  Holm rejects at least everything Bonferroni does and sometimes more, with the same
  family-wise error guarantee. Nothing is traded away for it.

THE HONESTY CONDITION
  The family is declared by `--against`, before the p-values are read, and printed in the
  output. A family assembled after seeing which opponents looked beatable is a search
  wearing a test's clothes, and no correction repairs that.

  `--items` restricts every comparison to the same stratum -- see pair_test.py for why the
  BART truncation split needs it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextlib
import hashlib
import io
import json
import os
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

from evaluation_harness._common import (  # noqa: E402
    GOALS,
    ROOT,
    ROUNDS,
    RUNS,
    dataset_item_ids,
    die,
    item_selection,
)
from evaluation_harness._fingerprint import measuring_modules  # noqa: E402
from evaluation_harness._runs import default_metric, direction, per_item, runs_on, warn_on_ambiguous_runs  # noqa: E402  # noqa: E402 -- one implementation of "score per item"
from evaluation_harness.stats import EXACT_UP_TO, fmt_p, holm, sign_flip_p  # noqa: E402 -- one implementation of the paired test


def _opponents(runs: list, against: str, exclude: str) -> list[str]:
    return sorted(
        {m["config_id"] for _d, m in runs if m["config_id"] != exclude and against in m["config_id"]}
    )


# Under the PROJECT, not beside the code: installed, the code sits in site-packages.
CACHE = ROOT / ".cache" / "family_test"


def _cache_key(argv: list[str], runs_dir: Path, args) -> str:
    """Everything the answer depends on: this script and every module it imports (read from
    the source, as the run code hash is: a hand-kept list missed an import added later), the exact
    arguments, the bytes of every run of this dataset (metrics.json + predictions.jsonl),
    the project's goals (a goal sets a metric's direction, so it moves the wins and "ahead"
    counts), and any --items / --exclude-dataset input. Change any of them and the key
    changes, so a hit is the same computation, already done -- the test is seeded and
    deterministic."""
    h = hashlib.sha256()
    for f in measuring_modules(Path(__file__).resolve().parent, ("family_test.py",)):
        h.update(f.name.encode() + b"\0" + f.read_bytes())
    h.update("\0".join([*argv, str(runs_dir.resolve())]).encode())
    for d, _m in runs_on(args.dataset_id, runs_dir=runs_dir):
        mj, pj = d / "metrics.json", d / "predictions.jsonl"
        h.update(d.name.encode() + mj.read_bytes() + (pj.read_bytes() if pj.is_file() else b""))
    for g in sorted(GOALS.glob("*.yaml")) if GOALS.is_dir() else []:
        h.update(g.name.encode() + b"\0" + g.read_bytes())
    # A round's record decides which arms --round keeps (its retirements, its carried arms).
    for r in sorted(ROUNDS.glob("*/*.yaml")) if ROUNDS.is_dir() else []:
        h.update(r.as_posix().encode() + b"\0" + r.read_bytes())
    if args.items:
        h.update(args.items.read_bytes())
    if args.exclude_dataset:
        h.update("\0".join(sorted(dataset_item_ids(args.exclude_dataset))).encode())
    return h.hexdigest()


def main() -> int:
    """Run the family test, or replay its output when the exact same test has already run.

    Each run is ~20,000 seeded permutations per opponent in pure Python (~18 s for a family
    of 29), and the report checker, the self-test (which re-runs the checker once per
    planted defect) and the site build ask the same questions dozens of times per `make
    ci`. EVAL_NO_CACHE=1 forces a recomputation."""
    args = _parser().parse_args()
    runs_dir = args.runs_dir or RUNS
    use_cache = not os.environ.get("EVAL_NO_CACHE") and runs_dir.is_dir()
    if use_cache:
        hit = CACHE / f"{_cache_key(sys.argv[1:], runs_dir, args)}.json"
        if hit.is_file():
            c = json.loads(hit.read_text(encoding="utf-8"))
            sys.stdout.write(c["stdout"])
            sys.stderr.write(c["stderr"])
            return c["rc"]
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = _run(args)
    sys.stdout.write(out.getvalue())
    sys.stderr.write(err.getvalue())
    if use_cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = hit.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"stdout": out.getvalue(), "stderr": err.getvalue(), "rc": rc}), encoding="utf-8"
        )
        tmp.replace(hit)  # atomic: a concurrent reader never sees half a file
    return rc


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", required=True, help="config_id of the arm under test")
    ap.add_argument(
        "--against", required=True, help="substring selecting the opponent family, declared in advance"
    )
    ap.add_argument("--metric", help="default: the primary metric the runs recorded")
    ap.add_argument("--runs-dir", type=Path, default=None, help="default: EVAL_RUNS_DIR, else data/runs")
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument("--items", type=Path, help="file of item_ids; restrict to exactly these")
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument(
        "--asc",
        action="store_true",
        help="lower is better: wins and 'ahead' count the lower score "
        "(default: inferred from the metric and the runs)",
    )
    ap.add_argument("--desc", action="store_true", help="higher is better, whatever the runs declare")
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--round", help="only opponents in play in this round of a goal (rN; ADR-0004)")
    ap.add_argument("--goal", help="the goal --round belongs to, when several goals have one")
    return ap


def _run(args) -> int:
    # The directory read is the directory warned about: --runs-dir, else EVAL_RUNS_DIR.
    runs_dir = args.runs_dir or RUNS
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(runs_dir, args.dataset_id, label=runs_dir.name)
    args.metric = args.metric or default_metric(args.dataset_id, runs_dir=runs_dir)
    runs = runs_on(args.dataset_id, runs_dir=runs_dir)
    if args.round:
        from evaluation_harness._rounds import arms_of, resolve  # noqa: PLC0415

        keep_arms = set(arms_of(resolve(args.round, args.goal))) | {args.a}
        runs = [(d, m) for d, m in runs if m["config_id"] in keep_arms]
    lower = direction(runs, args.metric, args.asc, args.desc)
    A = per_item([r for r in runs if r[1]["config_id"] == args.a], args.metric)
    if not A:
        die(f"no runs for {args.a} on {args.dataset_id}")

    drop, keep = item_selection(args.exclude_dataset, args.items)

    rng = random.Random(args.seed)
    rows: list[dict] = []
    for opp in _opponents(runs, args.against, args.a):
        B = per_item([r for r in runs if r[1]["config_id"] == opp], args.metric)
        items = sorted(set(A) & set(B) - drop)
        if keep is not None:
            items = [i for i in items if i in keep]
        if len(items) < 3:
            continue
        deltas = [A[i] - B[i] for i in items]
        rows.append(
            {
                "opp": opp,
                "n": len(items),
                "delta": statistics.fmean(deltas),
                "wins": sum(1 for d in deltas if (d < 0 if lower else d > 0)),
                "p": sign_flip_p(deltas, permutations=args.permutations, rng=rng),
            }
        )
    if not rows:
        die("no opponents with enough shared items")

    # HOLM STEP-DOWN. Sorted ascending, threshold alpha/(m-i), and the moment one fails
    # every larger p-value fails with it -- that carry-forward is the whole procedure, and
    # dropping it turns Holm into a per-test comparison with no family-wise guarantee.
    m = len(rows)
    rows.sort(key=lambda r: r["p"])
    verdicts = holm({r["opp"]: r["p"] for r in rows}, alpha=args.alpha)
    for r in rows:
        r["thresh"], r["sep"] = verdicts[r["opp"]]

    n_items = rows[0]["n"]
    stratum = f"{n_items} items"
    if args.items:
        stratum += f" (from {args.items.name})"
    elif args.exclude_dataset:
        stratum += f" (excluding {args.exclude_dataset})"
    print(f"  {args.a}  vs family '{args.against}'   metric={args.metric}  {stratum}")
    print(f"  family size m={m}, declared before the p-values were read")
    print(f"  Holm step-down at alpha={args.alpha}" + ("  (lower is better)" if lower else ""))
    # SAY WHICH p. Up to EXACT_UP_TO items it is exact, and every command prints the same number.
    # Above that it is a seeded estimate drawn from one random stream for the whole family, so
    # pair-test or the inspector, which draw one per pair, can differ in the third decimal.
    # Per row: opponents can share different numbers of items, so one family can hold both.
    est = [r["n"] > EXACT_UP_TO for r in rows]
    if any(est) and not all(est):
        print(
            f"  p: exact up to {EXACT_UP_TO} shared items, a seeded estimate above ({args.permutations} "
            "permutations, one random stream for the family) -- marked ~\n"
        )
    elif n_items <= EXACT_UP_TO:
        print(f"  p: exact, over all 2^{n_items} sign patterns\n")
    else:
        print(
            f"  p: a seeded estimate ({args.permutations} permutations, one random stream for the family);\n"
            "     pair-test and the inspector estimate one pair at a time and can differ in the third decimal\n"
        )
    width = max(len(r["opp"]) for r in rows) + 2
    print(f"    {'opponent':{width}} {'delta':>9} {'A wins':>9} {'p':>8} {'thresh':>8}   verdict")
    for r in rows:
        pv = ("~" if any(est) and not all(est) and r["n"] > EXACT_UP_TO else "") + fmt_p(r["p"])
        print(
            f"    {r['opp']:{width}} {r['delta']:+9.4f} {r['wins']:>4}/{r['n']:<4} "
            f"{pv:>8} {r['thresh']:8.4f}   {'SEPARATED' if r['sep'] else '--'}"
        )
    sep = sum(1 for r in rows if r["sep"])
    ahead = sum(1 for r in rows if (r["delta"] < 0 if lower else r["delta"] > 0))
    print(f"\n    separated from {sep} of {m} opponents; ahead on the point estimate against {ahead} of {m}")
    # The gap between those two numbers is the finding most of the time: an ordering the
    # means assert and the data cannot support.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
