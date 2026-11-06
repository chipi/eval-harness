#!/usr/bin/env python3
"""Bring the project's runs to one outputs file each, once (idempotent; RFC-024), or move them between stores (RFC-025).

    evh run-migrate --dry-run     what would change: runs, files before and after
    evh run-migrate               write it
    evh run-migrate --to sqlite   move every run's outputs into data/runs.sqlite (after setting runs.store: sqlite)
    evh run-migrate --to files    move them back into each run's outputs.jsonl (after setting runs.store: files)

For every run directory under data/runs* that still has an `outputs/` folder: its `outputs/<item>.txt` become one
`outputs.jsonl`, in the dataset's order, each line checked against the bytes of the file it came from. A derived run
(a re-score, a judging, a sheet import) whose outputs are byte copies of its source's keeps none of its own: it reads
its source's. One that differs, or whose source is not here, keeps its own file and is named. A leftover row checkpoint
(`outputs/_rows.jsonl`) is dropped when predictions.jsonl has every row it holds, else kept as `rows.partial.jsonl`.
Before a run's folder is removed, V5's signature and every output read back are checked equal to what the files
held; any difference stops the migration with nothing of that run changed.

`--to` moves runs one at a time: written to the target store, every output's sha256 and the order read back equal to
the source's, then deleted from the source. A crash between leaves the run in both, and the next `--to` finishes it.
It refuses while the project's store (runs.store, or EVAL_RUNS_STORE) is not the target, so nothing writes to the old
store after the move.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _outputs
from evaluation_harness._common import die, evh_prog, write_json


def _old_signature(texts: dict[str, bytes]) -> str:
    """V5's digest as the per-item files gave it."""
    h = hashlib.sha256()
    for item in sorted(texts, key=lambda i: f"{i}.txt"):
        h.update(f"{item}.txt".encode() + b"\0" + texts[item] + b"\x1e")
    return h.hexdigest()


def _metrics(d: Path) -> dict[str, Any]:
    m = d / "metrics.json"
    try:
        return json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
    except ValueError:
        return {}


def _order(d: Path, items: list[str]) -> list[str]:
    """The dataset's order for these items; any it does not name, after, sorted."""
    ds = _metrics(d).get("dataset_id") or (_metrics(d).get("derived") or {}).get("dataset_id")
    f = _common.DATASETS / f"{ds}.json" if ds else None
    known = [it["item_id"] for it in json.loads(f.read_text())["items"]] if f and f.is_file() else []
    have = set(items)
    return [i for i in known if i in have] + sorted(have - set(known))


def _read_files(d: Path) -> dict[str, bytes]:
    return {f.stem: f.read_bytes() for f in sorted((d / "outputs").glob("*.txt"))}


def _texts_of(d: Path) -> dict[str, str] | None:
    """A run's outputs in either layout (the old folder, or outputs.jsonl), None when it has neither."""
    if (d / "outputs").is_dir():
        raw = _read_files(d)
        return {i: b.decode("utf-8") for i, b in raw.items() if _utf8(b)}
    if _outputs.own(d):
        return _outputs.outputs(d)
    return None


def _source_of(d: Path, measured_by_name: dict[str, list[Path]]) -> Path | None:
    """The measured run a derived run's `derived.from` names, in either layout (a dry run has not moved any)."""
    frm = (_metrics(d).get("derived") or {}).get("from")
    if not frm:
        return None
    seen = {d}
    name = Path(str(frm)).name
    for c in sorted(measured_by_name.get(name, []), key=lambda c: (c.parent.name != "runs", str(c))):
        if c not in seen:
            return c
    return None


def _runs() -> list[Path]:
    out = []
    for root in sorted(p for p in _common.DATA.glob("runs*") if p.is_dir()):
        for depth in ("*", "*/*", "*/*/*"):
            out += [d for d in root.glob(depth) if (d / "outputs").is_dir()]
    return sorted(set(out))


