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

# NUMERIC IDS SURVIVE THE BULLET STRIPPER. SciFact document ids are numbers, and the
# line parser used to `.lstrip("-*0123456789. )")` -- a character class, which deleted
# the id itself. Every non-JSON answer then parsed as nothing and the pipeline silently
# scored as its first stage. Found by external review.
check("numeric ids, bare per line", parse_ranking("4983923\n13734012") == ["4983923", "13734012"])
check("numeric ids, numbered list", parse_ranking("1. 4983923\n2. 13734012") == ["4983923", "13734012"])
check("numeric ids, bulleted", parse_ranking("- 4983923\n* 13734012") == ["4983923", "13734012"])
check("a bare number is not mistaken for numbering", parse_ranking("42") == ["42"])

# ── the machinery itself ─────────────────────────────────────────────────────
check("dcg discounts by log2(rank+1)", abs(dcg([1.0, 1.0]) - (1 + 1/math.log2(3))) < 1e-12)
check("dedupe keeps first occurrence", dedupe(["b", "a", "b"]) == (["b", "a"], 1))
check("scorer_sha256 is stable", scorer_sha256() == scorer_sha256())

# GRADE 0 MEANS JUDGED-AND-NOT-RELEVANT, which is the opposite of a hit. Membership in
# the qrels used to be the test, so a grade-0 entry counted for recall and MRR (nDCG was
# already right, 2^0-1 = 0). Found by external review.
G0 = {"d1": 1, "d0": 0}
r0 = score_ranking(["d0"], G0)
check("grade 0 is not a hit for recall", r0["recall_10"] == 0.0)
check("grade 0 is not a hit for mrr", r0["mrr_10"] == 0.0)
check("grade 0 does not count toward n_relevant", r0["n_relevant"] == 1.0)
check("grade 0 is not found_any", r0["found_any"] == 0.0)
r1 = score_ranking(["d1"], G0)
check("the grade-1 doc still scores 1.0", r1["ndcg_10"] == 1.0 and r1["recall_10"] == 1.0)

# PROSE IS NOT A RANKING. The parser used to take the first "[" anywhere in the body,
# so a model reasoning aloud and mentioning one id in passing was scored as if it had
# answered with a one-document ranking. On sf_qwen_s that hit 50 of 200 items, nearly
# all replies the token limit cut off mid-sentence; llama_l lost 0.0417 nDCG to it.
# The lead-in allowance is measured, not guessed: of 200 replies, 150 put the array at
# character 0 and the 50 with anything before it had at least 140 characters of it.
PROSE = ("The claim states that rapamycin decreases the concentration of "
         "triacylglycerols in fruit flies. Looking at the candidates, the most relevant "
         "is [4983]. The evidence in that abstract directly addresses it.")
check("prose mentioning an id in passing -> None, not a 1-doc ranking",
      parse_ranking(PROSE) is None)
check("a finished sentence before the array is prose, however short",
      parse_ranking("I checked. [a]") is None)
check("a short wrapper with no finished sentence still parses",
      parse_ranking("Here are the results:\n[\"a\",\"b\"]") == ["a", "b"])
check("a bare single-id array is still a ranking",
      parse_ranking("[6157837]") == ["6157837"])

# COMMA-SEPARATED IDS ON ONE LINE. Rejected whole before, because the line has a space,
# so the most natural non-JSON answer scored as unreadable.
check("comma-separated ids parse", parse_ranking("4983, 13734012") == ["4983", "13734012"])
check("comma-separated, no spaces", parse_ranking("4983,13734012") == ["4983", "13734012"])
check("a numbered line of comma-separated ids",
      parse_ranking("1. 4983, 13734012") == ["4983", "13734012"])
check("a prose line with commas is still refused",
      parse_ranking("The claim is X, which implies Y") is None)

# A LEADING ARRAY THAT WILL NOT PARSE IS A REFUSAL, NOT A HINT. llama_l opens with a
# real array and corrects itself in prose; json.loads fails, and the line path used to
# split the line on commas and accept "[8925851" and "21884449]" as document ids --
# 25 of 200 items on one run. The harvested ranking scored BELOW the BM25 fallback the
# pipeline uses for an unreadable reply (0.6386 against 0.7155 on the same bytes), so
# the arm was punished for the parser's guess.
SELFCORRECT = ("[24737389, 8925851, 7487927, 4459491, 13717103, 30813140, 21884449, "
               "4459491 is removed and  [30813140, 40078758]")
check("a leading array that fails to parse -> None, not harvested fragments",
      parse_ranking(SELFCORRECT) is None)
check("a bracket-laden token is never an id",
      parse_ranking("[8925851\n21884449]") is None)
check("but a clean comma list on one line still parses",
      parse_ranking("8925851, 21884449") == ["8925851", "21884449"])

# TRAILING COMMAS. "4983," split to ["4983", ""], the empty part failed the all(), and
# the whole line was discarded -- so this parsed as ["999"].
check("trailing commas on separate lines",
      parse_ranking("4983,\n13734012,\n999") == ["4983", "13734012", "999"])

# AN ARRAY INSIDE A SENTENCE IS NOT A RANKING. The lead is short and unfinished, so the
# wrapper and sentence-end guards both let these through.
check("'See [4983]' is prose, not a one-document ranking",
      parse_ranking("See [4983]") is None)
check("an array with a trailing clause is prose",
      parse_ranking("The most relevant document is [4983], because it shows the effect.")
      is None)
check("a lead-in ending in a colon on the SAME line still parses",
      parse_ranking("Here you go: [\"a\",\"b\"]") == ["a", "b"])
check("and an array that begins its own line still parses",
      parse_ranking("Here are the results:\n[\"a\",\"b\"]") == ["a", "b"])

print(f"\n{sum(1 for _, c in ok if c)}/{len(ok)} passed")
sys.exit(0 if all(c for _, c in ok) else 1)
