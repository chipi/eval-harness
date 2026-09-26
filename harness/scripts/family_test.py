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

import argparse
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import DATA, SOURCES, read_json  # noqa: E402
from pair_test import per_item  # noqa: E402 -- one implementation of "score per item"


def _opponents(runs_dir: Path, dataset_id: str, against: str, exclude: str) -> list[str]:
    found = set()
    for d in sorted(runs_dir.glob("*")):
        mj = d / "metrics.json"
        if not mj.is_file():
            continue
        m = read_json(mj)
        cid = m.get("config_id")
        if m.get("dataset_id") == dataset_id and cid and cid != exclude and against in cid:
            found.add(cid)
    return sorted(found)


def _sign_flip(deltas: list[float], permutations: int, rng: random.Random) -> float:
    obs = abs(statistics.fmean(deltas))
    hits = sum(
        1 for _ in range(permutations)
        if abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in deltas)) >= obs
    )
    return (hits + 1) / (permutations + 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", required=True, help="config_id of the arm under test")
    ap.add_argument("--against", required=True,
                    help="substring selecting the opponent family, declared in advance")
    ap.add_argument("--metric", default="coverage")
    ap.add_argument("--runs-dir", default=None, help="default: data/runs")
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument("--items", type=Path, help="file of item_ids; restrict to exactly these")
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=20260926)
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir) if args.runs_dir else DATA / "runs"
    A = per_item(runs_dir, args.dataset_id, args.a, args.metric)
    if not A:
        print(f"  no runs for {args.a} on {args.dataset_id}")
        return 1

    drop: set[str] = set()
    if args.exclude_dataset:
        drop = {p.stem for p in (SOURCES / args.exclude_dataset).glob("*.txt")}
    keep: set[str] | None = None
    if args.items:
        keep = {ln.strip() for ln in args.items.read_text(encoding="utf-8").splitlines() if ln.strip()}

    rng = random.Random(args.seed)
    rows = []
    for opp in _opponents(runs_dir, args.dataset_id, args.against, args.a):
        B = per_item(runs_dir, args.dataset_id, opp, args.metric)
        items = sorted(set(A) & set(B) - drop)
        if keep is not None:
            items = [i for i in items if i in keep]
        if len(items) < 3:
            continue
        deltas = [A[i] - B[i] for i in items]
        rows.append({
            "opp": opp,
            "n": len(items),
            "delta": statistics.fmean(deltas),
            "wins": sum(1 for d in deltas if d > 0),
            "p": _sign_flip(deltas, args.permutations, rng),
        })
    if not rows:
        print("  no opponents with enough shared items")
        return 1

    # HOLM STEP-DOWN. Sorted ascending, threshold alpha/(m-i), and the moment one fails
    # every larger p-value fails with it -- that carry-forward is the whole procedure, and
    # dropping it turns Holm into a per-test comparison with no family-wise guarantee.
    m = len(rows)
    rows.sort(key=lambda r: r["p"])
    still_rejecting = True
    for i, r in enumerate(rows):
        r["thresh"] = args.alpha / (m - i)
        if still_rejecting and r["p"] >= r["thresh"]:
            still_rejecting = False
        r["sep"] = still_rejecting

    n_items = rows[0]["n"]
    stratum = f"{n_items} items"
    if args.items:
        stratum += f" (from {args.items.name})"
    elif args.exclude_dataset:
        stratum += f" (excluding {args.exclude_dataset})"
    print(f"  {args.a}  vs family '{args.against}'   metric={args.metric}  {stratum}")
    print(f"  family size m={m}, declared before the p-values were read")
    print(f"  Holm step-down at alpha={args.alpha}\n")
    width = max(len(r["opp"]) for r in rows) + 2
    print(f"    {'opponent':{width}} {'delta':>9} {'wins':>9} {'p':>8} {'thresh':>8}   verdict")
    for r in rows:
        print(f"    {r['opp']:{width}} {r['delta']:+9.4f} {r['wins']:>4}/{r['n']:<4} "
              f"{r['p']:8.4f} {r['thresh']:8.4f}   {'SEPARATED' if r['sep'] else '--'}")
    sep = sum(1 for r in rows if r["sep"])
    ahead = sum(1 for r in rows if r["delta"] > 0)
    print(f"\n    separated from {sep} of {m} opponents; ahead on the point estimate "
          f"against {ahead} of {m}")
    # The gap between those two numbers is the finding most of the time: an ordering the
    # means assert and the data cannot support.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
