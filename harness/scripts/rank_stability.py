#!/usr/bin/env python3
"""How many items before a leaderboard stops moving? Measured, not assumed. $0.

    python scripts/rank_stability.py --dataset-id cnn_dailymail_200 [--metric coverage]

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
import random
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent

from _common import RUNS, die  # noqa: E402
from _runs import default_metric, direction, matrix, runs_on, warn_on_ambiguous_runs  # noqa: E402  # noqa: E402
from stats import spearman  # noqa: E402 - midranks of midranks are the midranks: same rho

#: The half sizes measured: two disjoint halves of n items each.
SIZES = (10, 20, 50, 100)


def load(dataset_id: str, metric: str, match: str | None):
    """All arms' per-item scores on this dataset; optionally filtered by config_id substring."""
    return matrix(runs_on(dataset_id, match=match), metric)


def ranks_on(M, arms, items):
    """Ranks by mean score, with TIED ARMS SHARING THE AVERAGE RANK.

    The previous version handed every arm a distinct integer from `sorted`, which is
    stable and therefore broke ties alphabetically. Two arms with identical scores got
    different ranks decided by their names, and everything downstream -- rho, the median
    rank move, P(same winner) -- measured that.

    Average ranks (the standard midrank convention) are what makes the tie-correct rho
    above meaningful: tied arms are now genuinely indistinguishable to it.
    """
    mu = {a: statistics.fmean(M[a][i] for i in items) for a in arms}
    order = sorted(arms, key=lambda a: -mu[a])
    out: dict = {}
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and mu[order[j + 1]] == mu[order[i]]:
            j += 1
        midrank = (i + j) / 2 + 1  # 1-indexed average of the tied block
        for k in range(i, j + 1):
            out[order[k]] = midrank
        i = j + 1
    return out


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
    """Measure how many items it takes before the ranking stops moving."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--metric", help="default: the primary metric the runs recorded")
    ap.add_argument("--match")
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--asc", action="store_true", help="lower is better (default: inferred)")
    ap.add_argument("--desc", action="store_true", help="higher is better, whatever the runs declare")
    args = ap.parse_args()
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(RUNS, args.dataset_id, label=RUNS.name)

    args.metric = args.metric or default_metric(args.dataset_id, args.match)
    M = load(args.dataset_id, args.metric, args.match)
    if direction(runs_on(args.dataset_id, match=args.match), args.metric, args.asc, args.desc):
        # Ranked best first, whichever way is better: for cost or latency the best is the
        # lowest. Negating once here keeps every rank and "winner" below the right way up.
        M = {a: {i: -v for i, v in s.items()} for a, s in M.items()}
    arms = sorted(M)
    if len(arms) < 3:
        die(f"{len(arms)} arm(s) with per-item '{args.metric}' on {args.dataset_id}: need at least 3 to rank")
    items = sorted(set.intersection(*(set(M[a]) for a in arms)))
    if 2 * SIZES[0] > len(items):
        print(
            f"  {len(items)} items shared by the {len(arms)} arms: too few for two disjoint halves of "
            f"{SIZES[0]}, the smallest size measured. Rank stability needs at least {2 * SIZES[0]}."
        )
        return 1
    print(f"  {len(arms)} arms, {len(items)} items, metric={args.metric}, {args.draws} draws per size\n")

    full = ranks_on(M, arms, items)
    winner = min(arms, key=lambda a: full[a])
    rng = random.Random(args.seed)

    print(
        f"  {'n per half':>11} {'rho(half A, half B)':>21} {'5th pct':>9} "
        f"{'P(same winner)':>15} {'median |rank move|':>19} {'arms tied 1st':>14}"
    )
    worst_ties = 0.0
    for n in SIZES:
        if 2 * n > len(items):
            continue
        rhos, same, moves, ties, undecided = [], 0, [], [], 0
        for _ in range(args.draws):
            pick = rng.sample(items, 2 * n)
            A, B = pick[:n], pick[n:]
            ra, rb = ranks_on(M, arms, A), ranks_on(M, arms, B)
            r = spearman([ra[a] for a in arms], [rb[a] for a in arms])
            if r == r:  # NaN means every arm tied; no ordering to correlate
                rhos.append(r)
            # A WINNER ONLY COUNTS IF IT IS UNIQUE IN BOTH HALVES. With midranks a tied
            # leading block shares one rank, so `min` would still return the
            # alphabetically first of them and two halves tied the same way would be
            # scored as agreeing. That is exactly the DBpedia artifact: P(same winner)
            # 0.94 at n=10 falling to 0.28 at n=100, because at n=10 most arms were tied
            # and the alphabet decided. A draw where either half has no unique best is
            # counted as UNDECIDED and reported separately, never as agreement.
            wa = [a for a in arms if ra[a] == min(ra.values())]
            wb = [a for a in arms if rb[a] == min(rb.values())]
            if len(wa) == 1 and len(wb) == 1:
                same += 1 if wa[0] == wb[0] else 0
            else:
                undecided += 1
            moves.append(statistics.median(abs(ra[a] - full[a]) for a in arms))
            ties.append(tied_at_top(M, arms, A))
        rhos.sort()
        decided = args.draws - undecided
        mean_ties = statistics.fmean(ties)
        flag = "  <- ties decide" if mean_ties >= 2.0 else ""
        rho_m = statistics.fmean(rhos) if rhos else float("nan")
        rho_5 = rhos[int(0.05 * len(rhos))] if rhos else float("nan")
        # Denominator is DECIDED draws, not all draws: "of the times both halves named a
        # unique best arm, how often was it the same one". Dividing by all draws would
        # mix "they disagreed" with "neither half had an answer".
        pw = (same / decided) if decided else float("nan")
        print(
            f"  {n:>11} {rho_m:>21.3f} {rho_5:>9.3f} "
            f"{pw:>15.2f} {statistics.fmean(moves):>19.2f} "
            f"{mean_ties:>14.1f}{flag}"
            + (f"   [{undecided}/{args.draws} draws undecided]" if undecided else "")
        )
        worst_ties = max(worst_ties, mean_ties)
    print(f"\n  full-{len(items)} ordering's leader: {winner}")
    print("  'P(same winner)' = of the draws where BOTH halves had a UNIQUE best arm, how")
    print("  often it was the same one. Draws where either half's top was tied are counted")
    print("  as undecided and excluded, never as agreement. 'rank move' = median")
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
