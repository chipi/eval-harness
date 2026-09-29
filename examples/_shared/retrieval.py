"""Scoring for tasks whose answer is a RANKED LIST: retrieval, reranking, recommendation.

The fourth metric shape this harness has met, and the first where POSITION carries meaning.

    summarisation   one text   vs one text   -> continuous
    classification  one label  vs one label  -> 0 or 1
    extraction      a set      vs a set      -> membership, order irrelevant
    retrieval       a LIST     vs a set      -> membership AND order

An extraction arm that finds the right entities in a different order is correct. A
retrieval arm that finds the right document at rank 50 instead of rank 1 is not, and no
set-valued metric can say so. That is the whole reason this file is separate from
`extraction.py`, which it otherwise resembles.

WHAT THE GOLD IS, AND WHAT IT IS NOT
  Gold is a SET of relevant documents ("qrels"), possibly graded. It says nothing about
  the order the relevant documents should appear in relative to each other, only that
  they should appear above the irrelevant ones. So the metric is asymmetric: the
  prediction is ordered, the truth is not.

THREE THINGS THAT LOOK LIKE LENIENCY AND ARE ACTUALLY REWARDS FOR BAD BEHAVIOUR
  Each of these is a place where the obvious, tidy implementation quietly pays an arm for
  something it should be punished for. The extraction scorer in this repo shipped with
  exactly this class of bug -- an unreadable answer scored 1.0 -- so they are decided here
  before any arm runs rather than after one exploits them.

  1. AN UNREADABLE ANSWER IS NOT AN EMPTY RANKING. `parsed=False` scores zero on every
     quality metric. An arm whose output could not be read did not "return no results";
     it failed. (Unlike extraction there is no empty-gold case here to make this pay 1.0 --
     every query has at least one relevant document -- but the asymmetry is the same and
     the next corpus may not be so forgiving.)

  2. A HALLUCINATED DOCUMENT ID KEEPS ITS SLOT. An LLM reranker can emit an id that is not
     in the corpus. Dropping it would slide every real document UP one rank and improve
     the score -- so inventing ids would be a scoring strategy. Unknown ids stay in the
     list, occupy their position, and contribute zero gain. `unknown_ids` counts them.

  3. A DUPLICATE IS COLLAPSED, NOT COUNTED TWICE. An arm that returns the same relevant
     document ten times would otherwise fill the whole top-10 with gain. First occurrence
     wins, later ones are removed, and `duplicate_ids` counts them. Removing rather than
     zeroing is deliberate: the arm produced a 10-item list containing 1 distinct document,
     and that is a 1-item list padded, not a 10-item list of which 9 are wrong.

nDCG'S GAIN FUNCTION IS DECLARED EVEN THOUGH IT DOES NOT MATTER HERE
  `gain = 2**rel - 1`, matching `pytrec_eval`/BEIR. On SciFact every relevance grade is 1,
  where `2**1 - 1 == 1` and this is indistinguishable from linear gain. It is written down
  because the next corpus may be graded, and a metric that silently changes meaning
  between two datasets is worse than one that is merely wrong.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from codehash import code_digest

#: Cut-offs reported on every run. 10 is the ranking cut-off people quote; 100 is the one a
#: two-stage pipeline actually depends on, because a reranker cannot retrieve what the
#: first stage never returned.
#: A list-numbering or bullet prefix: "1. ", "2) ", "- ", "* ". Deliberately requires
#: the delimiter AND trailing space, so a bare numeric id is never mistaken for
#: numbering -- see parse_ranking.
_LIST_PREFIX = re.compile(r"^(?:\d{1,3}[.)]\s+|[-*\u2022]\s+)")

#: How much text may sit BEFORE a JSON array and still count as a wrapper rather than
#: prose. See `parse_ranking`: measured on sf_qwen_s, the wrapper case is 0 characters
#: (150 of 200 replies) and the prose case starts at 140, so anything in between
#: separates them. 64 is chosen inside that gap, wide enough for "Here are the results:"
#: and far below the shortest real prose reply.
_WRAPPER_MAX = 64
#: A sentence that has ENDED means the model was talking, not labelling.
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
#: What a document id may look like on the line path. Anything with a bracket, a quote
#: or a space in it is a fragment of prose, not an id -- see `parse_ranking`.
_ID_TOKEN = re.compile(r"^[\w.\-]+$")

NDCG_AT = 10
RECALL_AT = (10, 100)
MRR_AT = 10


def normalize_id(x: Any) -> str:
    """Document ids compared as strings, stripped.

    Deliberately NOT casefolded and NOT stripped of punctuation, unlike the extraction
    normaliser: a document id is an identifier, not a mention. Two ids that differ in case
    are two ids, and a scorer that merged them would be inventing matches.
    """
    return str(x).strip()


def scorer_sha256() -> str:
    """Hash of the whole scoring rule.

    `extraction.py` shipped with only its string normaliser hashed, on the reasoning that
    a normaliser has the most room to move a score. The bug that cost this repo a sweep
    lived in the per-item rule, which no hash covered. This file is fingerprinted whole
    from the start.

    AND `parse_ranking` IS IN IT, which it was not. An external review found the
    retrieval parser covered by no hash anywhere -- the one piece of code that decides
    whether a model's answer is a ranking at all. It is the scorer's first step, so it
    belongs in the scorer's hash.
    """
    return code_digest(normalize_id, dedupe, dcg, score_ranking, parse_ranking,
                       consts={"NDCG_AT": NDCG_AT, "RECALL_AT": RECALL_AT,
                               "MRR_AT": MRR_AT, "_LIST_PREFIX": _LIST_PREFIX,
                               "_WRAPPER_MAX": _WRAPPER_MAX,
                               "_SENTENCE_END": _SENTENCE_END,
                               "_ID_TOKEN": _ID_TOKEN})


def dedupe(ranking: Sequence[str]) -> tuple[List[str], int]:
    """First occurrence wins. Returns the deduped list and how many were removed."""
    seen: Set[str] = set()
    out: List[str] = []
    for d in ranking:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out, len(ranking) - len(out)


def dcg(gains: Iterable[float]) -> float:
    """Discounted cumulative gain, rank 1 discounted by log2(2) = 1."""
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def score_ranking(ranking: Sequence[str], qrels: Dict[str, int],
                  corpus_ids: Optional[Set[str]] = None,
                  parsed: bool = True) -> Dict[str, float]:
    """The metric block for ONE query.

    `ranking`   the arm's ordered document ids, best first
    `qrels`     {doc_id: relevance grade}, the judged-relevant documents
    `corpus_ids` every id in the corpus, so hallucinated ids can be COUNTED (they are
                never removed -- see the module docstring)
    `parsed`    False when the arm's output could not be read at all
    """
    n_rel = sum(1 for g in qrels.values() if g > 0)
    zero = {
        "ndcg_10": 0.0, "recall_10": 0.0, "recall_100": 0.0, "mrr_10": 0.0,
        "rank_of_first": 0.0, "found_any": 0.0,
        "n_returned": 0.0, "n_relevant": float(n_rel),
        "unknown_ids": 0.0, "duplicate_ids": 0.0,
    }
    if not parsed:
        return zero
    clean, dupes = dedupe([normalize_id(d) for d in (ranking or []) if normalize_id(d)])
    if not clean:
        return {**zero, "duplicate_ids": float(dupes)}

    # RELEVANT MEANS GRADE > 0, not "appears in the qrels".
    #
    # TREC-style judgments include grade-0 entries meaning "a human looked at this and
    # it is NOT relevant" -- genuinely useful information, and the opposite of a hit.
    # Membership-based tests counted them as relevant for recall and MRR (nDCG was
    # already correct, since 2^0-1 = 0). SciFact happens to be all grade-1 so nothing
    # published here moved, but the next corpus will not be. Found by review.
    rel = {d: g for d, g in qrels.items() if g > 0}
    gains = [float(2 ** rel[d] - 1) if d in rel else 0.0 for d in clean]
    ideal = sorted((float(2 ** g - 1) for g in rel.values()), reverse=True)

    idcg = dcg(ideal[:NDCG_AT])
    ndcg = (dcg(gains[:NDCG_AT]) / idcg) if idcg else 0.0

    out: Dict[str, float] = {
        "ndcg_10": round(ndcg, 10),
        "n_returned": float(len(clean)),
        "n_relevant": float(n_rel),
        # Ids the arm produced that are not documents. Descriptive, but the number that
        # says an LLM reranker is inventing rather than reordering.
        "unknown_ids": float(sum(1 for d in clean if corpus_ids is not None
                                 and d not in corpus_ids)),
        "duplicate_ids": float(dupes),
    }
    for k in RECALL_AT:
        hit = sum(1 for d in clean[:k] if d in rel)
        out[f"recall_{k}"] = round(hit / n_rel, 10) if n_rel else 0.0

    # RECIPROCAL RANK of the first relevant document, 0 if none inside the cut-off.
    rr = 0.0
    first = 0
    for i, d in enumerate(clean, start=1):
        if d in rel:
            first = i
            if i <= MRR_AT:
                rr = 1.0 / i
            break
    out["mrr_10"] = round(rr, 10)
    # Descriptive and NOT a quality metric: 0 means "never found", which sorts as the best
    # possible rank if anyone averages it carelessly. It is here to be read, not ranked.
    out["rank_of_first"] = float(first)
    out["found_any"] = 1.0 if first else 0.0
    return out


def parse_ranking(text: str) -> Optional[List[str]]:
    """A model's answer as an ordered list of document ids, or None if unreadable.

    None is not "returned nothing" -- an empty list is that. None means the output was not
    a ranking at all, and the two are scored differently.

    Forgiving about wrappers, strict about content: a JSON array, a fenced block holding
    one, or one id per line. A ranking is an ordering, so anything that loses the order --
    a JSON object, a set -- is refused rather than guessed at.
    """
    if not text or not text.strip():
        return None
    body = text.strip()
    if "```" in body:
        start = body.find("```")
        end = body.find("```", start + 3)
        if end > start:
            inner = body[start + 3:end]
            body = inner.split("\n", 1)[1] if inner.lstrip().startswith("json") else inner
            body = body.strip()
    # The array may sit behind a WRAPPER ("Here are the results:") but not behind PROSE.
    #
    # This used to accept the first "[" anywhere in the body, and that is how a model
    # reasoning aloud got scored as if it had answered. A reply like
    #
    #   "The claim states that rapamycin decreases ... the most relevant is [4983]. The
    #    evidence in that abstract ..."
    #
    # parsed as the one-document ranking ["4983"] -- a confident, plausible, wrong
    # answer -- instead of being refused as unreadable. On sf_qwen_s it hit 50 of 200
    # items, nearly all of them replies the token limit cut off mid-reasoning.
    #
    # The two cases separate cleanly and the threshold is measured, not guessed: of 200
    # replies, 150 put the array at character 0, and the 50 with anything before it have
    # at least 140 characters of it. No reply in the corpus has a short lead-in, so the
    # "Here are the results:" case the previous version was protecting never actually
    # occurred -- but it is cheap to keep allowing, so a lead-in is accepted while it is
    # short AND contains no finished sentence.
    opened = body.find("[")
    if opened != -1:
        lead = body[:opened].strip()
        if len(lead) > _WRAPPER_MAX or _SENTENCE_END.search(lead):
            return None
        # THE ARRAY MUST BEGIN A LINE, or sit behind a lead-in that ends in a colon.
        # Without this, "See [4983]" and "The most relevant document is [4983], because
        # ..." both parse as a one-document ranking: the lead is short and has no
        # finished sentence, so the two earlier guards let them through. An answer is
        # a list; a sentence that happens to cite one id is not.
        same_line = body[:opened].rsplit("\n", 1)[-1].strip()
        if same_line and not same_line.endswith(":"):
            return None
        depth, cut = 0, None
        for i in range(opened, len(body)):
            if body[i] == "[":
                depth += 1
            elif body[i] == "]":
                depth -= 1
                if depth == 0:
                    cut = i + 1
                    break
        if cut:
            try:
                val = json.loads(body[opened:cut])
            except ValueError:
                val = None
            if isinstance(val, list):
                return [normalize_id(v) for v in val if normalize_id(v)]
        # A LEADING ARRAY THAT WILL NOT PARSE IS A REFUSAL, NOT A HINT.
        #
        # Falling through to the line path here is what produced the worst number in
        # this example. llama_l opens with a real array and then corrects itself in
        # prose -- "..., 4459491 is removed and [30813140, ..." -- so json.loads fails,
        # the line path splits the line on commas, and tokens like "[8925851" and
        # "21884449]" were accepted as document ids because they contain no space. 25
        # of 200 items on the 2026-09-29 llama_l run harvested fragments that way.
        #
        # Those bracket tokens are never real ids, so they counted as hallucinations
        # and the harvested partial ranking scored BELOW the BM25 fallback the pipeline
        # is supposed to use when a reply is unreadable -- 0.6386 against 0.7155 on the
        # same bytes. The arm was punished for the parser's guess. Found by external
        # review.
        return None
    # One id per line: what a model produces when told "just list them".
    #
    # THE BULLET STRIPPER MUST NOT EAT THE ID. This used to be
    # `.lstrip("-*0123456789. )")`, a character class -- which on SciFact, whose
    # document ids ARE numbers, deleted the id itself. "4983923" became "" and every
    # non-JSON answer parsed as nothing, so the pipeline silently fell back to the
    # first stage's ranking and the arm was scored as BM25. Found by review.
    #
    # A numbering prefix is now matched as a PREFIX -- digits followed by a delimiter
    # and whitespace, or a bullet followed by whitespace -- so "1. 4983923" loses the
    # "1. " and a bare "4983923" loses nothing.
    #
    # COMMA-SEPARATED IDS ON ONE LINE are a ranking too. "4983, 13734012" used to be
    # rejected whole, because the line contains a space -- so a model that answered in
    # the most natural non-JSON format scored as unreadable. Each comma-separated part
    # must still look like an id, so a prose line ("The claim is X, which implies Y")
    # is rejected exactly as before: its parts contain spaces.
    ids = []
    for raw in body.splitlines():
        ln = _LIST_PREFIX.sub("", raw.strip(), count=1).strip()
        if not ln:
            continue
        # Trailing commas are dropped rather than failing the line: "4983," used to
        # split to ["4983", ""], the empty part failed the all() below, and the whole
        # line was thrown away -- so "4983,\n13734012,\n999" parsed as ["999"].
        parts = [x.strip() for x in ln.split(",")] if "," in ln else [ln]
        parts = [x for x in parts if x]
        # `_ID_TOKEN`, not just "no spaces". A bracket or a quote in a token means the
        # line is prose that happens to lack a space, not a list of ids.
        if parts and all(_ID_TOKEN.match(x) and len(x) <= 64 for x in parts):
            ids.extend(parts)
    return ids or None


PRIMARY_METRIC = "ndcg_10"

METRIC_KINDS = {
    "ndcg_10": "quality",
    "recall_10": "quality",
    "recall_100": "quality",
    "mrr_10": "quality",
    "parsed": "quality",
    # Descriptive: diagnostics, not rankings. `rank_of_first` in particular must never be
    # ranked -- 0 means "never found" and would sort as the best possible position.
    "rank_of_first": "descriptive",
    "found_any": "descriptive",
    "n_returned": "descriptive",
    "n_relevant": "descriptive",
    "unknown_ids": "descriptive",
    "duplicate_ids": "descriptive",
    "truncated": "descriptive",
    "reasoning_tokens": "descriptive",
    "confidence": "descriptive",
    # Emitted by the reranking provider, and DESCRIPTIVE on purpose. `llm_named_unknown`
    # counts document ids the model invented; undeclared, it fell into the leaderboard's
    # quality columns where higher reads as better -- so an arm that hallucinated more
    # looked like it had improved. `llm_parsed` is the share of queries whose LLM reply
    # was a usable ordering: a diagnostic for WHY a pipeline scored what it did, not a
    # quality claim about the pipeline, whose quality is ndcg_10.
    "llm_named_unknown": "descriptive",
    "llm_parsed": "descriptive",
}
