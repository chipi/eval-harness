#!/usr/bin/env python3
"""Paired bootstrap over items, for metrics that have no per-item value.

    python scripts/bootstrap_test.py --dataset-id dbpedia_280 \
        --a db_qwen_m_n200_v1 --against _n200_v1 --metric macro_f1

WHY THIS EXISTS: family_test.py CANNOT ANSWER THIS QUESTION

  `family_test.py` runs a sign-flip permutation on paired per-item deltas. That requires
  a per-item value, and accuracy has one: score each item 1 or 0, and the mean IS
  accuracy. **Macro-F1 does not.** Precision for a class needs every prediction of that
  class across the whole run, so F1 is a property of the SET and there is no per-item
  number whose average is macro-F1.

  This is a property of the statistic, not a missing feature, and the wrong fix is to
  invent a per-item pseudo-F1 and feed it to the existing test. It would run, produce a
  p-value, and mean nothing.

  So: a different test, in a different file, with a different name. Resample ITEMS with
  replacement; recompute both arms' macro-F1 on the same resampled set; read the
  distribution of the difference. The pairing is kept -- both arms are scored on the
  identical draw every time -- which matters because most of the variance in these
  studies is between items rather than between arms.

WHAT IT REPORTS, AND WHAT IT DOES NOT
  A 95% percentile interval for the difference, and a bootstrap p from the share of draws
  on the wrong side of zero. These are APPROXIMATE in a way the permutation test is not:
  the permutation test's null is exact by construction, the bootstrap's interval is an
  asymptotic argument that behaves poorly with few items or a metric near its ceiling.
  Both conditions hold on DBpedia. Read the interval, not the p-value alone.

  `--metric accuracy` is supported ONLY as a cross-check: accuracy can be tested both
  ways, so running both is how you find out whether this implementation agrees with the
  exact test on a case where the exact test is available.

MEASURED: THIS TEST IS ANTI-CONSERVATIVE, AND BY HOW MUCH

  The cross-check was run and the two tests DISAGREE. Same arm, same data, same metric
  (`correct`), same Holm family of 26 on dbpedia_280:

      family_test.py   sign-flip permutation, exact null    separated from  8 of 26
      bootstrap_test.py  paired percentile bootstrap        separated from 11 of 26

  Per-opponent, the bootstrap's p is consistently the smaller one -- against
  `anthropic_l` the permutation says 1.0000 and the bootstrap says 0.7353; against
  `deepseek_l`, 0.4984 against 0.2720.

  That is the known failure mode of a percentile bootstrap with few items and a metric
  pinned near its ceiling, which is exactly this dataset. So:

      TREAT A `SEPARATED` VERDICT HERE AS AN UPPER BOUND on how much separation exists.
      Where a permutation test is available, IT is the answer and this is a sanity check.
      Use this script for macro-F1 because nothing exact exists for macro-F1 -- not
      because it is a second opinion worth weighing equally.

  The interval is the honest output. A 95% CI spanning zero means the arms are not
  ordered by this data whatever the point estimates say, and that reading does not depend
  on the p-value being well calibrated.

THE HONESTY CONDITION IS THE SAME
  `--against` declares the family before the p-values are read, and Holm is applied
  across it exactly as in family_test.py.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import RUNS, SOURCES, die  # noqa: E402
from classification_report import gold_labels, per_class, predictions  # noqa: E402


def _macro_f1(pairs: list, labels: list) -> float:
    stats = per_class(pairs, labels)
    return sum(s["f1"] for s in stats.values()) / len(labels)


def _accuracy(pairs: list, labels: list) -> float:
    return sum(1 for g, p in pairs if g == p) / len(pairs) if pairs else 0.0


METRICS = {"macro_f1": _macro_f1, "accuracy": _accuracy}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", required=True, help="config_id of the arm under test")
    ap.add_argument("--against", required=True,
                    help="substring selecting the opponent family, declared in advance")
    ap.add_argument("--metric", default="macro_f1", choices=sorted(METRICS))
    ap.add_argument("--draws", type=int, default=5000)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument("--items", type=Path, help="file of item_ids; restrict to exactly these")
    args = ap.parse_args()

    gold = gold_labels(args.dataset_id)
    labels = sorted(set(gold.values()))
    preds = predictions(args.dataset_id, None)
    if args.a not in preds:
        die(f"no runs for {args.a} on {args.dataset_id}")

    drop: set = set()
    if args.exclude_dataset:
        drop = {p.stem for p in (SOURCES / args.exclude_dataset).glob("*.txt")}
    keep = None
    if args.items:
        keep = {ln.strip() for ln in args.items.read_text(encoding="utf-8").splitlines()
                if ln.strip()}

    opponents = sorted(c for c in preds
                       if c != args.a and args.against in c and preds[c])
    if not opponents:
        die(f"no opponents matching {args.against!r}")

    fn = METRICS[args.metric]
    rng = random.Random(args.seed)
    rows = []
    for opp in opponents:
        items = sorted((set(preds[args.a]) & set(preds[opp]) & set(gold)) - drop)
        if keep is not None:
            items = [i for i in items if i in keep]
        if len(items) < 10:
            continue
        a_pairs = {i: (gold[i], preds[args.a][i]) for i in items}
        b_pairs = {i: (gold[i], preds[opp][i]) for i in items}
        observed = fn(list(a_pairs.values()), labels) - fn(list(b_pairs.values()), labels)

        deltas = []
        n = len(items)
        for _ in range(args.draws):
            # ONE resample, BOTH arms. Drawing separately for each arm would throw away
            # the pairing and inflate the variance of the difference by roughly two.
            draw = [items[rng.randrange(n)] for _ in range(n)]
            deltas.append(fn([a_pairs[i] for i in draw], labels)
                          - fn([b_pairs[i] for i in draw], labels))
        deltas.sort()
        lo = deltas[int(0.025 * len(deltas))]
        hi = deltas[min(int(0.975 * len(deltas)), len(deltas) - 1)]
        below = sum(1 for d in deltas if d <= 0) / len(deltas)
        # Two-sided, and floored at 1/draws: a bootstrap cannot report a p smaller than
        # its own resolution, and printing 0.0000 would claim precision it does not have.
        p = max(2 * min(below, 1 - below), 1.0 / args.draws)
        rows.append({"opp": opp, "n": n, "delta": observed, "lo": lo, "hi": hi, "p": p})

    if not rows:
        die("no opponents with enough shared items")

    m = len(rows)
    rows.sort(key=lambda r: r["p"])
    still = True
    for i, r in enumerate(rows):
        r["thresh"] = args.alpha / (m - i)
        if still and r["p"] >= r["thresh"]:
            still = False
        r["sep"] = still

    print(f"  {args.a}  vs family '{args.against}'   metric={args.metric}  "
          f"{rows[0]['n']} items")
    print(f"  paired bootstrap, {args.draws} draws, seed {args.seed}")
    print(f"  family size m={m}, declared before the p-values were read")
    print(f"  Holm step-down at alpha={args.alpha}\n")
    w = max(len(r["opp"]) for r in rows) + 2
    print(f"    {'opponent':{w}} {'delta':>9} {'95% CI':>20} {'p':>8} {'thresh':>8}   verdict")
    for r in rows:
        ci = f"[{r['lo']:+.4f}, {r['hi']:+.4f}]"
        print(f"    {r['opp']:{w}} {r['delta']:+9.4f} {ci:>20} {r['p']:8.4f} "
              f"{r['thresh']:8.4f}   {'SEPARATED' if r['sep'] else '--'}")
    sep = sum(1 for r in rows if r["sep"])
    ahead = sum(1 for r in rows if r["delta"] > 0)
    spans = sum(1 for r in rows if r["lo"] <= 0 <= r["hi"])
    print(f"\n    separated from {sep} of {m}; ahead on the point estimate against "
          f"{ahead} of {m}")
    print(f"    {spans} of {m} intervals span zero — those arms are not ordered by this "
          f"data,")
    print("    whatever the point estimates say.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
