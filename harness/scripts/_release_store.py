"""A release in one database: the files a release copy made (`_release.copy_data`), moved into `data/project.sqlite`
and sealed, and the layout checks that say it is (RFC-032 step 9).

Apart from `_release` because it is the disk's own business: a release's database is a file nothing opens for writing,
its folder holds that file alone, and the release's config.yaml says `store: sqlite`. Everything else about a release
goes through `_store`.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from evaluation_harness import _common, _outputs, _store

#: The modification time every file of a release carries (2000-01-01 UTC) when it goes into the database. The files
#: table keeps it, so a file's checkout time made the release's bytes differ on every render, and rsync re-sent ~230 MB
#: a deploy for data that had not changed. Nothing reads it from a release, which never changes after the seal.
RELEASE_MTIME_NS = 946_684_800 * 10**9


def _release_root(data: Path) -> Path:
    """The project a release's data/ belongs to (its config.yaml and its caches are beside it)."""
    if data.name != "data":
        _common.die(f"{data}: a release's data is its project's data/ folder", "bad-argument")
    return data.parent


def seal(db: Path) -> None:
    """A release's database made the one file a release holds: the per-item tables in it (a read-only open creates
    none), every page checkpointed, the journal out of write-ahead logging (so no `-wal` or `-shm` is ever made beside
    it), the setup lock gone. Then written again whole (`VACUUM INTO`, replacing the file): the pages of a database that
    was written to carry how it was written (the file change counter in its header moved with the number of
    checkpoints the move happened to make, 3 or 5), so two builds of the same data differed; the copy's bytes depend
    on the tables' contents alone, and rsync sends a deploy's database only when its data changed."""
    conn = sqlite3.connect(str(db), isolation_level=None)
    fresh = Path(f"{db}-sealing")
    fresh.unlink(missing_ok=True)
    try:
        _outputs.ensure_tables(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        mode = conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if mode == "delete":
            conn.execute("VACUUM INTO ?", (str(fresh),))
    finally:
        conn.close()
    if mode != "delete":
        _common.die(f"{db}: could not switch the database out of write-ahead logging ({mode})", "failed")
    os.replace(fresh, db)
    for suffix in ("-wal", "-shm", "-setup-lock"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)


def name_store(data: Path, store: str) -> None:
    """The release's config.yaml names its store: a project with none is refused, a release included."""
    (_release_root(data) / "config.yaml").write_text(f"store: {store}\n", encoding="utf-8")


def to_sqlite(data: Path) -> None:
    """The release's data/, as `copy_data` wrote it (files), made one database and sealed. Moved by `data-migrate`, in
    a process of its own: the project it moves is the release, not this process's. Every file first gets one
    modification time, so the same data makes the same bytes."""
    root = _release_root(data)
    name_store(data, "sqlite")
    for dirpath, _dirs, names in os.walk(data):
        for name in names:
            os.utime(
                os.path.join(dirpath, name), ns=(RELEASE_MTIME_NS, RELEASE_MTIME_NS), follow_symlinks=False
            )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_STORE_READONLY")
    }
    env.update(EVAL_HOME=str(root), EVAL_STORE="sqlite")
    done = subprocess.run(  # nosec B603 - this interpreter, a script of this package
        [sys.executable, str(Path(__file__).with_name("data_migrate.py")), "--to", "sqlite"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode:
        _common.die(
            f"moving the release's data into its database failed (exit {done.returncode}):\n"
            + (done.stdout + done.stderr)[-800:],
            "failed",
        )
    seal(data / _store.DB)


def layout_problems(data: Path) -> list[str]:
    """What is wrong with a release's data/ folder on disk: in SQLite the database alone (no `-wal`, `-shm` or lock
    file) and out of write-ahead logging; in files, no database."""
    if not _store.sqlite():
        return [f"a files release holds {_store.DB}"] if (data / _store.DB).exists() else []
    held = sorted(os.listdir(data)) if data.is_dir() else []
    if held != [_store.DB]:
        return [f"a SQLite release's data/ holds {held}, not just {_store.DB}"]
    with open(data / _store.DB, "rb") as fh:
        versions = fh.read(20)[18:20]  # the header's file-format versions: 2 means write-ahead logging
    if versions != b"\x01\x01":
        return [f"{_store.DB} is still in write-ahead logging (a -wal and -shm would be written beside it)"]
    return []
