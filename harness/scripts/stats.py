"""The harness's paired test, in one place: sign-flip on per-item deltas, Holm across a family.
And its rank correlation: Spearman's rho, with ties.

    from evaluation_harness.stats import sign_flip_p, holm, exact_ci, compare, spearman

Used by pair_test.py, family_test.py and the catalog's run inspector, so the command line
and the inspector cannot disagree (ADR-0002). `spearman` is the one copy rank_stability,
summeval_analysis, silver_calibrate and the judge scorer (judging.py) use.

EXACT UP TO 30 ITEMS. The two-sided p is counted over all 2^n sign patterns (meet in the
middle: two halves of at most 2^15 sums each, so it is instant). Before 0.4.0 the harness
estimated it by Monte Carlo at every n, and near a threshold the estimate can land on either
side: one pair is p 0.0254 exactly (26 of 1024 patterns, not significant at a 0.025 Holm
step) against a 20,000-permutation estimate of 0.0237 (significant). Above 30 items it is the
seeded estimate, unchanged: p = (hits + 1) / (permutations + 1).

Standard library only.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import bisect
import copy
import hashlib
import json
import math
import os
import random
import statistics
from collections import OrderedDict
from collections.abc import Callable
from itertools import chain, compress
from typing import Any

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
                            _DISK[rec["k"]] = rec["v"] if "v" in rec else float.fromhex(rec["p"])
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
    _keep(_disk_key(key), p)


def kept(algo: str, data: str, compute: Callable[[], Any]) -> Any:
    """Another test's result (JSON: its p, and what a later draw needs from it), kept in the same EVH_P_CACHE
    file: read back exactly when it is there, else computed and appended. `algo` names the test and every
    setting that changes its result (permutations, seed), `data` is its input exactly (floats as float.hex);
    a change to either is a new key."""
    k = hashlib.sha256(f"{algo}:".encode() + data.encode()).hexdigest()
    # Kept in the process too, as the sign-flip p's are (_P): a catalog build decides each goal twice (the glance
    # and its page), and without EVH_P_CACHE every bootstrap-t was drawn again, 9,999 resamples each time.
    if k in _KEPT:
        _KEPT.move_to_end(k)
        return copy.deepcopy(_KEPT[k])
    if os.environ.get("EVH_P_CACHE") and (v := _disk().get(k)) is not None:
        _remember(k, v)
        return copy.deepcopy(v)
    v = compute()
    _keep(k, v)
    _remember(k, v)
    return copy.deepcopy(v)


_KEPT: OrderedDict = OrderedDict()


def _remember(k: str, v: Any) -> None:
    _KEPT[k] = copy.deepcopy(v)
    while len(_KEPT) > _P_MAX:
        _KEPT.popitem(last=False)


def _keep(k: str, v: Any) -> None:
    path = os.environ.get("EVH_P_CACHE")
    if not path:
        return
    _disk()[k] = v
    line = {"k": k, "p": v.hex()} if isinstance(v, float) else {"k": k, "v": v}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a+b") as fh:  # one line, one write: an append
            # after a torn last line (a writer killed mid-line), start a new one
            torn = fh.tell() > 0 and (fh.seek(-1, os.SEEK_END) or fh.read(1) != b"\n")
            fh.write((b"\n" if torn else b"") + (json.dumps(line) + "\n").encode())
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
    """{name: (threshold, significant)} by Holm step-down; stops at the first p over its threshold.

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
    """A 95% interval for the mean paired difference: `cluster_ci` with every item its own cluster.

    Up to EXACT_UP_TO items it agrees with the paired test: the set of shifts d for which the
    sign-flip test on (delta - d) does not reject at alpha, found by bisection on each side of
    the mean. Above that it is a t interval, which is close to the test but not derived from it. None when no shift can be rejected at all (n=5 and below:
    the smallest attainable p is over alpha), so there is no interval to draw.
    """
    return cluster_ci(list(deltas), [1] * len(deltas), alpha)


def clustered(deltas: dict, clusters: dict) -> tuple[list[float], list[int]]:
    """Per cluster, the sum of its items' paired differences and how many items it has, in a fixed order.

    deltas: {item_id: difference}; clusters: {item_id: cluster key}. An item with no key is a cluster of
    its own. Items that share a source (one thread's comments, one document's questions) are not
    independent: testing them one by one counts the same evidence several times and makes p and the
    interval too small (Miller 2024, "Adding error bars to evals"). The test then flips one sign per
    cluster, which is valid when the clusters, not the items, are independent."""
    totals: dict = {}
    sizes: dict = {}
    for item in sorted(deltas):
        key = clusters.get(item)
        key = ("item", item) if key is None or key == "" else ("cluster", str(key))
        totals[key] = totals.get(key, 0.0) + deltas[item]
        sizes[key] = sizes.get(key, 0) + 1
    keys = sorted(totals)
    return [totals[k] for k in keys], [sizes[k] for k in keys]


