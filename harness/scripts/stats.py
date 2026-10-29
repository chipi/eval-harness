"""The harness's paired test, in one place: sign-flip on per-item deltas, Holm across a family.
And its rank correlation: Spearman's rho, with ties.

    from evaluation_harness.stats import sign_flip_p, holm, exact_ci, compare, spearman

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

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import bisect
import hashlib
import json
import math
import os
import random
import statistics
from collections import OrderedDict
from itertools import chain, compress

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
    if rng is None:
        # A fresh generator seeded with `seed` draws the same signs for every call with as many
        # items, so they are drawn once (_signs) and each permutation's mean is summed in C. The
        # same draws in the same order; an item keeps its delta or takes its negation (both
        # exact), and fsum is exactly rounded whatever order it reads the values in: the same
        # p, bit for bit, many times faster.
        key = (tuple(deltas), permutations, seed)
        if key in _P:
            _P.move_to_end(key)
            return _P[key]
        stored = _stored_p(key)
        if stored is None:
            n, a = len(deltas), abs(obs)
            neg = [-d for d in deltas]
            hits = sum(
                1
                for keep in _signs(n, permutations, seed)
                if abs(math.fsum(chain(compress(deltas, keep), compress(neg, keep.translate(_FLIP)))) / n)
                >= a
            )
            stored = (hits + 1) / (permutations + 1)
            _store_p(key, stored)
        _P[key] = stored
        while len(_P) > _P_MAX:
            _P.popitem(last=False)
        return _P[key]
    # The shared stream: the signs fmean(d if rng.random() < 0.5 else -d ...) drew, from _draw,
    # summed as above (fmean is fsum / n). The same p, and the same generator state after, so the
    # next opponent's draws are unchanged too.
    n, a = len(deltas), abs(obs)
    neg = [-d for d in deltas]
    hits = 0
    for _ in range(permutations):
        keep = _draw(rng, n)
        if abs(math.fsum(chain(compress(deltas, keep), compress(neg, keep.translate(_FLIP)))) / n) >= a:
            hits += 1
    return (hits + 1) / (permutations + 1)


#: Estimated p by (deltas, permutations, seed): a page and the glance test the same pairs.
#: Both caches are bounded, least recently used out first, and a sign is one byte. As tuples of
#: ±1.0 a table was ~31 MB at n=200 and was kept for every item count ever seen: a long-running
#: inspector meets many, and grew past its 256 MiB limit until the kernel killed it every few
#: minutes. A dropped table is drawn again from the same seed, so a p never changes, only speed.
_P: OrderedDict = OrderedDict()
_P_MAX = 4096

#: A file of estimated p's that outlives the process: `EVH_P_CACHE=<path>`, one JSON line per p,
#: {"k": sha256 of the deltas (as float.hex), permutations and seed; "p": the p as float.hex}. Each
#: `evh` command is a fresh process, so without it every `evh goals` (and every MCP call, RFC-018)
#: drew the same ~500 tests again (about 50 s here). A stored p is the one the test computed, read
#: back exactly; the file is read once, appended when writable, and only read when it is not (a
#: deployment precomputes it). Unset: nothing is stored. A file that cannot be read is no cache.
_DISK: dict | None = None
#: Part of every key: a change to how a p is computed (the draw, the exact cut-off) is a new key,
#: so a file written by the old code is never read as the new code's answer.
_P_ALGO = f"sign-flip-1:exact<={EXACT_UP_TO}"


def _disk_key(key: tuple) -> str:
    deltas, permutations, seed = key
    h = hashlib.sha256(f"{_P_ALGO}:{permutations}:{seed}:".encode())
    h.update(",".join(float(d).hex() for d in deltas).encode())
    return h.hexdigest()


def _disk() -> dict:
    global _DISK
    if _DISK is None:
        _DISK = {}
        path = os.environ.get("EVH_P_CACHE")
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            rec = json.loads(line)
                            _DISK[rec["k"]] = float.fromhex(rec["p"])
                        except (ValueError, KeyError, TypeError):
                            continue  # a torn line from an interrupted writer
            except (OSError, ValueError):  # unreadable, or not UTF-8: computed, not read
                _DISK = {}
    return _DISK


def _stored_p(key: tuple) -> float | None:
    if not os.environ.get("EVH_P_CACHE"):
        return None
    return _disk().get(_disk_key(key))


def _store_p(key: tuple, p: float) -> None:
    path = os.environ.get("EVH_P_CACHE")
    if not path:
        return
    k = _disk_key(key)
    _disk()[k] = p
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a+b") as fh:  # one short line: an atomic append
            # after a torn last line (a writer killed mid-line), start a new one
            torn = fh.tell() > 0 and (fh.seek(-1, os.SEEK_END) or fh.read(1) != b"\n")
            fh.write((b"\n" if torn else b"") + (json.dumps({"k": k, "p": p.hex()}) + "\n").encode())
    except OSError:
        pass  # read-only (a deployment's precomputed file): the p is still right, only not kept


_SIGNS: OrderedDict = OrderedDict()
_SIGNS_MAX = 2
_FLIP = bytes.maketrans(b"\x00\x01", b"\x01\x00")
_TOP_BIT_CLEAR = bytes(int(b < 128) for b in range(256))


def _draw(rng: random.Random, n: int) -> bytes:
    """n signs from rng, exactly as n calls of `rng.random() < 0.5` draw them: 1 keeps an item's
    sign, 0 flips it.

    CPython's random() is (a >> 5, b >> 6) of two 32-bit Mersenne Twister words scaled by 2**-53,
    so it is below 0.5 exactly when a's top bit is clear; getrandbits(64 * n) takes the same 2n
    words in the same order (word i at bits 32i..32i+31), so byte 3 of every 8 is that top byte.
    One call in C instead of n in Python (family_test's 116 million draws were ~7 s a family),
    and the generator is left where the n calls leave it. A generator that defines its own
    random() or getrandbits() is drawn the slow way."""
    t = type(rng)
    if t.random is random.Random.random and t.getrandbits is random.Random.getrandbits:
        return rng.getrandbits(64 * n).to_bytes(8 * n, "little")[3::8].translate(_TOP_BIT_CLEAR)
    return bytes(rng.random() < 0.5 for _ in range(n))


def _signs(n: int, permutations: int, seed: int) -> list:
    """The signs a fresh random.Random(seed) gives `permutations` passes over n items, in the
    order sign_flip_p draws them: one bytes per pass, 1 where a draw below 0.5 keeps the item's
    sign and 0 where it flips. Kept for the last _SIGNS_MAX (n, permutations, seed)."""
    key = (n, permutations, seed)
    if key in _SIGNS:
        _SIGNS.move_to_end(key)
        return _SIGNS[key]
    rng = random.Random(seed)
    _SIGNS[key] = [_draw(rng, n) for _ in range(permutations)]
    while len(_SIGNS) > _SIGNS_MAX:
        _SIGNS.popitem(last=False)
    return _SIGNS[key]


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
    """A 95% interval for the mean paired difference.

    Up to EXACT_UP_TO items it agrees with the paired test: the set of shifts d for which the
    sign-flip test on (delta - d) does not reject at alpha, found by bisection on each side of
    the mean. Above that it is a t interval, which is close to the test but not derived from it. None when no shift can be rejected at all (n=5 and below:
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
