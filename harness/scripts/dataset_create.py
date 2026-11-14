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

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from pathlib import Path
from typing import Any

from evaluation_harness import (
    _card,
    _dataset_version,
    _fetch,
    _fields,
    _jsonout,
    _licences,
    _source,
    _sources,
    _store,
)
from evaluation_harness._common import (
    DATASETS,
    ROOT,
    SOURCES,
    dataset_id_ok,
    die,
    evh_prog,
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


def _recorded_source_dir(source_dir: Path, dataset_id: str, rels: list[str]) -> str:
    """The `source_dir` a dataset records: the folder, relative to the project, when it lies inside it. A folder outside
    it has the item files `rels` copied into data/sources/<id>/, byte for byte, and that is recorded: a bare folder
    name read nothing anywhere else, so the dataset could not be materialized. Refused, before anything is written,
    when data/sources/<id>/ already holds other content."""
    try:
        source_dir.resolve().relative_to(ROOT)
        return _relative_source_dir(source_dir)
    except ValueError:
        pass
    if not rels:
        return ""
    dest = SOURCES / dataset_id
    have = {p.relative_to(dest).as_posix() for p in _store.rglob(dest, "*") if _store.is_file(p)}
    if have and (
        have != set(rels)
        or any(_store.read_bytes(dest / r) != _store.read_bytes(source_dir / r) for r in rels)
    ):
        die(
            f"{dest} already holds other content than the {len(rels)} item file(s) of {source_dir}: items copied "
            "from a folder outside the project go there. Move it, or name the dataset differently.",
            "would-overwrite",
        )
    for r in rels:
        _store.mkdir((dest / r).parent, parents=True, exist_ok=True)
        _store.write_bytes(dest / r, _store.read_bytes(source_dir / r))
    where = dest.relative_to(ROOT).as_posix()
    print(
        f"  copied {len(rels)} item file(s) from {source_dir.resolve()} to {where}/ (the dataset reads them there)"
    )
    return where


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
            "  Declare the fields there first (schemas/fieldset.schema.json, docs: CONCEPTS, item fields).",
            "not-found",
        )
    problems = _fields.fieldset_problems(fieldset_id, fs)
    if problems:
        die(f"{_fields.fieldset_path(fieldset_id)}: {problems[0]}", "invalid-file")
    return fs


def _attach(items: list, fieldset: dict, path: Path) -> None:
    """Put the values in `path` (rows keyed by item_id) on the matching items, typed."""
    if not _store.is_file(path):
        die(f"no fields file at {path}", "not-found")
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
        die(f"{path}: {len(bad)} problem(s)\n  " + "\n  ".join(bad[:15]), "invalid-file")


def _from_manifest(path: Path, fieldset, source_dir: Path, tags: list) -> list:
    """Items from a manifest: each row an item_id and its source_url (pinned by source_sha256,
    or fetched and pinned now), or a source_path under --source-dir. Other columns are fields."""
    if not _store.is_file(path):
        die(f"no manifest at {path}", "not-found")
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
            if not _store.is_file(p):
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
        die(f"{path}: {len(bad)} problem(s)\n  " + "\n  ".join(bad[:15]), "invalid-file")
    if not items:
        die(f"{path}: no items", "invalid-file")
    if pinned:
        print(f"  pinned {pinned} item(s) now: fetched, and their sha256 recorded")
    return items


