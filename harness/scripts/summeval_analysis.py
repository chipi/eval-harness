#!/usr/bin/env python3
"""The derived SummEval figures, recomputed from the committed runs. $0, no network.

    python scripts/summeval_analysis.py

Everything REPORT_SUMMEVAL.md states that is not one run's own metric: the split-half
stability of the judges' order, price against quality, the family ladders, the
per-dimension leaders, and tie rate against quality. `check_report_claims.py` imports
`compute()` and compares the report with it, so these figures are checked the way the
leaderboard rows are, rather than copied once from a scratch script.

The split-half draw is seeded, so the same runs always give the same figures.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "data" / "runs"
DATASET, PREFIX, SUFFIX = "summeval_100", "se_", "_n100_v1"
FREE = {"bartscore", "unieval", "unievalpub", "rouge1", "rouge2", "rougeL", "coverage", "length", "random"}
DIMENSIONS = ("coherence", "consistency", "fluency", "relevance")
FAMILIES = ("anthropic", "deepseek", "gemma", "glm", "llama", "mistral", "openai", "qwen")
#: qwen_l's model was withdrawn before this run; qwen37max is the large Qwen judge here.
LARGE = {"qwen": "qwen37max"}
SEED, DRAWS, HALVES = 20261018, 400, (10, 20, 50)


def _ranks(x: list) -> list:
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a: list, b: list) -> float:
    """Spearman rank correlation coefficient."""
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def split_half(scores: dict, items: list, n: int, rng: random.Random) -> dict:
    """{rho, p5, same_winner} over DRAWS pairs of disjoint n-item halves.
    scores: arm -> {item_id -> per-item score}."""
    names = sorted(scores)
    rhos, same = [], 0
    for _ in range(DRAWS):
        pick = rng.sample(items, 2 * n)
        a_half, b_half = pick[:n], pick[n:]
        sa = [statistics.fmean(scores[a][i] for i in a_half) for a in names]
        sb = [statistics.fmean(scores[a][i] for i in b_half) for a in names]
        rhos.append(spearman(sa, sb))
        same += names[sa.index(max(sa))] == names[sb.index(max(sb))]
    rhos.sort()
    return {"rho": statistics.fmean(rhos), "p5": rhos[DRAWS // 20], "same_winner": same / DRAWS}


def summarisation_hosted(n: int = 20) -> dict:
    """The same split-half for the summarisation experiment's hosted arms -- the same 24
    models -- so the two experiments' stability is compared like for like. Its report's
    own figure (0.443) is over all 29 arms, local ones included."""
    scores = {}
    for mj in sorted(RUNS.glob("cnn_*_n200_v1_*/metrics.json")):
        if "20260929" in mj.parent.name:
            continue  # the 2026-09-29 re-runs duplicate arms; every other check skips them too
        m = json.loads(mj.read_text(encoding="utf-8"))
        if m.get("dataset_id") != "cnn_dailymail_200" or (m.get("params") or {}).get("provider") != "litellm":
            continue
        rows = {}
        for line in (mj.parent / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["item_id"]] = r["coverage"]
        scores[m["config_id"]] = rows
    items = sorted(next(iter(scores.values())))
    return {"n_arms": len(scores), **split_half(scores, items, n, random.Random(SEED))}


def sign_flip(deltas: list, permutations: int, rng: random.Random) -> float:
    """Two-sided paired sign-flip permutation p, as scripts/family_test.py computes it."""
    obs = abs(statistics.fmean(deltas))
    hits = sum(
        1
        for _ in range(permutations)
        if abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in deltas)) >= obs
    )
    return (hits + 1) / (permutations + 1)


def tier_tests(per_item: dict, items: list, permutations: int = 20000) -> dict:
    """Large tier against small, per family: paired over articles, Holm over the eight."""
    rng = random.Random(SEED)
    out = {}
    for fam in FAMILIES:
        lg, sm = LARGE.get(fam, f"{fam}_l"), f"{fam}_s"
        if lg in per_item and sm in per_item:
            d = [per_item[lg][i] - per_item[sm][i] for i in items]
            out[fam] = {"delta": statistics.fmean(d), "p": sign_flip(d, permutations, rng)}
    m = len(out)
    for k, (_fam, v) in enumerate(sorted(out.items(), key=lambda kv: kv[1]["p"])):
        v["holm_threshold"] = 0.05 / (m - k)
    stop = False
    for _fam, v in sorted(out.items(), key=lambda kv: kv[1]["p"]):
        stop = stop or v["p"] > v["holm_threshold"]
        v["separated"] = not stop
    return out


def load() -> dict:
    """arm -> {"scores", "rows" (item_id -> prediction row), "billed"}."""
    arms = {}
    for mj in sorted(RUNS.glob(f"{PREFIX}*{SUFFIX}_*/metrics.json")):
        m = json.loads(mj.read_text(encoding="utf-8"))
        if m.get("dataset_id") != DATASET:
            continue
        arm = m["config_id"][len(PREFIX) : -len(SUFFIX)]
        if arm in arms:
            raise SystemExit(f"two runs for {m['config_id']}: cannot pick one")
        rows, billed = {}, 0.0
        for line in (mj.parent / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["item_id"]] = r
                billed += float(((r.get("_meta") or {}).get("usage") or {}).get("cost") or 0)
        arms[arm] = {"scores": m["scores"], "rows": rows, "billed": billed}
    return arms


def compute() -> dict:
    """All derived SummEval figures: stability, ladders, tier tests, per-dimension leaders."""
    arms = load()
    judges = {a: v for a, v in arms.items() if a not in FREE}
    names = sorted(judges)
    items = sorted(next(iter(judges.values()))["rows"])

    rng = random.Random(SEED)
    per_item = {a: {i: r["tau"] for i, r in judges[a]["rows"].items()} for a in names}
    stability = {n: split_half(per_item, items, n, rng) for n in HALVES}

    cost = [judges[a]["billed"] for a in names]
    tau = [judges[a]["scores"]["tau"] for a in names]
    dearest = max(names, key=lambda a: judges[a]["billed"])
    cheapest = min(names, key=lambda a: judges[a]["billed"])
    ladders = {}
    for fam in FAMILIES:
        tiers = {"s": f"{fam}_s", "m": f"{fam}_m", "l": LARGE.get(fam, f"{fam}_l")}
        ladders[fam] = {t: judges[a]["scores"]["tau"] for t, a in tiers.items() if a in judges}
    dims = {}
    for d in DIMENSIONS:
        k = f"tau_{d}"
        best = max(names, key=lambda a: judges[a]["scores"][k])
        worst = min(names, key=lambda a: judges[a]["scores"][k])
        dims[d] = {
            "best": best,
            "best_tau": judges[best]["scores"][k],
            "worst": worst,
            "worst_tau": judges[worst]["scores"][k],
        }
    return {
        "arms": {a: {"scores": v["scores"], "billed": v["billed"]} for a, v in arms.items()},
        "n_judges": len(names),
        "n_items": len(items),
        "stability": stability,
        "summarisation_hosted_20": summarisation_hosted(20),
        "spearman_cost_tau": spearman(cost, tau),
        "price_range": judges[dearest]["billed"] / judges[cheapest]["billed"],
        "dearest": dearest,
        "cheapest": cheapest,
        "spearman_tie_rate_tau": spearman([judges[a]["scores"]["tie_rate"] for a in names], tau),
        "ladders": ladders,
        "tier_tests": tier_tests(per_item, items),
        "dimensions": dims,
        "total_billed": sum(cost),
    }


def main() -> int:
    """Print the derived SummEval figures."""
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return 0
    f = compute()
    print(f"{f['n_judges']} hosted judges, {f['n_items']} articles, ${f['total_billed']:.4f} billed")
    print(f"\nsplit-half stability of the judges' order ({DRAWS} draws, seed {SEED})")
    for n, s in f["stability"].items():
        print(
            f"  {n:3d} articles per half   rho {s['rho']:.3f}   5th pct {s['p5']:.3f}"
            f"   same unique winner {s['same_winner']:.0%}"
        )
    sh = f["summarisation_hosted_20"]
    print(f"  the summarisation experiment's {sh['n_arms']} hosted arms, 20 per half: rho {sh['rho']:.3f}")
    print(
        f"\nSpearman(billed cost, tau) = {f['spearman_cost_tau']:+.3f} over a "
        f"{f['price_range']:.1f}x price range ({f['dearest']} / {f['cheapest']})"
    )
    print(f"Spearman(tie rate, tau)    = {f['spearman_tie_rate_tau']:+.3f}")
    print("\nfamily ladders, tau by tier")
    for fam, lad in f["ladders"].items():
        print(f"  {fam:9s} " + "  ".join(f"{t} {v:.4f}" for t, v in lad.items()))
    print("\nlarge tier against small, paired over articles, Holm over the eight")
    for fam, t in sorted(f["tier_tests"].items(), key=lambda kv: kv[1]["p"]):
        print(
            f"  {fam:9s} {t['delta']:+.4f}  p {t['p']:.4f}  threshold {t['holm_threshold']:.4f}  "
            f"{'separated' if t['separated'] else 'not separated'}"
        )
    print("\nper-dimension leaders among the judges")
    for d, r in f["dimensions"].items():
        print(f"  {d:11s} best {r['best']} {r['best_tau']:.4f}   worst {r['worst']} {r['worst_tau']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