def migrate(dry_run: bool) -> dict[str, int]:
    """Every run brought to the one-file layout; counts of what was done."""
    runs = _runs()
    measured = [d for d in runs if not (_metrics(d).get("derived") or {}).get("from")]
    derived = [d for d in runs if d not in measured]
    # Every measured run of the project, in either layout, by name: what a derived run's `from` names.
    by_name: dict[str, list[Path]] = {}
    for root in sorted(p for p in _common.DATA.glob("runs*") if p.is_dir()):
        for depth in ("*", "*/*", "*/*/*"):
            for c in root.glob(depth):
                layout = c.is_dir() and ((c / "outputs").is_dir() or _outputs.own(c))
                if layout and not (_metrics(c).get("derived") or {}).get("from"):
                    by_name.setdefault(c.name, []).append(c)
    n = {"runs": len(runs), "own_file": 0, "reads_source": 0, "files_before": 0, "kept_checkpoint": 0}
    reads_source: list[tuple[Path, dict[str, str], dict[str, bytes]]] = []
    for d in [*measured, *derived]:  # sources first, so a derived run can be compared with its source's file
        raw = _read_files(d)
        n["files_before"] += len(raw) + sum(1 for _ in (d / "outputs").glob("_rows.jsonl"))
        bad = [i for i, b in raw.items() if not _utf8(b)]
        if bad:
            die(
                f"{d}: output(s) not UTF-8, which outputs.jsonl cannot hold exactly: {', '.join(bad[:5])}",
                "invalid-file",
            )
        texts = {i: b.decode("utf-8") for i, b in raw.items()}
        src = _source_of(d, by_name) if d in derived else None
        same_as_source = src is not None and _texts_of(src) == texts
        if not dry_run:
            if not same_as_source and texts:
                _outputs.write_all(d, texts, _order(d, list(texts)))
                back = _outputs.outputs(d)
                if back != texts or _outputs.signature(d) != _old_signature(raw):
                    _outputs.store().delete(d)
                    die(
                        f"{d}: the outputs read back are not the files' bytes; nothing of it changed",
                        "mismatch",
                    )
            rows = d / "outputs" / "_rows.jsonl"
            if rows.is_file():
                kept = _checkpoint_needed(rows, d / "predictions.jsonl")
                if kept:
                    shutil.move(str(rows), str(d / _outputs.ROWS))
                    n["kept_checkpoint"] += 1
            shutil.rmtree(d / "outputs")
        n["reads_source" if same_as_source else "own_file"] += 1
        if same_as_source:
            reads_source.append((d, texts, raw))
        if d in derived and not same_as_source and texts:
            print(
                f"  {d.relative_to(_common.DATA)}: keeps its own outputs ({'its source is not here' if src is None else 'they differ from its source'})"
            )
    # Every derived run without outputs of its own records its source's directory (derived.from_dir), so it reads
    # that run and no other of the same name; one already migrated without it gets it now (idempotent).
    n["from_dir"] = 0
    for d in sorted(
        {
            c
            for root in _common.DATA.glob("runs*")
            if root.is_dir()
            for depth in ("*", "*/*", "*/*/*")
            for c in root.glob(depth)
        }
    ):
        m = _metrics(d)
        der = m.get("derived") or {}
        if not d.is_dir() or not der.get("from") or der.get("from_dir") or _outputs.own(d):
            continue
        if (d / "outputs").is_dir() and dry_run:
            src = _source_of(d, by_name)  # moved above in a real run; in a dry run it still has its folder
        elif (d / "outputs").is_dir():
            continue
        else:
            src = _source_of(d, by_name)
        if src is None:
            continue
        n["from_dir"] += 1
        if not dry_run:
            der["from_dir"] = src.relative_to(_common.DATA).as_posix()
            write_json(d / "metrics.json", m)
    if not dry_run:
        # Once every run is moved: what a derived run reads through the one reader is what its files held, else
        # it gets its own file back (and is named).
        _outputs.reset()
        for d, texts, raw in reads_source:
            if _outputs.outputs(d) != texts or _outputs.signature(d) != _old_signature(raw):
                _outputs.write_all(d, texts, _order(d, list(texts)))
                n["reads_source"] -= 1
                n["own_file"] += 1
                print(
                    f"  {d.relative_to(_common.DATA)}: its source's outputs read back differently: keeps its own"
                )
    return n


