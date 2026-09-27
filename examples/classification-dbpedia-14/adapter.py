"""ML vs LLM on DBpedia-14 ontology classification. The seam for this example.

Almost all the behaviour lives in `examples/_shared/classification.py`. What is HERE is
the only thing that is about DBpedia: the fourteen labels, the spellings a model might
answer with, and a rule table. That split is the point of having a second classification
example at all — if this file had been a copy of the AG News adapter, the two would have
drifted and stopped being comparable for reasons nobody could see.

WHAT THIS CORPUS EXERCISES THAT AG NEWS DID NOT

  1. FOURTEEN LABELS, AND THEY ARE CamelCase. `EducationalInstitution` and
     `MeanOfTransportation` are not things a model says out loud. It will answer
     "Educational Institution", "school", "vehicle" — so the alias table does real work
     here, where on AG News every arm returned a bare label and the parser never fired
     except on one narrating arm.

  2. A CEILING. Published accuracy on DBpedia-14 is ~0.98-0.99 for fine-tuned
     transformers, against 0.945 on AG News. Expect the arms to bunch and almost nothing
     to separate. That is the opposite statistical regime from AG News and it is why
     running both is worth more than running either twice.

  3. NO NATURAL CATCH-ALL. AG News has "World", which is genuinely where uncategorised
     news goes. DBpedia's fourteen classes are siblings in an ontology — none of them
     means "other". The keyword arm's default is therefore ARBITRARY, declared below, and
     its cost shows up as a column in that arm's confusion matrix rather than as a number
     nobody can account for.
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
#: the gold reference files contain. Not ours to reorder or prettify.
LABELS = [
    "Company", "EducationalInstitution", "Artist", "Athlete", "OfficeHolder",
    "MeanOfTransportation", "Building", "NaturalPlace", "Village", "Animal",
    "Plant", "Album", "Film", "WrittenWork",
]

#: What a model might answer instead of the canonical CamelCase string.
#:
#: DELIBERATELY CONSERVATIVE. Every entry here is a spacing variant or an unambiguous
#: synonym. Tempting additions that are NOT here: "music" (Artist or Album?), "record"
#: (Album or WrittenWork?), "place" (NaturalPlace, Building or Village?). An alias that
#: could belong to two labels does not make the parser more forgiving, it makes it guess
#: — and a parser that guesses is scoring itself rather than the model.
#:
#: The canonical label is always its own alias; the shared module adds that.
ALIASES: Dict[str, tuple] = {
    "EducationalInstitution": ("educational institution", "education institution",
                               "school", "university", "college"),
    "MeanOfTransportation": ("mean of transportation", "means of transportation",
                             "meanoftransportation", "transportation", "vehicle"),
    "NaturalPlace": ("natural place", "naturalplace", "natural feature"),
    "OfficeHolder": ("office holder", "officeholder", "politician"),
    "WrittenWork": ("written work", "writtenwork", "book", "novel", "publication"),
    "Village": ("village", "settlement"),
    "Athlete": ("athlete", "sportsperson"),
    "Building": ("building", "structure"),
    "Company": ("company", "business", "corporation", "organisation", "organization"),
    "Film": ("film", "movie"),
}

#: Hand-written rules, in priority order, first match wins.
#:
#: Written from the fourteen label names and general knowledge of what a Wikipedia
#: abstract for each looks like — NOT by reading the slice and patching failures, which
#: would make this a model fitted on the eval set and void every claim in this example.
#: Ordered most-specific first, because these texts overlap heavily: a film article
#: mentions people, an athlete article mentions clubs, a village article mentions rivers.
RULES = [
    ("Album", r"\b(album|studio album|ep released|track listing|records|label released|"
              r"debut album|discography)\b"),
    ("Film", r"\b(film|movie|directed by|screenplay|starring|feature film|documentary)\b"),
    ("WrittenWork", r"\b(novel|book|magazine|journal|newspaper|published by|author of|"
                    r"written by|manga|comic)\b"),
    ("Athlete", r"\b(footballer|football player|cricketer|baseball|basketball player|"
                r"boxer|athlete|plays for|played for|olympic)\b"),
    ("OfficeHolder", r"\b(politician|senator|congressman|governor|minister|mayor|"
                     r"member of parliament|elected|president of the)\b"),
    ("Artist", r"\b(singer|musician|painter|composer|guitarist|actor|actress|band|"
               r"artist|sculptor)\b"),
    ("EducationalInstitution", r"\b(school|university|college|academy|institute|campus|"
                               r"students|faculty)\b"),
    ("MeanOfTransportation", r"\b(locomotive|aircraft|automobile|ship|vessel|"
                             r"motorcycle|railcar|class of|engine|fuselage)\b"),
    ("Animal", r"\b(species of|genus|family of moth|beetle|bird|fish|spider|snail|"
               r"moth|subspecies)\b"),
    ("Plant", r"\b(plant|flowering|shrub|tree native|genus of|herb|orchid|fern)\b"),
    ("Village", r"\b(village|hamlet|rural|population of|census|district of iran|"
                r"municipality)\b"),
    ("NaturalPlace", r"\b(river|mountain|lake|creek|valley|peak|tributary|island)\b"),
    ("Building", r"\b(building|church|castle|hotel|stadium|bridge|tower|"
                 r"listed on the national register|historic)\b"),
    ("Company", r"\b(company|corporation|founded in|headquartered|manufacturer|"
                r"subsidiary|firm|inc\.|ltd)\b"),
]

#: The catch-all when no rule fires. ARBITRARY, and that is the honest description: unlike
#: AG News's "World", no DBpedia class means "other". Company is the corpus's first label
#: and nothing more. Whatever this is will be over-predicted, and the confusion matrix is
#: where that shows up rather than being hidden in an accuracy number.
DEFAULT_LABEL = "Company"

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
