"""Move a project's data between files and its database (RFC-025), the whole of data/ at once.

    evh data-migrate --to sqlite --dry-run   what would move
    evh data-migrate --to sqlite             everything under data/ into data/project.sqlite (store: sqlite first)
    evh data-migrate --to files              back (store: files first)

A project is files or its database, never both. Each file is written to the target, read back and compared (a file's
sha256; a run's outputs by item, text, sha256 and order; its checkpoint's rows by their exact text, each of its scores'
rows by their canonical text, `row_line` of each) before the old copy is removed;
any difference stops the move with that file in its old place. A move a crash stopped is finished by the next one.
Into SQLite the outputs and score sets go in the order of their run's time (run.json's `started_at`, else `created_at`; a
run with neither first), then the key, so a score set's id is its place in that order and a run added since lands after
every older one: a release's rsync of the database stays small (RFC-033).
Refused while the project's store (`store` in config.yaml, or EVAL_STORE) is not the target, while data/ holds Python
(code is never in the database: keep it outside data/ and name it by path), and while a run is still in the layout
before 0.8.0 (`evh migrate` first).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _outputs, _store
from evaluation_harness._common import die
from evaluation_harness.ops import legacy

#: The per-item files of a run (its outputs, its checkpoint) and of each of its scores (their rows): kept in the
#: database's per-item tables, not as files.
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


def run_time(text: str | bytes | None) -> float | None:
    """A run's time from its run.json: `started_at`, else `created_at` (the committed runs hold the second alone), as
    seconds since the epoch (a time with no zone is UTC); None when the text is no JSON object, or holds neither as an
    ISO time."""
    try:
        doc = json.loads(text) if text else None
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    for field in ("started_at", "created_at"):
        v = doc.get(field)
        if isinstance(v, str):
            try:
                t = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                continue
            return (t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)).timestamp()
    return None


def _run_stamp(run: Path) -> float | None:
    """The time of the run in folder `run`, from its run.json on disk or already in the database."""
    p = run / "run.json"
    if p.is_file():
        return run_time(p.read_bytes())
    return run_time(_store.read_bytes(p)) if _store.is_file(p) else None


def _in_time_order(d: Path) -> tuple[float, str]:
    """Where a folder with per-item files goes in the database: by its run's time, then its key. A score is its run's
    (runs/<id>/scores/<key>); one with no time (no run.json, or none of the two fields) goes first, as the oldest."""
    run = d.parent.parent if d.parent.name == "scores" else d
    t = _run_stamp(run)
    return (float("-inf") if t is None else t, d.relative_to(_common.DATA).as_posix())


def _file_order(p: Path, stamps: dict[str, float]) -> tuple[int, float, str]:
    """Where a file goes in the `files` table: what is not under a run (datasets, goals, references, ...) first, in
    path order, then everything under runs/<id>/ by that run's time, then its path: a run added since is appended after
    the older ones, as in the per-item tables, and a change to the first group stays in the front pages."""
    rel = p.relative_to(_common.DATA).as_posix()
    parts = rel.split("/")
    if parts[0] != "runs" or len(parts) < 3:
        return (0, 0.0, rel)
    if parts[1] not in stamps:
        t = _run_stamp(_common.DATA / "runs" / parts[1])
        stamps[parts[1]] = float("-inf") if t is None else t
    return (1, stamps[parts[1]], rel)


def _is_run(d: Path) -> bool:
    """Whether `d` holds per-item files: a run (its run.json) or one of its scores (its score.json under scores/), the
    record on disk or already in the database (a migration a crash stopped after moving the record, before the
    per-item files, is finished by the next one)."""
    names = ("score.json", "metrics.json") if d.parent.name == "scores" else ("run.json",)
    return any((d / n).is_file() or _store.is_file(d / n) for n in names)


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
            f"{len(old)} run(s) in the layout before 0.8.0 (an outputs/ folder): evh migrate first",
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
    # The order the database is built in: by the run's time, then the key. A score set's id is its place in it, the
    # outputs and rows fill their tables in it, and the metrics' ids follow the order the names are first met, so one
    # data gives one database, and a run added since lands after every older one in each table: a release's delta stays
    # at its end. (The order is read before any file moves: run.json goes into the database with the others.)
    runs = sorted({p.parent for p in files if p.name in PER_ITEM and _is_run(p.parent)}, key=_in_time_order)
    run_set = set(runs)
    per_item = {p for p in files if p.name in PER_ITEM and p.parent in run_set}
    stamps: dict[str, float] = {}
    for p in sorted((p for p in files if p not in per_item), key=lambda p: _file_order(p, stamps)):
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
        n["runs"] += d.parent.name != "scores"
        n["outputs"] += len(outs)
        texts = [(o["item_id"], o["text"], o["sha256"]) for o in outs]
        bad = [i for i, t, s in texts if _outputs.sha256(t) != s]
        if bad:
            die(
                f"{d.relative_to(data)}: output(s) whose text does not match its sha256: {', '.join(bad[:5])}",
                "mismatch",
            )
        try:
            scored = disk.rows(d)
        except ValueError as exc:
            die(f"{exc}; a score's rows are JSON objects, one per line", "invalid-file")
        partial = disk.rows_text(d, partial=True)
        n["rows"] += len(scored or ()) + len((partial or "").splitlines())
        if dry_run:
            continue
        if texts and not st.has(d):
            st.write_all(d, {i: t for i, t, _ in texts}, [i for i, _, _ in texts])
        if [(o["item_id"], o["text"], o["sha256"]) for o in st.lines(d)] != texts:
            die(
                f"{d.relative_to(data)}: its outputs read back from the database differ; they stay files",
                "mismatch",
            )
        if scored is not None:
            if st.rows(d) is None:
                st.put_rows(d, scored)
            if st.rows_text(d) != disk.rows_text(d):
                die(
                    f"{d.relative_to(data)}: its rows read back from the database differ; they stay files",
                    "mismatch",
                )
        if partial is not None:
            if st.rows_text(d, partial=True) is None:
                st.put_partial(d, partial)
            if st.rows_text(d, partial=True) != partial:
                die(
                    f"{d.relative_to(data)}: its checkpoint read back from the database differs; it stays a file",
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
    """Everything in the database back to files; counts of what moved. A file, an output and a checkpoint come back
    byte for byte; a score's rows are written as canonical lines (`row_line` of each row the database gives back) and
    compared with the database's as canonical text, so a file that was not canonical comes back canonical."""
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
    if "rows" in have:
        die(
            f"{path.name} still holds the per-item rows of an older format (table `rows`): evh migrate first",
            "old-format",
        )
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
    # The project's store is files while this runs (config first), so the database is read here as a database: the rows
    # as `_outputs.read_set` assembles them, the checkpoint's lines as they are.
    names: dict[int, str] = {}
    sets = {r[0] for r in conn.execute("SELECT key FROM score_sets")} if "score_sets" in have else set()
    marked = (
        {r[0] for r in conn.execute("SELECT DISTINCT run FROM rows_partial")}
        if "rows_partial" in have
        else set()
    )
    runs: set[str] = sets | marked
    if "outputs" in have:
        runs |= {r[0] for r in conn.execute("SELECT DISTINCT run FROM outputs")}
    for key in sorted(runs):
        d = data / key
        n["runs"] += Path(key).parent.name != "scores"
        outs = (
            conn.execute(
                "SELECT item_id, text, sha256 FROM outputs WHERE run = ? ORDER BY rowid", (key,)
            ).fetchall()
            if "outputs" in have
            else []
        )
        n["outputs"] += len(outs)
        made = _outputs.read_set(conn, key, names) if key in sets else None
        scored = None if made is None else made[0]
        partial = (
            "".join(
                r[0] for r in conn.execute("SELECT line FROM rows_partial WHERE run = ? ORDER BY n", (key,))
            )
            if key in marked
            else None
        )
        n["rows"] += len(scored or ()) + len((partial or "").splitlines())
        if dry_run:
            continue
        d.mkdir(parents=True, exist_ok=True)
        if outs:
            disk.write_all(d, {i: t for i, t, _ in outs}, [i for i, _, _ in outs])
            if [(o["item_id"], o["text"], o["sha256"]) for o in disk.lines(d)] != [tuple(o) for o in outs]:
                die(f"{key}: its outputs written back differ", "mismatch")
        if partial is not None:
            disk.put_partial(d, partial)
            if disk.rows_text(d, partial=True) != partial:
                die(f"{key}: its checkpoint written back differs", "mismatch")
        if scored is not None:
            disk.put_rows(d, scored)
            if disk.rows_text(d) != "".join(_outputs.row_line(r) for r in scored):
                die(f"{key}: its rows written back differ", "mismatch")
    conn.close()
    if not dry_run:
        _store.close()
        for f in (path, Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-setup-lock")):
            f.unlink(missing_ok=True)
    return n


def body(**inputs: Any) -> int:
    """Move every file under data/ into the project's database, or back."""
    args = legacy.namespace(inputs, "data-migrate")
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
