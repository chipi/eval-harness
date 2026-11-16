"""The datasets' operations (RFC-032 step 6): `evh dataset-list`, `dataset-show`, `fieldset-*`, `failure-modes-*`,
`label-set-*`, `tag-set-*`, `reference-*`, `capture-*`, and the resources under /api/v1/datasets, /fieldsets,
/failure-modes, /references and /captures. A dataset, a label set, a tag set, a reference and a capture are written by
their own commands (dataset-create, label-import, reference-promote, capture, ...), never edited: only the fieldsets and
the failure-mode lists are. The older views (`evh dataset-list`, `references`, `captures`, `labels`, `tags`) stay as they
are until the catalog moves onto the model (step 8)."""

from __future__ import annotations

from typing import Any

from evaluation_harness.catalog_periods import PERIODS
from evaluation_harness.ops.registry import Op

_SET = {
    "type": "object",
    "description": "fields to set, by dotted key; the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}
_D = "evaluation_harness.ops.datasets"
_PERIOD = {
    "type": "string",
    "enum": [k for k, *_ in PERIODS],
    "description": "add each row's numbers in a period counted from today: "
    + ", ".join(f"{k} ({label})" for k, label, _ in PERIODS),
}

OPS = (
    Op("dataset-list", "read", "every dataset: its version, items, fieldset, parent, whether it is sealed, the parts that are here, its label sets and references; and what the catalog knows of it: its arms and systems, its tags, where it came from",
       "GET", "/datasets", f"{_D}:list_datasets", f"{_D}:say_datasets",
       inputs={
           "tag": {"type": "array", "items": {"type": "string"}, "description": "KEY=VALUE: only datasets with this tag"},
           "period": _PERIOD,
       }),
    Op("dataset-show", "read", "one dataset: its record (the item count for the items), its parts and where they are, its lineage, label sets, references, capture and tag sets; and what the catalog knows of it: its arms and systems, its tags, the baselines promoted on it, its item fields",
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
    Op("label-set-list", "read", "a dataset's label sets: who gave the labels, from what, under which guideline, how many, when; which sets cover its items, a set of another dataset covering the items it shares; how often two sets agree (kappa, alpha) with each pair's confusion matrix and, on request, the items people contest", "GET",
       "/datasets/{dataset}/label-sets", f"{_D}:list_label_sets", f"{_D}:say_label_sets",
       inputs={
           "contested": {"type": "boolean", "description": "per item, how many people's label sets agree with the gold reference, the most contested first"},
       }),
    Op("label-set-show", "read", "one label set: its record (the item count for the items), its folder and the references promoted from it; with items, the label of each item",
       "GET", "/datasets/{dataset}/label-sets/{set}", f"{_D}:show_label_set", f"{_D}:say_label_set",
       inputs={"items": {"type": "boolean", "description": "the label of each item too"}}, public_hidden=("items",)),
    Op("tag-set-list", "read", "a dataset's tag sets: the failure-mode list each is named from, the outputs tagged; and per arm how often each failure mode was tagged", "GET",
       "/datasets/{dataset}/tag-sets", f"{_D}:list_tag_sets", f"{_D}:say_tag_sets"),
    Op("tag-set-show", "read", "one tag set: its record (the runs and outputs counted), the failure modes tagged and how often",
       "GET", "/datasets/{dataset}/tag-sets/{set}", f"{_D}:show_tag_set", f"{_D}:say_tag_set"),
    Op("reference-list", "read", "every reference: its tier, dataset, items, who wrote it, the label set and person or model it came from, and how many arms are scored against it",
       "GET", "/references", f"{_D}:list_references", f"{_D}:say_references", inputs={"period": _PERIOD}),
    Op("reference-show", "read", "one reference: its manifest (the item count for the checksums), where it came from, its folder, and the arms scored against it",
       "GET", "/references/{tier}/{name}", f"{_D}:show_reference", f"{_D}:say_reference"),
    Op("capture-list", "read", "every capture: what read it, when, how many records, and the datasets and label sets made from it",
       "GET", "/captures", f"{_D}:list_captures", f"{_D}:say_captures"),
    Op("capture-show", "read", "one capture: its record (the record count for the records) and what was made from it",
       "GET", "/captures/{capture}", f"{_D}:show_capture", f"{_D}:say_capture"),
)  # fmt: skip


def _catalog() -> tuple[Any, dict]:
    """The adapter and what the catalog collects from it: the arms by dataset."""
    from evaluation_harness.ops.views import _view  # noqa: PLC0415

    return _view()


def list_datasets(tag: list[str] | None = None, period: str | None = None) -> dict[str, Any]:
    """Every dataset with its parts and what hangs on it, and the catalog's view of it: its arms and systems, its tags
    and where it came from; with `tag`, only the datasets with every tag given; with `period`, each one's runs and spend
    in the period against the one before."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415
    from evaluation_harness.model import period_views  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415
    from evaluation_harness.ops.views import _period  # noqa: PLC0415

    want = []
    for t in tag or []:
        k, sep, val = t.partition("=")
        if not sep or not k:
            raise Problem(f"tag {t!r}: KEY=VALUE", "bad-argument")
        want.append((k, val))
    A, by_ds = _catalog()
    rows = []
    recorded = v.list_datasets()
    # A dataset that runs were recorded on but whose record is not in this project is a row too, as the catalog lists it.
    bare = [
        {"dataset": d, "version": None, "items": None, "description": None, "fieldset": None, "parent": None,
         "sealed": False, "parts": {}, "label_sets": [], "references": [], "recorded": False}
        for d in sorted(set(by_ds) - {r["dataset"] for r in recorded})
    ]  # fmt: skip
    for r in [{**x, "recorded": True} for x in recorded] + bare:
        c = by_ds.get(r["dataset"])
        tags = dict((c or {}).get("tags") or {})
        if want and not all(tags.get(k) == val for k, val in want):
            continue
        rows.append(
            {
                **r,
                "arms": len(c["arms"]) if c else None,
                "systems": cb._n_systems({r["dataset"]: c}) if c else None,
                "tags": tags,
                "origin": (c or {}).get("origin") or None,
            }
        )
    out: dict[str, Any] = {"datasets": rows, "item_word": A.item_word}
    key = _period(period)
    if key:
        got = period_views.rows_in(A, by_ds, cb.period_datasets(A, by_ds), key)
        for row in rows:
            row["period"] = _jsonout.plain(got["rows"].get(row["dataset"]))
        out["period"] = {"key": key, "line": got["line"]}
    return out


def show_dataset(dataset: str) -> dict[str, Any]:
    """The dataset: record, parts, lineage and what hangs on it, and the catalog's view of it: its arms and systems, its
    tags, the baselines promoted on it and a summary of each of its item fields."""
    from evaluation_harness import _fields, _jsonout  # noqa: PLC0415
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness.catalog_adapter import item_fields  # noqa: PLC0415
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    out = v.show_dataset(dataset)
    A, by_ds = _catalog()
    c = by_ds.get(dataset)
    out["catalog"] = None
    if c is not None:
        fl = item_fields(A, dataset)
        fs = fl.get("fieldset")
        items = [{"item_id": i, "fields": f} for i, f in (fl.get("values") or {}).items()]
        out["catalog"] = _jsonout.plain(
            {
                "arms": len(c["arms"]),
                "systems": cb._n_systems({dataset: c}),
                "tags": c.get("tags") or {},
                "origin": c.get("origin") or None,
                "baselines": c.get("baselines") or [],
                "fields": {"fieldset": fs.get("fieldset_id", ""), "fields": _fields.summary(fs, items)}
                if fs
                else None,
            }
        )
    return out


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


def list_label_sets(dataset: str, contested: bool = False) -> dict[str, Any]:
    """The dataset's label sets, which sets cover its items (a set of another dataset covers the items it shares), how often two
    of them agree (Cohen's kappa, Krippendorff's alpha, all together, each pair's confusion matrix) and, on request, the items
    people contest. A hidden dataset's labels are per-item text (RFC-019 section 4): its confusion matrices stay out of a
    public answer, the counts and the coefficients stay."""
    from evaluation_harness import _jsonout, _visibility  # noqa: PLC0415
    from evaluation_harness._common import load_dataset  # noqa: PLC0415
    from evaluation_harness._label_sets import agreement, agreement_all, coverage  # noqa: PLC0415
    from evaluation_harness._label_sets import contested as contested_items  # noqa: PLC0415
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415
    from evaluation_harness.ops.legacy import refusing  # noqa: PLC0415

    with refusing():
        rows = v.list_label_sets(dataset)
        n = len(load_dataset(dataset).get("items") or [])
        cov = coverage(dataset)
        pairs = agreement(dataset)
        together = agreement_all(dataset)
        disputed = contested_items(dataset) if contested else None
    if not _visibility.text_shown(dataset, public=_visibility.public_env()):
        pairs = [{k: x for k, x in p.items() if k != "confusion"} for p in pairs]
    out: dict[str, Any] = {
        "dataset": dataset,
        "items": n,
        "label_sets": rows,
        "coverage": [{**c, "items": sorted(c["items"])} for c in cov],
        "agreement": pairs,
        "agreement_all": together,
    }
    if contested:
        out["contested"] = disputed
    return _jsonout.plain(out)


def show_label_set(dataset: str, set: str, items: bool = False) -> dict[str, Any]:
    """The label set's record, folder and references; with `items`, the label of each item."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_label_set(dataset, set, items)


def list_tag_sets(dataset: str) -> dict[str, Any]:
    """The dataset's tag sets, and per arm how many outputs were tagged and how often each failure mode was."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness._tags import counts  # noqa: PLC0415
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    rows = v.list_tag_sets(dataset)
    return {"dataset": dataset, "tag_sets": rows, "arms": _jsonout.plain(counts(dataset))}


def show_tag_set(dataset: str, set: str) -> dict[str, Any]:
    """The tag set's record and its modes counted."""
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    return v.show_tag_set(dataset, set)


def list_references(period: str | None = None) -> dict[str, Any]:
    """Every reference, who wrote it and how many arms are scored against it; with `period`, the arms and runs in it."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415
    from evaluation_harness.model import period_views  # noqa: PLC0415
    from evaluation_harness.ops.views import _period  # noqa: PLC0415

    A, by_ds = _catalog()
    scored: dict[str, int] = {}
    author: dict[str, Any] = {}
    for c in by_ds.values():
        for r in c["refs"]:
            author[r["id"]] = r.get("author")
        for a in c["arms"]:
            if a.get("reference") and not a["judge"]:
                scored[a["reference"]] = scored.get(a["reference"], 0) + 1
    rows = [
        {**r, "author": author.get(r["reference"]), "scored": scored.get(r["reference"], 0)}
        for r in v.list_references()
    ]
    out: dict[str, Any] = {"references": rows}
    key = _period(period)
    if key:
        got = period_views.rows_in(A, by_ds, cb.period_references(A, by_ds), key)
        for row in rows:
            row["period"] = _jsonout.plain(got["rows"].get(row["reference"]))
        out["period"] = {"key": key, "line": got["line"]}
    return out


def show_reference(tier: str, name: str) -> dict[str, Any]:
    """The reference's manifest and folder, and the arms scored against it (best first)."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import arm_views  # noqa: PLC0415
    from evaluation_harness.model import dataset_views as v  # noqa: PLC0415

    out = v.show_reference(tier, name)
    _, by_ds = _catalog()
    rid = out["reference"]
    hit = next(((ds, c) for ds, c in by_ds.items() for r in c["refs"] if r["id"] == rid), None)
    out["scored_against"] = []
    if hit:
        _, c = hit
        tiers = {x["id"]: x["tier"] for x in c["refs"]}
        out["scored_against"] = _jsonout.plain(
            [
                {
                    "arm": a["arm"],
                    "label": a["label"],
                    "metric": a["metric"],
                    "mean": a["mean"],
                    "n": a["n"],
                    "row": arm_views.kind(a, tiers),
                }
                for a in sorted(
                    (a for a in c["arms"] if a["reference"] == rid and not a["judge"]),
                    key=lambda a: -(a["mean"] or 0),
                )
            ]
        )
    return out


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
    from evaluation_harness import catalog_views  # noqa: PLC0415

    return catalog_views.say(catalog_views.print_datasets, r)


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
    if r.get("catalog"):
        from evaluation_harness import catalog_views  # noqa: PLC0415

        lines += [
            "  " + x if x else x
            for x in catalog_views.say(catalog_views.print_dataset_catalog, r["catalog"]).split("\n")
        ]
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


def _confusion_lines(p: dict[str, Any]) -> str:
    """A pair's confusion matrix: the first set's labels down, the second's across."""
    conf = p["confusion"]
    cols = sorted({c for row in conf.values() for c in row})
    corner = f"{p['a'].split('/')[-1]} ↓ · {p['b'].split('/')[-1]} →"
    first = max(len(x) for x in [*conf, corner]) + 2
    widths = [len(c) + 3 for c in cols]
    lines = ["    " + corner.ljust(first) + "".join(c.rjust(w) for c, w in zip(cols, widths, strict=True))]
    for r in sorted(conf):
        lines.append(
            "    "
            + r.ljust(first)
            + "".join(str(conf[r].get(c, 0)).rjust(w) for c, w in zip(cols, widths, strict=True))
        )
    return "\n".join(lines)


def _pair_line(p: dict[str, Any]) -> str:
    """Two label sets compared, in words: both label, the same answers, sharing one, kappa and alpha."""
    if p.get("kind") != "categories":
        return f"both label {p['both']}; free text, not compared as text"

    def coef(k: str) -> str:
        return "undefined" if p.get(k) is None else f"{p[k]:.2f}"

    alpha = coef("alpha") + (" (MASI)" if p.get("alpha_distance") == "MASI" else "")
    return (
        f"both label {p['both']}, the same answers on {p['same']}, sharing one on {p['share']}; "
        f"Cohen's kappa {coef('kappa')}, Krippendorff's alpha {alpha}"
    )


def say_label_sets(r: dict[str, Any]) -> str:
    """label-set-list's answer as text: the sets that cover the dataset's items, how they agree, the items people contest."""
    if not r["coverage"] and not r["label_sets"]:
        return f"{r['dataset']}: no labels yet (evh label-sheet, evh label-import, evh label-from-run)"
    from evaluation_harness._label_sets import source_line  # noqa: PLC0415

    out = [f"{r['dataset']}: {r['items']} item(s), {len(r['coverage'])} label set(s)"]
    for c in r["coverage"]:
        g = (c.get("guideline") or {}).get("path") or "no guideline"
        out.append(
            f"  {c['dataset_id']}/{c['set']}: {source_line(c['source'])}, {len(c['items'])} of {r['items']} item(s), {g}"
        )
    t = r.get("agreement_all")
    if t:
        ci = t.get("ci")
        out.append(
            f"  all {t['sets']} sets together: Krippendorff's alpha {t['alpha']}"
            + (f" (95% interval {ci[0]} to {ci[1]})" if ci else "")
            + f" over {t['items']} item(s) labelled twice or more, {t['alpha_distance']}"
        )
    for p in r["agreement"]:
        out.append(f"  {p['a']} and {p['b']}: {_pair_line(p)}")
        if p.get("confusion"):
            out.append(_confusion_lines(p))
    if "contested" in r:
        d = r["contested"]
        if not d:
            out.append("  contested: no gold reference, or no person set labels its items beside it")
        else:
            out.append(
                f"  contested: {d['contested']} of {d['items']} item(s) have a person who disagrees with the {d['tier']} reference"
            )
            out += [
                f"    {x['item_id']}: {x['agree']} of {x['people']} agree"
                for x in d["rows"]
                if x["agree"] < x["people"]
            ][:40]
    return "\n".join(out)


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
    if r["first"]:
        lines.append(f"  records from {r['first']} to {r['last']}")
    if r["continues"]:
        lines.append(f"  continues    {r['continues']}")
    if r["sample"]:
        s = r["sample"]
        lines.append(
            f"  a sample: rate {s['rate']}, seed {s['seed']} ({s.get('kept')} of {s.get('read')} read)"
        )
    lines += [f"  dataset      {d}" for d in r["datasets"]]
    lines += [f"  label set    {s}" for s in r["label_sets"]]
    return "\n".join(lines)
