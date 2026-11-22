"""What a dataset is made of and what hangs on it (RFC-032 step 6): the views the dataset-*, fieldset-*, failure-modes-*,
label-set-*, reference-*, capture-* and tag-set-* operations answer, read through the layout in model/datasets. A view
never carries a list that grows with the items (a dataset's items, a label set's items, a reference's checksums, a
capture's records, a tag set's tags): it carries their count."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.datasets import (
    CAPTURE,
    DATASET,
    FAILURE_MODES,
    FIELDSET,
    LABEL_SET,
    REFERENCE,
    TAG_SET,
    exposure_file,
    materialized_dir,
    profile_file,
    reference_items,
    rows_file,
    source_dir,
)
from evaluation_harness.model.entity import Entity, Problem


def rel(path: Path) -> str:
    """A path relative to the project, as the commands print it."""
    try:
        return path.relative_to(_common.project_root()).as_posix()
    except ValueError:
        return str(path)


def where(entity: Entity, rid: str) -> str:
    """The record's file, relative to the project."""
    return rel(entity.path(rid))


def _without(record: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in keys}


def parts(dataset_id: str, record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Where each part of the dataset is and whether it is here: its source's item folder and row map, its profile,
    its materialized copy, and a sealed side's exposure register (only where it is or should be)."""
    found = {
        "source": (source_dir(record), _store.is_dir),
        "rows": (rows_file(dataset_id), _store.is_file),
        "profile": (profile_file(dataset_id), _store.is_file),
        "materialized": (materialized_dir(dataset_id), _store.is_dir),
    }
    if record.get("sealed") or _store.is_file(exposure_file(dataset_id)):
        found["exposure"] = (exposure_file(dataset_id), _store.is_file)
    return {k: {"path": rel(p), "present": bool(here(p))} for k, (p, here) in found.items()}


def _delta(record: dict[str, Any]) -> dict[str, int]:
    d = record.get("derived_from") or {}
    return {k: len(d.get(k) or []) for k in ("added", "removed", "changed")}


def label_set_row(set_id: str, rec: dict[str, Any]) -> dict[str, Any]:
    """A label set as a list shows it."""
    from evaluation_harness import _visibility  # noqa: PLC0415

    src = rec.get("source") or {}
    return {
        "set": set_id,
        "dataset": rec.get("dataset_id"),
        "kind": src.get("kind"),
        "source": src,
        "guideline": rec.get("guideline"),
        "actor": rec.get("actor"),
        # A hidden dataset's notes are free text a person wrote on its items, which can quote them (RFC-019 section 4).
        "note": rec.get("note")
        if _visibility.text_shown(rec.get("dataset_id"), public=_visibility.public_env())
        else None,
        "items": rec.get("n_items", len(rec.get("items") or {})),
        "created_at": rec.get("created_at"),
    }


def _label_set_of(man: dict[str, Any]) -> str | None:
    """The id of the label set a reference was promoted from (its manifest names the set's dataset and its name), None for
    labels a script fetches."""
    pf = man.get("promoted_from") or {}
    return f"{pf.get('dataset_id')}/{pf['labels']}" if pf.get("labels") else None


def reference_row(rid: str, man: dict[str, Any]) -> dict[str, Any]:
    """A reference as a list shows it."""
    src = (man.get("promoted_from") or {}).get("source") or {}
    return {
        "reference": rid,
        "tier": man.get("tier"),
        "dataset": man.get("dataset_id"),
        "items": reference_items(man),
        "label_set": _label_set_of(man),
        "kind": src.get("kind"),
        "promoted_by": man.get("promoted_by"),
        "created_at": man.get("created_at"),
    }


def _tagged(rec: dict[str, Any]) -> int:
    if isinstance(rec.get("n_tagged"), int):
        return rec["n_tagged"]
    return sum(len(by_item) for by_item in (rec.get("runs") or {}).values())


def tag_set_row(set_id: str, rec: dict[str, Any]) -> dict[str, Any]:
    """A tag set as a list shows it."""
    return {
        "set": set_id,
        "dataset": rec.get("dataset_id"),
        "failure_modes": rec.get("failure_modes"),
        "runs": len(rec.get("runs") or {}),
        "tagged": _tagged(rec),
        "created_at": rec.get("created_at"),
    }


def _plain_json(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _records(
    entity: Entity, data: Path | None = None, check_format: bool = True
) -> list[tuple[str, dict[str, Any]]]:
    """Every record of the entity that reads, by id; one that does not is `evh validate`'s to name, as in references_of.
    `data`: another data directory than the project's (a deployment's copy of it); `check_format` False reads a tree of
    another format as it is (the catalog reads copies), through the JSON a record is."""
    ent = entity.under(data)
    out = []
    for rid in ent.ids(check_format=check_format):
        if check_format:
            try:
                out.append((rid, ent.get(rid)))
            except Problem:
                continue
        elif (doc := _plain_json(ent.path(rid))) is not None:
            out.append((rid, doc))
    return out


def _made_from(capture_id: str, datasets: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [i for i, d in datasets if (d.get("made_from") or {}).get("capture") == capture_id]


# -- datasets ---------------------------------------------------------------------------------------------------------


def list_datasets() -> list[dict[str, Any]]:
    """Every dataset: what it is, its parent, whether it is sealed, which parts are here, its label sets and references."""
    refs: dict[str, list[str]] = {}
    for rid, man in _records(REFERENCE):
        refs.setdefault(str(man.get("dataset_id")), []).append(rid)
    sets: dict[str, list[str]] = {}
    for sid in LABEL_SET.ids():
        sets.setdefault(sid.split("/", 1)[0], []).append(sid)
    out = []
    for ds, rec in _records(DATASET):
        out.append(
            {
                "dataset": ds,
                "version": rec.get("version"),
                "items": len(rec.get("items") or []),
                "description": rec.get("description"),
                "fieldset": rec.get("fieldset"),
                "parent": (rec.get("derived_from") or {}).get("dataset_id"),
                "sealed": bool(rec.get("sealed")),
                "parts": {k: v["present"] for k, v in parts(ds, rec).items() if k != "exposure"},
                "label_sets": sets.get(ds, []),
                "references": refs.get(ds, []),
            }
        )
    return out


def show_dataset(dataset: str) -> dict[str, Any]:
    """One dataset: its record less its items, its parts with their paths, its lineage, and what hangs on it."""
    from evaluation_harness.model.datasets import references_of  # noqa: PLC0415

    rec = DATASET.get(dataset)
    everyone = _records(DATASET)
    parent = (rec.get("derived_from") or {}).get("dataset_id")
    cap = (rec.get("made_from") or {}).get("capture")
    return {
        "dataset": dataset,
        "file": where(DATASET, dataset),
        "n_items": len(rec.get("items") or []),
        "record": _without(rec, "items"),
        "parts": parts(dataset, rec),
        "lineage": {
            "parent": {"dataset": parent, "exists": any(i == parent for i, _ in everyone), **_delta(rec)}
            if parent
            else None,
            "children": [
                {"dataset": i, **_delta(d)}
                for i, d in everyone
                if (d.get("derived_from") or {}).get("dataset_id") == dataset
            ],
        },
        "label_sets": [label_set_row(i, r) for i, r in _records(LABEL_SET) if i.split("/", 1)[0] == dataset],
        "references": [reference_row(i, REFERENCE.get(i)) for i in references_of(dataset)],
        "captures": [cap] if cap else [],
        "tag_sets": [tag_set_row(i, r) for i, r in _records(TAG_SET) if i.split("/", 1)[0] == dataset],
    }


# -- fieldsets and failure-mode lists ---------------------------------------------------------------------------------


def list_fieldsets() -> list[dict[str, Any]]:
    """Every fieldset: its fields counted, the datasets that use it, its file."""
    datasets = _records(DATASET)
    return [
        {
            "fieldset": i,
            "description": f.get("description"),
            "fields": len(f.get("fields") or []),
            "datasets": [d for d, r in datasets if r.get("fieldset") == i],
            "file": where(FIELDSET, i),
        }
        for i, f in _records(FIELDSET)
    ]


def show_fieldset(fieldset: str) -> dict[str, Any]:
    """The fieldset's record, its file, and the datasets that use it."""
    rec = FIELDSET.get(fieldset)
    return {
        "fieldset": fieldset,
        "record": rec,
        "file": where(FIELDSET, fieldset),
        "datasets": [d for d, r in _records(DATASET) if r.get("fieldset") == fieldset],
    }


def list_failure_modes() -> list[dict[str, Any]]:
    """Every failure-mode list: its modes counted, the tag sets made from it, its file."""
    tags = _records(TAG_SET)
    return [
        {
            "failure_modes": i,
            "description": f.get("description"),
            "modes": len(f.get("modes") or []),
            "tag_sets": [t for t, r in tags if r.get("failure_modes") == i],
            "file": where(FAILURE_MODES, i),
        }
        for i, f in _records(FAILURE_MODES)
    ]


def show_failure_modes(failure_modes: str) -> dict[str, Any]:
    """The list's record, its file, and the tag sets made from it."""
    rec = FAILURE_MODES.get(failure_modes)
    return {
        "failure_modes": failure_modes,
        "record": rec,
        "file": where(FAILURE_MODES, failure_modes),
        "tag_sets": [t for t, r in _records(TAG_SET) if r.get("failure_modes") == failure_modes],
    }


# -- label sets, tag sets -----------------------------------------------------------------------------------------------


def _owned(entity: Entity, dataset: str) -> list[tuple[str, dict[str, Any]]]:
    DATASET.get(dataset)
    return [(i, r) for i, r in _records(entity) if i.split("/", 1)[0] == dataset]


def list_label_sets(dataset: str) -> list[dict[str, Any]]:
    """The dataset's label sets."""
    return [label_set_row(i, r) for i, r in _owned(LABEL_SET, dataset)]


def show_label_set(dataset: str, set: str, items: bool = False) -> dict[str, Any]:
    """One label set: its record less its items, where its folder is, and the references promoted from it; with
    `items`, the label of each item too."""
    from evaluation_harness import _visibility  # noqa: PLC0415

    sid = f"{dataset}/{set}"
    rec = LABEL_SET.get(sid)
    # What a person wrote on a hidden dataset's items is free text, which can quote them (RFC-019 section 4).
    hidden = not _visibility.text_shown(dataset, public=_visibility.public_env())
    out = {
        "set": sid,
        "items": rec.get("n_items", len(rec.get("items") or {})),
        "record": _without(rec, "items", *(("notes", "note") if hidden else ())),
        "folder": rel(LABEL_SET.path(sid).parent),
        "references": [reference_row(i, m) for i, m in _records(REFERENCE) if _label_set_of(m) == sid],
    }
    if items:
        # Labels are reference material: a public server answers with none (the gold references are not published).
        out["labels"] = {} if hidden or _visibility.public_env() else rec.get("items") or {}
    return out


def list_tag_sets(dataset: str) -> list[dict[str, Any]]:
    """The dataset's tag sets."""
    return [tag_set_row(i, r) for i, r in _owned(TAG_SET, dataset)]


def show_tag_set(dataset: str, set: str) -> dict[str, Any]:
    """One tag set: its record less the tags, how many of each failure mode were tagged, and its file."""
    sid = f"{dataset}/{set}"
    rec = TAG_SET.get(sid)
    modes = Counter(
        m
        for by_item in (rec.get("runs") or {}).values()
        for t in by_item.values()
        for m in t.get("modes") or []
    )
    return {
        "set": sid,
        "runs": len(rec.get("runs") or {}),
        "tagged": _tagged(rec),
        "modes": dict(modes.most_common()),
        "record": _without(rec, "runs"),
        "file": where(TAG_SET, sid),
    }


# -- references ---------------------------------------------------------------------------------------------------------


def list_references() -> list[dict[str, Any]]:
    """Every reference: its tier, its dataset, the label set and who it came from."""
    return [reference_row(i, m) for i, m in _records(REFERENCE)]


def show_reference(tier: str, name: str) -> dict[str, Any]:
    """One reference: its manifest less the checksums, and its folder."""
    rid = f"{tier}/{name}"
    man = REFERENCE.get(rid)
    return {
        "reference": rid,
        "items": reference_items(man),
        "label_set": _label_set_of(man),
        "record": _without(man, "items_sha256"),
        "folder": rel(REFERENCE.path(rid).parent),
    }


# -- captures ---------------------------------------------------------------------------------------------------------


def _capture_row(
    cid: str,
    doc: dict[str, Any],
    datasets: list[tuple[str, dict[str, Any]]],
    sets: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """A capture as a list shows it: what read it and when (the first and last of its records), whether it continues
    one, was sampled or scrubbed, and the datasets and label sets made from it."""
    times = sorted(r["created_at"] for r in doc.get("records") or [] if r.get("created_at"))
    return {
        "capture": cid,
        "importer": doc.get("importer"),
        "captured_at": doc.get("captured_at"),
        "window": doc.get("window") or {},
        "records": doc.get("n_records", len(doc.get("records") or [])),
        "first": times[0] if times else None,
        "last": times[-1] if times else None,
        "scrubbed": bool(doc.get("scrubbed")),
        "continues": doc.get("continues"),
        "sample": doc.get("sample"),
        "datasets": _made_from(cid, datasets),
        "label_sets": [i for i, r in sets if (r.get("source") or {}).get("capture") == cid],
        "query": doc.get("query") or {},
    }


def list_captures(data: Path | None = None, check_format: bool = True) -> list[dict[str, Any]]:
    """Every capture: what read it, when, how many records, and the datasets and label sets made from it."""
    datasets, sets = _records(DATASET, data, check_format), _records(LABEL_SET, data, check_format)
    return [_capture_row(i, c, datasets, sets) for i, c in _records(CAPTURE, data, check_format)]


def capture_views(data: Path | None = None, check_format: bool = True) -> list[dict[str, Any]]:
    """Every capture as the catalog's Captures page shows it (`list_captures` is the same listing)."""
    return list_captures(data, check_format)


def show_capture(capture: str) -> dict[str, Any]:
    """One capture: its record less the records' list, and the datasets and label sets made from it."""
    doc = CAPTURE.get(capture)
    return _capture_row(capture, doc, _records(DATASET), _records(LABEL_SET)) | {
        "record": _without(doc, "records"),
        "file": where(CAPTURE, capture),
    }
