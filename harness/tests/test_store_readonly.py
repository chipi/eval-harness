#!/usr/bin/env python3
"""A project's database that nothing may write (RFC-032 step 9): a release on the deployment's read-only mount.

    python tests/test_store_readonly.py

The release holds one database file in a folder the box mounts read-only. Opened as a project's database is (a lock
file beside it, write-ahead logging, tables created), it failed on the first request with `Read-only file system`
while /api/health said 200. A database is now opened read-only (SQLite's `mode=ro&immutable=1`) when
`EVAL_STORE_READONLY=1` or its folder is not writable: every read works, no file appears beside the database and its
bytes never change, and every write, through `_store` or `_outputs`, refuses as `ERROR (not-allowed)`, never as a raw
sqlite error. A file that is not a project's database is `invalid-file`; a release made without runs (no per-item
tables) reads as having none; a writable project is as it was.
"""

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

proj = Path(tempfile.mkdtemp(prefix="evh-readonly-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_STORE", "EVAL_STORE_READONLY"):
    os.environ.pop(k, None)
os.environ["EVAL_STORE"] = "sqlite"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _outputs, _release_store, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

data = proj / "data"
db = data / _store.DB
RUN = data / "runs" / "r1"
SCORE = RUN / "scores" / "s1@gold.ds"
ROWS = '{"item_id": "i1", "correct": 1}\n'


def sha() -> str:
    return hashlib.sha256(db.read_bytes()).hexdigest()


def beside() -> list[str]:
    return sorted(os.listdir(data))


def refusal(fn) -> str:
    """What a write said: the refusal's text, or what went wrong instead."""
    try:
        fn()
    except SystemExit as e:
        return str(e)
    except Exception as e:  # noqa: BLE001 -- the test names whatever came out instead of a refusal
        return f"{type(e).__name__}: {e}"
    return "no refusal"


def reopen() -> None:
    _outputs.reset()


def sqlite_store() -> _outputs.SqliteStore:
    st = _outputs.store()
    assert isinstance(st, _outputs.SqliteStore)
    return st


def make_project() -> None:
    """A sealed database as a release holds it: a file, a binary file, a run with outputs and rows."""
    reopen()
    for p in data.glob("*"):
        p.unlink()
    _store.write_text(data / "goals" / "g.yaml", "goal_id: g\n")
    _store.write_bytes(data / "b.bin", bytes(range(256)))
    _store.write_text(RUN / "run.json", "{}\n")
    st = sqlite_store()
    st.write_all(RUN, {"i1": "text one", "i2": "text two"}, ["i1", "i2"])
    st.put_rows(SCORE, ROWS)
    reopen()
    _release_store.seal(db)


try:
    data.mkdir(parents=True)
    make_project()
    check(
        "setup: a sealed database is the only file in data/, out of write-ahead logging",
        beside() == [_store.DB] and db.read_bytes()[18:20] == b"\x01\x01",
        (beside(), db.read_bytes()[18:20]),
    )

    # readonly(): the environment, or a folder that is not writable
    check("a writable folder and no setting: not read-only", _store.readonly() is False)
    os.environ["EVAL_STORE_READONLY"] = "0"
    check("EVAL_STORE_READONLY=0 is not a setting", _store.readonly() is False)
    os.environ["EVAL_STORE_READONLY"] = "1"
    check("EVAL_STORE_READONLY=1: read-only", _store.readonly() is True)
    os.environ.pop("EVAL_STORE_READONLY")

    def reads(label: str) -> None:
        """Every kind of read, then that nothing changed on disk."""
        before, names = sha(), beside()
        reopen()
        st = sqlite_store()
        got = {
            "read_text": _store.read_text(data / "goals" / "g.yaml"),
            "read_bytes": _store.read_bytes(data / "b.bin") == bytes(range(256)),
            "is_file": _store.is_file(data / "b.bin"),
            "is_dir": _store.is_dir(data / "runs"),
            "iterdir": sorted(p.name for p in _store.iterdir(data)),
            "glob": sorted(p.name for p in _store.glob(data / "goals", "*.yaml")),
            "stat": _store.stat(data / "b.bin").st_size,
            "output": st.read(RUN),
            "has": st.has(RUN),
            "rows": st.rows_text(SCORE),
            "runs": st.runs(),
            "item_across": list(st.item_across([RUN], "i1")) == [],
            "fingerprint": len(_store.fingerprint(data)) == 3,
            "open": _store.open_file(data / "goals" / "g.yaml").read(),
        }
        want = {
            "read_text": "goal_id: g\n",
            "read_bytes": True,
            "is_file": True,
            "is_dir": True,
            "iterdir": ["b.bin", "goals", "runs"],
            "glob": ["g.yaml"],
            "stat": 256,
            "output": {"i1": "text one", "i2": "text two"},
            "has": True,
            "rows": ROWS,
            "runs": ["runs/r1"],
            "item_across": True,
            "fingerprint": True,
            "open": "goal_id: g\n",
        }
        wrong = {k: v for k, v in got.items() if v != want[k]}
        check(f"{label}: every read works", not wrong, wrong)
        check(
            f"{label}: reading left the database and its folder as they were (no lock file, no -wal, no -shm)",
            sha() == before and beside() == names == [_store.DB],
            (beside(), sha() == before),
        )

    def writes(label: str) -> None:
        """Every kind of write refuses as the project does, and changes nothing."""
        before = sha()
        reopen()
        stage = _store.staging(data / "adopted", "ro-")
        (stage / "f.txt").write_text("x")
        disk_file = proj / "plain.txt"
        disk_file.write_text("x")
        st = sqlite_store()

        def opened(mode):
            """Refused at the open: a writer made and left to be closed would try again when it is collected."""
            return lambda: _store.open_file(data / "o.txt", mode)

        attempts = {
            "write_text": lambda: _store.write_text(data / "w.txt", "x"),
            "write_bytes": lambda: _store.write_bytes(data / "w.bin", b"x"),
            "create_new": lambda: _store.create_new(data / "n.bin", b"x"),
            "unlink": lambda: _store.unlink(data / "b.bin"),
            "rmtree": lambda: _store.rmtree(data / "goals"),
            "replace": lambda: _store.replace(data / "b.bin", data / "b2.bin"),
            "copy_file": lambda: _store.copy_file(disk_file, data / "copied.txt"),
            "adopt": lambda: _store.adopt(stage, data / "adopted"),
            "open w": opened("w"),
            "open a": opened("a"),
            "outputs add": lambda: st.add(RUN, "i3", "text"),
            "outputs write_all": lambda: st.write_all(RUN, {"i1": "x"}, ["i1"]),
            "outputs delete": lambda: st.delete(RUN),
            "rows put": lambda: st.put_rows(SCORE, ROWS),
            "rows append": lambda: st.append_row(SCORE, ROWS),
            "rows drop": lambda: st.drop_rows(SCORE),
            "Writer.add": lambda: _outputs.writer(RUN).add("i3", "text"),
        }
        said = {k: refusal(fn) for k, fn in attempts.items()}
        wrong = {
            k: v[:160]
            for k, v in said.items()
            if not v.startswith("ERROR (not-allowed)") or "read-only" not in v
        }
        check(
            f"{label}: all {len(attempts)} writes refuse as `ERROR (not-allowed)`, none as a sqlite error",
            not wrong,
            wrong,
        )
        check(
            f"{label}: the refused writes changed nothing",
            sha() == before
            and beside() == [_store.DB]
            and _store.read_bytes(data / "b.bin") == bytes(range(256)),
            (beside(),),
        )
        shutil.rmtree(stage, ignore_errors=True)
        disk_file.unlink()

    # EVAL_STORE_READONLY=1, in a folder that is writable
    os.environ["EVAL_STORE_READONLY"] = "1"
    reads("EVAL_STORE_READONLY=1")
    writes("EVAL_STORE_READONLY=1")
    os.environ.pop("EVAL_STORE_READONLY")

    # A folder that is not writable (the deployment's mount): no setting needed
    if os.geteuid() == 0:
        print("  --   a folder that is not writable: skipped, root writes to it")
    else:
        data.chmod(0o555)
        try:
            check("a folder that is not writable: read-only without a setting", _store.readonly() is True)
            reads("a folder not writable")
            writes("a folder not writable")
        finally:
            data.chmod(0o755)

    # Immutable means no lock is taken: a writer holding the database does not stop a release's read
    reopen()
    os.environ["EVAL_STORE_READONLY"] = "1"
    holder = sqlite3.connect(str(db), timeout=1)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        t0 = time.monotonic()
        locked = refusal(lambda: _store.read_text(data / "goals" / "g.yaml"))
        took = time.monotonic() - t0
    finally:
        holder.rollback()
        holder.close()
    check(
        "a database another connection holds locked is still read at once (no lock is taken)",
        locked == "no refusal" and took < 5,
        (locked, took),
    )
    os.environ.pop("EVAL_STORE_READONLY")

    # What is not a project's database
    reopen()
    os.environ["EVAL_STORE_READONLY"] = "1"
    keep = db.read_bytes()
    db.write_bytes(b"this is not a database at all")
    said = refusal(lambda: _store.is_file(data / "b.bin"))
    check(
        "a file that is not a database: `ERROR (invalid-file)`", said.startswith("ERROR (invalid-file)"), said
    )
    reopen()
    db.write_bytes(keep)
    c = sqlite3.connect(str(db))
    c.execute("DROP TABLE files")
    c.execute("CREATE TABLE other (x)")
    c.commit()
    c.close()
    said = refusal(lambda: _store.is_file(data / "b.bin"))
    check(
        "a database with no files table: `ERROR (invalid-file)`",
        said.startswith("ERROR (invalid-file)"),
        said,
    )

    # Sealing a database made without runs gives it the tables, so a read-only open finds them, and the journal DELETE
    reopen()
    db.unlink()
    c = sqlite3.connect(str(db))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        "CREATE TABLE files (path TEXT PRIMARY KEY, data BLOB NOT NULL, sha256 TEXT NOT NULL, mtime_ns INTEGER NOT NULL)"
    )
    c.commit()
    c.close()
    _release_store.seal(db)
    c = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    c.close()
    check(
        "sealing a database made without runs: the per-item tables are there, the journal is out of WAL, one file",
        {"files", "outputs", "rows"} <= have
        and db.read_bytes()[18:20] == b"\x01\x01"
        and beside() == [_store.DB],
        (have, beside()),
    )

    # A release made without runs has no per-item tables: read-only, it has no outputs and creates none
    reopen()
    db.unlink()
    c = sqlite3.connect(str(db))
    c.execute(
        "CREATE TABLE files (path TEXT PRIMARY KEY, data BLOB NOT NULL, sha256 TEXT NOT NULL, mtime_ns INTEGER NOT NULL)"
    )
    c.execute("INSERT INTO files VALUES ('goals/g.yaml', ?, 'x', 1)", (b"goal_id: g\n",))
    c.commit()
    c.close()
    before = sha()
    st = sqlite_store()
    check(
        "no per-item tables: no outputs, no rows, no runs, and none created",
        st.read(RUN) == {} and st.rows_text(SCORE) is None and st.runs() == [] and st.row_runs() == []
        and not st.has(RUN) and sha() == before and _store.read_text(data / "goals" / "g.yaml") == "goal_id: g\n",
        sha() == before,
    )  # fmt: skip

    # No database at all: reads find nothing, a write refuses (it would have made one)
    reopen()
    db.unlink()
    check(
        "no database: nothing is a file; the read of one is FileNotFoundError, as in a writable project",
        not _store.is_file(data / "b.bin") and _store.connect(create=False) is None,
    )
    try:
        _store.read_bytes(data / "b.bin")
        raised = False
    except FileNotFoundError:
        raised = True
    check("no database: read_bytes raises FileNotFoundError", raised)
    check(
        "no database: a write refuses and makes none",
        refusal(lambda: _store.write_text(data / "w.txt", "x")).startswith("ERROR (not-allowed)")
        and not db.exists(),
    )
    os.environ.pop("EVAL_STORE_READONLY")
    db.write_bytes(keep)

    # A writable project is as it was: write-ahead logged, written and read back
    reopen()
    _store.write_text(data / "w.txt", "back to normal\n")
    check(
        "writable: a write works and is read back",
        _store.read_text(data / "w.txt") == "back to normal\n" and not _store.readonly(),
    )
    conn = _store.connect(create=False)
    assert conn is not None
    check(
        "writable: the database is opened write-ahead logged, as before",
        conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal",
    )
finally:
    data.chmod(0o755)
    _outputs.reset()
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
