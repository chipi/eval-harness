"""Make a dataset version from a capture (RFC-019): choose records, freeze them as items.

    evh dataset-from-capture --capture fleet_2026_10 --dataset-id triage_v1 --fieldset triage --field evidence_level
    evh dataset-from-capture --capture fleet_2026_11 --dataset-id triage_v2 --from triage_v1 --where stage:propose

Only a record's BODY becomes the item: it is written to data/sources/<dataset>/<id>.txt (text) or
.json (anything else, as canonical JSON), so its sha256 is the capture's `body_sha256`. Fields,
outcome and source never enter an item's bytes; a record's fields become item fields only through a
declared field set (--fieldset keeps every field it declares; --field narrows that to the ones named).
The dataset is written by dataset-create's own code and
records how its items were chosen (`made_from`).

Selection, in this order: --where FIELD:VALUE (a record field; a dotted path reaches inside one),
--one-per FIELD (the newest record per value), --dedup exact|text (the same body, or the same text with case and
whitespace folded: the first is kept). Sampling is the capture's: `evh capture --sample-rate R --seed S`.
--from D_prev makes a new version: the earlier version's items stay, the new records are added, a
record of an item the earlier version has replaces it (a corrected body is counted as changed), and
the lineage (added, removed, changed) is recorded as dataset-create --from records it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from evaluation_harness import _fields, _importers, _store
from evaluation_harness._common import (
    CAPTURES,
    DATASETS,
    SOURCES,
    dataset_id_ok,
    die,
    how,
    load_dataset,
    read_json,
    sha256,
)
from evaluation_harness.dataset_create import _fieldset, _lineage, _relative_source_dir, _say_lineage, _write
from evaluation_harness.model import datasets as _datasets
from evaluation_harness.ops import legacy


def dig(fields: dict, path: str):
    """A record field by name, or by a dotted path inside one."""
    cur = fields
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def load_capture(capture_id: str, captures_dir: Path | None = None) -> tuple[dict, list]:
    """(capture.json, its records), every record checked against the hash the capture recorded; from the project's
    captures, or `captures_dir`."""
    base = (captures_dir or CAPTURES) / dataset_id_ok(capture_id)
    if not _store.is_file(base / "capture.json"):
        die(f"no capture {capture_id!r} at {base}", "not-found")
    doc = read_json(base / "capture.json")
    recs, bad = [], []
    for entry in doc.get("records") or []:
        f = base / "records" / f"{entry['id']}.json"
        if not _store.is_file(f):
            bad.append(f"{entry['id']}: its record file is missing")
            continue
        rec = read_json(f)
        if _importers.record_sha256(rec) != entry["sha256"]:
            bad.append(f"{entry['id']}: the record does not match the hash the capture recorded")
            continue
        recs.append(rec)
    if bad:
        die(
            f"capture {capture_id}: {len(bad)} record(s) changed or missing since it was made\n  "
            + "\n  ".join(bad[:10]),
            "mismatch",
        )
    return doc, recs


def _text(value) -> str:
    """A field's value as --where compares it: missing or null is ""."""
    return "" if value is None else str(value)


def select(recs: list, args) -> list:
    """The records --where, --one-per and --dedup keep, in capture order."""
    for w in args.where:
        if "!=" in w:
            name, want = w.split("!=", 1)
            recs = [r for r in recs if _text(dig(r.get("fields") or {}, name)) != want]
            continue
        name, sep, want = w.partition(":")
        if not sep:
            die(f"--where {w!r}: FIELD:VALUE or FIELD!=VALUE", "bad-argument")
        recs = [r for r in recs if _text(dig(r.get("fields") or {}, name)) == want]
    if args.one_per:
        # One record per value of a field, the newest (by created_at, then id): many records on one
        # fingerprint are not independent items for the paired test.
        best: dict = {}
        for r in recs:
            key = _text(dig(r.get("fields") or {}, args.one_per))
            rank = (r.get("created_at") or "", r["id"])
            if key not in best or rank > best[key][0]:
                best[key] = (rank, r["id"])
        keep = {rid for _, rid in best.values()}
        recs = [r for r in recs if r["id"] in keep]
    if args.dedup:
        seen, kept = set(), []
        for r in recs:
            text = _importers.canonical(r["body"] if r.get("body") is not None else r["fields"]).decode(
                "utf-8"
            )
            key = " ".join(text.lower().split()) if args.dedup == "text" else text
            if key not in seen:
                seen.add(key)
                kept.append(r)
        recs = kept
    return recs