def _from_source(name: str, query_text: str, dataset_id: str, fieldset, force: bool) -> tuple[list, dict]:
    """(items, what the source said) from a dataset source (E5): its items written into data/sources/<id>/, a
    `source_url` one pinned as a manifest's is, its row and fields kept."""
    import json  # noqa: PLC0415

    try:
        query = json.loads(query_text or "{}")
    except ValueError as e:
        die(f"--query is not JSON: {e}", "bad-argument")
    if not isinstance(query, dict):
        die("--query is a JSON object", "bad-argument")
    cls, _path = _sources.resolve(name)
    src = cls({})
    try:
        said = src.describe(query) or {}
        got = list(src.items(query))
    except (ValueError, OSError) as e:
        die(f"--source {name}: {e}", "invalid-file")
    block = _source.block(said.get("source") or {"provider": name})
    bad = _source.problems(block) + _card.problems(said.get("card") or {})
    out = SOURCES / dataset_id
    if _store.exists(out) and any(_store.iterdir(out)) and not force:
        die(f"{out} has files: the items of another fetch (--force to replace them)", "would-overwrite")
    items, ids = [], set()
    for n, it in enumerate(got, 1):
        iid = str(it.get("item_id") or "")
        if not iid or iid.startswith("/") or ".." in iid.split("/") or iid in ids:
            bad.append(f"item {n}: item_id {iid!r} is empty, a path out of the folder, or repeated")
            continue
        ids.add(iid)
        item: dict = {"item_id": iid}
        if it.get("text") is not None:
            dest = out / f"{iid}.txt"
            _store.mkdir(dest.parent, parents=True, exist_ok=True)
            _store.write_text(dest, str(it["text"]), encoding="utf-8")
            item.update(source_path=f"{iid}.txt", source_sha256=sha256(dest))
        elif it.get("file"):
            f = Path(it["file"])
            dest = out / f"{iid}{f.suffix}"
            _store.mkdir(dest.parent, parents=True, exist_ok=True)
            _store.copy_file(f, dest)
            item.update(source_path=dest.relative_to(out).as_posix(), source_sha256=sha256(dest))
        elif it.get("source_url"):
            url, pin = str(it["source_url"]), str(it.get("source_sha256") or "")
            if not pin:
                try:
                    _, pin = _fetch.fetch(url, None)
                except _fetch.FetchError as exc:
                    bad.append(f"item {iid}: {exc}")
                    continue
            item.update(source_path=f"{iid}{_fetch.suffix_of(url)}", source_url=url, source_sha256=pin)
        else:
            bad.append(f"item {iid}: no text, file or source_url")
            continue
        if it.get("row") is not None:
            item["source_row"] = it["row"]
        if it.get("fields"):
            if not fieldset:
                bad.append(f"item {iid}: fields need --fieldset to declare them")
            else:
                vals, errs = _fields.values_from(fieldset, it["fields"])
                bad += [f"item {iid}: {e}" for e in errs]
                if vals:
                    item["fields"] = vals
        items.append(item)
    if bad:
        die(f"--source {name}: {len(bad)} problem(s)\n  " + "\n  ".join(bad[:15]), "invalid-file")
    if not items:
        die(f"--source {name}: no items", "not-found")
    return items, {**said, "source": block}


def _lineage(parent_id: str, dataset_id: str, items: list) -> dict:
    """What a new version changes against the dataset it is made from (--from): the item ids
    added, removed, and kept with different bytes."""
    if parent_id == dataset_id:
        die(
            f"--from {parent_id}: a dataset cannot be made from itself; name the new version (e.g. _v2)",
            "bad-argument",
        )
    path = DATASETS / f"{parent_id}.json"
    if not _store.is_file(path):
        die(f"--from {parent_id}: no dataset at {path}", "not-found")
    old = {it["item_id"]: it["source_sha256"] for it in read_json(path).get("items") or []}
    new = {it["item_id"]: it["source_sha256"] for it in items}
    return {
        "dataset_id": parent_id,
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": sorted(k for k in new.keys() & old.keys() if new[k] != old[k]),
    }


def _say_lineage(lin: dict | None) -> None:
    if not lin:
        return
    n = {k: len(lin[k]) for k in ("added", "removed", "changed")}
    print(
        f"  derived from {lin['dataset_id']}: {n['added']} added, {n['removed']} removed, "
        f"{n['changed']} changed"
        + ("  (the same items: a new id for the same selection)" if not any(n.values()) else "")
    )


def parent_version(dataset_id: str | None) -> str | None:
    """A dataset's stored version (E3), None when there is no such dataset."""
    path = DATASETS / f"{dataset_id}.json" if dataset_id else None
    return read_json(path).get("version") if path and _store.is_file(path) else None


