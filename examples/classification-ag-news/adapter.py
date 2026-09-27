"""ML vs LLM on AG News topic classification. The seam for this example.

Almost all the behaviour lives in `examples/_shared/classification.py`. What is HERE is
the only thing that is about AG News: four labels, the spellings a model might answer
with, and a rule table.

THIS FILE USED TO BE 500 LINES AND IS NOW 120. The parser, the scorers, the five
providers and the fingerprint moved to `_shared` when the DBpedia example needed exactly
the same ones — abstracted on the SECOND use, which is the only point at which the seam
was visible. A shared module with one caller is a guess about the future; a shared module
with two callers is a fact about the present.

The move changes `parser_sha256` and the harness's `adapter.sha256`, because it is
genuinely a different implementation. Runs already on disk keep the hashes they recorded,
so nothing measured is invalidated; a re-run is distinguishable from the original, which
is exactly what those fields are for. What the move must NOT change is any SCORE, and it
does not: `score()` recomputed over all 28 stored runs — 5,600 item-scores — reproduces
them with max abs delta 0.000e+00.

WHAT THIS CORPUS EXERCISES
  Four coarse classes, short news text, and a published fine-tuned baseline at ~0.945 to
  check our instrument against. The hosted field lands 0.835-0.910 and a 44MB fine-tuned
  classifier beats all of it, which is the finding this example exists for. Its sibling,
  DBpedia-14, has fourteen classes and a ~0.98 ceiling — deliberately the opposite
  regime.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))

from classification import (  # noqa: E402
    METRIC_KINDS,
    PRIMARY_METRIC,
    TRANSIENT_MARKERS,
    ClassificationTask,
)

__all__ = ["call_system", "score", "warmup", "fingerprint",
           "PRIMARY_METRIC", "METRIC_KINDS", "TRANSIENT_MARKERS"]

#: The dataset's own label order. Index IS the stored integer, and these strings are what
#: the gold reference files contain. Not ours to reorder.
LABELS = ["World", "Sports", "Business", "Sci/Tech"]

#: What a model might answer instead of the canonical string. The canonical label is
#: always its own alias; the shared module adds that.
#:
#: "World" carries "politics" and "general" because that is what the class actually is on
#: this corpus — the catch-all for news that is not sport, money or technology — and a
#: model that answers "politics" has classified correctly in every sense but spelling.
ALIASES: Dict[str, tuple] = {
    "Sci/Tech": ("sci-tech", "scitech", "science/technology", "sci tech",
                 "science and technology", "technology", "science", "tech"),
    "Business": ("finance", "financial", "economy", "economics"),
    "Sports": ("sport",),
    "World": ("international", "world news", "politics", "general"),
}

#: Hand-written rules, in priority order, first match wins.
#:
#: Written from the four label names and general knowledge of news desks — NOT by reading
#: the slice and patching what it got wrong, which would make this a model fitted on the
#: eval set and put it on the wrong side of every claim here. It scores 0.67 at n=200,
#: and its confusion matrix shows the default firing far more often than the rules do.
RULES = [
    ("Sports", r"\b(game|games|season|coach|league|championship|cup|match|matches|"
               r"player|players|team|teams|score|scored|goal|goals|inning|nfl|nba|mlb|"
               r"nhl|olympic|olympics|tournament|playoff|playoffs|striker|midfield)\b"),
    ("Sci/Tech", r"\b(software|internet|computer|computers|microsoft|google|linux|"
                 r"web|online|chip|chips|semiconductor|nasa|space|scientist|scientists|"
                 r"research|researchers|technology|browser|server|servers|wireless|"
                 r"broadband|satellite|telescope|spacecraft)\b"),
    ("Business", r"\b(profit|profits|earnings|revenue|shares|stock|stocks|market|"
                 r"markets|investor|investors|merger|acquisition|quarterly|dividend|"
                 r"nasdaq|dow|economy|inflation|oil prices|bankruptcy|ceo)\b"),
]

#: The catch-all when no rule fires. Unlike DBpedia's, this one is NOT arbitrary: "World"
#: is genuinely where uncategorised news goes on this corpus, which is what a rule-based
#: classifier's default should be when the taxonomy offers one.
DEFAULT_LABEL = "World"

TASK = ClassificationTask(
    labels=LABELS,
    aliases=ALIASES,
    rules=RULES,
    default_label=DEFAULT_LABEL,
    prompt_dir=HERE,
)


def call_system(text: str, params: Dict[str, Any]):
    return TASK.call_system(text, params)


def score(output: str, reference: Optional[str], source: Optional[str] = None) -> Dict[str, float]:
    return TASK.score(output, reference, source)


def warmup(params: Dict[str, Any]) -> None:
    TASK.warmup(params)


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delegates, supplying the HuggingFace identity for the two local providers.

    The HF lookup stays here rather than in the shared module for the same reason
    `hf_identity` is not in the harness core: a HuggingFace cache layout is a HuggingFace
    concept, and a future Ollama or ONNX provider would bring its own.
    """
    hf = None
    if params.get("provider") in ("hf_local", "hf_zeroshot"):
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        hf = hf_model_fingerprint(
            params["model"],
            revision=params.get("revision"),
            device=str(params.get("device", "cpu")),
            precision=str(params.get("precision", "fp32")),
        )
    return TASK.fingerprint(params, hf_fingerprint=hf)
