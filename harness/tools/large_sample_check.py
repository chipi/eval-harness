#!/usr/bin/env python3
"""Does the normal approximation give the harness's resampled p's at 1,000 and 10,000 units (PLAN_0.8.0 S2)?

    python tools/large_sample_check.py [--sizes 1000,10000] [--per 40] [--jobs 24] [--out FILE]

For each kind of per-item difference the harness meets (a continuous score, one bounded to [-1, 1] with ties at 0,
a 0/1 outcome, a heavy-tailed one, a sparse one, and clusters of 3 and of 8), and each size, it draws `--per`
datasets with an effect spread over the range where decisions are made (|z| about 1 to 3.5), and computes:
- the sign-flip p the harness reports (stats.sign_flip_p: 20,000 seeded permutations) against
  p = erfc(|z| / sqrt 2), z = sum(d) / sqrt(sum(d^2)), the permutation distribution's own normal limit;
- the bootstrap-t p of the contender test (stats.bootstrap_t_p: 9,999 resamples, clusters resampled) against
  p = 1 - Phi(T), T = (m + margin) / se with the same cluster-robust se.
It prints, per kind and size, the largest difference, how many differences exceed three Monte Carlo standard errors of
the resampled p, and whether every decision at 0.05, 0.025, 0.01 and 0.005 agrees; and writes every case as JSON.
Every dataset is seeded: the same command prints the same table.
"""

import argparse
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _store, stats  # noqa: E402

os.environ.pop("EVH_P_CACHE", None)  # every p computed, none read from a cache
# This tool is the evidence for the threshold, so it never takes the limit itself: both tests resample at every size
# (set again in each worker, which imports this file).
stats.LARGE_SAMPLE = 10**18

KINDS = ("continuous", "bounded", "binary", "heavy", "sparse", "clusters3", "clusters8")
LEVELS = (0.05, 0.025, 0.01, 0.005)


def deltas(kind: str, n: int, shift: float, rng: random.Random) -> tuple[list[float], list[int]]:
    """`n` units' totals and sizes (one item per unit; for the cluster kinds n clusters of 3 or 8 items) with the
    mean shifted by `shift` sds."""
    if kind == "continuous":
        return [rng.gauss(shift * 0.2, 0.2) for _ in range(n)], [1] * n
    if kind == "bounded":  # coverage-like: two scores in [0, 1], their difference; a third of items tie at 0
        out = []
        for _ in range(n):
            if rng.random() < 1 / 3:
                out.append(0.0)
            else:
                a, b = rng.betavariate(2, 3), rng.betavariate(2, 3)
                out.append(max(-1.0, min(1.0, a - b + shift * 0.25)))
        return out, [1] * n
    if kind == "binary":  # two arms right or wrong: -1, 0, +1
        p = min(0.45, max(0.0, 0.15 + shift * 0.03))
        return [1.0 if (u := rng.random()) < p else (-1.0 if u < p + 0.15 else 0.0) for _ in range(n)], [
            1
        ] * n
    if kind == "heavy":  # Student t with 3 degrees of freedom
        return [
            shift * 0.2 + 0.2 * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 2) / 3) for _ in range(n)
        ], [1] * n
    if kind == "sparse":  # 95% of items unchanged
        return [rng.gauss(shift * 0.2, 0.2) * 4 if rng.random() < 0.05 else 0.0 for _ in range(n)], [1] * n
    k = 3 if kind == "clusters3" else 8
    g = n
    totals, sizes = [], []
    for _ in range(g):
        c = rng.gauss(0, 0.15)  # a shared effect per cluster: items in a cluster are not independent
        totals.append(sum(rng.gauss(shift * 0.2 + c, 0.2) for _ in range(k)))
        sizes.append(k)
    return totals, sizes


