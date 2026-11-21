"""A dataset record as a Hugging Face dataset README: YAML metadata, then the card (PLAN_0.8.0 P1).

The front matter uses the Hub's own card keys (`license` as the Hub spells an SPDX id, lowercased; `pretty_name`;
`configs` naming the data file when one is given), and the body asks the datasheet questions with the record's
answers, each under the heading the Hub's dataset card template uses where one fits. Nothing is invented: a question
the card does not answer is left out, and the licence is left out when it is `unknown` or none was given.
"""

from __future__ import annotations

from typing import Any

import yaml
from evaluation_harness._card import QUESTIONS

#: Where each card answer goes, under the Hub template's headings (Dataset Creation, Uses, Bias, Risks, …).
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Uses", ("dataUseCases",)),
    (
        "Dataset Creation",
        (
            "dataCollection",
            "dataCollectionType",
            "dataCollectionRawData",
            "dataCollectionTimeframe",
            "dataCollectionMissingData",
            "dataPreprocessingProtocol",
            "dataManipulationProtocol",
            "dataImputationProtocol",
        ),
    ),
    (
        "Annotations",
        (
            "dataAnnotationProtocol",
            "dataAnnotationPlatform",
            "dataAnnotationAnalysis",
            "annotationsPerItem",
            "annotatorDemographics",
            "machineAnnotationTools",
        ),
    ),
    ("Personal and Sensitive Information", ("personalSensitiveInformation",)),
    ("Bias, Risks, and Limitations", ("dataBiases", "dataLimitations", "dataSocialImpact")),
    ("Maintenance", ("dataReleaseMaintenancePlan",)),
)


def readme(record: dict[str, Any], data_file: str | None = None) -> str:
    """The README text: front matter and the card's answers; `data_file` (the file a publish writes) names its data."""
    meta: dict[str, Any] = {"pretty_name": record["dataset_id"]}
    lic = record.get("licence")
    if lic and lic != "unknown":
        meta["license"] = lic.lower() if not lic.startswith("LicenseRef-") else "other"
        if lic.startswith("LicenseRef-"):
            meta["license_name"] = lic[len("LicenseRef-") :]
    if data_file:
        meta["configs"] = [{"config_name": "default", "data_files": [{"split": "test", "path": data_file}]}]
    src = record.get("source") or {}
    lines = [
        "---",
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip(),
        "---",
        "",
        f"# {record['dataset_id']}",
        "",
        record.get("description") or "",
        "",
        (
            f"Version {record.get('version')}, {len(record.get('items') or [])} items, frozen by the evaluation"
            " harness: each item's id and the sha256 of its bytes are its identity."
        ),
    ]
    if src.get("ref") or src.get("url"):
        lines += [
            "",
            "Source: "
            + " ".join(str(x) for x in (src.get("provider"), src.get("ref"), src.get("url")) if x)
            + (f", revision {src['revision']}" if src.get("revision") else "")
            + ".",
        ]
    card = record.get("card") or {}
    for heading, keys in SECTIONS:
        answered = [k for k in keys if card.get(k)]
        if not answered:
            continue
        lines += ["", f"## {heading}", ""]
        for k in answered:
            lines += [f"**{QUESTIONS[k]}** {card[k]}", ""]
    return "\n".join(lines).rstrip() + "\n"
