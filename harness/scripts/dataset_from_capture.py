#!/usr/bin/env python3
"""Make a dataset version from a capture (RFC-019): choose records, freeze them as items.

    evh dataset-from-capture fleet_2026_10 --dataset-id triage_v1 --fieldset triage --field evidence_level
    evh dataset-from-capture fleet_2026_11 --dataset-id triage_v2 --from triage_v1 --where stage:propose

Only a record's BODY becomes the item: it is written to data/sources/<dataset>/<id>.txt (text) or
.json (anything else, as canonical JSON), so its sha256 is the capture's `body_sha256`. Fields,
outcome and source never enter an item's bytes; a record's fields become item fields only through a
declared field set (--fieldset, --field). The dataset is written by dataset-create's own code and
records how its items were chosen (`made_from`).

Selection, in this order: --where FIELD:VALUE (a record field; a dotted path reaches inside one),
--dedup exact|text (the same body, or the same text with case and whitespace folded: the first is
kept), then --sample N [--by FIELD] --seed S (a seeded sample, stratified by a field when given).
--from D_prev makes a new version: the earlier version's items stay, the new records are added, and
the lineage (added, removed, changed) is recorded as dataset-create --from records it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import random
import shutil
from collections import defaultdict

from evaluation_harness import _fields, _importers
from evaluation_harness._common import (
    CAPTURES,
    DATASETS,
    ROOT,
    SOURCES,
    dataset_id_ok,
    die,
    how,
    load_dataset,
    read_json,
    sha256,
)
from evaluation_harness.dataset_create import _fieldset, _lineage, _relative_source_dir, _say_lineage, _write


def dig(fields: dict, path: str):
    """A record field by name, or by a dotted path inside one."""
    cur = fields
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def load_capture(capture_id: str) -> tuple[dict, list]:
    """(capture.json, its records), every record checked against the hash the capture recorded."""
    base = CAPTURES / dataset_id_ok(capture_id)
    if not (base / "capture.json").is_file():
        die(f"no capture {capture_id!r} at {base}")
    doc = read_json(base / "capture.json")
    recs, bad = [], []
    for entry in doc.get("records") or []:
        f = base / "records" / f"{entry['id']}.json"
        if not f.is_file():
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
            + "\n  ".join(bad[:10])
        )
    return doc, recs


def _text(value) -> str:
    """A field's value as --where compares it: missing or null is ""."""
    return "" if value is None else str(value)


def select(recs: list, args) -> list:
    """The records --where, --dedup and --sample keep, in capture order."""
    for w in args.where:
        if "!=" in w:
            name, want = w.split("!=", 1)
            recs = [r for r in recs if _text(dig(r.get("fields") or {}, name)) != want]
            continue
        name, sep, want = w.partition(":")
        if not sep:
            die(f"--where {w!r}: FIELD:VALUE or FIELD!=VALUE")
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
    if args.sample is not None:
        if args.seed is None:
            die("--sample needs --seed, so the same sample can be drawn again")
        rng = random.Random(args.seed)
        if args.by:
            groups = defaultdict(list)
            for r in recs:
                groups[str(dig(r.get("fields") or {}, args.by))].append(r)
            # Proportional allocation, largest remainders first; at least one per group while N allows.
            total = len(recs)
            quota = {k: args.sample * len(v) / total for k, v in groups.items()}
            take = {k: int(q) for k, q in quota.items()}
            for k in sorted(quota, key=lambda k: (-(quota[k] - take[k]), k))[
                : args.sample - sum(take.values())
            ]:
                take[k] += 1
            chosen = {id(r) for k, v in sorted(groups.items()) for r in rng.sample(v, min(take[k], len(v)))}
        else:
            chosen = {id(r) for r in rng.sample(recs, min(args.sample, len(recs)))}
        recs = [r for r in recs if id(r) in chosen]
    return recs


