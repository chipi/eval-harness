"""The datasets' operations (RFC-032 step 6): `evh dataset-list`, `dataset-show`, `fieldset-*`, `failure-modes-*`,
`label-set-*`, `tag-set-*`, `reference-*`, `capture-*`, and the resources under /api/v1/datasets, /fieldsets,
/failure-modes, /references and /captures. A dataset, a label set, a tag set, a reference and a capture are written by
their own commands (dataset-create, label-import, reference-promote, capture, ...), never edited: only the fieldsets and
the failure-mode lists are. The older views (`evh datasets`, `references`, `captures`, `labels`, `tags`) stay as they
are until the catalog moves onto the model (step 8)."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_SET = {
    "type": "object",
    "description": "fields to set, by dotted key; the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}
_D = "evaluation_harness.ops.datasets"

OPS = (
    Op("dataset-list", "read", "every dataset: its version, items, fieldset, parent, whether it is sealed, the parts that are here, its label sets and references",
       "GET", "/datasets", f"{_D}:list_datasets", f"{_D}:say_datasets"),
    Op("dataset-show", "read", "one dataset: its record (the item count for the items), its parts and where they are, its lineage, label sets, references, capture and tag sets",
       "GET", "/datasets/{dataset}", f"{_D}:show_dataset", f"{_D}:say_dataset"),
    Op("fieldset-list", "read", "every fieldset: the facts each item carries, how many, and the datasets that use it",
       "GET", "/fieldsets", f"{_D}:list_fieldsets", f"{_D}:say_fieldsets"),
    Op("fieldset-show", "read", "one fieldset: its fields and the datasets that use it", "GET", "/fieldsets/{fieldset}",
       f"{_D}:show_fieldset", f"{_D}:say_fieldset"),
    Op("fieldset-new", "edit", "make a fieldset (data/fields/<id>.yaml), checked against its schema", "POST",
       "/fieldsets/{fieldset}", f"{_D}:new_fieldset", f"{_D}:say_saved", inputs={"set": _SET}, required=("set",)),
    Op("fieldset-set", "edit", "change a fieldset's fields, checked; its comments kept", "PATCH", "/fieldsets/{fieldset}",
       f"{_D}:set_fieldset", f"{_D}:say_saved", inputs={"set": _SET, "unset": _UNSET}),
    Op("failure-modes-list", "read", "every failure-mode list: its modes counted and the tag sets made from it",
       "GET", "/failure-modes", f"{_D}:list_failure_modes", f"{_D}:say_failure_modes"),
    Op("failure-modes-show", "read", "one failure-mode list: its modes and the tag sets made from it", "GET",
       "/failure-modes/{failure_modes}", f"{_D}:show_failure_modes", f"{_D}:say_failure_mode"),
    Op("failure-modes-new", "edit", "make a failure-mode list (data/failure-modes/<id>.yaml), checked against its schema",
       "POST", "/failure-modes/{failure_modes}", f"{_D}:new_failure_modes", f"{_D}:say_saved",
       inputs={"set": _SET}, required=("set",)),
    Op("failure-modes-set", "edit", "change a failure-mode list's fields, checked; its comments kept", "PATCH",
       "/failure-modes/{failure_modes}", f"{_D}:set_failure_modes", f"{_D}:say_saved",
       inputs={"set": _SET, "unset": _UNSET}),
    Op("label-set-list", "read", "a dataset's label sets: who gave the labels, how many, when", "GET",
       "/datasets/{dataset}/label-sets", f"{_D}:list_label_sets", f"{_D}:say_label_sets"),
    Op("label-set-show", "read", "one label set: its record (the item count for the items), its folder and the references promoted from it",
       "GET", "/datasets/{dataset}/label-sets/{set}", f"{_D}:show_label_set", f"{_D}:say_label_set"),
    Op("tag-set-list", "read", "a dataset's tag sets: the failure-mode list each is named from, the outputs tagged", "GET",
       "/datasets/{dataset}/tag-sets", f"{_D}:list_tag_sets", f"{_D}:say_tag_sets"),
    Op("tag-set-show", "read", "one tag set: its record (the runs and outputs counted), the failure modes tagged and how often",
       "GET", "/datasets/{dataset}/tag-sets/{set}", f"{_D}:show_tag_set", f"{_D}:say_tag_set"),
    Op("reference-list", "read", "every reference: its tier, dataset, items, and the label set and person or model it came from",
       "GET", "/references", f"{_D}:list_references", f"{_D}:say_references"),
    Op("reference-show", "read", "one reference: its manifest (the item count for the checksums), where it came from and its folder",
       "GET", "/references/{tier}/{name}", f"{_D}:show_reference", f"{_D}:say_reference"),
    Op("capture-list", "read", "every capture: what read it, when, how many records, and the datasets and label sets made from it",
       "GET", "/captures", f"{_D}:list_captures", f"{_D}:say_captures"),
    Op("capture-show", "read", "one capture: its record (the record count for the records) and what was made from it",
       "GET", "/captures/{capture}", f"{_D}:show_capture", f"{_D}:say_capture"),
)  # fmt: skip


def list_datasets() -> dict[str, Any]:
    """Every dataset with its parts and what hangs on it."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"datasets": v.list_datasets()}