def cluster_ci(totals: list, sizes: list, alpha: float = ALPHA):
    """A 95% interval for the mean per-item difference when items come in clusters.

    totals, sizes: per cluster, its summed difference and its number of items (`clustered`). Up to
    EXACT_UP_TO clusters it inverts the cluster sign-flip test: the shifts d for which the test on
    (total - d * size) does not reject at alpha. Above that it is the cluster-robust t interval (CR1:
    the clusters' residuals, G/(G-1), G-1 degrees of freedom). With one item per cluster both are the
    item-level interval exactly. None below 2 clusters, or when no shift can be rejected (5 clusters
    and fewer, where the smallest attainable p is over alpha)."""
    g, n = len(totals), sum(sizes)
    if g < 2 or min_attainable_p(g) > alpha:
        return None
    mean = math.fsum(totals) / n
    if g > EXACT_UP_TO:
        resid = [t - m * mean for t, m in zip(totals, sizes, strict=True)]
        var = g / (g - 1) * math.fsum(r * r for r in resid) / n**2
        z = 1.959964
        t = z + (z**3 + z) / (4 * (g - 1))  # Cornish-Fisher: t quantile without scipy
        half = t * math.sqrt(var)
        return [mean - half, mean + half]
    ratios = [t / m for t, m in zip(totals, sizes, strict=True)]
    span = (max(ratios) - min(ratios)) or abs(mean) or 1.0

    def rejected(d):
        return exact_p([t - d * m for t, m in zip(totals, sizes, strict=True)]) <= alpha

    lo_start, hi_start = min(ratios) - span, max(ratios) + span

    def bound(outer):
        inner = mean  # never rejected: the shifted sum is 0
        for _ in range(30):  # the interval to ~1e-9 of its span; it is shown to 3 decimals
            mid = (inner + outer) / 2
            inner, outer = (inner, mid) if rejected(mid) else (mid, outer)
        return inner

    return [bound(lo_start), bound(hi_start)]


#: The one-sided level of a non-inferiority test, and the fewest items (or clusters) a continuous measure needs
#: before one is run (RFC-015, research/internal/stats-0.8.0: below 100 the bootstrap-t did not hold its level).
NONINF_LEVEL = 0.025
NONINF_MIN_UNITS = 100
#: The floor when clusters differ in size, on their effective number: sizes 1-20 with a heavy tail of cluster losses
#: erred 0.033 at 147 effective clusters and 0.026 at 236 (1500 and 1000 simulations, nominal 0.025).
NONINF_MIN_UNEQUAL = 250
NONINF_DRAWS = 9999
_Z975 = 1.959963984540054


def is_binary(*series: dict) -> bool:
    """Every value of every series is 0 or 1 (right/wrong per item)."""
    return all(v in (0, 1, 0.0, 1.0, True, False) for x in series for v in x.values())


def tango_p(x12: int, x21: int, n: int, margin: float) -> float:
    """One-sided p of Tango's score test (1998) for paired 0/1 outcomes, H0: difference <= -margin.

    x12: items the arm got right and the reference wrong; x21: the reverse; n: all paired items. Valid with
    zero discordant items, where McNemar-type tests are not; at or below its level on every grid simulated
    (research/internal/stats-0.8.0/tango_binary.py)."""
    if n == 0:
        return 1.0
    d0 = -margin
    a = 2 * n
    b = -x12 - x21 + (2 * n - x12 + x21) * d0
    c = -x21 * d0 * (1 - d0)
    q21 = (math.sqrt(max(b * b - 4 * a * c, 0.0)) - b) / (2 * a)
    var = n * (2 * q21 + d0 * (1 - d0))
    num = x12 - x21 - n * d0
    if var <= 0:
        return 0.0 if num > 0 else 1.0
    return 0.5 * math.erfc(num / math.sqrt(var) / math.sqrt(2))


def _mean_se(totals: list, sizes: list) -> tuple[float, float]:
    """The mean per item and its (cluster-robust, CR1) standard error; with one item per cluster s/sqrt(n)."""
    g, n = len(totals), sum(sizes)
    m = math.fsum(totals) / n
    ss = math.fsum((t - k * m) ** 2 for t, k in zip(totals, sizes, strict=True))
    return m, math.sqrt(g / (g - 1) * ss) / n