def normal_sf(z: float) -> float:
    """1 - Phi(z), the standard normal's upper tail."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def one(case: tuple) -> dict:
    """One dataset: both tests by resampling and by the normal approximation."""
    kind, n, i = case
    rng = random.Random(f"{kind}/{n}/{i}")
    t_target = 1.0 + 2.5 * rng.random()
    totals, sizes = deltas(kind, n, 0.0, rng)
    # the effect that puts the mean near t_target standard errors from 0
    m, se = stats._mean_se(totals, sizes)
    shift_items = t_target * se - m
    totals = [t + shift_items * k for t, k in zip(totals, sizes, strict=True)]
    per_item = [t / k for t, k in zip(totals, sizes, strict=True)]
    row = {"kind": kind, "n": n, "case": i}
    # The sign-flip per unit: an item, or a cluster's total as pair-test --cluster flips it.
    t0 = time.time()
    p_res = stats.sign_flip_p(totals)
    s, q = math.fsum(totals), math.fsum(d * d for d in totals)
    p_apx = math.erfc(abs(s) / math.sqrt(q) / math.sqrt(2)) if q else 1.0
    row["sign_flip"] = {"resampled": p_res, "approx": p_apx, "seconds": round(time.time() - t0, 2),
                        "mc_se": math.sqrt(max(p_res * (1 - p_res), 1e-12) / stats.PERMUTATIONS)}  # fmt: skip
    m, se = stats._mean_se(totals, sizes)
    t0 = time.time()
    p_bt = stats.bootstrap_t_p(totals, sizes, 0.0)  # T = m / se, drawn above to lie between 1 and 3.5
    if p_bt is not None:
        t_obs = m / se
        row["bootstrap_t"] = {"resampled": p_bt, "approx": normal_sf(t_obs), "seconds": round(time.time() - t0, 2),
                              "mc_se": math.sqrt(max(p_bt * (1 - p_bt), 1e-12) / stats.NONINF_DRAWS)}  # fmt: skip
    row["mean"] = statistics_mean(per_item)
    return row


def statistics_mean(xs: list) -> float:
    """The mean: the sum exactly rounded (fsum), divided by the count."""
    return math.fsum(xs) / len(xs)


def summary(rows: list, test: str) -> list[str]:
    """One line per kind of data and size: the largest |resampled p - approximate p|, how many cases differ by more
    than 3 Monte Carlo SEs, and how many would decide differently at any of LEVELS."""
    out = []
    for kind in KINDS:
        for n in sorted({r["n"] for r in rows}):
            got = [r[test] for r in rows if r["kind"] == kind and r["n"] == n and test in r]
            if not got:
                continue
            diffs = [abs(g["resampled"] - g["approx"]) for g in got]
            beyond = sum(abs(g["resampled"] - g["approx"]) > 3 * g["mc_se"] for g in got)
            split = sum(any((g["resampled"] < a) != (g["approx"] < a) for a in LEVELS) for g in got)
            out.append(
                f"  {kind:<11} n={n:<6} cases {len(got):>3}  max |dp| {max(diffs):.4f}  beyond 3 MC se {beyond:>2}  "
                f"decisions that differ {split:>2}"
            )
    return out


def main() -> int:
    """Run every case, print the table, write the cases."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", default="1000,10000")
    ap.add_argument("--per", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=24)
    ap.add_argument("--out", default=str(HARNESS / ".build" / "large_sample_check.json"))
    args = ap.parse_args()
    cases = [(k, int(n), i) for n in args.sizes.split(",") for k in KINDS for i in range(args.per)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(one, cases, chunksize=1))
    _store.mkdir(Path(args.out).parent, parents=True, exist_ok=True)
    _store.write_text(Path(args.out), json.dumps(rows, indent=1))
    print(f"{len(rows)} datasets in {time.time() - t0:.0f} s; cases in {args.out}")
    print("sign-flip (two-sided), resampled against erfc(|z|/sqrt 2):")
    print("\n".join(summary(rows, "sign_flip")))
    print("bootstrap-t (one-sided, the contender test), resampled against 1 - Phi(T):")
    print("\n".join(summary(rows, "bootstrap_t")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
