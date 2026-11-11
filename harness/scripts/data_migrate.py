#!/usr/bin/env python3
"""Move a project's data between files and its database (RFC-025), the whole of data/ at once.

    evh data-migrate --to sqlite --dry-run   what would move
    evh data-migrate --to sqlite             everything under data/ into data/project.sqlite (store: sqlite first)
    evh data-migrate --to files              back, byte for byte (store: files first)

A project is files or its database, never both. Each file is written to the target, read back and compared (a file's
sha256; a run's outputs by item, text, sha256 and order; its rows by their exact text) before the old copy is removed;
any difference stops the move with that file in its old place. A move a crash stopped is finished by the next one.
Refused while the project's store (`store` in config.yaml, or EVAL_STORE) is not the target, while data/ holds Python
(code is never in the database: keep it outside data/ and name it by path), and while a run is still in the layout
before 0.8.0 (`evh run-migrate` first).
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

from evaluation_harness import _common, _jsonout, _outputs, _store
from evaluation_harness._common import die, evh_prog

#: A run's per-item files: kept in the database's per-item tables, not as files.
PER_ITEM = (_outputs.FILE, _outputs.PREDICTIONS, _outputs.ROWS)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _disk_files(data: Path) -> list[Path]:
    """Every file under data/ on disk, the database's own files left out."""
    out = []
    for root, dirs, files in os.walk(data):
        dirs.sort()
        for f in sorted(files):
            p = Path(root) / f
            if p.parent == data and (f == _store.DB or f.startswith(_store.DB + "-")):
                continue
            out.append(p)
    return out


def _is_run(d: Path) -> bool:
    """Whether `d` is a run: its record is on disk, or already in the database (a migration a crash stopped after
    moving the record, before the run's outputs and rows, is finished by the next one)."""
    return any((d / n).is_file() or _store.is_file(d / n) for n in ("metrics.json", "run.json"))


def _links(data: Path) -> list[Path]:
    """Every symbolic link under data/, to a file or a folder: os.walk does not follow one into a folder."""
    out = []
    for root, dirs, files in os.walk(data):
        out += [Path(root) / n for n in [*dirs, *files] if os.path.islink(os.path.join(root, n))]
    return sorted(out)


def _refusals(data: Path, files: list[Path]) -> None:
    links = _links(data)
    if links:
        die(
            "data/ holds symbolic links, which a migration would leave behind (a linked folder is not walked): put"
            " what each points to in its place first:\n  "
            + "\n  ".join(str(p.relative_to(data)) for p in links[:10]),
            "not-allowed",
        )
    code = [p for p in files if p.suffix == ".py"]
    if code:
        die(
            "data/ holds Python, which is never in the database: keep it outside data/ (named by path) first:\n  "
            + "\n  ".join(str(p.relative_to(data)) for p in code[:10]),
            "not-allowed",
        )
    old = sorted({p.parent.parent for p in files if p.parent.name == "outputs" and _is_run(p.parent.parent)})
    if old:
        die(
            f"{len(old)} run(s) in the layout before 0.8.0 (an outputs/ folder): evh run-migrate first",
            "not-allowed",
        )


def to_sqlite(dry_run: bool) -> dict[str, int]:
    """Every file under data/ into the database; counts of what moved."""
    data = _common.DATA
    files = _disk_files(data)
    _refusals(data, files)
    n = {"files": 0, "runs": 0, "outputs": 0, "rows": 0, "bytes": 0}
    st = _outputs.store_named("sqlite")
    disk = _outputs.store_named("files")
    runs = sorted({p.parent for p in files if p.name in PER_ITEM and _is_run(p.parent)})
    run_set = set(runs)
    per_item = {p for p in files if p.name in PER_ITEM and p.parent in run_set}
    for p in files:
        if p in per_item:
            continue
        b = p.read_bytes()
        n["files"] += 1
        n["bytes"] += len(b)
        if dry_run:
            continue
        there = _store.read_bytes(p) if _store.is_file(p) else None
        if there is not None and there != b:
            die(
                f"{p.relative_to(data)}: already in the database with different bytes; nothing of it changed",
                "would-overwrite",
            )
        if there is None:
            _store.write_bytes(p, b, p.stat().st_mtime_ns)  # the file's own time, not the migration's
        if _sha(_store.read_bytes(p)) != _sha(b):
            die(f"{p.relative_to(data)}: read back from the database differs; it stays a file", "mismatch")
        p.unlink()
    for d in runs:
        outs = disk.lines(d)
        n["runs"] += 1
        n["outputs"] += len(outs)
        texts = [(o["item_id"], o["text"], o["sha256"]) for o in outs]
        bad = [i for i, t, s in texts if _outputs.sha256(t) != s]
        if bad:
            die(
                f"{d.relative_to(data)}: output(s) whose text does not match its sha256: {', '.join(bad[:5])}",
                "mismatch",
            )
        rows = {pt: disk.rows_text(d, pt) for pt in (False, True)}
        n["rows"] += sum(len(t.splitlines()) for t in rows.values() if t)
        if dry_run:
            continue
        if texts and not st.has(d):
            st.write_all(d, {i: t for i, t, _ in texts}, [i for i, _, _ in texts])
        if [(o["item_id"], o["text"], o["sha256"]) for o in st.lines(d)] != texts:
            die(
                f"{d.relative_to(data)}: its outputs read back from the database differ; they stay files",
                "mismatch",
            )
        for pt, text in rows.items():
            if text is None:
                continue
            if st.rows_text(d, pt) is None:
                st.put_rows(d, text, pt)
            if st.rows_text(d, pt) != text:
                die(
                    f"{d.relative_to(data)}: its rows read back from the database differ; they stay files",
                    "mismatch",
                )
        for name in PER_ITEM:
            (d / name).unlink(missing_ok=True)
    if not dry_run:  # the emptied folders go too, deepest first (os.walk bottom-up), data/ itself stays
        for root, _dirs, _files in os.walk(data, topdown=False):
            q = Path(root)
            if q != data and not any(q.iterdir()):
                q.rmdir()
    return n