def bootstrap_t_p(totals: list, sizes: list, margin: float, draws: int = NONINF_DRAWS) -> float | None:
    """One-sided p of the studentized bootstrap for H0: mean difference <= -margin (RFC-015's specification,
    resampling clusters when there are clusters). T = (m + margin)/se; t* = (m* - m)/se* over resamples, those
    with se* = 0 dropped; p = (1 + #{t* >= T})/(kept + 1). None when every unit's difference is the same (no
    test is possible). Seeded by the data, so the same comparison always gives the same p."""
    g = len(totals)
    m, se = _mean_se(totals, sizes)
    if se == 0:
        return None
    t_obs = (m + margin) / se
    data = ",".join(f"{t.hex()}/{k}" for t, k in zip(totals, sizes, strict=True)) + f"|{float(margin).hex()}"

    def compute() -> float:
        rng = random.Random(int(hashlib.sha256(data.encode()).hexdigest()[:16], 16))
        kept = beyond = 0
        for _ in range(draws):
            pick = [rng.randrange(g) for _ in range(g)]
            ms, ses = _mean_se([totals[i] for i in pick], [sizes[i] for i in pick])
            if ses == 0:
                continue
            kept += 1
            beyond += (ms - m) / ses >= t_obs
        return (1 + beyond) / (kept + 1)

    return kept(f"bootstrap-t-1:{draws}", data, compute)


REDUCERS = ("mean", "majority", "at_least_K")


def reduce_repeats(values: list, how: str = "mean") -> float:
    """One item's score from its repeats (inspect_ai's epochs reducers, under our word "repeat"): `mean` (the
    default), `majority` (1 when more than half of 0/1 repeats are 1, else 0) or `at_least_K` (1 when at least K
    of them are 1: pass@k's question, "did any of K tries work", is at_least_1). The last two are for 0/1 scores and
    refuse others."""
    if how in ("", "mean"):
        return statistics.fmean(values)
    if any(v not in (0, 1, 0.0, 1.0, True, False) for v in values):
        raise ValueError(f"reduce {how!r} is for 0/1 scores; these repeats are not")
    ones = sum(1 for v in values if v)
    if how == "majority":
        return 1.0 if ones * 2 > len(values) else 0.0
    if how.startswith("at_least_") and how[len("at_least_") :].isdigit():
        return 1.0 if ones >= int(how[len("at_least_") :]) else 0.0
    raise ValueError(f"reduce {how!r}: one of mean, majority, at_least_K (e.g. at_least_2)")


def paired_se(arm: dict, reference: dict, clusters: dict | None = None) -> float | None:
    """The standard error of the mean paired difference arm - reference over their shared items (cluster-robust
    with clusters); None below 2 units."""
    shared = sorted(set(arm) & set(reference))
    d = {i: arm[i] - reference[i] for i in shared}
    totals, sizes = clustered(d, clusters) if clusters is not None else (list(d.values()), [1] * len(d))
    if len(totals) < 2:
        return None
    return _mean_se(totals, sizes)[1]


def detectable_margin(se: float, candidates: int, power: float = 0.8, level: float = NONINF_LEVEL) -> float:
    """The smallest margin a truly equal arm can be shown within, with probability `power`, when `candidates` arms are
    tested together (Holm's first step, level / candidates, one-sided): (z_(1 - level/k) + z_power) * se. Miller 2024's
    recommendation 5 (power before running), for the contender test. A margin under it will rarely admit anyone, so
    a goal with many arms on few items says so."""
    z = statistics.NormalDist()
    return (z.inv_cdf(1 - level / max(candidates, 1)) + z.inv_cdf(power)) * se