def _utf8(b: bytes) -> bool:
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _checkpoint_needed(rows: Path, predictions: Path) -> bool:
    """Whether a row checkpoint holds a row predictions.jsonl does not (then it is kept)."""

    def ids(p: Path) -> set[str]:
        out = set()
        for line in p.read_text(encoding="utf-8").splitlines() if p.is_file() else []:
            try:
                out.add(json.loads(line).get("item_id"))
            except ValueError:
                continue
        return out

    return not ids(rows) <= ids(predictions)


def _run_dirs_of(st: _outputs.Store) -> list[Path]:
    """Every run directory a store holds outputs for."""
    if isinstance(st, _outputs.SqliteStore):
        return sorted(Path(k) if Path(k).is_absolute() else _common.DATA / k for k in st.runs())
    roots = {*(p for p in _common.DATA.glob("runs*") if p.is_dir()), _common.RUNS}
    return sorted(
        {
            d
            for r in roots
            if r.is_dir()
            for depth in ("*", "*/*", "*/*/*")
            for d in r.glob(depth)
            if st.has(d)
        }
    )


def move(to: str, dry_run: bool) -> dict[str, int]:
    """Every run's outputs moved from the other store into `to`; counts of runs and outputs moved."""
    configured = _common.runs_store()
    if configured != to:
        die(
            f"the project's runs store is {configured}: set runs.store: {to} in config.yaml (or EVAL_RUNS_STORE={to})"
            " first, so nothing writes to the old store after the move",
            "not-allowed",
        )
    src = _outputs.store_named("files" if to == "sqlite" else "sqlite")
    dst = _outputs.store_named(to)
    n = {"runs": 0, "outputs": 0, "finished": 0}
    for d in _run_dirs_of(src):
        rows = src.rows(d)
        bad = [r.get("item_id") for r in rows if _outputs.sha256(str(r.get("text", ""))) != r.get("sha256")]
        if bad:
            die(
                f"{d}: output(s) whose text does not match its sha256: {', '.join(map(str, bad[:5]))}",
                "mismatch",
            )
        texts = {r["item_id"]: r["text"] for r in rows}
        order = list(texts)
        if dst.has(d):
            if dst.read(d) != texts:
                die(
                    f"{d}: already in the {to} store with different outputs; nothing of it changed",
                    "would-overwrite",
                )
            n["finished"] += 1  # a move a crash stopped after the write: only the delete is left
        n["runs"] += 1
        n["outputs"] += len(texts)
        if dry_run:
            continue
        if not dst.has(d):
            dst.write_all(d, texts, order)
        back = dst.rows(d)
        if [(r["item_id"], r["text"], r["sha256"]) for r in back] != [
            (r["item_id"], r["text"], r["sha256"]) for r in rows
        ]:
            dst.delete(d)
            die(f"{d}: the outputs read back from the {to} store differ; it stays in the old one", "mismatch")
        src.delete(d)
    if not dry_run:
        _outputs.reset()
    return n


def main() -> int:
    """Migrate every run under data/runs* to one outputs file."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="count what would change; write nothing")
    ap.add_argument(
        "--to",
        choices=_common.RUNS_STORES,
        help="move every run's outputs into this store (the project's runs.store must already name it)",
    )
    args = ap.parse_args()
    if args.to:
        _common.runs_store()  # a malformed setting refuses before anything is read
    n = migrate(args.dry_run)
    after = n["own_file"] + n["kept_checkpoint"]
    verb = "would become" if args.dry_run else "became"
    print(
        f"{n['runs']} run(s) with an outputs/ folder: {n['own_file']} {verb} one outputs.jsonl each, "
        f"{n['reads_source']} derived read their source's; {n['files_before']} file(s) {verb} {after}"
        + ("" if n["runs"] else " (already in this format)")
        + (
            f"; {n['from_dir']} derived run(s) {'would record' if args.dry_run else 'recorded'} their source's directory"
            if n["from_dir"]
            else ""
        )
    )
    if args.to:
        m = move(args.to, args.dry_run)
        print(
            f"{m['runs']} run(s), {m['outputs']} output(s) {'would move' if args.dry_run else 'moved'} into the {args.to}"
            f" store" + (f" ({m['finished']} a stopped move had already written)" if m["finished"] else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
