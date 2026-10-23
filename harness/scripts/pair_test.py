#!/usr/bin/env python3
"""One pre-registered pair, tested on its own: sign-flip permutation on paired deltas.

    python scripts/pair_test.py --dataset-id cnn_dailymail_200 \
        --a cnn_deepseek_m_n200_v1 --b cnn_anthropic_m_n200_v1 --metric coverage

WHY A SECOND TEST, WHEN leaderboard.py ALREADY HAS ONE
  `_significance` answers "which of all k(k-1)/2 pairs differ?" and pays the Nemenyi
  multiplicity price for every one of them. That is the right price for that question and
  the wrong question for a decision. A comparison fixed BEFORE looking -- "is the 67x
  dearer arm better?" -- is one test, and correcting it for 275 comparisons nobody made
  is throwing away power to answer a question that was never asked.

  The honesty condition is that the pair is named in advance. Six pairs picked after
  reading the table are a search, not a test; EVAL_REPORT.md section 3.1b says so about its
  own six and Holm-corrects them. --family N applies BONFERRONI (alpha/N) here, which is
  Holm's strictest step applied to every member: conservative, never the reverse. Holm's
  step-down needs every p-value in the family at once, which one pair does not have.

THE TEST
  Per item, delta = A - B (items both arms scored, means over repeats). Under the null the
  sign of each delta is a coin flip, so: flip each sign at random, recompute the mean,
  repeat. p = how often |mean| of a flipped sample reaches the observed |mean| (counted
  over every sign pattern up to 30 items, estimated above that: stats.py). No
  distributional assumption, and it keeps the pairing -- which matters here, where ~74% of
  the variance is between articles.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import (  # noqa: E402
    RUNS,
    dataset_item_ids,
    default_metric,
    read_item_ids,
    warn_on_ambiguous_runs,
)
from _runs import direction, per_item, runs_on  # noqa: E402
from stats import EXACT_UP_TO, sign_flip_p  # noqa: E402


def main() -> int:
    """Test a pre-registered pair with sign-flip permutation."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", required=True, help="config_id of the arm under test")
    ap.add_argument("--b", required=True, help="config_id it is compared against")
    ap.add_argument("--metric", help="default: the primary metric the runs recorded")
    ap.add_argument("--runs-dir", type=Path, default=None, help="default: EVAL_RUNS_DIR, else data/runs")
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument(
        "--items",
        type=Path,
        help="file of item_ids (one per line); restrict the test to exactly these",
    )
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument(
        "--family", type=int, default=1, help="how many pairs were tested together (Bonferroni: alpha/family)"
    )
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument(
        "--asc",
        action="store_true",
        help="lower is better: 'A wins' counts items where A scored lower "
        "(default: inferred from the metric and the runs)",
    )
    ap.add_argument("--desc", action="store_true", help="higher is better, whatever the runs declare")
    args = ap.parse_args()
    # The directory read is the directory warned about: --runs-dir, else EVAL_RUNS_DIR.
    runs_dir = args.runs_dir or RUNS
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _common.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(runs_dir, args.dataset_id, label=runs_dir.name)
    args.metric = args.metric or default_metric(args.dataset_id, runs_dir=runs_dir)
    runs = runs_on(args.dataset_id, runs_dir=runs_dir)
    lower = direction(runs, args.metric, args.asc, args.desc)
    A = per_item([r for r in runs if r[1]["config_id"] == args.a], args.metric)
    B = per_item([r for r in runs if r[1]["config_id"] == args.b], args.metric)
    items = sorted(set(A) & set(B))
    if args.exclude_dataset:
        prior = dataset_item_ids(args.exclude_dataset)
        items = [i for i in items if i not in prior]
    # AN EXPLICIT ITEM SET, because some strata are not datasets. The one this was added
    # for: the 154 articles that fitted inside BART's 1024-token encoder. On the other 46
    # the local arm summarised two thirds of an article and was scored against a reference
    # written from all of it, so "bart vs an LLM over all 200" averages two different
    # tasks. The stratum is a property of a RUN, not of a dataset, so --exclude-dataset
    # cannot express it. Passing the ids in a file rather than recomputing them inside each
    # script means the leaderboard, the pair tests and the report all use provably the same
    # set -- and a reader can diff it.
    if args.items:
        keep = read_item_ids(args.items)
        items = [i for i in items if i in keep]
    if len(items) < 3:
        print(f"  only {len(items)} shared item(s) — nothing to test")
        return 1

    deltas = [A[i] - B[i] for i in items]
    obs = statistics.fmean(deltas)
    wins = sum(1 for d in deltas if (d < 0 if lower else d > 0))
    ties = sum(1 for d in deltas if d == 0)

    p = sign_flip_p(deltas, permutations=args.permutations, seed=args.seed)
    # BONFERRONI, not Holm. One pair cannot do Holm: the step-down procedure compares the
    # smallest p to alpha/m, the next to alpha/(m-1), and so on, which needs the whole
    # family's p-values at once. alpha/m applied to every member is the strictest step
    # applied throughout -- always conservative relative to Holm, never anti-conservative,
    # so a pair that clears this has cleared Holm too. A pair that does NOT clear it may
    # still clear Holm; run the family's p-values through the step-down to find out.
    thresh = 0.05 / args.family

    print(f"  {args.a}  vs  {args.b}    metric={args.metric}  N={len(items)}")
    print(f"    delta (A - B)      {obs:+.4f}")
    print(
        f"    items A wins       {wins}/{len(items)}"
        + (" (lower is better)" if lower else "")
        + (f" ({ties} exact tie(s))" if ties else "")
    )
    how = (
        f"exact, all 2^{len(items)} sign patterns"
        if len(items) <= EXACT_UP_TO
        else f"{args.permutations} permutations"
    )
    print(f"    sign-flip p        {p:.4f}  ({how})")
    if args.family > 1:
        verdict = "SEPARATED" if p < thresh else "NOT-SEPARATED"
        print(f"    Bonferroni/{args.family}     threshold {thresh:.4f} -> {verdict}")
        if p >= thresh:
            print("    (conservative: Holm's later steps are looser — check the family)")
    else:
        print(f"    verdict            {'SEPARATED' if p < 0.05 else 'NOT-SEPARATED'} at 0.05")
        print("    (uncorrected: valid only if this pair was named before the table was read)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
