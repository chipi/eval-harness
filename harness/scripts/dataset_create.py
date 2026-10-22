#!/usr/bin/env python3
"""Freeze a selection of source items into a dataset.

A dataset is not "the data". It is a NAMED, FROZEN selection plus the hash of
every item in it — which is what makes two runs comparable. The `dataset_id` is
the comparison contract:

    A metric compared across two different dataset_ids is not a comparison.
    It is a coincidence.

Sources are immutable. If an item changes, that is a NEW dataset (`_v2`), never
an edit in place — every number already published was measured on the old bytes.

    python scripts/dataset_create.py --dataset-id smoke_v1
    python scripts/dataset_create.py --dataset-id smoke_v1 --limit 3 --tag quick

Items can carry fields a project declares (ADR-0003), and can live at a URL:

    --fieldset tickets --fields fields.csv     values by item_id, typed by data/fields/tickets.yaml
    --manifest items.csv                       one row per item: item_id, source_url (and
                                               source_sha256 to pin it; without it the bytes are
                                               fetched and pinned now); other columns are fields
    --update-fields --fields fields.csv        new values on an existing dataset whose items are
                                               unchanged: fields are not its identity, so no run
                                               measured on it is invalidated
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _fetch
import _fields
from _common import (
    DATASETS,
    ROOT,
    SCHEMAS,
    SOURCES,
    die,
    how,
    now,
    read_json,
    sha256,
    write_json,
)


def _relative_source_dir(source_dir: Path) -> str:
    """``source_dir`` relative to the harness root, or its bare name if it lies outside.

    Never an absolute path: a dataset is copied between machines and checked into git, and
    the directory it was built from is not a property of the host that built it.
    """
    try:
        return source_dir.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return source_dir.name


def _identity(items: list) -> list:
    """What freezes a dataset: each item's id, bytes and where they come from. Not its fields."""
    keys = ("item_id", "source_path", "source_url", "source_sha256")
    return [{k: it.get(k) for k in keys} for it in items]


def _fieldset(fieldset_id):
    """The named field set, checked against its schema; None when none is named."""
    if not fieldset_id:
        return None
    fs = _fields.load_fieldset(fieldset_id)
    if fs is None:
        die(
            f"no field set {fieldset_id!r}: expected {_fields.fieldset_path(fieldset_id)}\n"
            "  Declare the fields there first (schemas/fieldset.schema.json, docs: CONCEPTS, item fields)."
        )
    if fs.get("fieldset_id") != fieldset_id:
        die(
            f"{_fields.fieldset_path(fieldset_id)}: fieldset_id {fs.get('fieldset_id')!r} is not its file name"
        )
    try:
        import jsonschema  # noqa: PLC0415

        jsonschema.validate(fs, json.loads((SCHEMAS / "fieldset.schema.json").read_text()))
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — jsonschema.ValidationError, reported as it is
        die(f"{_fields.fieldset_path(fieldset_id)}: {getattr(exc, 'message', exc)}")
    return fs


def _attach(items: list, fieldset: dict, path: Path) -> None:
    """Put the values in `path` (rows keyed by item_id) on the matching items, typed."""
    if not path.is_file():
        die(f"no fields file at {path}")
    by_id = {it["item_id"]: it for it in items}
    bad = []
    for n, row in enumerate(_fields.read_rows(path), 1):
        iid = str(row.get("item_id") or "").strip()
        if iid not in by_id:
            bad.append(f"row {n}: item_id {iid!r} is not an item of this dataset")
            continue
        vals, errs = _fields.values_from(fieldset, row, skip=("item_id",))
        bad += [f"row {n} ({iid}): {e}" for e in errs]
        # An empty cell in a declared column means "this item has no value": it clears one
        # that was there (--update-fields), and on a new dataset leaves it absent.
        cleared = {
            c
            for c, raw in row.items()
            if c in _fields.declared(fieldset) and (raw is None or (isinstance(raw, str) and not raw.strip()))
        }
        merged = {k: v for k, v in by_id[iid].get("fields", {}).items() if k not in cleared}
        merged.update(vals)
        if merged:
            by_id[iid]["fields"] = merged
        else:
            by_id[iid].pop("fields", None)
    if bad:
        die(f"{path}: {len(bad)} problem(s)\n  " + "\n  ".join(bad[:15]))


