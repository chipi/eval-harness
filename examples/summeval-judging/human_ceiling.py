#!/usr/bin/env python3
"""How well does one expert agree with the other two? The human ceiling for a judge's τ.

    python examples/summeval-judging/human_ceiling.py

WHY
  A judge's τ against the expert means says how it ranks, not how close that is to
  expert-level: without knowing how well the experts agree with each other, τ 0.54 has
  nothing to be compared with. The gold this experiment scores against keeps only the mean
  of the three experts, so that question cannot be answered from it.

WHAT IT MEASURES
  SummEval's original release publishes each expert's own 1-5 scores. For every article,
  dimension and expert, this takes Kendall τ-b over the 16 summaries between that expert
  and the mean of the OTHER two — leave-one-out, so no expert is compared with itself —
  then averages exactly as a judge's `tau` is averaged: over the four dimensions per
  article, then over articles. The τ-b is the adapter's own function.

  Before using the file it checks that the mean of its three experts reproduces this
  experiment's gold, article by article and dimension by dimension, so the ceiling is
  about the same data the judges were scored on.

  One bias, stated rather than corrected: a judge is compared with the mean of three
  experts, and one expert here with the mean of two, which is a noisier target. The
  ceiling is therefore somewhat pessimistic.

  Downloads the 5.8 MB annotation file (MIT) once into harness/data/sources/ (gitignored);
  no model, $0. Writes docs/evidence/summeval_human_ceiling.json, which
  check_report_claims reads.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import random
import statistics
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
URL = "https://storage.googleapis.com/sfr-summarization-repo-research/model_annotations.aligned.jsonl"
CACHE = ROOT / "harness" / "data" / "sources" / "summeval_original" / "model_annotations.aligned.jsonl"
GOLD = ROOT / "harness" / "data" / "references" / "gold" / "summeval_100"
MATERIALIZED = ROOT / "harness" / "data" / "materialized" / "summeval_100"
RUNS = ROOT / "harness" / "data" / "runs"
OUT = ROOT / "docs" / "evidence" / "summeval_human_ceiling.json"


def _adapter():
    spec = importlib.util.spec_from_file_location("se_adapter", HERE / "adapter.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["se_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


def _article_key(item_id: str) -> str:
    return item_id.split("-test-", 1)[1]


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def main() -> int:
    ad = _adapter()
    if not CACHE.is_file():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=120) as r:  # a constant https URL  # nosec B310
            CACHE.write_bytes(r.read())
    raw = CACHE.read_bytes()
    original: dict = {}
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            original.setdefault(_article_key(row["id"]), []).append(
                (_norm(row["decoded"]), row["expert_annotations"])
            )

    # Each of our 16 summaries matched to its row in the original by its TEXT, not by
    # position: the two releases need not list an article's summaries in the same order.
    # Text alone is not enough. In 37 articles two or more systems wrote the same summary
    # word for word -- and the experts often scored the copies differently. Inside such a
    # group, the rows are assigned so that each one's expert mean reproduces our gold at
    # that position; a group where more than one assignment does is counted, not hidden.
    def mean_of(ann, d):
        return statistics.fmean(e[d] for e in ann)

    items, duplicate_groups, ambiguous_groups, scored_differently = {}, 0, 0, 0
    for gp in sorted(GOLD.glob("*.txt")):
        key = _article_key(gp.stem)
        item = ad._item((MATERIALIZED / gp.name).read_text(encoding="utf-8"))
        gold_ref = json.loads(gp.read_text())
        rows = original.get(key, [])
        experts = [None] * ad.N_SUMMARIES
        texts = [_norm(t) for t in item["summaries"]]
        for text in sorted(set(texts)):
            ours = [i for i, t in enumerate(texts) if t == text]
            theirs = [ann for t, ann in rows if t == text]
            if len(ours) != len(theirs):
                raise SystemExit(f"{key}: {len(ours)} copies of a summary here, {len(theirs)} there")
            if len(ours) > 1:
                duplicate_groups += 1
                # Order-proof: the copies' expert MEANS, which is what the gold is. Comparing
                # the annotation lists would count the same three scores in another order
                # as a disagreement, and the file does not document its annotator order.
                scored_differently += any(
                    any(abs(mean_of(a, d) - mean_of(theirs[0], d)) > 1e-9 for d in ad.DIMS)
                    for a in theirs[1:]
                )
            fits = [
                perm
                for perm in itertools.permutations(theirs)
                if all(
                    abs(mean_of(a, d) - gold_ref[d][i]) < 1e-6 for i, a in zip(ours, perm) for d in ad.DIMS
                )
            ]
            if not fits:
                raise SystemExit(f"{key}: no assignment of a duplicate group reproduces the gold")
            if len({json.dumps(f) for f in fits}) > 1:
                ambiguous_groups += 1
            for i, a in zip(ours, fits[0]):
                experts[i] = a
        items[gp.stem] = {"gold": gold_ref, "experts": experts}
    if len(items) != len(original):
        raise SystemExit(f"{len(items)} articles here, {len(original)} in the original release")
    for stem, it in items.items():
        for d in ad.DIMS:
            means = [statistics.fmean(e[d] for e in s) for s in it["experts"]]
            if any(abs(a - b) > 1e-6 for a, b in zip(means, it["gold"][d])):
                raise SystemExit(f"{stem}/{d}: the experts' mean does not reproduce the gold")

    def rest_of(it, k):
        """The reference without expert k: the mean of the other two, in our order."""
        return json.dumps(
            {
                d: [statistics.fmean(s[j][d] for j in range(3) if j != k) for s in it["experts"]]
                for d in ad.DIMS
            }
        )

    per_expert = [[] for _ in range(3)]
    per_dim = {d: [] for d in ad.DIMS}
    expert_by_item = {}
    for stem, it in items.items():
        for k in range(3):
            one = json.dumps({d: [s[k][d] for s in it["experts"]] for d in ad.DIMS})
            sc = ad.score(one, rest_of(it, k))
            per_expert[k].append(sc["tau"])
            expert_by_item.setdefault(stem, []).append(sc["tau"])
            for d in ad.DIMS:
                per_dim[d].append(sc[f"tau_{d}"])
    experts = [statistics.fmean(v) for v in per_expert]

    judge_by_item: dict = {}
    # Every arm on the same footing: its committed outputs scored against each
    # leave-one-out reference, averaged over the three. Re-scoring against the full gold
    # first must reproduce the arm's committed tau, or the alignment is wrong.
    arms = {}
    for mj in sorted(RUNS.glob("se_*_n100_v1_*/metrics.json")):
        m = json.loads(mj.read_text())
        if m.get("dataset_id") != "summeval_100":
            continue
        arm = m["config_id"][len("se_") : -len("_n100_v1")]
        full, loo, loo_by_item = [], [], {}
        for stem, it in items.items():
            out = (mj.parent / "outputs" / f"{stem}.txt").read_text(encoding="utf-8")
            full.append(ad.score(out, json.dumps(it["gold"]))["tau"])
            loo.append(statistics.fmean(ad.score(out, rest_of(it, k))["tau"] for k in range(3)))
            loo_by_item[stem] = loo[-1]
        if abs(statistics.fmean(full) - m["scores"]["tau"]) > 1e-6:
            raise SystemExit(
                f"{arm}: re-scoring gives {statistics.fmean(full):.6f}, the run says {m['scores']['tau']:.6f}"
            )
        arms[arm] = {
            "tau": round(m["scores"]["tau"], 4),
            "tau_vs_two_experts": round(statistics.fmean(loo), 4),
        }
        judge_by_item[arm] = loo_by_item

    ceiling = statistics.fmean(experts)

    # A no-model reference row. Each of the 16 positions is the same system on every
    # article, so score each summary by the mean expert score its position got on the OTHER
    # 99 articles, against the same leave-one-out two-expert references as the arms.
    stems_all = sorted(items)
    prior_by_item = []
    for stem in stems_all:
        pred = json.dumps(
            {
                d: [
                    statistics.fmean(items[o]["gold"][d][i] for o in stems_all if o != stem)
                    for i in range(ad.N_SUMMARIES)
                ]
                for d in ad.DIMS
            }
        )
        prior_by_item.append(
            statistics.fmean(ad.score(pred, rest_of(items[stem], k))["tau"] for k in range(3))
        )
    position_prior = {
        "tau_vs_two_experts": round(statistics.fmean(prior_by_item), 4),
        "share_of_one_expert": round(statistics.fmean(prior_by_item) / ceiling, 4),
    }

    # How sure is "93%"? A paired bootstrap over articles (seeded), for the two best judges:
    # the ratio judge / expert and the gap expert - judge, resampling the same articles on
    # both sides. The best judge is chosen on these same articles, so its interval is the
    # optimistic one; that selection is not corrected for.
    stems = sorted(items)
    expert_item = {st: statistics.fmean(expert_by_item[st]) for st in stems}
    rng = random.Random(20261018)
    draws = [[rng.choice(stems) for _ in stems] for _ in range(10000)]
    top = sorted(
        (
            a
            for a in arms
            if a
            not in (
                "bartscore",
                "unieval",
                "unievalpub",
                "rouge1",
                "rouge2",
                "rougeL",
                "coverage",
                "length",
                "random",
            )
        ),
        key=lambda a: -arms[a]["tau_vs_two_experts"],
    )[:2]
    for arm in top:
        ratios, gaps = [], []
        for d in draws:
            e = statistics.fmean(expert_item[st] for st in d)
            j = statistics.fmean(judge_by_item[arm][st] for st in d)
            ratios.append(j / e)
            gaps.append(e - j)
        ratios.sort()
        gaps.sort()
        arms[arm]["share_ci95"] = [round(ratios[250], 3), round(ratios[9749], 3)]
        arms[arm]["gap_ci95"] = [round(gaps[250], 4), round(gaps[9749], 4)]
    # And how much of "93%" is picking the best of 24 on these same articles? Split the
    # articles in half at random, pick the best judge on one half, and score it on the other:
    # the held-out share is what choosing on the same items cannot inflate.
    judges = [
        a
        for a in arms
        if a
        not in (
            "bartscore",
            "unieval",
            "unievalpub",
            "rouge1",
            "rouge2",
            "rougeL",
            "coverage",
            "length",
            "random",
        )
    ]
    picked_in, picked_out = [], []
    for _ in range(2000):
        half = rng.sample(stems, len(stems) // 2)
        rest = [st for st in stems if st not in set(half)]
        best = max(judges, key=lambda a: statistics.fmean(judge_by_item[a][st] for st in half))
        ea, eb = (statistics.fmean(expert_item[st] for st in h) for h in (half, rest))
        picked_in.append(statistics.fmean(judge_by_item[best][st] for st in half) / ea)
        picked_out.append(statistics.fmean(judge_by_item[best][st] for st in rest) / eb)
    selection = {
        "splits": 2000,
        "share_in_sample": round(statistics.fmean(picked_in), 4),
        "share_held_out": round(statistics.fmean(picked_out), 4),
    }
    result = {
        "selection_corrected_best_judge": selection,
        "what": "Kendall tau-b per article between one SummEval expert and the mean of the other "
        "two (leave-one-out), averaged over the four dimensions and then over the 100 "
        "articles; and every arm scored against the same two-expert references",
        "source": URL,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "n_articles": len(items),
        "gold_reproduced": True,
        "arms_rescored_exactly": True,
        "duplicate_summary_groups": duplicate_groups,
        "duplicate_groups_with_more_than_one_fitting_assignment": ambiguous_groups,
        "duplicate_groups_scored_differently": scored_differently,
        "duplicate_articles": sum(1 for it in original.values() if len({t for t, _ in it}) < len(it)),
        "tau_per_position": [round(x, 4) for x in experts],
        "note": "tau_per_position is per position in each row's expert_annotations list; it is "
        "per annotator only if the file keeps one annotator order, which its "
        "documentation does not state. tau_mean does not depend on it.",
        "tau_mean": round(ceiling, 4),
        "tau_by_dimension": {d: round(statistics.fmean(v), 4) for d, v in per_dim.items()},
        "position_prior": position_prior,
        "arms": dict(sorted(arms.items(), key=lambda kv: -kv[1]["tau_vs_two_experts"])),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"gold reproduced, and every arm re-scored exactly, on all {len(items)} articles")
    print(
        f"identical-text groups: {duplicate_groups} in {result['duplicate_articles']} articles, "
        f"{scored_differently} scored differently by the experts; with more than one fitting "
        f"assignment: {ambiguous_groups}"
    )
    print(
        f"one expert vs the other two: tau {ceiling:.4f} "
        f"(by position in the file: {', '.join(f'{x:.4f}' for x in experts)})"
    )
    for d, v in result["tau_by_dimension"].items():
        print(f"  {d:11s} {v:.4f}")
    print(
        f"position prior (other 99 articles only): {position_prior['tau_vs_two_experts']:.4f} "
        f"= {position_prior['share_of_one_expert']:.0%} of one expert"
    )
    print("\narms against the same two-expert references (tau vs all three in brackets):")
    for arm, r in result["arms"].items():
        extra = (
            f"  share 95% CI {r['share_ci95'][0]:.0%}-{r['share_ci95'][1]:.0%}, "
            f"gap {r['gap_ci95'][0]:+.4f} to {r['gap_ci95'][1]:+.4f}"
            if "share_ci95" in r
            else ""
        )
        print(
            f"  {arm:12s} {r['tau_vs_two_experts']:.4f}  ({r['tau']:.4f})"
            f"  {r['tau_vs_two_experts'] / ceiling:.0%} of one expert{extra}"
        )
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