# The keys _write sets itself; an update passes the record's others through as they are.
_OWN = frozenset(
    ("dataset_id", "version", "description", "created_at", "licence", "source", "source_dir", "fieldset",
     "fields_sha256", "derived_from", "items", "actor")
)  # fmt: skip


def _write(
    out: Path,
    dataset_id: str,
    items: list,
    previous: dict,
    fieldset,
    description: str,
    source_dir: str,
    lineage: dict | None = None,
    extra: dict | None = None,
    licence: str | None = None,
    source: dict | None = None,
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
            die(f"{len(bad)} field problem(s)\n  " + "\n  ".join(bad[:15]), "invalid-file")
    doc: dict[str, Any] = {
        "dataset_id": dataset_id,
        "version": "",
        "description": description,
        "created_at": created_at,
    }
    if licence:
        doc["licence"] = licence
    if source is None:
        # A fetcher's rows file beside the items (data/sources/<id>.rows.json): where each came from.
        source, rows = _source.from_rows_file(SOURCES / f"{dataset_id}.rows.json", items)
        for it in items:
            if it["item_id"] in rows:
                it["source_row"] = rows[it["item_id"]]
    if source:
        doc["source"] = source
    if source_dir:
        doc["source_dir"] = source_dir
    if fieldset:
        doc["fieldset"] = fieldset["fieldset_id"]
        doc["fields_sha256"] = _fields.digest(items)
    if lineage:
        doc["derived_from"] = lineage
    doc.update(extra or {})  # optional keys another command records (made_from: dataset-from-capture)
    if doc.get("split"):
        doc["split"] = {**doc["split"], "from_version": parent_version(doc["split"]["from"])}
    doc["version"] = _dataset_version.expected(doc, parent_version)
    from evaluation_harness._actor import actor  # noqa: PLC0415

    # Who wrote this record (RFC-027); a re-create that selects the same items keeps it, as it keeps created_at.
    doc["actor"] = previous["actor"] if unchanged and previous.get("actor") else actor()
    doc["items"] = items
    write_json(out, doc)


def _lineage_only(args: argparse.Namespace, out: Path, previous: dict, fieldset) -> int:
    """--from P --lineage-only: an existing dataset gains the record of the one it was made from (the fleet's
    feedback 16: a version made, and cited by runs, before anyone recorded its parent). Its items, created_at and
    every other key stay as they are; its version is recomputed from the lineage (V22)."""
    if not previous:
        die(f"--lineage-only: no dataset at {out}", "not-found")
    if not args.from_:
        die("--lineage-only needs --from DATASET_ID: the dataset this one was made from", "bad-argument")
    if args.update_fields or args.fields or args.manifest or args.source_name or args.force:
        die(
            "--lineage-only changes the lineage alone: no --fields, --manifest, --source or --force",
            "bad-argument",
        )
    if previous.get("split"):
        die(
            f"{args.dataset_id} is a side of a split of {previous['split'].get('from')}: that is its lineage",
            "not-allowed",
        )
    had = (previous.get("derived_from") or {}).get("dataset_id")
    if had and had != args.from_:
        die(f"{args.dataset_id} already records it was made from {had}, not {args.from_}", "not-allowed")
    seen, at = {args.dataset_id}, args.from_
    while at:  # a lineage is a chain back to a first version, never a loop
        if at in seen:
            die(
                f"--from {args.from_}: {at} is already derived from {args.dataset_id} (a loop)",
                "bad-argument",
            )
        seen.add(at)
        path = DATASETS / f"{at}.json"
        at = (read_json(path).get("derived_from") or {}).get("dataset_id") if _store.is_file(path) else None
    lineage = _lineage(args.from_, args.dataset_id, previous.get("items") or [])
    before = previous.get("version")
    _write(
        out,
        args.dataset_id,
        [dict(it) for it in previous.get("items") or []],
        previous,
        fieldset,
        previous.get("description", ""),
        previous.get("source_dir", ""),
        lineage,
        extra={k: v for k, v in previous.items() if k not in _OWN},
        licence=previous.get("licence"),
        source=previous.get("source") or {},
    )
    now_v = read_json(out).get("version")
    print(
        f"{out.relative_to(DATASETS.parents[1])}  lineage recorded; the items, and so every run measured on them, "
        f"are unchanged" + (f"; version {before} -> {now_v}" if before != now_v else f"; version {now_v}")
    )
    _say_lineage(lineage)
    return 0


def main() -> int:
    """Freeze a dataset from source items."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="lowercase_with_underscores")
    ap.add_argument("--source-dir", type=Path, default=SOURCES)
    ap.add_argument("--glob", default="*", help="which files under --source-dir are items")
    ap.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "descend into subdirectories of --source-dir (off by default: a corpus fetched "
            "into a subdirectory of the source dir is not swallowed into this dataset)"
        ),
    )
    ap.add_argument("--limit", type=int, help="take only the first N (sorted) — a smoke cut")
    ap.add_argument("--tag", action="append", default=[], help="tag every item (repeatable)")
    ap.add_argument("--description", default="")
    ap.add_argument(
        "--licence",
        help="the dataset's licence: an id from evh licences, unknown, or LicenseRef-<name> (optional)",
    )
    ap.add_argument(
        "--include-docs",
        action="store_true",
        help="also treat README files as items (they are skipped by default)",
    )
    ap.add_argument("--force", action="store_true", help="overwrite an existing dataset")
    ap.add_argument(
        "--from",
        dest="from_",
        metavar="DATASET_ID",
        help="the dataset this version is made from: recorded with the items added, removed and changed",
    )
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
        "--source",
        dest="source_name",
        metavar="NAME",
        help="read the items from a dataset source: folder, manifest, huggingface, kaggle, zenodo, openml, croissant,"
        " the project's own (data/dataset_sources/NAME.py) or path/to/source.py:Class",
    )
    ap.add_argument(
        "--query", default="{}", help="with --source: what to read, as JSON (each source says its keys)"
    )
    ap.add_argument(
        "--update-fields",
        action="store_true",
        help="replace the field values of an existing dataset; its items must be unchanged",
    )
    ap.add_argument(
        "--lineage-only",
        action="store_true",
        help="with --from: record which dataset an existing one was made from, its items untouched (a dataset "
        "already cited by runs gains the link; its version follows from it)",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("dataset-create", args.json, live=sys.stderr):
        why = _licences.problem(args.licence) if args.licence is not None else None
        if why:
            die(why, "bad-argument")
        licence = _licences.canonical(args.licence) if args.licence else None

        out = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
        previous = {}
        if _store.exists(out):
            try:
                previous = read_json(out)
            except Exception:  # noqa: BLE001 — an unreadable previous file is simply replaced
                previous = {}
        fieldset = _fieldset(
            args.fieldset or (previous.get("fieldset") if args.update_fields or args.lineage_only else None)
        )
        if args.fields and not fieldset:
            die(
                "field values need a field set: pass --fieldset <id> (data/fields/<id>.yaml declares them)",
                "bad-argument",
            )

        if args.lineage_only:
            return _lineage_only(args, out, previous, fieldset)

        if args.update_fields:
            if not previous:
                die(f"--update-fields: no dataset at {out} to update", "not-found")
            if not args.fields:
                die("--update-fields needs --fields FILE", "bad-argument")
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
                previous.get("derived_from"),
                # Every other key of the record (card, tags, text, split, made_from …) is not the fields: kept.
                extra={k: v for k, v in previous.items() if k not in _OWN},
                licence=previous.get("licence"),
                source=previous.get("source") or {},
            )
            print(
                f"{out.relative_to(DATASETS.parents[1])}  fields updated on {len(items)} item(s); "
                "the items, and so every run measured on them, are unchanged"
            )
            return 0

        if _store.exists(out) and not args.force:
            die(
                f"{out} already exists.\n"
                "  A dataset is FROZEN — runs cite it by id and were measured on these bytes.\n"
                "  Make a new version (e.g. _v2) instead, or pass --force if nothing cites it yet.\n"
                "  To correct its fields only, pass --update-fields --fields FILE.",
                "would-overwrite",
            )

        if args.source_name:
            if args.manifest:
                die("--source and --manifest: one way to name the items", "bad-argument")
            items, said = _from_source(args.source_name, args.query, args.dataset_id, fieldset, args.force)
            lic = licence or (_licences.canonical(said["licence"]) if said.get("licence") else None)
            if said.get("licence") and not lic:
                die(f"--source {args.source_name}: {_licences.problem(said['licence'])}", "invalid-file")
            lineage = _lineage(args.from_, args.dataset_id, items) if args.from_ else None
            _write(
                out,
                args.dataset_id,
                items,
                previous,
                fieldset,
                args.description
                or said.get("description")
                or f"{len(items)} item(s) from source {args.source_name}",
                _relative_source_dir(SOURCES / args.dataset_id),
                lineage,
                {"card": said["card"]} if said.get("card") else None,
                licence=lic,
                source=said["source"],
            )
            print(
                f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s) from {said['source']['provider']})"
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

        if args.manifest:
            items = _from_manifest(args.manifest, fieldset, args.source_dir, args.tag)
            if args.fields:
                _attach(items, fieldset, args.fields)
            desc = args.description or f"{len(items)} item(s) from {args.manifest.name}"
            lineage = _lineage(args.from_, args.dataset_id, items) if args.from_ else None
            _write(
                out,
                args.dataset_id,
                items,
                previous,
                fieldset,
                desc,
                _recorded_source_dir(
                    args.source_dir,
                    args.dataset_id,
                    [it["source_path"] for it in items if not it.get("source_url")],
                )
                if _store.is_dir(args.source_dir)
                else "",
                lineage,
                licence=licence,
            )
            print(f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s))")
            _jsonout.values({"dataset_id": args.dataset_id, "items": len(items), "path": str(out)})
            _say_lineage(lineage)
            print(
                "Next: "
                + how(
                    f"evh dataset-materialize --dataset-id {args.dataset_id}",
                    f"make dataset-materialize DATASET_ID={args.dataset_id}",
                )
            )
            return 0

        if not _store.is_dir(args.source_dir):
            die(f"no source dir at {args.source_dir} — put your raw inputs there first", "not-found")

        # Skip the directory's own documentation and dotfiles. Every data dir here
        # ships a README explaining what belongs in it, and the first cold drop-in
        # of this skeleton froze `sources/README.md` as a data item — "1 item, all
        # hashes verified" — which is exactly the kind of quiet wrong answer this
        # tooling exists to prevent.
        def is_item(p: Path) -> bool:
            if not _store.is_file(p) or p.name.startswith("."):
                return False
            return args.include_docs or p.name.lower() not in {"readme.md", "readme.txt", "readme"}

        # through the store: a source folder under data/ is in the database in SQLite mode, where pathlib's glob found
        # nothing ("no items matched", the store matrix, 2026-11-08)
        walk = _store.rglob if args.recursive else _store.glob
        files = sorted(p for p in walk(args.source_dir, args.glob) if is_item(p))
        if args.limit:
            files = files[: args.limit]
        if not files:
            die(
                f"no items matched {args.glob!r} under {args.source_dir}\n"
                "  Put your inputs in that directory first. READMEs are skipped by\n"
                "  design — pass --include-docs if documentation really is your data.",
                "not-found",
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

        lineage = _lineage(args.from_, args.dataset_id, items) if args.from_ else None
        _write(
            out,
            args.dataset_id,
            items,
            previous,
            fieldset,
            args.description or f"{len(items)} item(s) from {args.source_dir.name}/",
            # Relative to the project when it sits inside it, else the folder's items copied into data/sources/<id>.
            # Never an absolute path: that wrote "/Users/<name>/projects/..." into every committed dataset, a
            # machine's name in a public repo.
            _recorded_source_dir(
                args.source_dir, args.dataset_id, [p.relative_to(args.source_dir).as_posix() for p in files]
            ),
            lineage,
            licence=licence,
        )
        print(f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s))")
        _jsonout.values({"dataset_id": args.dataset_id, "items": len(items), "path": str(out)})
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
