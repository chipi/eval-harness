"""The harness's paired test, in one place: sign-flip on per-item deltas, Holm across a family.
And its rank correlation: Spearman's rho, with ties.

    from stats import sign_flip_p, holm, exact_ci, compare, spearman

Used by pair_test.py, family_test.py and the catalog's run inspector, so the command line
and the inspector cannot disagree (ADR-0002). `spearman` is the one copy rank_stability,
summeval_analysis, silver_calibrate and the judge scorer (judging.py) use.

EXACT UP TO 30 ITEMS. The two-sided p is counted over all 2^n sign patterns (meet in the
middle: two halves of at most 2^15 sums each, so it is instant). Before 0.4.0 the harness
estimated it by Monte Carlo at every n, and near a threshold the estimate can land on either
side: one pair is p 0.0254 exactly (26 of 1024 patterns, not separated at a 0.025 Holm
step) against a 20,000-permutation estimate of 0.0237 (separated). Above 30 items it is the
seeded estimate, unchanged: p = (hits + 1) / (permutations + 1).

Standard library only.
"""

from __future__ import annotations

import bisect
import math
import random
import statistics

PERMUTATIONS = 20000
SEED = 20260926
ALPHA = 0.05
EXACT_UP_TO = 30
_EPS = 1e-12


def ranks(xs) -> list:
    """1-based ranks, ascending, tied values sharing the average of the ranks they span
    (midranks). Ranking a list of midranks gives the same list back."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(xs, ys, constant: float = math.nan) -> float:
    """Pearson's r. When either side has no spread (or there are fewer than two values) there is
    nothing to correlate and `constant` is returned: NaN by default, because 0.0 reads as "no
    agreement" when nothing was asked. A caller that reports 0.0 there says so explicitly."""
    if len(xs) != len(ys):
        raise ValueError(f"correlation: {len(xs)} values against {len(ys)}")
    if len(xs) < 2:
        return constant
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return constant
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / math.sqrt(sxx * syy)


def spearman(xs, ys, constant: float = math.nan) -> float:
    """Spearman's rho: Pearson's r on the two lists' midranks, which is exact with ties (the
    `1 - 6*sum(d^2)/(n(n^2-1))` shortcut is not). `constant` as for `pearson`."""
    if len(xs) != len(ys):
        raise ValueError(f"correlation: {len(xs)} values against {len(ys)}")
    return pearson(ranks(xs), ranks(ys), constant)


def _signed_sums(xs: list) -> list:
    """Every sum of +-x over xs (2^len values), built by doubling: each element adds itself to,
    and subtracts itself from, every sum so far. The same multiset of sums as enumerating each
    sign pattern, ~20x faster, which is what makes the exact interval (a bisection of exact
    p-values) take about a second instead of ten at 30 items."""
    sums = [0.0]
    for x in xs:
        sums = [s + x for s in sums] + [s - x for s in sums]
    return sums


def exact_p(deltas: list) -> float:
    """Exact two-sided sign-flip p: the share of all 2^n sign patterns with |sum| >= |observed|."""
    n = len(deltas)
    if n == 0:
        return 1.0
    obs = abs(sum(deltas)) - _EPS * max(1.0, abs(sum(deltas)))
    if obs <= 0:  # no difference at all: every pattern is at least as extreme
        return 1.0
    half = n // 2
    left = _signed_sums(deltas[:half])
    right = sorted(_signed_sums(deltas[half:]))
    hits = 0
    for x in left:  # count r with x + r >= obs or x + r <= -obs
        hits += len(right) - bisect.bisect_left(right, obs - x)
        hits += bisect.bisect_right(right, -obs - x)
    return hits / 2**n


def sign_flip_p(
    deltas: list,
    permutations: int = PERMUTATIONS,
    seed: int = SEED,
    rng: random.Random | None = None,
) -> float:
    """Two-sided paired sign-flip p: exact up to EXACT_UP_TO items, else a seeded estimate.

    rng: a generator shared across calls, for callers whose published estimates drew every
    opponent from one stream (family_test.py); otherwise a fresh one seeded with `seed`.
    """
    if not deltas:
        return 1.0
    if len(deltas) <= EXACT_UP_TO:
        return exact_p(deltas)
    obs = statistics.fmean(deltas)
    rng = rng or random.Random(seed)
    hits = sum(
        1
        for _ in range(permutations)
        if abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in deltas)) >= abs(obs)
    )
    return (hits + 1) / (permutations + 1)


def fmt_p(p: float) -> str:
    """A p-value as every command prints it: four decimals, and "<0.0001" for what would print
    as 0.0000 (a p is never zero). Every other value prints exactly as it always has."""
    s = f"{p:.4f}"
    return "<0.0001" if s == "0.0000" else s


def holm(pvalues: dict, alpha: float = ALPHA, family: int | None = None) -> dict:
    """{name: (threshold, separated)} by Holm step-down; stops at the first p over its threshold.

    family: the number of comparisons being corrected for, when it is larger than the ones
    passed (a pair opened from a page that tested many keeps that page's correction).
    """
    out, m, stopped = {}, max(len(pvalues), family or 0), False
    for i, (name, p) in enumerate(sorted(pvalues.items(), key=lambda kv: kv[1])):
        thr = alpha / (m - i)
        ok = not stopped and p <= thr
        stopped = stopped or not ok
        out[name] = (thr, ok)
    return out


def min_attainable_p(n: int) -> float:
    """The smallest two-sided p a paired sign-flip test can return on n items."""
    return 2 / 2**n if n else 1.0