def show_dataset(dataset: str) -> dict[str, Any]:
    """The dataset: record, parts, lineage and what hangs on it."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_dataset(dataset)


def list_fieldsets() -> dict[str, Any]:
    """Every fieldset."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"fieldsets": v.list_fieldsets()}


def show_fieldset(fieldset: str) -> dict[str, Any]:
    """The fieldset's record, file and datasets."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_fieldset(fieldset)


def new_fieldset(fieldset: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the fieldset from its fields."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.datasets import FIELDSET  # noqa: PLC0415

    return FIELDSET.save(
        fieldset, _settings_form.set_values({"fieldset_id": fieldset}, list(set.items()), []), by, new=True
    )


def set_fieldset(
    fieldset: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Change the fieldset's fields."""
    from evaluation_harness.model.datasets import FIELDSET  # noqa: PLC0415

    return FIELDSET.patch(fieldset, list((set or {}).items()), list(unset or []), by)


def list_failure_modes() -> dict[str, Any]:
    """Every failure-mode list."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"failure_modes": v.list_failure_modes()}


def show_failure_modes(failure_modes: str) -> dict[str, Any]:
    """The list's record, file and tag sets."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_failure_modes(failure_modes)


def new_failure_modes(failure_modes: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the failure-mode list from its fields."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.datasets import FAILURE_MODES  # noqa: PLC0415

    return FAILURE_MODES.save(
        failure_modes,
        _settings_form.set_values({"failure_modes_id": failure_modes}, list(set.items()), []),
        by,
        new=True,
    )


def set_failure_modes(
    failure_modes: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Change the failure-mode list's fields."""
    from evaluation_harness.model.datasets import FAILURE_MODES  # noqa: PLC0415

    return FAILURE_MODES.patch(failure_modes, list((set or {}).items()), list(unset or []), by)


def list_label_sets(dataset: str) -> dict[str, Any]:
    """The dataset's label sets."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"dataset": dataset, "label_sets": v.list_label_sets(dataset)}


def show_label_set(dataset: str, set: str) -> dict[str, Any]:
    """The label set's record, folder and references."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_label_set(dataset, set)


def list_tag_sets(dataset: str) -> dict[str, Any]:
    """The dataset's tag sets."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"dataset": dataset, "tag_sets": v.list_tag_sets(dataset)}


def show_tag_set(dataset: str, set: str) -> dict[str, Any]:
    """The tag set's record and its modes counted."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_tag_set(dataset, set)


def list_references() -> dict[str, Any]:
    """Every reference."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"references": v.list_references()}


def show_reference(tier: str, name: str) -> dict[str, Any]:
    """The reference's manifest and folder."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_reference(tier, name)


def list_captures() -> dict[str, Any]:
    """Every capture."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return {"captures": v.list_captures()}


def show_capture(capture: str) -> dict[str, Any]:
    """The capture's record and what was made from it."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_capture(capture)


def say_saved(r: dict[str, Any]) -> str:
    """A save's answer as text."""
    return f"{r['id']}: {'saved' if r['changed'] else 'unchanged (nothing to save)'}"


def _table(rows: list[tuple[str, ...]]) -> str:
    """Rows of cells, each column as wide as its widest cell (the last one is not padded)."""
    w = [max(len(r[i]) for r in rows) for i in range(len(rows[0]) - 1)]
    return "\n".join(
        "  ".join(c.ljust(w[i]) if i < len(w) else c for i, c in enumerate(r)).rstrip() for r in rows
    )


def say_datasets(r: dict[str, Any]) -> str:
    """dataset-list's answer as text: one dataset a line."""
    if not r["datasets"]:
        return "no datasets yet: evh dataset-create --dataset-id <id> --source-dir <folder>"
    rows: list[tuple[str, ...]] = []
    for d in r["datasets"]:
        here = [k for k, v in d["parts"].items() if v]
        rows.append(
            (
                d["dataset"],
                f"v{d['version']}",
                f"{d['items']} items",
                "sealed" if d["sealed"] else "",
                f"from {d['parent']}" if d["parent"] else "",
                f"fieldset {d['fieldset']}" if d["fieldset"] else "",
                f"here: {' '.join(here) or 'none'}; {len(d['label_sets'])} label set(s), {len(d['references'])} reference(s)",
            )
        )
    return _table(rows)


def say_dataset(r: dict[str, Any]) -> str:
    """dataset-show's answer as text: the record's facts, the parts, the lineage and what hangs on it."""
    rec = r["record"]
    lines = [f"{r['dataset']}  v{rec.get('version')}  {r['n_items']} items  ({r['file']})"]
    if rec.get("description"):
        lines.append(f"  {rec['description']}")
    if rec.get("fieldset"):
        lines.append(f"  fieldset     {rec['fieldset']}")
    if rec.get("sealed"):
        lines.append(f"  sealed       held out at {rec['sealed'].get('at', '?')}")
    p = r["lineage"]["parent"]
    if p:
        lines.append(
            f"  derived from {p['dataset']}{'' if p['exists'] else ' (not in this project)'}: "
            f"{p['added']} added, {p['removed']} removed, {p['changed']} changed"
        )
    for c in r["lineage"]["children"]:
        lines.append(
            f"  made into    {c['dataset']}: {c['added']} added, {c['removed']} removed, {c['changed']} changed"
        )
    lines += [f"  made from    capture {c}" for c in r["captures"]]
    for name, x in r["parts"].items():
        lines.append(f"  {name:<12} {x['path']}{'' if x['present'] else '  (not here)'}")
    for s in r["label_sets"]:
        lines.append(f"  label set    {s['set']}: {s['kind']}, {s['items']} items")
    for x in r["references"]:
        lines.append(f"  reference    {x['reference']}: {x['items']} items")
    for t in r["tag_sets"]:
        lines.append(f"  tag set      {t['set']}: {t['tagged']} output(s) in {t['runs']} run(s)")
    return "\n".join(lines)


def say_fieldsets(r: dict[str, Any]) -> str:
    """fieldset-list's answer as text: one fieldset a line."""
    if not r["fieldsets"]:
        return (
            "no fieldsets yet: evh fieldset-new <id> --set fields.0.name=<field> --set fields.0.type=choice"
        )
    return _table(
        [
            (f["fieldset"], f"{f['fields']} fields", ", ".join(f["datasets"]) or "no dataset", f["file"])
            for f in r["fieldsets"]
        ]
    )


def say_fieldset(r: dict[str, Any]) -> str:
    """fieldset-show's answer as text: its fields, one a line, and the datasets that use it."""
    rec = r["record"]
    lines = [f"{r['fieldset']}  ({r['file']})"]
    if rec.get("description"):
        lines.append(f"  {rec['description']}")
    lines += [f"  field        {f.get('name')} ({f.get('type')})" for f in rec.get("fields") or []]
    lines.append(f"  used by      {', '.join(r['datasets']) or 'no dataset'}")
    return "\n".join(lines)


def say_failure_modes(r: dict[str, Any]) -> str:
    """failure-modes-list's answer as text: one list a line."""
    if not r["failure_modes"]:
        return "no failure-mode lists yet: evh failure-modes-new <id> --set modes.0.id=<mode>"
    return _table(
        [
            (f["failure_modes"], f"{f['modes']} modes", f"{len(f['tag_sets'])} tag set(s)", f["file"])
            for f in r["failure_modes"]
        ]
    )


def say_failure_mode(r: dict[str, Any]) -> str:
    """failure-modes-show's answer as text: its modes, one a line, and the tag sets made from it."""
    rec = r["record"]
    lines = [f"{r['failure_modes']}  ({r['file']})"]
    if rec.get("description"):
        lines.append(f"  {rec['description']}")
    lines += [
        f"  mode         {m.get('id')}" + (f": {m['label']}" if m.get("label") else "")
        for m in rec.get("modes") or []
    ]
    lines.append(f"  tag sets     {', '.join(r['tag_sets']) or 'none'}")
    return "\n".join(lines)


def say_label_sets(r: dict[str, Any]) -> str:
    """label-set-list's answer as text: one set a line."""
    if not r["label_sets"]:
        return f"{r['dataset']} has no label sets (evh label-import, label-from-run, label-from-capture)"
    return _table(
        [
            (s["set"], f"{s['kind']}", f"{s['items']} items", str(s["created_at"] or ""))
            for s in r["label_sets"]
        ]
    )


def say_label_set(r: dict[str, Any]) -> str:
    """label-set-show's answer as text: where the labels came from, and the references promoted from it."""
    rec = r["record"]
    lines = [f"{r['set']}  {r['items']} items  ({r['folder']})"]
    lines += [f"  source       {k} = {v}" for k, v in sorted((rec.get("source") or {}).items())]
    for k in ("guideline", "created_at", "actor", "note"):
        if rec.get(k):
            lines.append(f"  {k:<12} {rec[k]}")
    lines += [f"  reference    {x['reference']}" for x in r["references"]]
    return "\n".join(lines)


def say_tag_sets(r: dict[str, Any]) -> str:
    """tag-set-list's answer as text: one set a line."""
    if not r["tag_sets"]:
        return f"{r['dataset']} has no tag sets (evh sheet-import --tags)"
    return _table(
        [
            (
                t["set"],
                t["failure_modes"] or "",
                f"{t['tagged']} output(s) in {t['runs']} run(s)",
                str(t["created_at"] or ""),
            )
            for t in r["tag_sets"]
        ]
    )


def say_tag_set(r: dict[str, Any]) -> str:
    """tag-set-show's answer as text: the list it is named from and each failure mode's count."""
    rec = r["record"]
    lines = [f"{r['set']}  {r['tagged']} output(s) in {r['runs']} run(s)  ({r['file']})"]
    lines.append(f"  failure modes {rec.get('failure_modes')}")
    lines += [f"  {m:<20} {n}" for m, n in r["modes"].items()]
    return "\n".join(lines)


def say_references(r: dict[str, Any]) -> str:
    """reference-list's answer as text: one reference a line."""
    if not r["references"]:
        return "no references yet: evh reference-promote"
    return _table(
        [
            (
                x["reference"],
                str(x["dataset"]),
                f"{x['items']} items",
                f"from {x['label_set']}" if x["label_set"] else f"from {x['kind'] or 'a script'}",
            )
            for x in r["references"]
        ]
    )


def say_reference(r: dict[str, Any]) -> str:
    """reference-show's answer as text: what it is and where it came from."""
    rec = r["record"]
    src = (rec.get("promoted_from") or {}).get("source") or {}
    lines = [
        f"{r['reference']}  {rec.get('tier')}  {r['items']} items, dataset {rec.get('dataset_id')}  ({r['folder']})"
    ]
    if r["label_set"]:
        lines.append(f"  label set    {r['label_set']}")
    if src:
        lines.append(f"  from         {src.get('kind')}" + (f", {src['by']}" if src.get("by") else ""))
    for k in ("reason", "caveat", "promoted_by", "created_at", "source"):
        if rec.get(k):
            lines.append(f"  {k.replace('_', ' '):<12} {rec[k]}")
    return "\n".join(lines)


def say_captures(r: dict[str, Any]) -> str:
    """capture-list's answer as text: one capture a line."""
    if not r["captures"]:
        return "no captures yet: evh capture --importer ... --query ... --capture <id>"
    return _table(
        [
            (
                c["capture"],
                f"{c['records']} records",
                str(c["captured_at"] or ""),
                f"datasets: {', '.join(c['datasets']) or 'none'}; label sets: {len(c['label_sets'])}",
            )
            for c in r["captures"]
        ]
    )


def say_capture(r: dict[str, Any]) -> str:
    """capture-show's answer as text: what read it and what was made from it."""
    lines = [
        f"{r['capture']}  {r['records']} records from {r['importer']}, captured {r['captured_at']}"
        + ("  scrubbed" if r["scrubbed"] else "")
        + f"  ({r['file']})"
    ]
    if r["continues"]:
        lines.append(f"  continues    {r['continues']}")
    lines += [f"  dataset      {d}" for d in r["datasets"]]
    lines += [f"  label set    {s}" for s in r["label_sets"]]
    return "\n".join(lines)
