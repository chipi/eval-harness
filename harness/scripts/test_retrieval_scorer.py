#!/usr/bin/env python3
"""Assertions for the ranked-list scorer. No network, no models, no arguments.

    python scripts/test_retrieval_scorer.py

Written BEFORE the first arm ran, which is the opposite of how the extraction scorer got
its tests. That one shipped, paid an unreadable answer 1.0 on 12% of items, and only then
grew the assertion that would have caught it.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "_shared"))
from retrieval import (dcg, dedupe, parse_ranking, score_ranking,  # noqa: E402
                       scorer_sha256)

ok = []
def check(label, cond): ok.append((label, cond)); print(f"  {'ok  ' if cond else 'FAIL'} {label}")

Q1 = {"d1": 1}                      # one relevant document, the SciFact majority case
Q3 = {"d1": 1, "d2": 1, "d3": 1}    # three, so IDCG has three terms

# ── position is the whole point ───────────────────────────────────────────────
check("relevant at rank 1 -> ndcg 1.0",
      score_ranking(["d1", "x", "y"], Q1)["ndcg_10"] == 1.0)
r2 = score_ranking(["x", "d1", "y"], Q1)
check("relevant at rank 2 -> ndcg 1/log2(3)",
      abs(r2["ndcg_10"] - 1 / math.log2(3)) < 1e-9)
check("rank 2 scores LESS than rank 1",
      r2["ndcg_10"] < score_ranking(["d1"], Q1)["ndcg_10"])
check("relevant at rank 11 -> ndcg 0 (outside the cut-off)",
      score_ranking([f"x{i}" for i in range(10)] + ["d1"], Q1)["ndcg_10"] == 0.0)
check("...but recall@100 still sees it",
      score_ranking([f"x{i}" for i in range(10)] + ["d1"], Q1)["recall_100"] == 1.0)
check("...and recall@10 does not",
      score_ranking([f"x{i}" for i in range(10)] + ["d1"], Q1)["recall_10"] == 0.0)

# ── the set-vs-list asymmetry ────────────────────────────────────────────────
check("all 3 relevant, any order among themselves -> ndcg 1.0",
      score_ranking(["d3", "d1", "d2"], Q3)["ndcg_10"] == 1.0)
check("3 relevant, one pushed below an irrelevant -> ndcg < 1.0",
      score_ranking(["d1", "d2", "x", "d3"], Q3)["ndcg_10"] < 1.0)

# ── THE THREE REWARDS-FOR-BAD-BEHAVIOUR, each asserted in the direction that fails ──
u = score_ranking(["d1"], Q1, parsed=False)
check("unparsed -> ndcg 0.0, NOT scored as an empty ranking", u["ndcg_10"] == 0.0)
check("unparsed zeroes recall and mrr too",
      u["recall_10"] == 0.0 and u["recall_100"] == 0.0 and u["mrr_10"] == 0.0)

CORPUS = {"d1", "d2", "d3", "x", "y"}
hall = score_ranking(["ghost1", "ghost2", "d1"], Q1, corpus_ids=CORPUS)
real = score_ranking(["x", "y", "d1"], Q1, corpus_ids=CORPUS)
check("a hallucinated id KEEPS its slot: same score as a real wrong answer",
      abs(hall["ndcg_10"] - real["ndcg_10"]) < 1e-12)
check("...and is counted", hall["unknown_ids"] == 2.0)
check("dropping them would have scored better (the bug this prevents)",
      score_ranking(["d1"], Q1, corpus_ids=CORPUS)["ndcg_10"] > hall["ndcg_10"])

dup = score_ranking(["d1"] * 10, Q1)
check("a duplicate cannot fill the top-10: ndcg 1.0, not >1", dup["ndcg_10"] == 1.0)
check("duplicates are counted and removed",
      dup["duplicate_ids"] == 9.0 and dup["n_returned"] == 1.0)
check("duplicating an irrelevant doc does not push a relevant one down twice",
      score_ranking(["x", "x", "x", "d1"], Q1)["ndcg_10"]
      == score_ranking(["x", "d1"], Q1)["ndcg_10"])

# ── empty and degenerate ─────────────────────────────────────────────────────
check("empty ranking -> 0.0 on everything", score_ranking([], Q1)["ndcg_10"] == 0.0)
check("nothing relevant returned -> found_any 0, rank_of_first 0",
      score_ranking(["x", "y"], Q1)["found_any"] == 0.0
      and score_ranking(["x", "y"], Q1)["rank_of_first"] == 0.0)
check("rank_of_first is 1-indexed", score_ranking(["x", "d1"], Q1)["rank_of_first"] == 2.0)
# 1e-9, not 1e-12: score_ranking rounds to 10 decimal places, so 1/3 comes back as
# 0.3333333333. The scorer is right and the first version of this assertion was wrong.
check("mrr_10 is 1/rank", abs(score_ranking(["x", "x2", "d1"], Q1)["mrr_10"] - 1/3) < 1e-9)

# ── parsing ──────────────────────────────────────────────────────────────────
check("JSON array parses", parse_ranking('["a","b","c"]') == ["a", "b", "c"])
check("fenced JSON parses", parse_ranking('```json\n["a","b"]\n```') == ["a", "b"])
check("preamble before an array is tolerated",
      parse_ranking('Here you go:\n["a","b"]') == ["a", "b"])
check("one id per line parses", parse_ranking("a\nb\nc") == ["a", "b", "c"])
check("numbered list parses", parse_ranking("1. a\n2. b") == ["a", "b"])
check("prose is unreadable, not an empty ranking",
      parse_ranking("I could not find any relevant documents in the corpus.") is None)
check("empty text -> None", parse_ranking("") is None)
check("order is preserved through parsing", parse_ranking('["c","a","b"]') == ["c", "a", "b"])

# ── the machinery itself ─────────────────────────────────────────────────────
check("dcg discounts by log2(rank+1)", abs(dcg([1.0, 1.0]) - (1 + 1/math.log2(3))) < 1e-12)
check("dedupe keeps first occurrence", dedupe(["b", "a", "b"]) == (["b", "a"], 1))
check("scorer_sha256 is stable", scorer_sha256() == scorer_sha256())

print(f"\n{sum(1 for _, c in ok if c)}/{len(ok)} passed")
sys.exit(0 if all(c for _, c in ok) else 1)
