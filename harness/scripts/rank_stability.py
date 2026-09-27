#!/usr/bin/env python3
"""How many items before a leaderboard stops moving? Measured, not assumed. $0.

    python scripts/rank_stability.py --dataset-id cnn_dailymail_200 --metric coverage

WHY
  "Is n big enough?" is normally answered from a power table, which needs an effect size
  you do not have until you have run the experiment -- and if you take that effect size
  from a small pilot you inherit the pilot's error. This repo did exactly that: journal
  entry 40 predicted deepseek_m vs deepseek_s would need n~2472 from a delta measured on
  20 articles; it separated at 200, because the real delta was 4x the pilot's.

  This asks the question the other way round, from data already on disk. Draw TWO DISJOINT
  subsets of n items, rank the arms independently in each, and correlate the two rankings.
  That is the agreement between two honest evals of size n -- no "true" ordering is
  assumed, neither half is privileged, and nothing is re-used between the halves.

READING IT
  rho is Spearman between the two halves' orderings. It is bounded above by the noise in
  the arms themselves, not by 1.0: two evals of the same arms on different items disagree
  even when both are correct. The n where the curve flattens is where more items stop
  buying you ordering.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import RUNS, read_json  # noqa: E402


def load(dataset_id: str, metric: str, match: str | None):
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for d in sorted(RUNS.glob("*")):
        mj, pj = d / "metrics.json", d / "predictions.jsonl"
        if not (mj.is_file() and pj.is_file()):
            continue
        m = read_json(mj)
        if m.get("dataset_id") != dataset_id:
            continue
        cid = m.get("config_id", d.name)
        if match and match not in cid:
            continue
        for line in pj.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if metric in row:
                    acc[cid][row["item_id"]].append(float(row[metric]))
    return {a: {i: statistics.fmean(v) for i, v in it.items()} for a, it in acc.items()}


def spearman(x: list[float], y: list[float]) -> float:
    n = len(x)
    dsq = sum((x[i] - y[i]) ** 2 for i in range(n))
    return 1 - 6 * dsq / (n * (n * n - 1))


def ranks_on(M, arms, items):
    mu = {a: statistics.fmean(M[a][i] for i in items) for a in arms}
    order = sorted(arms, key=lambda a: -mu[a])
    return {a: i + 1 for i, a in enumerate(order)}


def tied_at_top(M, arms, items) -> int:
    """How many arms share the best mean score on this item set.

    WHY THIS COLUMN EXISTS. `sorted` is stable and `arms` is alphabetical, so when arms
    TIE the ordering is decided by arm name — and every statistic below then measures the
    alphabet rather than the data.

    It is not hypothetical. On dbpedia_280, a saturated 14-class task, this script
    reported P(same winner) = 0.94 at n=10 FALLING to 0.28 at n=100 — backwards, and the
    opposite of AG News (0.32 rising to 0.90). The cause: at n=10 with arms near 0.98
    accuracy, most of the 27 arms score 10/10, the tie is broken by name every time, and
    "the same winner" is guaranteed. As n grows the ties break and the real instability
    appears, so the number falls.

    rho is inflated the same way, which is why it came out non-monotonic (0.782, 0.713,
    0.669, 0.751) instead of rising.

    So the tie count is printed beside them. A number near 1 means the ordering is doing
    the work; a large one means it is not, whatever rho says.
    """
    mu = {a: statistics.fmean(M[a][i] for i in items) for a in arms}
    best = max(mu.values())
    return sum(1 for a in arms if mu[a] == best)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--metric", default="coverage")
    ap.add_argument("--match")
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260926)
    args = ap.parse_args()

    M = load(args.dataset_id, args.metric, args.match)
    arms = sorted(M)
    items = sorted(set.intersection(*(set(M[a]) for a in arms)))
    if len(arms) < 3:
        print(f"  {len(arms)} arm(s) — need at least 3 to rank"); return 1
    print(f"  {len(arms)} arms, {len(items)} items, metric={args.metric}, "
          f"{args.draws} draws per size\n")

    full = ranks_on(M, arms, items)
    winner = min(arms, key=lambda a: full[a])
    rng = random.Random(args.seed)

    print(f"  {'n per half':>11} {'rho(half A, half B)':>21} {'5th pct':>9} "
          f"{'P(same winner)':>15} {'median |rank move|':>19} {'arms tied 1st':>14}")
    worst_ties = 0.0
    for n in (10, 20, 50, 100):
        if 2 * n > len(items):
            continue
        rhos, same, moves, ties = [], 0, [], []
        for _ in range(args.draws):
            pick = rng.sample(items, 2 * n)
            A, B = pick[:n], pick[n:]
            ra, rb = ranks_on(M, arms, A), ranks_on(M, arms, B)
            rhos.append(spearman([ra[a] for a in arms], [rb[a] for a in arms]))
            same += 1 if min(arms, key=lambda a: ra[a]) == min(arms, key=lambda a: rb[a]) else 0
            moves.append(statistics.median(abs(ra[a] - full[a]) for a in arms))
            ties.append(tied_at_top(M, arms, A))
        rhos.sort()
        mean_ties = statistics.fmean(ties)
        flag = "  <- ties decide" if mean_ties >= 2.0 else ""
        print(f"  {n:>11} {statistics.fmean(rhos):>21.3f} {rhos[int(0.05*len(rhos))]:>9.3f} "
              f"{same/args.draws:>15.2f} {statistics.fmean(moves):>19.2f} "
              f"{mean_ties:>14.1f}{flag}")
        worst_ties = max(worst_ties, mean_ties)
    print(f"\n  full-{len(items)} ordering's leader: {winner}")
    print("  'P(same winner)' = the two halves crown the same arm. 'rank move' = median")
    print("  positions an arm sits from its full-set rank, in a half of that size.")
    print("  'arms tied 1st' = how many arms share the best score. `sorted` is stable and")
    print("  arms are alphabetical, so ties are broken by NAME -- where this is large,")
    print("  rho and P(same winner) are measuring the alphabet, not the data.")
    if worst_ties >= 2.0:
        print(f"\n  WARNING: up to {worst_ties:.1f} arms tie for first in a half. This")
        print("  metric is saturated at these sizes; read the tie column before rho.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