def _held_elsewhere() -> bool:
    """Whether another process has the database open. As a job (RFC-026), a server on this project lets go of it once
    it sees the migration hold the project (within a second): asked again for up to 30 s before refusing."""
    import time  # noqa: PLC0415

    end = time.monotonic() + (30 if os.environ.get("EVH_JOB") else 0)
    while _store.held_elsewhere():
        if time.monotonic() >= end:
            return True
        time.sleep(0.5)
    return False


def to_files(dry_run: bool) -> dict[str, int]:
    """Everything in the database back to files, byte for byte; counts of what moved."""
    data = _common.DATA
    path = data / _store.DB
    n = {"files": 0, "runs": 0, "outputs": 0, "rows": 0, "bytes": 0}
    if not path.is_file():
        return n
    if not dry_run and _held_elsewhere():
        die(
            f"{path.name} is open in another process (a catalog-serve, a run): stop it first; moving back deletes the"
            " database, and that process would go on writing to the deleted file",
            "not-allowed",
        )
    conn = sqlite3.connect(str(path), timeout=60)
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    disk = _outputs.store_named("files")
    for key, blob, sha, mtime_ns in conn.execute(
        "SELECT path, data, sha256, mtime_ns FROM files ORDER BY path"
    ).fetchall():
        b = bytes(blob)
        if _sha(b) != sha:
            die(f"{key}: its bytes in the database do not match their sha256", "mismatch")
        n["files"] += 1
        n["bytes"] += len(b)
        if dry_run:
            continue
        f = data / key
        if f.is_file() and f.read_bytes() != b:
            die(f"{key}: already a file with different bytes; nothing of it changed", "would-overwrite")
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f".{f.name}.migrating")
        tmp.write_bytes(b)
        os.utime(tmp, ns=(mtime_ns, mtime_ns))  # the file's time as the database kept it
        os.replace(tmp, f)
        if f.read_bytes() != b:
            die(f"{key}: written back, the file differs", "mismatch")
    runs: set[str] = set()
    if "outputs" in have:
        runs |= {r[0] for r in conn.execute("SELECT DISTINCT run FROM outputs")}
    if "rows" in have:
        runs |= {r[0] for r in conn.execute("SELECT DISTINCT run FROM rows")}
    for key in sorted(runs):
        d = data / key
        n["runs"] += 1
        outs = (
            conn.execute(
                "SELECT item_id, text, sha256 FROM outputs WHERE run = ? ORDER BY rowid", (key,)
            ).fetchall()
            if "outputs" in have
            else []
        )
        n["outputs"] += len(outs)
        rows = {}
        for pt in (0, 1):
            got = (
                conn.execute(
                    "SELECT row FROM rows WHERE run = ? AND partial = ? ORDER BY n", (key, pt)
                ).fetchall()
                if "rows" in have
                else []
            )
            rows[bool(pt)] = "".join(r[0] for r in got) if got else None
        n["rows"] += sum(len(t.splitlines()) for t in rows.values() if t)
        if dry_run:
            continue
        d.mkdir(parents=True, exist_ok=True)
        if outs:
            disk.write_all(d, {i: t for i, t, _ in outs}, [i for i, _, _ in outs])
            if [(o["item_id"], o["text"], o["sha256"]) for o in disk.lines(d)] != [tuple(o) for o in outs]:
                die(f"{key}: its outputs written back differ", "mismatch")
        for pt, text in rows.items():
            if text is not None:
                disk.put_rows(d, text, pt)
                if disk.rows_text(d, pt) != text:
                    die(f"{key}: its rows written back differ", "mismatch")
    conn.close()
    if not dry_run:
        _store.close()
        for f in (path, Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-setup-lock")):
            f.unlink(missing_ok=True)
    return n


def main() -> int:
    """Move every file under data/ into the project's database, or back."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--to", required=True, choices=_common.STORES, help="the store to move the project's data into"
    )
    ap.add_argument("--dry-run", action="store_true", help="count what would move; move nothing")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("data-migrate", args.json, live=sys.stderr):
        configured = _common.store()
        if configured != args.to:
            die(
                f"the project's store is {configured}: set `store: {args.to}` in config.yaml (or EVAL_STORE={args.to})"
                " first, so nothing writes to the old place after the move",
                "not-allowed",
            )
        n = to_sqlite(args.dry_run) if args.to == "sqlite" else to_files(args.dry_run)
        _outputs.reset()
        verb = "would move" if args.dry_run else "moved"
        print(
            f"{n['files']} file(s) ({n['bytes']:,} bytes) and {n['runs']} run(s)' {n['outputs']} output(s) and "
            f"{n['rows']} row(s) {verb} into the {args.to} store"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