def noninferior(
    arm: dict,
    reference: dict,
    margin: float,
    higher_is_better: bool = True,
    clusters: dict | None = None,
    level: float = NONINF_LEVEL,
) -> dict:
    """Is `arm` no worse than `reference` by more than `margin` (in the measure's units)? A one-sided test
    of H0: difference <= -margin, the difference taken in the measure's better direction.

    0/1 per item and no clusters: Tango's score test at `level`, at any size. Anything else (a continuous
    measure, repeats averaged, or clusters): the bootstrap-t at half the level, from NONINF_MIN_UNITS items or
    clusters; below that the answer is "too few", never a guess. Returns {"verdict": "non-inferior" |
    "not shown" | "too few" | "untestable", "method", "p", "level", "n", "units", "delta"}."""
    shared = sorted(set(arm) & set(reference))
    sign = 1 if higher_is_better else -1
    d = {i: (arm[i] - reference[i]) * sign for i in shared}
    out: dict = {"n": len(shared), "delta": math.fsum(d.values()) / len(d) if d else None, "margin": margin}
    if len(shared) < 2:
        return {
            **out,
            "verdict": "untestable",
            "method": None,
            "p": None,
            "level": level,
            "units": len(shared),
        }
    if clusters is None and is_binary({i: arm[i] for i in shared}, {i: reference[i] for i in shared}):
        x12 = sum(1 for v in d.values() if v > 0)
        x21 = sum(1 for v in d.values() if v < 0)
        p = tango_p(x12, x21, len(shared), margin)
        return {
            **out,
            "verdict": "non-inferior" if p <= level else "not shown",
            "method": "tango",
            "p": p,
            "level": level,
            "units": len(shared),
        }
    totals, sizes = clustered(d, clusters) if clusters is not None else (list(d.values()), [1] * len(d))
    if clusters is not None and all(k == 1 for k in sizes):
        # Every cluster one item: the item-level test exactly, Tango included, as compare() promises.
        return noninferior(arm, reference, margin, higher_is_better, None, level)
    # The units a bootstrap counts: clusters of very unequal size carry less information than their number, so the
    # floor is on the effective number (sum k)^2 / sum k^2, equal to the count only when sizes are equal. With sizes
    # 1-20 and a heavy tail of cluster losses, 100 clusters (about 60 effective) erred 0.043 at a nominal 0.025.
    effective = sum(sizes) ** 2 / sum(k * k for k in sizes)
    base = {
        **out,
        "method": "bootstrap-t",
        "level": level / 2,
        "units": len(totals),
        "effective": round(effective, 1),
    }
    floor = NONINF_MIN_UNITS if len(set(sizes)) == 1 else NONINF_MIN_UNEQUAL
    base["floor"] = floor
    if effective < floor:
        return {**base, "verdict": "too few", "p": None}
    bp = bootstrap_t_p(totals, sizes, margin)
    if bp is None:  # every unit differs by the same amount: decided by that amount alone
        return {**base, "verdict": "non-inferior" if out["delta"] > -margin else "not shown", "p": None}
    return {**base, "verdict": "non-inferior" if bp <= level / 2 else "not shown", "p": bp}


def compare(
    arms: dict,
    baseline: str,
    higher_is_better: bool = True,
    neutral: bool = False,
    family: int | None = None,
    threshold: float | None = None,
    clusters: dict | None = None,
) -> dict:
    """Test every arm against `baseline` on the items both scored; Holm across the family.

    arms: {arm_id: {item_id: float}}. clusters: {item_id: cluster key}, when items come in related
    groups: p and the interval then come from one sign per cluster (`clustered`), and each row says how
    many clusters it had. Returns {"items": [...], "rows": [...]} where each row has n (shared items),
    mean, baseline_mean, delta (arm - baseline), wins/losses/ties (by direction), p, ci, threshold,
    verdict, and with clusters "clusters".
    """
    base = arms.get(baseline) or {}
    rows, pvals = [], {}
    for arm, scores in arms.items():
        if arm == baseline:
            continue
        shared = sorted(set(scores) & set(base))
        deltas = [scores[i] - base[i] for i in shared]
        # The unit the test counts: an item, or with clusters a cluster's summed difference.
        if clusters is not None:
            units, sizes = clustered(dict(zip(shared, deltas, strict=True)), clusters)
        else:
            units, sizes = deltas, [1] * len(deltas)
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
            "min_p": min_attainable_p(len(units)),
            "ci": cluster_ci(units, sizes),
        }
        if clusters is not None:
            row["clusters"] = len(units)
        if len(units) >= 2 and any(deltas):
            row["p"] = sign_flip_p(units)
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
        row["verdict"] = "untestable" if row.get("clusters", row["n"]) < 2 else "identical"
    elif ok and neutral:  # a measurement with no better direction (length, counts)
        row["verdict"] = "significant: higher" if row["delta"] > 0 else "significant: lower"
    elif ok:
        better = (row["delta"] > 0) == higher_is_better
        row["verdict"] = "significant: better" if better else "significant: worse"
    else:
        row["verdict"] = "not significant"


def compare_by(
    arms: dict,
    baseline: str,
    groups: dict,
    higher_is_better: bool = True,
    neutral: bool = False,
    family: int | None = None,
    clusters: dict | None = None,
) -> dict:
    """`compare` within each group of items, with ONE Holm correction over every (group, arm)
    test. Breaking a comparison into k groups makes k times the chances of a false
    "significant", so the correction counts all of them, ranked together, not each group alone.

    groups: {group name: set of item ids}. Returns {"groups": [{"group", "items", "rows"}],
    "family_size"}; each row is `compare`'s, its threshold and verdict from the joint Holm.
    """
    out, pvals = [], {}
    for g, members in groups.items():
        sub = {a: {i: v for i, v in s.items() if i in members} for a, s in arms.items()}
        res = compare(sub, baseline, higher_is_better, neutral, clusters=clusters)
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
