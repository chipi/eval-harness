"""How many items before a leaderboard stops moving? Measured, not assumed. $0.

    evh rank-stability cnn_dailymail_200 [--metric coverage]

WHY
  "Is n big enough?" is normally answered from a power table, which needs an effect size
  you do not have until you have run the eval -- and if you take that effect size
  from a small pilot you inherit the pilot's error. This repo did exactly that: journal
  entry 40 predicted deepseek_m vs deepseek_s would need n~2472 from a delta measured on
  20 articles; it was significant at 200, because the real delta was 4x the pilot's.

  This asks the question the other way round, from data already on disk. Draw TWO DISJOINT
  subsets of n items, rank the arms independently in each, and correlate the two rankings.
  That is the agreement between two honest measurements of size n -- no "true" ordering is
  assumed, neither half is privileged, and nothing is re-used between the halves.

READING IT
  rho is Spearman between the two halves' orderings. It is bounded above by the noise in
  the arms themselves, not by 1.0: two measurements of the same arms on different items disagree
  even when both are correct. The n where the curve flattens is where more items stop
  buying you ordering.
"""

from __future__ import annotations

import argparse
import random
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

from evaluation_harness import _jsonout  # noqa: E402
from evaluation_harness._common import die  # noqa: E402
from evaluation_harness._runs import default_metric, direction, matrix, runs_on, warn_on_ambiguous_runs  # noqa: E402  # noqa: E402
from evaluation_harness.stats import spearman  # noqa: E402 - midranks of midranks are the midranks: same rho

#: The half sizes always measured (two disjoint halves of n items each). They are drawn first, in this order, so
#: their numbers do not depend on the sizes added for a dataset (sizes_for).
SIZES = (10, 20, 50, 100)
#: The smallest half measured: a line needs a start, and fewer items say little about an order.
SMALLEST = 5


