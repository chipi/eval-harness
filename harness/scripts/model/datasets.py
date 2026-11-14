"""Datasets and what belongs to them (RFC-032 step 6): the dataset's record and its parts (items, source, profile, the
materialized copy, the sealed side's exposure), and the entities around it (fieldsets, failure-mode lists, label sets,
tag sets, references, captures), with one table of where each lives. Nothing outside the model builds these paths.

A dataset's record is data/datasets/<id>.json; its parts stay where they always were (owner, 2026-11-14: the layout is
named here, nothing is moved):

    the source's item files   the folder its record names (`source_dir`, relative to the project), else data/sources
    the source's row map      data/sources/<id>.rows.json
    its profile               data/profiles/<id>.json (a stored part: it needs item texts git does not hold)
    its materialized copy     data/materialized/<id>/ (local state, rebuilt by dataset-materialize)
    its exposure register     data/exposure/<id>.jsonl (a sealed side's)

The picks are one log for the project, data/picks.jsonl.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.entity import Entity

#: A dataset id as dataset-create allows it (capitals too): an id the model's lists would leave out is never made.
DATASET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: A label set's or tag set's own name.
SET_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,99}")
_PARTS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _dataset_links(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The fieldset, the parent and the capture a dataset names exist."""
    out = []
    fs = record.get("fieldset")
    if fs and not _store.is_file(FIELDSET.path(str(fs))):
        out.append({"path": ["fieldset"], "message": f"no fieldset {fs!r} in this project"})
    parent = (record.get("derived_from") or {}).get("dataset_id")
    if parent and not _store.is_file(record_file(str(parent))):
        out.append(
            {"path": ["derived_from", "dataset_id"], "message": f"no dataset {parent!r} in this project"}
        )
    cap = (record.get("made_from") or {}).get("capture")
    if cap and not _store.is_file(CAPTURE.path(str(cap))):
        out.append({"path": ["made_from", "capture"], "message": f"no capture {cap!r} in this project"})
    return out


DATASET = Entity(
    name="dataset",
    plural="datasets",
    folder="datasets",
    id_field="dataset_id",
    schema="dataset.schema.json",
    suffix=".json",
    links=_dataset_links,
    id_pattern=DATASET_ID,
    editable=False,
)
FIELDSET = Entity(
    name="fieldset",
    plural="fieldsets",
    folder="fields",
    id_field="fieldset_id",
    schema="fieldset.schema.json",
)
FAILURE_MODES = Entity(
    name="failure-mode list",
    plural="failure-mode lists",
    folder="failure-modes",
    id_field="failure_modes_id",
    schema="failure-modes.schema.json",
)
LABEL_SET = Entity(
    name="label set",
    plural="label sets",
    folder="labels",
    id_field="set",
    parent_field="dataset_id",
    schema="label-set.schema.json",
    suffix="/labels.json",
    id_pattern=_PARTS,
    editable=False,
)
TAG_SET = Entity(
    name="tag set",
    plural="tag sets",
    folder="tags",
    id_field="set",
    parent_field="dataset_id",
    schema="tag-set.schema.json",
    suffix="/tags.json",
    id_pattern=_PARTS,
    editable=False,
)
#: A reference's id is `<tier>/<name>`; its name is the dataset's id unless it was promoted under another
#: (`gold/ag_news_200_adj1`), so the manifest names no field the name must equal.
REFERENCE = Entity(
    name="reference",
    plural="references",
    folder="references",
    id_field="",
    parent_field="tier",
    schema="reference.schema.json",
    suffix="/manifest.json",
    id_pattern=_PARTS,
    editable=False,
)
CAPTURE = Entity(
    name="capture",
    plural="captures",
    folder="captures",
    id_field="capture_id",
    schema="capture.schema.json",
    suffix="/capture.json",
    id_pattern=_PARTS,
    editable=False,
)


def _data(data: Path | None) -> Path:
    """The data directory read: the project's, or another one given (a deployment's copy of it)."""
    return _common.DATA if data is None else Path(data)


def record_file(dataset_id: str, data: Path | None = None) -> Path:
    """The dataset's record."""
    return _data(data) / "datasets" / f"{dataset_id}.json"


def source_dir(record: dict[str, Any]) -> Path:
    """Where a dataset's item files are: the folder its record names, relative to the project (as dataset-create
    records it), else data/sources. The one place this is worked out (seven readers did it, one of them against the
    directory the command ran in: from a subfolder every item was missing, 2026-11-14)."""
    rec = record.get("source_dir") if isinstance(record, dict) else None
    if not rec:
        return _common.SOURCES
    p = Path(str(rec))
    return p if p.is_absolute() else _common.ROOT / p


def rows_file(dataset_id: str, data: Path | None = None) -> Path:
    """The source's row map (each item's row and sha256 in the source it was fetched from)."""
    return _data(data) / "sources" / f"{dataset_id}.rows.json"


def profile_file(dataset_id: str, data: Path | None = None) -> Path:
    """The dataset's profile."""
    return _data(data) / "profiles" / f"{dataset_id}.json"


def materialized_dir(dataset_id: str, data: Path | None = None) -> Path:
    """The dataset's materialized copy on this machine."""
    return _data(data) / "materialized" / dataset_id


def exposure_file(dataset_id: str, data: Path | None = None) -> Path:
    """A sealed side's exposure register."""
    return _data(data) / "exposure" / f"{dataset_id}.jsonl"


def picks_file(data: Path | None = None) -> Path:
    """The project's picks."""
    return _data(data) / "picks.jsonl"


def label_set_dir(set_id: str, data: Path | None = None) -> Path:
    """A label set's folder (`<dataset>/<set>`): its labels.json and a text per item."""
    return LABEL_SET.under(data).path(set_id).parent


def reference_dir(reference_id: str, data: Path | None = None) -> Path:
    """A reference's folder (`<tier>/<name>`): its manifest and a text per item."""
    return REFERENCE.under(data).path(reference_id).parent


def references_of(dataset_id: str, data: Path | None = None, check_format: bool = True) -> list[str]:
    """The ids of every reference on the dataset, by the dataset its manifest names (a reference promoted under
    another name, `gold/ag_news_200_adj1`, is the dataset's too); sorted."""
    ref = REFERENCE.under(data)
    out = []
    for rid in ref.ids(check_format=check_format):
        try:
            man = ref.get(rid)
        except Exception:  # noqa: BLE001 — a manifest that does not read is validate's (V16) to say
            continue
        if man.get("dataset_id") == dataset_id:
            out.append(rid)
    return out


def label_sets_of(dataset_id: str, data: Path | None = None, check_format: bool = True) -> list[str]:
    """The ids of the dataset's label sets (`<dataset>/<set>`), sorted."""
    return [
        i for i in LABEL_SET.under(data).ids(check_format=check_format) if i.split("/", 1)[0] == dataset_id
    ]


#: How a score read against a label set is labelled: `labels-<dataset>-<set>` (`labels.<dataset>.<set>` in the
#: score's folder name, `labels/<dataset>/<set>` as the reference it is scored against).
LABELS_LABEL = "labels-"


def label_of(set_id: str) -> str:
    """The label a run scored against the label set `<dataset>/<set>` is read under."""
    ds, _, name = set_id.partition("/")
    return f"{LABELS_LABEL}{ds}-{name}"


def is_label_of(label: str, dataset_id: str) -> bool:
    """Whether `label` is one a score against one of the dataset's label sets is read under."""
    return str(label).startswith(f"{LABELS_LABEL}{dataset_id}-")