def exact_ci(deltas: list, alpha: float = ALPHA):
    """Interval for the mean paired difference that agrees with the paired test.

    The set of shifts d for which the sign-flip test on (delta - d) does not reject at
    alpha: exact up to EXACT_UP_TO items (found by bisection on each side of the mean),
    a t interval above that. None when no shift can be rejected at all (n=5 and below:
    the smallest attainable p is over alpha), so there is no interval to draw.
    """
    n = len(deltas)
    if n < 2 or min_attainable_p(n) > alpha:
        return None
    mean = statistics.fmean(deltas)
    if n > EXACT_UP_TO:
        sd = statistics.stdev(deltas)
        z = 1.959964
        t = z + (z**3 + z) / (4 * (n - 1))  # Cornish-Fisher: t quantile without scipy
        half = t * sd / math.sqrt(n)
        return [mean - half, mean + half]
    span = (max(deltas) - min(deltas)) or abs(mean) or 1.0

    def rejected(d):
        return exact_p([x - d for x in deltas]) <= alpha

    def bound(outer):
        inner = mean  # never rejected: the shifted sum is 0
        for _ in range(30):  # the interval to ~1e-9 of its span; it is shown to 3 decimals
            mid = (inner + outer) / 2
            inner, outer = (inner, mid) if rejected(mid) else (mid, outer)
        return inner

    return [bound(min(deltas) - span), bound(max(deltas) + span)]


def compare(
    arms: dict,
    baseline: str,
    higher_is_better: bool = True,
    neutral: bool = False,
    family: int | None = None,
    threshold: float | None = None,
) -> dict:
    """Test every arm against `baseline` on the items both scored; Holm across the family.

    arms: {arm_id: {item_id: float}}. Returns {"items": [...], "rows": [...]} where each row
    has n (shared items), mean, baseline_mean, delta (arm - baseline), wins/losses/ties
    (by direction), p, threshold, verdict.
    """
    base = arms.get(baseline) or {}
    rows, pvals = [], {}
    for arm, scores in arms.items():
        if arm == baseline:
            continue
        shared = sorted(set(scores) & set(base))
        deltas = [scores[i] - base[i] for i in shared]
        sign = 1 if higher_is_better else -1
        row = {
            "arm": arm,
            "n": len(shared),
            "mean": statistics.fmean(scores[i] for i in shared) if shared else None,
            "baseline_mean": statistics.fmean(base[i] for i in shared) if shared else None,
            "delta": statistics.fmean(deltas) if deltas else None,
            "wins": sum(1 for d in deltas if d * sign > 0),
            "losses": sum(1 for d in deltas if d * sign < 0),
            "ties": sum(1 for d in deltas if d == 0),
            "min_p": min_attainable_p(len(shared)),
            "ci": exact_ci(deltas),
        }
        if len(shared) >= 2 and any(deltas):
            row["p"] = sign_flip_p(deltas)
            pvals[arm] = row["p"]
        else:
            row["p"] = None
        rows.append(row)
    verdicts = holm(pvals, family=family)
    if threshold is not None:
        # A pair opened from a page that tested many: the page's Holm threshold for this row,
        # so the verdict is the same one the page showed (family size alone loses the rank).
        verdicts = {a: (threshold, p <= threshold) for a, p in pvals.items()}
    for row in rows:
        thr, ok = verdicts.get(row["arm"], (None, False))
        _set_verdict(row, thr, ok, higher_is_better, neutral)
    items = sorted(set().union(*(set(s) for s in arms.values()))) if arms else []
    return {"items": items, "rows": rows, "family_size": max(len(pvals), family or 0)}


def _set_verdict(row: dict, thr, ok: bool, higher_is_better: bool, neutral: bool) -> None:
    row["threshold"] = thr
    if row["p"] is None:
        row["verdict"] = "untestable" if row["n"] < 2 else "identical"
    elif ok and neutral:  # a measurement with no better direction (length, counts)
        row["verdict"] = "separated: higher" if row["delta"] > 0 else "separated: lower"
    elif ok:
        better = (row["delta"] > 0) == higher_is_better
        row["verdict"] = "separated: better" if better else "separated: worse"
    else:
        row["verdict"] = "not separated"


def compare_by(
    arms: dict,
    baseline: str,
    groups: dict,
    higher_is_better: bool = True,
    neutral: bool = False,
    family: int | None = None,
) -> dict:
    """`compare` within each group of items, with ONE Holm correction over every (group, arm)
    test. Breaking a comparison into k groups makes k times the chances of a false
    "separated", so the correction counts all of them, ranked together, not each group alone.

    groups: {group name: set of item ids}. Returns {"groups": [{"group", "items", "rows"}],
    "family_size"}; each row is `compare`'s, its threshold and verdict from the joint Holm.
    """
    out, pvals = [], {}
    for g, members in groups.items():
        sub = {a: {i: v for i, v in s.items() if i in members} for a, s in arms.items()}
        res = compare(sub, baseline, higher_is_better, neutral)
        for row in res["rows"]:
            if row["p"] is not None:
                pvals[(g, row["arm"])] = row["p"]
        out.append({"group": g, "items": len(set(sub.get(baseline) or {})), "rows": res["rows"]})
    verdicts = holm(pvals, family=family)
    for grp in out:
        for row in grp["rows"]:
            thr, ok = verdicts.get((grp["group"], row["arm"]), (None, False))
            _set_verdict(row, thr, ok, higher_is_better, neutral)
    return {"groups": out, "family_size": max(len(pvals), family or 0)}