def body(**inputs: Any) -> int:
    """Freeze a capture's chosen records as a dataset."""
    args = legacy.namespace(inputs, "dataset-from-capture", {"from": "from_"})
    out = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if _store.exists(out) and not args.force:
        die(
            f"{out} already exists: a dataset is frozen. Make a new version (e.g. _v2), or --force if nothing cites it.",
            "would-overwrite",
        )
    tags = {}
    for t in args.tag:
        k, sep, v = t.partition("=")
        if not sep or not k.strip():
            die(f"--tag {t!r}: KEY=VALUE", "bad-argument")
        tags[k.strip()] = v.strip()
    fieldset = _fieldset(args.fieldset)
    if args.field and not fieldset:
        die("--field needs --fieldset: a field set declares what an item may carry", "bad-argument")
    doc, recs = load_capture(args.capture)
    kept = select(recs, args)
    if not kept and not args.from_:
        die("no record was kept: nothing to freeze", "not-enough")

    src = SOURCES / args.dataset_id
    if _store.exists(src):
        # Only what this dataset's record says the harness wrote here goes: anything else in the folder (a
        # capture's own export, say) may be the only copy, so it is refused, never deleted.
        ours = (
            {it.get("source_path", it["item_id"]) for it in load_dataset(args.dataset_id).get("items") or []}
            if _store.exists(out)
            else set()
        )
        other = sorted(
            p.relative_to(src).as_posix()
            for p in _store.rglob(src, "*")
            if _store.is_file(p) and p.relative_to(src).as_posix() not in ours
        )
        if other:
            die(
                f"{src} holds {len(other)} file(s) the harness did not write ({', '.join(other[:3])}"
                f"{', …' if len(other) > 3 else ''}): items go in this folder and replace what is there. "
                "Move them, or name the dataset differently.",
                "would-overwrite",
            )
        _store.rmtree(src)
    _store.mkdir(src, parents=True)
    items, bad = [], []
    if args.from_:
        prev = load_dataset(args.from_)
        prev_src = _datasets.source_dir(prev)
        for it in prev.get("items") or []:
            p = prev_src / it.get("source_path", it["item_id"])
            if not _store.is_file(p):
                die(
                    f"--from {args.from_}: no source file {p} for {it['item_id']}; fetch or materialize it first",
                    "not-materialized",
                )
            _store.copy_file(p, src / it["source_path"])
            items.append(dict(it))
    # A field set keeps the fields it declares; --field narrows that to the ones named.
    keep_fields = list(args.field) or (list(_fields.declared(fieldset)) if fieldset else [])
    # A record in this capture replaces the earlier version's item of the same id: the capture is what
    # the item is now (a corrected body is a change, counted as one), and the earlier items it does not
    # hold stay as they were.
    at = {it["item_id"]: i for i, it in enumerate(items)}
    seen: set = set()
    for r in kept:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        body = r["body"] if r.get("body") is not None else r["fields"]
        name = f"{r['id']}.{'txt' if isinstance(body, str) else 'json'}"
        if r["id"] in at:
            old = items[at[r["id"]]].get("source_path")
            if old and old != name and _store.is_file(src / old):
                _store.unlink(src / old)
        _store.write_bytes(src / name, _importers.canonical(body))
        item = {"item_id": r["id"], "source_path": name, "source_sha256": sha256(src / name)}
        if keep_fields:
            row = {f: dig(r.get("fields") or {}, f) for f in keep_fields}
            vals, errs = _fields.values_from(fieldset, {k: str(v) for k, v in row.items() if v is not None})
            bad += [f"{r['id']}: {e}" for e in errs]
            if vals:
                item["fields"] = vals
        if r["id"] in at:
            items[at[r["id"]]] = item
        else:
            at[r["id"]] = len(items)
            items.append(item)
    if bad:
        die(f"{len(bad)} field problem(s)\n  " + "\n  ".join(bad[:15]), "invalid-file")
    lineage = _lineage(args.from_, args.dataset_id, items) if args.from_ else None
    made_from = {
        "capture": args.capture,
        "capture_sha256": hashlib.sha256(
            _store.read_bytes(CAPTURES / args.capture / "capture.json")
        ).hexdigest(),
        "query": doc.get("query") or {},
        "where": list(args.where),
        "one_per": args.one_per,
        "dedup": args.dedup,
        "records": len(recs),
        "kept": len(kept),
    }
    previous = read_json(out) if _store.exists(out) else {}
    _write(
        out,
        args.dataset_id,
        items,
        previous,
        fieldset,
        args.description or f"{len(kept)} record(s) from capture {args.capture}",
        _relative_source_dir(src),
        lineage,
        {
            "made_from": made_from,
            **({"tags": tags} if tags else {}),
            **({"text": "hidden"} if args.hide_text else {}),
        },
    )
    print(
        f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s); {len(kept)} of {len(recs)} records kept)"
    )
    _say_lineage(lineage)
    print(
        "Next: "
        + how(
            f"evh dataset-materialize --dataset-id {args.dataset_id}",
            f"make dataset-materialize DATASET_ID={args.dataset_id}",
        )
    )
    return 0
