"""The contender test with clusters (`stats.noninferior`, the harness's own code: its floors, the bootstrap-t at half the
level) at a true difference exactly at -margin, so every "non-inferior" is a type I error, over cluster sizes and shapes
beyond the 100 clusters of 3 checked before (PLAN_0.8.0, "not done": the clustered bootstrap-t at other sizes).

Each item's difference is -margin + its cluster's shift + its own noise (both mean 0), so the mean difference per item
is -margin whatever the sizes. B is 1,999 (the harness draws 9,999): at a one-sided 1.25% the p granularity, 1/2000,
does not move a decision that matters to the rate, and 9,999 would make the grid take hours in pure Python.

    python research/internal/stats-0.8.0/bootstrap_clusters.py [--sims 1500] [--workers N] [--only SHAPE]

Prints one row per scenario: the clusters, their sizes, the effective number, the share refused as "too few", and the
type I error with its Monte Carlo 95% interval; the level a valid test keeps is 0.025.
"""

import argparse
import functools
import math
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "harness"))
os.environ["EVH_P_CACHE"] = ""
os.environ["EVH_WORKERS"] = "1"
from evaluation_harness import stats

MARGIN, SD = 0.02, 0.05
B = 1999


def sizes_of(shape: str, units: int, rng: random.Random) -> list[int]:
    if shape.startswith("equal "):
        return [int(shape.split()[1])] * units
    if shape == "uniform 1-20":
        return [rng.randint(1, 20) for _ in range(units)]
    if shape == "geometric, mean 5":
        return [min(1 + int(rng.expovariate(1 / 4)), 60) for _ in range(units)]
    if shape == "one of 100, the rest 2":
        return [100] + [2] * (units - 1)
    raise ValueError(shape)


def noise(kind: str, rng: random.Random) -> float:
    if kind == "normal":
        return rng.gauss(0, SD)
    if kind == "losses with a long tail":  # a lognormal tail of losses, mean 0, sd SD
        s = 1.0
        mean = math.exp(s * s / 2)
        scale = SD / math.sqrt((math.exp(s * s) - 1) * math.exp(s * s))
        return -(rng.lognormvariate(0, s) - mean) * scale
    raise ValueError(kind)


def one(sc: dict, rng: random.Random) -> str:
    """One simulated comparison: 'rejected', 'too few' or 'kept'."""
    sizes = sizes_of(sc["shape"], sc["units"], rng)
    arm, ref, clusters = {}, {}, {}
    i = 0
    for c, k in enumerate(sizes):
        shift = rng.gauss(0, sc["shift"])
        for _ in range(k):
            if sc["noise"] == "0/1":
                # 0/1 scores: the reference right with 0.8, the arm with 0.78 plus the cluster's shift (clipped)
                p_arm = min(max(0.78 + shift, 0.0), 1.0)
                arm[i], ref[i] = float(rng.random() < p_arm), float(rng.random() < 0.80)
            else:
                ref[i] = 0.5
                arm[i] = 0.5 - MARGIN + shift + noise(sc["noise"], rng)
            clusters[i] = f"c{c}"
            i += 1
    v = stats.noninferior(arm, ref, MARGIN, True, clusters)["verdict"]
    return "rejected" if v == "non-inferior" else "too few" if v == "too few" else "kept"


def chunk(args: tuple) -> dict:
    sc, n, seed = args
    stats.bootstrap_t_p = functools.partial(_ORIGINAL, draws=B)
    rng = random.Random(seed)
    out = {"rejected": 0, "too few": 0, "kept": 0}
    for _ in range(n):
        out[one(sc, rng)] += 1
    return out


_ORIGINAL = stats.bootstrap_t_p

SCENARIOS = (
    [{"shape": f"equal {k}", "units": u, "shift": s, "noise": "normal"} for k in (2, 3, 8, 20) for u in (100, 300) for s in (0.01, 0.05)]
    + [{"shape": "equal 3", "units": 150, "shift": 0.05, "noise": "normal"}]
    + [{"shape": sh, "units": u, "shift": 0.03, "noise": "normal"} for sh, us in (("uniform 1-20", (400, 500)), ("geometric, mean 5", (500, 800)), ("one of 100, the rest 2", (1000, 1500))) for u in us]
    + [{"shape": "equal 3", "units": u, "shift": 0.03, "noise": "losses with a long tail"} for u in (100, 300)]
    + [{"shape": "uniform 1-20", "units": 400, "shift": 0.03, "noise": "losses with a long tail"}]
    + [{"shape": "equal 5", "units": u, "shift": 0.05, "noise": "0/1"} for u in (100, 300)]
)  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--only", default="", help="only the scenarios whose shape contains this")
    args = ap.parse_args()
    scenarios = [sc for sc in SCENARIOS if args.only in sc["shape"]]
    per = 50
    jobs = []
    for j, sc in enumerate(scenarios):
        for c in range(math.ceil(args.sims / per)):
            jobs.append((j, (sc, min(per, args.sims - c * per), 20261111 + 1000 * j + c)))
    totals = [{"rejected": 0, "too few": 0, "kept": 0} for _ in scenarios]
    with ProcessPoolExecutor(args.workers) as ex:
        for (j, _a), got in zip(jobs, ex.map(chunk, [a for _, a in jobs]), strict=True):
            for k, v in got.items():
                totals[j][k] += v
    print(
        f"{'shape':24} {'units':>5} {'shift':>5} {'noise':24} {'eff':>6} {'too few':>8} {'type I':>7}  95% MC interval"
    )
    for sc, t in zip(scenarios, totals, strict=True):
        n = sum(t.values())
        rate = t["rejected"] / n
        half = 1.96 * math.sqrt(max(rate * (1 - rate), 1e-9) / n)
        sz = sizes_of(sc["shape"], sc["units"], random.Random(1))
        eff = sum(sz) ** 2 / sum(k * k for k in sz)
        flag = "  ABOVE 0.025" if rate - half > 0.025 else ""
        print(
            f"{sc['shape']:24} {sc['units']:>5} {sc['shift']:>5} {sc['noise']:24} {eff:>6.0f} {t['too few'] / n:>8.3f} "
            f"{rate:>7.4f}  [{max(rate - half, 0):.4f}, {rate + half:.4f}]{flag}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