def sizes_for(n_items: int) -> list[int]:
    """The half sizes measured on a dataset of `n_items`, in the order they are drawn: the SIZES that fit, then SMALLEST
    and the largest half (n_items // 2) when they are not among them. 20 items give a line (5, 10) rather than one
    point (the 0.8.0 newcomer run: one row, no line to flatten), and a dataset past 200 items is measured at its own
    size too."""
    fixed = [n for n in SIZES if 2 * n <= n_items]
    extra = {n for n in (SMALLEST, n_items // 2) if n >= SMALLEST and 2 * n <= n_items} - set(fixed)
    return fixed + sorted(extra)


def load(dataset_id: str, metric: str, match: str | None):
    """All arms' per-item scores on this dataset; optionally filtered by system_id substring."""
    return matrix(runs_on(dataset_id, match=match), metric)


def ranks_on(M, arms, items):
    """Ranks by mean score, with TIED ARMS SHARING THE AVERAGE RANK.

    Distinct integers from `sorted` would break ties alphabetically (it is stable), so
    two arms with identical scores would get ranks decided by their names, and rho, the
    median rank move and P(same winner) would measure that. Average ranks (the standard
    midrank convention) make tied arms indistinguishable to the tie-correct rho above.
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


def body(
    dataset: str,
    metric: str | None = None,
    match: str | None = None,
    draws: int = 400,
    seed: int = 20260926,
    asc: bool = False,
    desc: bool = False,
    as_json: bool = False,
) -> int:
    """Measure how many items it takes before the ranking stops moving."""
    return _run(
        argparse.Namespace(
            dataset_id=dataset,
            metric=metric,
            match=match,
            draws=draws,
            seed=seed,
            asc=asc,
            desc=desc,
            json=as_json,
        )
    )


def measure(
    dataset: str,
    metric: str | None = None,
    match: str | None = None,
    draws: int = 400,
    seed: int = 20260926,
    asc: bool = False,
    desc: bool = False,
) -> dict:
    """The table `rank-stability` prints, as values (charts.rank_stability draws it): per half size (sizes_for), the
    halves' mean and 5th-percentile rho, the share of decided draws naming the same winner, the median rank move, the
    arms tied first and the undecided draws, sorted by size; the full set's leader. Refused (Problem) with fewer than 3
    arms; `rows` is empty with too few items for two halves of SMALLEST."""
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    metric = metric or default_metric(dataset, match)
    M = load(dataset, metric, match)
    if direction(runs_on(dataset, match=match), metric, asc, desc):
        # Ranked best first, whichever way is better: for cost or latency the best is the
        # lowest. Negating once here keeps every rank and "winner" below the right way up.
        M = {a: {i: -v for i, v in s.items()} for a, s in M.items()}
    arms = sorted(M)
    if len(arms) < 3:
        raise Problem(
            f"{len(arms)} arm(s) with per-item '{metric}' on {dataset}: need at least 3 to rank", "not-enough"
        )
    items = sorted(set.intersection(*(set(M[a]) for a in arms)))
    full = ranks_on(M, arms, items)
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for n in sizes_for(len(items)):
        rhos, same, moves, ties, undecided = [], 0, [], [], 0
        for _ in range(draws):
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
        # Denominator is DECIDED draws, not all draws: "of the times both halves named a
        # unique best arm, how often was it the same one". Dividing by all draws would
        # mix "they disagreed" with "neither half had an answer".
        decided = draws - undecided
        rows.append({
            "n_per_half": n,
            "rho_mean": statistics.fmean(rhos) if rhos else None,
            "rho_5th_pct": rhos[int(0.05 * len(rhos))] if rhos else None,
            "p_same_winner": (same / decided) if decided else None,
            "median_rank_move": statistics.fmean(moves),
            "arms_tied_first": statistics.fmean(ties),
            "undecided_draws": undecided,
        })  # fmt: skip
    rows.sort(key=lambda r: r["n_per_half"])
    return {
        "dataset": dataset,
        "metric": metric,
        "arms": len(arms),
        "items": len(items),
        "draws": draws,
        "seed": seed,
        "leader": min(arms, key=lambda a: full[a]),
        "rows": rows,
    }


def _run(args: argparse.Namespace) -> int:
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    # Two runs sharing a system_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs("", args.dataset_id)
    try:
        m = measure(args.dataset_id, args.metric, args.match, args.draws, args.seed, args.asc, args.desc)
    except Problem as exc:
        die(str(exc), exc.kind)
    args.metric = m["metric"]
    if not m["rows"]:
        too_few = (
            f"  {m['items']} items shared by the {m['arms']} arms: too few for two disjoint halves of "
            f"{SMALLEST}, the smallest size measured. Rank stability needs at least {2 * SMALLEST}."
        )
        if args.json:  # a refusal: its message on stderr, nothing on stdout
            die(too_few.strip(), "not-enough")
        print(too_few)
        return 1
    print(f"  {m['arms']} arms, {m['items']} items, metric={args.metric}, {args.draws} draws per size\n")
    # Under --json the rows are kept and handed over as one table; the lines are for text.
    if not args.json:
        print(
            f"  {'n per half':>11} {'rho(half A, half B)':>21} {'5th pct':>9} "
            f"{'P(same winner)':>15} {'median |rank move|':>19} {'arms tied 1st':>14}"
        )
    nan = float("nan")
    table_rows: list[list] = []
    for r in m["rows"]:
        n, undecided, mean_ties = r["n_per_half"], r["undecided_draws"], r["arms_tied_first"]
        rho_m = nan if r["rho_mean"] is None else r["rho_mean"]
        rho_5 = nan if r["rho_5th_pct"] is None else r["rho_5th_pct"]
        pw = nan if r["p_same_winner"] is None else r["p_same_winner"]
        if args.json:
            table_rows.append(
                [n, rho_m, rho_5, pw, r["median_rank_move"], mean_ties, mean_ties >= 2.0, undecided]
            )
        else:
            print(
                f"  {n:>11} {rho_m:>21.3f} {rho_5:>9.3f} "
                f"{pw:>15.2f} {r['median_rank_move']:>19.2f} "
                f"{mean_ties:>14.1f}{'  <- ties decide' if mean_ties >= 2.0 else ''}"
                + (f"   [{undecided}/{args.draws} draws undecided]" if undecided else "")
            )
    # Saturation is read from the sizes of SIZES up, where a metric's ties mean something: halves of SMALLEST tie for
    # most metrics (their row says so), and counting them called SciFact saturated. A dataset too small for those is
    # read from what it has.
    judged = [r for r in m["rows"] if r["n_per_half"] >= SIZES[0]] or m["rows"]
    worst_ties = max(r["arms_tied_first"] for r in judged)
    _jsonout.table(
        [
            "n_per_half",
            "rho_mean",
            "rho_5th_pct",
            "p_same_winner",
            "median_rank_move",
            "arms_tied_first",
            "ties_decide",
            "undecided_draws",
        ],
        table_rows,
    )
    _jsonout.values(
        {
            "dataset_id": args.dataset_id,
            "metric": args.metric,
            "arms": m["arms"],
            "items": m["items"],
            "draws": args.draws,
            "seed": args.seed,
            "sizes": [r["n_per_half"] for r in m["rows"]],
            "leader": m["leader"],
            "worst_ties": worst_ties,
            "saturated": worst_ties >= 2.0,
        }
    )
    print(f"\n  full-{m['items']} ordering's leader: {m['leader']}")
    print("  'P(same winner)' = of the draws where BOTH halves had a UNIQUE best arm, how")
    print("  often it was the same one. Draws where either half's top was tied are counted")
    print("  as undecided and excluded, never as agreement. 'rank move' = median")
    print("  positions an arm sits from its full-set rank, in a half of that size.")
    print("  'arms tied 1st' = how many arms share the best score. Tied arms share a")
    print("  midrank, so where this is large rho has little order to agree about and most")
    print("  draws are undecided.")
    if worst_ties >= 2.0:
        print(f"\n  WARNING: up to {worst_ties:.1f} arms tie for first in a half. This")
        print("  metric is saturated at these sizes; read the tie column before rho.")
    return 0