def main() -> int:
    """Freeze a capture's chosen records as a dataset."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("capture", help="the capture's id (data/captures/<id>)")
    ap.add_argument("--dataset-id", required=True, help="lowercase_with_underscores")
    ap.add_argument("--from", dest="from_", metavar="DATASET_ID", help="the version this one grows from")
    ap.add_argument(
        "--where",
        action="append",
        default=[],
        help='FIELD:VALUE keeps matching records, FIELD!=VALUE drops them (repeatable; missing is "")',
    )
    ap.add_argument("--one-per", metavar="FIELD", help="keep one record per value of this field, the newest")
    ap.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="describe the dataset (source, environment, ...)",
    )
    ap.add_argument("--dedup", choices=("exact", "text"), help="drop records whose body repeats")
    ap.add_argument("--sample", type=int, help="keep N records, seeded")
    ap.add_argument("--by", help="with --sample: stratify by this field")
    ap.add_argument("--seed", type=int, help="with --sample: the seed")
    ap.add_argument("--fieldset", help="the field set (data/fields/<id>.yaml) declaring the item fields")
    ap.add_argument(
        "--field", action="append", default=[], help="a record field to keep as an item field (repeatable)"
    )
    ap.add_argument(
        "--hide-text", action="store_true", help="text: hidden: none of its text on any public surface"
    )
    ap.add_argument("--description", default="")
    ap.add_argument("--force", action="store_true", help="overwrite an existing dataset nothing cites yet")
    args = ap.parse_args()

    out = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if out.exists() and not args.force:
        die(
            f"{out} already exists: a dataset is frozen. Make a new version (e.g. _v2), or --force if nothing cites it."
        )
    tags = {}
    for t in args.tag:
        k, sep, v = t.partition("=")
        if not sep or not k.strip():
            die(f"--tag {t!r}: KEY=VALUE")
        tags[k.strip()] = v.strip()
    fieldset = _fieldset(args.fieldset)
    if args.field and not fieldset:
        die("--field needs --fieldset: a field set declares what an item may carry")
    doc, recs = load_capture(args.capture)
    kept = select(recs, args)
    if not kept and not args.from_:
        die("no record was kept: nothing to freeze")

    src = SOURCES / args.dataset_id
    if src.exists():
        shutil.rmtree(src)
    src.mkdir(parents=True)
    items, bad = [], []
    if args.from_:
        prev = load_dataset(args.from_)
        prev_src = _Path(prev.get("source_dir") or SOURCES)
        if not prev_src.is_absolute():
            prev_src = ROOT / prev_src
        for it in prev.get("items") or []:
            p = prev_src / it.get("source_path", it["item_id"])
            if not p.is_file():
                die(
                    f"--from {args.from_}: no source file {p} for {it['item_id']}; fetch or materialize it first"
                )
            shutil.copyfile(p, src / it["source_path"])
            items.append(dict(it))
    have = {it["item_id"] for it in items}
    for r in kept:
        if r["id"] in have:
            continue
        body = r["body"] if r.get("body") is not None else r["fields"]
        name = f"{r['id']}.{'txt' if isinstance(body, str) else 'json'}"
        (src / name).write_bytes(_importers.canonical(body))
        item = {"item_id": r["id"], "source_path": name, "source_sha256": sha256(src / name)}
        if fieldset and args.field:
            row = {f: dig(r.get("fields") or {}, f) for f in args.field}
            vals, errs = _fields.values_from(fieldset, {k: str(v) for k, v in row.items() if v is not None})
            bad += [f"{r['id']}: {e}" for e in errs]
            if vals:
                item["fields"] = vals
        items.append(item)
        have.add(r["id"])
    if bad:
        die(f"{len(bad)} field problem(s)\n  " + "\n  ".join(bad[:15]))
    lineage = _lineage(args.from_, args.dataset_id, items) if args.from_ else None
    made_from = {
        "capture": args.capture,
        "capture_sha256": hashlib.sha256((CAPTURES / args.capture / "capture.json").read_bytes()).hexdigest(),
        "query": doc.get("query") or {},
        "where": list(args.where),
        "one_per": args.one_per,
        "dedup": args.dedup,
        "sample": args.sample,
        "by": args.by,
        "seed": args.seed,
        "records": len(recs),
        "kept": len(kept),
    }
    previous = read_json(out) if out.exists() else {}
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


if __name__ == "__main__":
    raise SystemExit(main())
