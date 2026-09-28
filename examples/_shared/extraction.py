"""Scoring for tasks whose answer is a SET: entities, keyphrases, topics.

The third metric shape this harness has met. Summarisation compares one text to one text
and scores continuously. Classification compares one label to one label and scores 0 or 1.
Extraction compares a SET to a SET, and the interesting decisions are all in how you match
the members.

WHY PER-ITEM F1 IS LEGITIMATE HERE AND MACRO-F1 WAS NOT

  `_shared/classification.py` could not give the harness a macro-F1 metric, because
  macro-F1 needs a confusion matrix over the whole run -- there is no per-item number
  whose average is macro-F1.

  Extraction is different. An item has its own gold set and its own predicted set, so
  precision, recall and F1 are all well-defined ON THAT ITEM. Their means are honest
  per-item metrics, which means `family_test.py`'s sign-flip permutation works directly
  and no bootstrap is needed.

  What is still NOT per-item is CORPUS MICRO-F1 -- pooling every tp/fp/fn and computing
  one F1. Mean-of-per-item-F1 and corpus micro-F1 are different numbers answering
  different questions ("how did it do on a typical item" vs "how did it do over all the
  entities"), and both are worth reporting. The mean is the metric; the micro figure
  belongs in a report script.

THE EMPTY CASES, DECIDED UP FRONT
  15% of Few-NERD sentences contain no entities, so these are not edge cases:

      gold empty, prediction empty          F1 = 1.0   it correctly found nothing
      gold empty, prediction non-empty      F1 = 0.0   everything predicted is a false positive
      gold non-empty, prediction empty      F1 = 0.0   everything missed

  The first line is the one people get wrong by leaving precision undefined and dropping
  the item. Dropping it would delete exactly the items on which a hallucinating arm should
  be punished.

AN UNREADABLE ANSWER IS NOT AN EMPTY ONE, AND THE FIRST VERSION OF THIS FILE CONFLATED THEM
  `score_sets` used to take only the parsed set, so the caller had no way to say "there
  was no set here at all" -- both an arm that answered `[]` and an arm whose output could
  not be read arrived as `[]`. On the 15% of items whose gold is also empty, that paid a
  non-answer the full 1.0.

  It is not a theoretical hole. On few_nerd_280, glm_l spent its entire 600-token budget
  on item 0e88aabc reasoning aloud about which benchmark it was being evaluated on --
  "It matches FIGER? No, FIGER has 112 types" -- ran out of tokens, emitted no array,
  and scored 1.0, because the sentence ("Epsilon Centauri is a relatively young star")
  has no entities. Six of its 46 unreadable items were free 1.0s, worth +0.0214 f1.

  So `parsed` is a required part of the call now. An unreadable answer scores zero on
  every quality metric whatever the gold is, and is counted as missing every gold member.
  It is NOT counted as a false positive: it predicted nothing, it merely failed. That
  asymmetry means a CORPUS micro-F1 pooled from tp/fp/fn still forgives an unparsed
  empty-gold item; the per-item mean, which is the primary metric, does not.

MATCHING IS ONE-TO-ONE
  A prediction may satisfy at most one gold member and vice versa. Without that, one
  prediction overlapping three gold entities counts as three true positives and precision
  becomes unbounded nonsense. Greedy over a deterministic ordering, which is enough when
  matches are near-exact; a maximum-weight assignment would differ only where several
  predictions compete for one gold, and that is rare after normalisation.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Leading articles are dropped before comparison. "the Taft Hotel" and "Taft Hotel" are
#: the same entity, and an arm should not lose a point to a determiner. Not a free choice:
#: it is hashed into the fingerprint, and tightening it later moves every score.
_ARTICLES = ("the ", "a ", "an ")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Casefold, strip accents and punctuation, drop a leading article, squeeze space.

    Deliberately NOT stemming or lemmatising: "Olympics" and "Olympic" are different
    surface forms that a reader would judge differently, and a normaliser that collapses
    them is quietly grading a different task.
    """
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PUNCT.sub(" ", s.casefold())
    s = _WS.sub(" ", s).strip()
    for article in _ARTICLES:
        if s.startswith(article):
            s = s[len(article):]
            break
    return s


def normalizer_sha256() -> str:
    """Hash of the normaliser's source and its article list.

    The classification example learned this the hard way: the label parser turned out to
    be worth 8.6 accuracy points to one arm, and it was only attributable because its hash
    was on every run. A set-matcher has strictly more room to move a score than a label
    parser does, so it is fingerprinted from the start rather than after the surprise.
    """
    body = inspect.getsource(normalize) + repr(_ARTICLES)
    return hashlib.sha256(body.encode()).hexdigest()


def scorer_sha256() -> str:
    """Hash of the WHOLE scoring rule, not just the string normaliser.

    `normalizer_sha256` covers `normalize`, and that was the only scoring function
    fingerprinted when this file was written -- on the reasoning that a normaliser has the
    most room to move a score. That reasoning was right and the scope was wrong: the
    matcher and the empty-case conventions have at least as much room, and the bug in the
    module docstring lived in `prf`, which no hash covered. The scorer could be changed
    between two runs and nothing in either fingerprint would say so.

    So this covers every function whose output is a number: the normaliser, the member
    coercion, the matcher, the per-item rule and the metric block. Changing any of them
    changes every arm's fingerprint, which is the point -- two runs that disagree here are
    not comparable, however similar their config looks.
    """
    body = "".join(inspect.getsource(f) for f in
                   (normalize, as_members, match_one_to_one, prf, score_sets))
    return hashlib.sha256((body + repr(_ARTICLES)).encode()).hexdigest()


