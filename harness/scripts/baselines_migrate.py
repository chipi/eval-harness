#!/usr/bin/env python3
"""Bring a project's records to RFC-027: baselines per goal in versions, an actor on every record, split.split_by.

    evh baselines-migrate --dry-run     # what it would change, nothing written
    evh baselines-migrate

- each `data/baselines/<dataset>_baseline.json` becomes version 1 of the goal its record names
  (`data/baselines/<goal>/<dataset>/1.json`), or of the dataset's own when it names none (`_dataset/`), with
  `evidence: null` and `migrated: true` (promoted before 0.8.0, its evidence not recorded), `baseline_id` dropped;
- every run (in every runs directory), reference, label set, round, dataset and model record without an `actor` gets
  `{"type": "unknown", "name": "before 0.8.0", "from": "migration"}`: nobody recorded who made it. Picks are an
  append-only list and are not rewritten;
- a split side's `split.by` becomes `split.split_by`.

No reader keeps the old forms; a second run changes nothing. An actor is outside every fingerprint, so no hash moves.
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

from evaluation_harness import _baselines, _common, _jsonout, _store
from evaluation_harness._common import evh_prog, write_json
from evaluation_harness._common import read_json as _read_json

BEFORE = {"type": "unknown", "name": "before 0.8.0", "from": "migration"}


def read_json(path: Path) -> Any:
    """A record, or None when it does not parse: V1 names that; the migration leaves it as it is."""
    try:
        return _read_json(path)
    except (OSError, ValueError):
        return None


def _json_files(root: Path, pattern: str) -> list[Path]:
    return sorted(_store.rglob(root, pattern)) if _store.is_dir(root) else []


def plan() -> list[tuple[str, Path, Any]]:
    """(what, the file, the new content: a dict for JSON, text for YAML, None to remove) for every change."""
    out: list[tuple[str, Path, Any]] = []
    data = _common.DATA
    bdir = _common.BASELINES
    # Baselines: flat files to version 1 of their line.
    for f in sorted(_store.glob(bdir, "*.json")) if _store.is_dir(bdir) else []:
        b = read_json(f)
        if not isinstance(b, dict) or not b.get("dataset_id"):
            continue
        new = {k: v for k, v in b.items() if k != "baseline_id"} | {
            "goal": b.get("goal") or None,
            "version": 1,
            "replaces": None,
            "evidence": None,
            "migrated": True,
            "actor": b.get("actor") or BEFORE,
        }
        dest = _baselines.folder(new["goal"], b["dataset_id"]) / "1.json"
        out.append((f"baseline {f.name} -> {dest.relative_to(data).as_posix()}", dest, new))
        out.append((f"remove {f.relative_to(data).as_posix()}", f, None))
    # Runs, in every runs directory.
    for base in sorted(
        p for p in (_store.iterdir(data) if _store.is_dir(data) else []) if p.name.startswith("runs")
    ):
        for m in sorted(_store.glob(base, "*/metrics.json")):
            doc = read_json(m)
            if isinstance(doc, dict) and "actor" not in doc:
                out.append((f"actor on {m.relative_to(data).as_posix()}", m, doc | {"actor": BEFORE}))
    # References and label sets.
    for f in _json_files(data / "references", "manifest.json") + _json_files(data / "labels", "labels.json"):
        doc = read_json(f)
        if isinstance(doc, dict) and "actor" not in doc:
            out.append((f"actor on {f.relative_to(data).as_posix()}", f, doc | {"actor": BEFORE}))
    # Dataset records: the actor, and split.by -> split.split_by.
    for f in sorted(_store.glob(_common.DATASETS, "*.json")) if _store.is_dir(_common.DATASETS) else []:
        doc = read_json(f)
        if not isinstance(doc, dict):
            continue
        new = dict(doc)
        sp = new.get("split")
        if isinstance(sp, dict) and "by" in sp:
            new["split"] = {("split_by" if k == "by" else k): v for k, v in sp.items()}
        if "actor" not in new:
            new["actor"] = BEFORE
        if new != doc:
            out.append((f"actor/split on {f.relative_to(data).as_posix()}", f, new))
    # Rounds and model records (YAML).
    import yaml  # noqa: PLC0415

    # Each dumped as its own writer dumps it (_rounds.save, _models.update_record), so only the actor line is new.
    for f, width in [(f, 100) for f in _json_files(_common.ROUNDS, "*.yaml")] + [
        (f, None) for f in _json_files(data / "models", "*.yaml")
    ]:
        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue  # V1 names it
        if not isinstance(doc, dict) or "actor" in doc:
            continue
        doc = {**doc, "actor": BEFORE}
        text = (
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=width)
            if width
            else yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        )
        out.append((f"actor on {f.relative_to(data).as_posix()}", f, text))
    return out


def main() -> int:
    """Migrate the project's records to RFC-027."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="say what would change; write nothing")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("baselines-migrate", args.json, live=sys.stderr):
        changes = plan()
        if not changes:
            print("0 changed: already in this format")
            return 0
        for what, _f, _new in changes:
            print(("would: " if args.dry_run else "") + what)
        if args.dry_run:
            print(f"{len(changes)} change(s); nothing written (--dry-run)")
            return 0
        for _what, f, new in changes:
            if new is None:
                _store.unlink(f)
            elif isinstance(new, str):
                _store.write_text(f, new, encoding="utf-8")
            else:
                _store.mkdir(f.parent, parents=True, exist_ok=True)
                write_json(f, new)
        print(f"{len(changes)} change(s) written")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