def _from_manifest(path: Path, fieldset, source_dir: Path, tags: list) -> list:
    """Items from a manifest: each row an item_id and its source_url (pinned by source_sha256,
    or fetched and pinned now), or a source_path under --source-dir. Other columns are fields."""
    if not path.is_file():
        die(f"no manifest at {path}")
    known = ("item_id", "source_url", "source_path", "source_sha256")
    items, bad, pinned = [], [], 0
    for n, row in enumerate(_fields.read_rows(path), 1):
        iid = str(row.get("item_id") or "").strip()
        url, rel = str(row.get("source_url") or "").strip(), str(row.get("source_path") or "").strip()
        sha = str(row.get("source_sha256") or "").strip().lower()
        if not iid:
            bad.append(f"row {n}: no item_id")
            continue
        item: dict = {"item_id": iid}
        if url:
            # A pinned hash is taken as given: materialize fetches and checks it. Without one,
            # the bytes are fetched now and their hash becomes the item's identity.
            got = sha
            if not got:
                try:
                    _, got = _fetch.fetch(url, None)
                except _fetch.FetchError as exc:
                    bad.append(f"row {n} ({iid}): {exc}")
                    continue
                pinned += 1
            elif len(got) != 64 or any(c not in "0123456789abcdef" for c in got):
                bad.append(f"row {n} ({iid}): source_sha256 {got!r} is not a sha256")
                continue
            item.update(source_path=rel or f"{iid}{_fetch.suffix_of(url)}", source_url=url, source_sha256=got)
        elif rel:
            p = source_dir / rel
            if not p.is_file():
                bad.append(f"row {n} ({iid}): no file {p}")
                continue
            item.update(source_path=rel, source_sha256=sha256(p))
        else:
            bad.append(f"row {n} ({iid}): neither source_url nor source_path")
            continue
        if tags:
            item["tags"] = list(tags)
        extra = {k: v for k, v in row.items() if k not in known}
        if extra and not fieldset:
            bad.append(f"row {n} ({iid}): columns {', '.join(sorted(extra))} need --fieldset to declare them")
        elif fieldset:
            vals, errs = _fields.values_from(fieldset, extra)
            bad += [f"row {n} ({iid}): {e}" for e in errs]
            if vals:
                item["fields"] = vals
        items.append(item)
    if len({it["item_id"] for it in items}) != len(items):
        bad.append("an item_id appears more than once")
    if bad:
        die(f"{path}: {len(bad)} problem(s)\n  " + "\n  ".join(bad[:15]))
    if not items:
        die(f"{path}: no items")
    if pinned:
        print(f"  pinned {pinned} item(s) now: fetched, and their sha256 recorded")
    return items