Member = Tuple[str, Optional[str]]


def as_members(items: Iterable[Any], typed: bool) -> List[Member]:
    """Normalise a gold or predicted collection into comparable members.

    Accepts `{"text": ..., "type": ...}` dicts, `(text, type)` pairs, or bare strings, so
    a keyphrase example with no types uses the same code as a typed NER one.
    """
    out: List[Member] = []
    for it in items or []:
        if isinstance(it, dict):
            text, kind = it.get("text", ""), it.get("type")
        elif isinstance(it, (list, tuple)) and it:
            text, kind = it[0], (it[1] if len(it) > 1 else None)
        else:
            text, kind = it, None
        text = normalize(str(text))
        if not text:
            continue
        out.append((text, (str(kind).casefold() if typed and kind is not None else None)))
    return out


def match_one_to_one(pred: Sequence[Member], gold: Sequence[Member]) -> int:
    """True positives under one-to-one exact matching of normalised members."""
    remaining = list(gold)
    tp = 0
    for p in pred:
        for i, g in enumerate(remaining):
            if p == g:
                remaining.pop(i)
                tp += 1
                break
    return tp


def prf(pred: Sequence[Member], gold: Sequence[Member], parsed: bool = True) -> Dict[str, float]:
    """Precision, recall, F1 and the raw counts, for ONE item.

    The empty conventions are in the module docstring and are load-bearing on a corpus
    where 15% of items have no gold members.

    `parsed=False` says the arm produced nothing readable. That is a zero on every
    quality metric -- see the module docstring for the run where treating it as an empty
    set paid a non-answer 1.0.
    """
    if not parsed:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                "tp": 0.0, "fp": 0.0, "fn": float(len(gold))}
    if not gold and not pred:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0.0, "fp": 0.0, "fn": 0.0}
    tp = float(match_one_to_one(pred, gold))
    fp, fn = len(pred) - tp, len(gold) - tp
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1, "tp": tp, "fp": float(fp), "fn": float(fn)}


def score_sets(predicted: Iterable[Any], gold_json: Optional[str],
               parsed: bool = True) -> Dict[str, float]:
    """The metric block for one item, in both match modes.

    TYPED vs UNTYPED is the pair that disagrees, and it is the reason both are here.
    `untyped_f1` asks "did it find the entity at all"; `f1` asks "and did it label it
    right". An arm that spots every span and mistypes half of them looks mediocre on one
    and excellent on the other, and that difference is an engineering decision -- a
    type-confusion problem is fixed differently from a detection problem.
    """
    try:
        gold_raw = json.loads(gold_json) if gold_json else []
    except (TypeError, ValueError):
        gold_raw = []

    typed = prf(as_members(predicted, True), as_members(gold_raw, True), parsed)
    untyped = prf(as_members(predicted, False), as_members(gold_raw, False), parsed)
    out = {
        "f1": round(typed["f1"], 10),
        "precision": round(typed["precision"], 10),
        "recall": round(typed["recall"], 10),
        "untyped_f1": round(untyped["f1"], 10),
        # Raw counts, so a report script can pool them into a CORPUS micro-F1, which is
        # a different number from the mean of these per-item F1s and answers a different
        # question.
        "tp": typed["tp"], "fp": typed["fp"], "fn": typed["fn"],
        "untyped_tp": untyped["tp"], "untyped_fp": untyped["fp"], "untyped_fn": untyped["fn"],
        "n_predicted": float(len(as_members(predicted, True))),
        "n_gold": float(len(as_members(gold_raw, True))),
    }
    # WHAT THE TYPE HEAD COSTS. untyped_f1 - f1 is the share of credit lost purely to
    # mislabelling something the arm did find. Reported rather than left to subtraction by
    # eye, because it is the number that says which of two different problems you have.
    out["type_penalty"] = round(out["untyped_f1"] - out["f1"], 10)
    return out


PRIMARY_METRIC = "f1"

METRIC_KINDS = {
    "f1": "quality",
    "precision": "quality",
    "recall": "quality",
    "untyped_f1": "quality",
    # Descriptive: counts and diagnostics, not rankings.
    "type_penalty": "descriptive",
    "tp": "descriptive", "fp": "descriptive", "fn": "descriptive",
    "untyped_tp": "descriptive", "untyped_fp": "descriptive", "untyped_fn": "descriptive",
    "n_predicted": "descriptive",
    "n_gold": "descriptive",
    # An item whose output could not be parsed into a set at all. Quality, for the same
    # reason `parsed` is in the classification example: an arm that cannot be parsed
    # cannot be deployed, whatever it knows.
    "parsed": "quality",
    "truncated": "descriptive",
    "reasoning_tokens": "descriptive",
    "confidence": "descriptive",
}
