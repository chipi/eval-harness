"""A dataset's card: the datasheet questions, answered in Croissant's responsible-AI words (PLAN_0.8.0 E4).

A `card` block on the dataset record holds short texts under the property names of Croissant RAI 1.0 (2024-03-06),
without the `rai:` prefix, so `evh dataset-card --format croissant` (E6) writes them as they are. Each answers one of
the questions Datasheets for Datasets asks. All are optional; the card is what describes a dataset, never what it is,
so changing it is no new version (E3).
"""

from __future__ import annotations

from typing import Any

#: The card's keys (Croissant RAI 1.0 property names) and the question each answers, in the order a card is read.
QUESTIONS: dict[str, str] = {
    "dataUseCases": "What is it for, and what should it not be used for?",
    "dataCollection": "How were the items collected?",
    "dataCollectionType": "What kind of collection was it (scraped, surveyed, logged, written for the purpose…)?",
    "dataCollectionRawData": "Where do the raw items come from?",
    "dataCollectionTimeframe": "Over what period were they collected?",
    "dataCollectionMissingData": "What is missing, and why?",
    "dataPreprocessingProtocol": "What was done to the items before they were frozen?",
    "dataManipulationProtocol": "Were items changed (cleaned, merged, rewritten)? How?",
    "dataImputationProtocol": "Were missing values filled in? How?",
    "dataAnnotationProtocol": "How were the labels or reference answers made?",
    "dataAnnotationPlatform": "With what platform or tool were they made?",
    "dataAnnotationAnalysis": "How were several people's labels turned into one?",
    "annotationsPerItem": "How many labels does an item have?",
    "annotatorDemographics": "Who labelled them?",
    "machineAnnotationTools": "Which software labelled items, if any?",
    "personalSensitiveInformation": "Is there personal or sensitive information in it?",
    "dataBiases": "What biases are known?",
    "dataLimitations": "What are its known limits?",
    "dataSocialImpact": "What could its use do to people?",
    "dataReleaseMaintenancePlan": "Who maintains it, and how is it versioned or retired?",
}


def problems(card: Any) -> list[str]:
    """What is wrong with a card block, [] when nothing is."""
    if not isinstance(card, dict):
        return ["card is not an object"]
    out = [
        f"card.{k} is not a card key (evh dataset-describe --card-template lists them)"
        for k in card
        if k not in QUESTIONS
    ]
    out += [f"card.{k} is not a text" for k, v in card.items() if k in QUESTIONS and not isinstance(v, str)]
    return out


def template() -> str:
    """A card to fill, as YAML: each key with its question as a comment."""
    return "".join(f"# {q}\n{k}: \n" for k, q in QUESTIONS.items())