def _write(
    out: Path, dataset_id: str, items: list, previous: dict, fieldset, description: str, source_dir: str
) -> None:
    # A re-create that selects the SAME items keeps its original created_at. Without this
    # the documented first command, `make demo`, rewrites a tracked file on every run and
    # leaves a new clone with a dirty tree — a timestamp presented as a change when nothing
    # about the selection changed. What freezes a dataset is the item hashes; created_at is
    # a label, and it should move when the selection does, not when the clock does (nor when
    # a field is corrected: fields are not the selection).
    unchanged = (
        _identity(previous.get("items") or []) == _identity(items)
        and previous.get("dataset_id") == dataset_id
    )
    created_at = previous.get("created_at") if unchanged and previous.get("created_at") else now()
    if fieldset:
        bad = [p for it in items for p in _fields.problems(fieldset, it["item_id"], it.get("fields") or {})]
        if bad:
            die(f"{len(bad)} field problem(s)\n  " + "\n  ".join(bad[:15]))
    doc = {"dataset_id": dataset_id, "version": "1.0", "description": description, "created_at": created_at}
    if source_dir:
        doc["source_dir"] = source_dir
    if fieldset:
        doc["fieldset"] = fieldset["fieldset_id"]
        doc["fields_sha256"] = _fields.digest(items)
    doc["items"] = items
    write_json(out, doc)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="lowercase_with_underscores")
    ap.add_argument("--source-dir", type=Path, default=SOURCES)
    ap.add_argument("--glob", default="*", help="which files under --source-dir are items")
    ap.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "descend into subdirectories of --source-dir. OFF by default, and that default "
            "is the fix for a silent merge: this used to always recurse, so once an example "
            "had fetched its corpus into data/sources/<corpus>/, `make demo` — which takes "
            "the default source dir — swallowed that corpus into the synthetic smoke "
            "dataset. Ten items where five were expected, no error, and the failure "
            "surfaced three steps later as a missing materialized file. Real corpora are "
            "always created with an explicit --source-dir, so they never needed this."
        ),
    )
    ap.add_argument("--limit", type=int, help="take only the first N (sorted) — a smoke cut")
    ap.add_argument("--tag", action="append", default=[], help="tag every item (repeatable)")
    ap.add_argument("--description", default="")
    ap.add_argument(
        "--include-docs",
        action="store_true",
        help="also treat README files as items (they are skipped by default)",
    )
    ap.add_argument("--force", action="store_true", help="overwrite an existing dataset")
    ap.add_argument(
        "--fieldset", help="the field set (data/fields/<id>.yaml) that declares the items' fields"
    )
    ap.add_argument("--fields", type=Path, help="a .csv or .jsonl of field values, one row per item_id")
    ap.add_argument(
        "--manifest",
        type=Path,
        help="a .csv or .jsonl of items: item_id, source_url [, source_sha256] [, field columns]",
    )
    ap.add_argument(
        "--update-fields",
        action="store_true",
        help="replace the field values of an existing dataset; its items must be unchanged",
    )
    args = ap.parse_args()

    out = DATASETS / f"{args.dataset_id}.json"
    previous = {}
    if out.exists():
        try:
            previous = read_json(out)
        except Exception:  # noqa: BLE001 — an unreadable previous file is simply replaced
            previous = {}
    fieldset = _fieldset(args.fieldset or (previous.get("fieldset") if args.update_fields else None))
    if args.fields and not fieldset:
        die("field values need a field set: pass --fieldset <id> (data/fields/<id>.yaml declares them)")

    if args.update_fields:
        if not previous:
            die(f"--update-fields: no dataset at {out} to update")
        if not args.fields:
            die("--update-fields needs --fields FILE")
        # Merged: a value in the file replaces that value; every other value is kept.
        items = [dict(it) for it in previous["items"]]
        _attach(items, fieldset, args.fields)
        _write(
            out,
            args.dataset_id,
            items,
            previous,
            fieldset,
            previous.get("description", ""),
            previous.get("source_dir", ""),
        )
        print(
            f"{out.relative_to(DATASETS.parents[1])}  fields updated on {len(items)} item(s); "
            "the items, and so every run measured on them, are unchanged"
        )
        return 0

    if out.exists() and not args.force:
        die(
            f"{out} already exists.\n"
            "  A dataset is FROZEN — runs cite it by id and were measured on these bytes.\n"
            "  Make a new version (e.g. _v2) instead, or pass --force if nothing cites it yet.\n"
            "  To correct its fields only, pass --update-fields --fields FILE."
        )

    if args.manifest:
        items = _from_manifest(args.manifest, fieldset, args.source_dir, args.tag)
        if args.fields:
            _attach(items, fieldset, args.fields)
        desc = args.description or f"{len(items)} item(s) from {args.manifest.name}"
        _write(
            out,
            args.dataset_id,
            items,
            previous,
            fieldset,
            desc,
            _relative_source_dir(args.source_dir) if args.source_dir.is_dir() else "",
        )
        print(f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s))")
        print(
            "Next: "
            + how(
                f"evh dataset-materialize --dataset-id {args.dataset_id}",
                f"make dataset-materialize DATASET_ID={args.dataset_id}",
            )
        )
        return 0

    if not args.source_dir.is_dir():
        die(f"no source dir at {args.source_dir} — put your raw inputs there first")

    # Skip the directory's own documentation and dotfiles. Every data dir here
    # ships a README explaining what belongs in it, and the first cold drop-in
    # of this skeleton froze `sources/README.md` as a data item — "1 item, all
    # hashes verified" — which is exactly the kind of quiet wrong answer this
    # tooling exists to prevent.
    def is_item(p: Path) -> bool:
        if not p.is_file() or p.name.startswith("."):
            return False
        return args.include_docs or p.name.lower() not in {"readme.md", "readme.txt", "readme"}

    walk = args.source_dir.rglob if args.recursive else args.source_dir.glob
    files = sorted(p for p in walk(args.glob) if is_item(p))
    if args.limit:
        files = files[: args.limit]
    if not files:
        die(
            f"no items matched {args.glob!r} under {args.source_dir}\n"
            "  Put your inputs in that directory first. READMEs are skipped by\n"
            "  design — pass --include-docs if documentation really is your data."
        )

    items = [
        {
            "item_id": p.relative_to(args.source_dir).as_posix().rsplit(".", 1)[0],
            "source_path": p.relative_to(args.source_dir).as_posix(),
            "source_sha256": sha256(p),
            **({"tags": list(args.tag)} if args.tag else {}),
        }
        for p in files
    ]
    if args.fields:
        _attach(items, fieldset, args.fields)

    _write(
        out,
        args.dataset_id,
        items,
        previous,
        fieldset,
        args.description or f"{len(items)} item(s) from {args.source_dir.name}/",
        # Relative to the harness root when it sits inside it. `as_posix()` on the
        # resolved arg wrote an ABSOLUTE path into a committed file — every dataset in
        # this repo carries "/Users/<name>/projects/..." today. That leaks whoever ran
        # it into a public repo, and makes the file describe a machine rather than a
        # selection. The item hashes are what freeze a dataset; this field is a label.
        _relative_source_dir(args.source_dir),
    )
    print(f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s))")
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
