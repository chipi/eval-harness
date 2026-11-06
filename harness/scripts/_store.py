"""Everything under a project's data/, read and written only here (RFC-025): files, or one SQLite database.

The project's store is `store: sqlite` in its config.yaml, or EVAL_STORE (which wins), else `files`. Every function
takes a path. In the files store, and for any path outside data/ in either store, it is the filesystem, as pathlib
would do it. In the sqlite store a path under data/ is a row of `data/project.sqlite`, addressed by its path relative
to data/: directories are the paths' prefixes, so a directory exists while it holds a file, and removing one removes
everything under it, a run's outputs and rows included (they are in the same database, `_outputs`).

A project is either files or the database, never both: in the sqlite store nothing under data/ is read from or
written to the disk but the database itself.
"""

from __future__ import annotations

import fnmatch
import functools
import hashlib
import io
import os
import shutil
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from evaluation_harness import _common

DB = "project.sqlite"
SCHEMA_VERSION = "1"
#: One lock for the one connection: a server answers requests on several threads at once, and a sqlite3
#: connection used by two threads at once can crash the process (catalog-serve died that way, 2026-11-06).
#: `_outputs` takes the same lock for its tables in the same database.
_LOCK = threading.RLock()


def _locked(fn: Any) -> Any:
    """`fn` with the connection's lock held for the whole call (reentrant: a locked function may call another)."""

    @functools.wraps(fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        with _LOCK:
            return fn(*args, **kwargs)

    return run


_CONN: dict[str, sqlite3.Connection] = {}


def sqlite() -> bool:
    """Whether the project's store is the database."""
    return _common.store() == "sqlite"


def db_path() -> Path:
    """The project's database."""
    return _common.DATA / DB


def connect(create: bool = True) -> sqlite3.Connection | None:
    """The project's database, opened once per process (write-ahead logged, every commit synced); None when it does
    not exist and `create` is False. Its tables: `files` (everything under data/ that is not per item) and, from
    `_outputs`, `outputs` and `rows`."""
    path = db_path()
    key = str(path.resolve())
    with _LOCK:
        conn = _CONN.get(key)
        if conn is not None:
            return conn
        if not create and not path.is_file():
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=60, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, data BLOB NOT NULL, sha256 TEXT NOT NULL,"
            " mtime_ns INTEGER NOT NULL)"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
        _CONN[key] = conn
        return conn


def close() -> None:
    """Every open database closed (a test that changes project, a migration done)."""
    with _LOCK:
        for conn in _CONN.values():
            conn.close()
        _CONN.clear()


def _pathlike(x: Any) -> bool:
    """A path (str or os.PathLike): what this module stores. Anything else (a zip member, a package resource, an
    HTTP response) keeps its own methods, which every function here passes the call through to."""
    return isinstance(x, (str, os.PathLike))


def rel(path: Any) -> str | None:
    """A path's key in the database (its place under data/, `/`-separated) when the store is the database and the
    path is under data/; None for a path the filesystem keeps."""
    if not sqlite() or not _pathlike(path):
        return None
    try:
        key = Path(os.path.abspath(path)).relative_to(os.path.abspath(_common.DATA)).as_posix()
    except ValueError:
        return None
    if key in ("", ".") or key == DB or key.startswith(DB + "-"):
        return None
    return key


def _like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"


# ── reading ──────────────────────────────────────────────────────────────────────────────────────────────────────
@_locked
def _get(key: str) -> bytes | None:
    conn = connect(create=False)
    if conn is None:
        return None
    got = conn.execute("SELECT data FROM files WHERE path = ?", (key,)).fetchone()
    return bytes(got[0]) if got else None


def _missing(path: Any) -> FileNotFoundError:
    return FileNotFoundError(2, "No such file or directory (in the project's database)", str(path))


def read_bytes(path: Any) -> bytes:
    """The file's bytes."""
    if not _pathlike(path):
        return path.read_bytes()
    key = rel(path)
    if key is None:
        return Path(path).read_bytes()
    got = _get(key)
    if got is None:
        raise _missing(path)
    return got


def read_text(path: Any, encoding: str = "utf-8", errors: str | None = None) -> str:
    """The file's text."""
    if not _pathlike(path):
        return path.read_text(encoding=encoding, errors=errors)
    key = rel(path)
    if key is None:
        return Path(path).read_text(encoding=encoding, errors=errors)
    return read_bytes(path).decode(encoding, errors or "strict")


@_locked
def is_file(path: Any) -> bool:
    """Whether the path is a file."""
    if not _pathlike(path):
        return path.is_file()
    key = rel(path)
    if key is None:
        return Path(path).is_file()
    conn = connect(create=False)
    return bool(conn and conn.execute("SELECT 1 FROM files WHERE path = ?", (key,)).fetchone())


@_locked
def is_dir(path: Any) -> bool:
    """Whether the path is a directory (in the database: a prefix some file has; data/ itself always is)."""
    if not _pathlike(path):
        return path.is_dir()
    key = rel(path)
    if key is None:
        p = Path(path)
        return p.is_dir() or (sqlite() and _is_data_root(p))
    conn = connect(create=False)
    return bool(
        conn
        and conn.execute(
            "SELECT 1 FROM files WHERE path LIKE ? ESCAPE '\\' LIMIT 1", (_like(key),)
        ).fetchone()
    )


def _is_data_root(p: Path) -> bool:
    return os.path.abspath(p) == os.path.abspath(_common.DATA)


def exists(path: Any) -> bool:
    """Whether the path is a file or a directory."""
    if not _pathlike(path):
        return path.exists()
    return is_file(path) or is_dir(path)


@dataclass(frozen=True)
class Stat:
    """What callers read of a stat: when it last changed and how big it is."""

    st_mtime: float
    st_mtime_ns: int
    st_size: int


@_locked
def stat(path: Any) -> Any:
    """os.stat for the filesystem; size and modification time for a file in the database."""
    if not _pathlike(path):
        return path.stat()
    key = rel(path)
    if key is None:
        return Path(path).stat()
    conn = connect(create=False)
    got = (
        conn.execute("SELECT length(data), mtime_ns FROM files WHERE path = ?", (key,)).fetchone()
        if conn
        else None
    )
    if got is None:
        if is_dir(path):
            return Stat(0.0, 0, 0)
        raise _missing(path)
    return Stat(got[1] / 1e9, int(got[1]), int(got[0]))


@_locked
def _keys_under(key: str) -> list[str]:
    conn = connect(create=False)
    if conn is None:
        return []
    if key in ("", "."):
        return [r[0] for r in conn.execute("SELECT path FROM files ORDER BY path")]
    return [
        r[0]
        for r in conn.execute(
            "SELECT path FROM files WHERE path LIKE ? ESCAPE '\\' ORDER BY path", (_like(key),)
        )
    ]


def _root_key(path: Any) -> str | None:
    """The key of a directory path (data/ itself is the empty key) in the sqlite store; None for the filesystem."""
    if sqlite() and _is_data_root(Path(path)):
        return ""
    return rel(path)


def iterdir(path: Any) -> Iterator[Path]:
    """The directory's entries."""
    if not _pathlike(path):
        yield from path.iterdir()
        return
    key = _root_key(path)
    if key is None:
        yield from Path(path).iterdir()
        return
    base = Path(path)
    cut = len(key) + 1 if key else 0
    seen: set[str] = set()
    for k in _keys_under(key):
        name = k[cut:].split("/", 1)[0]
        if name not in seen:
            seen.add(name)
            yield base / name


def _match(paths: list[str], pattern: str) -> list[str]:
    """The relative paths `pattern` matches, as Path.glob would (`*` within one part, `**` across parts), with every
    directory the files imply."""
    parts = pattern.split("/")
    cands: set[str] = set()
    for k in paths:
        segs = k.split("/")
        for i in range(1, len(segs) + 1):
            cands.add("/".join(segs[:i]))
    out = []
    for c in cands:
        if _glob_ok(c.split("/"), parts):
            out.append(c)
    return sorted(out)


def _glob_ok(segs: list[str], parts: list[str]) -> bool:
    if not parts:
        return not segs
    if parts[0] == "**":
        return any(_glob_ok(segs[i:], parts[1:]) for i in range(len(segs) + 1))
    return bool(segs) and fnmatch.fnmatchcase(segs[0], parts[0]) and _glob_ok(segs[1:], parts[1:])


def glob(path: Any, pattern: str) -> Iterator[Path]:
    """Path.glob."""
    if not _pathlike(path):
        yield from path.glob(pattern)
        return
    key = _root_key(path)
    if key is None:
        yield from Path(path).glob(pattern)
        return
    cut = len(key) + 1 if key else 0
    for m in _match([k[cut:] for k in _keys_under(key)], pattern):
        yield Path(path) / m


def rglob(path: Any, pattern: str) -> Iterator[Path]:
    """Path.rglob."""
    if not _pathlike(path):
        yield from path.rglob(pattern)
        return
    yield from glob(path, "**/" + pattern)


# ── writing ──────────────────────────────────────────────────────────────────────────────────────────────────────
@_locked
def _put(key: str, data: bytes) -> None:
    conn = connect()
    assert conn is not None
    conn.execute(
        "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)",
        (key, sqlite3.Binary(data), hashlib.sha256(data).hexdigest(), time.time_ns()),
    )


def write_bytes(path: Any, data: bytes) -> None:
    """The file written whole (atomically in the database: one committed statement)."""
    if not _pathlike(path):
        path.write_bytes(data)
        return
    key = rel(path)
    if key is None:
        Path(path).write_bytes(data)
        return
    with _LOCK:
        _put(key, bytes(data))


def write_text(path: Any, text: str, encoding: str = "utf-8", newline: str | None = None) -> None:
    """The file written whole; `newline` as Path.write_text takes it (None or "\n" keeps "\n" on POSIX)."""
    if not _pathlike(path):
        path.write_text(text, encoding=encoding, newline=newline)
        return
    key = rel(path)
    if key is None:
        Path(path).write_text(text, encoding=encoding, newline=newline)
        return
    if newline not in (None, "", "\n"):
        text = text.replace("\n", newline)
    write_bytes(path, text.encode(encoding))


def mkdir(path: Any, parents: bool = False, exist_ok: bool = False) -> None:
    """Path.mkdir; nothing in the database, where a directory is the files it holds."""
    if not _pathlike(path):
        path.mkdir(parents=parents, exist_ok=exist_ok)
        return
    if rel(path) is None and not (sqlite() and _is_data_root(Path(path))):
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)


@_locked
def unlink(path: Any, missing_ok: bool = False) -> None:
    """The file removed."""
    if not _pathlike(path):
        path.unlink(missing_ok=missing_ok)
        return
    key = rel(path)
    if key is None:
        Path(path).unlink(missing_ok=missing_ok)
        return
    conn = connect(create=False)
    gone = conn.execute("DELETE FROM files WHERE path = ?", (key,)).rowcount if conn else 0
    if not gone and not missing_ok:
        raise _missing(path)


@_locked
def rmtree(path: Any, ignore_errors: bool = False) -> None:
    """The directory and everything under it removed; in the database a run's outputs and rows go with it."""
    key = rel(path)
    if key is None:
        shutil.rmtree(path, ignore_errors=ignore_errors)
        return
    conn = connect(create=False)
    if conn is None:
        if not ignore_errors:
            raise _missing(path)
        return
    with _LOCK:
        conn.execute("BEGIN IMMEDIATE")
        try:
            n = conn.execute("DELETE FROM files WHERE path LIKE ? ESCAPE '\\'", (_like(key),)).rowcount
            for table in _per_item_tables(conn):
                conn.execute(table[0], (key, _like(key)))
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    if not n and not ignore_errors:
        raise _missing(path)


def staging(dst: Any, prefix: str) -> Path:
    """A new, empty directory on disk to build the directory `dst` in, then put in place with `adopt`: beside `dst`
    for a path on disk (one rename, never a half directory), under the project's .build/staging/ for a path in the
    database (whose directories are only keys). Always on disk, so a command the caller runs on it (a capture's
    scrubber) sees real files; mode as a plain mkdir's."""
    import tempfile  # noqa: PLC0415

    if rel(dst) is None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        base = Path(dst).parent
    else:
        base = _common.ROOT / ".build" / "staging"
        base.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix=prefix, dir=base))
    umask = os.umask(0)
    os.umask(umask)
    d.chmod(0o777 & ~umask)  # a plain mkdir's mode, not mkdtemp's private 0700
    return d


def adopt(src: Path, dst: Any) -> None:
    """The directory `src` (from `staging`) becomes the directory `dst`, which must not exist or be empty: renamed on
    disk; in the database every file under it written under `dst` in one transaction (all of it, or none), then `src`
    removed."""
    key = rel(dst)
    if key is None:
        if Path(dst).is_dir():
            Path(dst).rmdir()  # empty: the rename needs the name free
        Path(src).rename(dst)
        return
    files = sorted(p for p in Path(src).rglob("*") if p.is_file())
    with _LOCK:
        conn = connect()
        assert conn is not None
        conn.execute("BEGIN IMMEDIATE")
        try:
            for f in files:
                _put(f"{key}/{f.relative_to(src).as_posix()}", f.read_bytes())
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    shutil.rmtree(src)


def _per_item_tables(conn: sqlite3.Connection) -> list[tuple[str]]:
    """The DELETE statements for the per-item tables that exist (`_outputs` creates them on first use)."""
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    stmts = {
        "outputs": "DELETE FROM outputs WHERE run = ? OR run LIKE ? ESCAPE '\\'",
        "rows": "DELETE FROM rows WHERE run = ? OR run LIKE ? ESCAPE '\\'",
    }
    return [(stmts[t],) for t in stmts if t in have]


def replace(src: Any, dst: Any) -> None:
    """os.replace: the file at `src` becomes the file at `dst`."""
    ks, kd = rel(src), rel(dst)
    if ks is None and kd is None:
        os.replace(src, dst)
        return
    data = read_bytes(src)
    write_bytes(dst, data)
    unlink(src)


def copy_file(src: Any, dst: Any) -> None:
    """shutil.copy2: a file copied, in or out of the database (into `dst` when it is a directory)."""
    if rel(src) is None and rel(dst) is None:
        shutil.copy2(src, dst)
        return
    if is_dir(dst) or str(dst).endswith(("/", os.sep)):
        dst = Path(dst) / Path(src).name
    if rel(dst) is None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
    write_bytes(dst, read_bytes(src))


def copy_tree(src: Any, dst: Any) -> None:
    """shutil.copytree (into an existing tree too): every file under `src`, in or out of the database."""
    if rel(src) is None and rel(dst) is None:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return
    for f in rglob(src, "*"):
        if is_file(f):
            copy_file(f, Path(dst) / Path(f).relative_to(Path(src)))


class _Writer(io.BytesIO):
    """A file opened for writing in the database: what is written is saved when it is closed."""

    def __init__(self, path: Path | str, initial: bytes = b"") -> None:
        super().__init__(initial)
        self.seek(0, io.SEEK_END)
        self._path = path

    def close(self) -> None:
        if not self.closed:
            write_bytes(self._path, self.getvalue())
        super().close()


def open_file(
    path: Any,
    mode: str = "r",
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> IO[Any]:
    """open() and Path.open: read (`r`, `rb`), write (`w`, `wb`) or append (`a`, `ab`)."""
    if isinstance(path, int) or not _pathlike(path):
        return (
            open(path, mode, buffering, encoding, errors, newline)
            if isinstance(path, int)
            else path.open(mode)
        )
    if rel(path) is None:
        return open(path, mode, buffering, encoding, errors, newline)
    text = "b" not in mode
    enc = encoding or "utf-8"
    if mode.startswith("r"):
        data = read_bytes(path)
        return io.StringIO(data.decode(enc, errors or "strict")) if text else io.BytesIO(data)
    initial = (read_bytes(path) if is_file(path) else b"") if mode.startswith("a") else b""
    raw = _Writer(path, initial)
    return io.TextIOWrapper(raw, encoding=enc, errors=errors, write_through=True) if text else raw


def stray_files() -> list[Path]:
    """Files on disk under data/ other than the database: none when the project's store is the database (never both,
    RFC-025); what validate names."""
    data = _common.DATA
    out = []
    for root, dirs, files in os.walk(data):
        dirs.sort()
        for f in sorted(files):
            q = Path(root) / f
            if not (q.parent == data and (f == DB or f.startswith(DB + "-"))):
                out.append(q)
    return out


def glob_str(pattern: str) -> list[str]:
    """glob.glob: the paths a pattern matches, as strings; one under data/ in the sqlite store matched in the
    database."""
    import glob as _glob  # noqa: PLC0415

    parts = Path(pattern).parts
    lit = next((i for i, x in enumerate(parts) if any(c in x for c in "*?[")), len(parts))
    base = Path(*parts[:lit]) if lit else Path(".")
    if rel(base) is None and not (sqlite() and _is_data_root(base)):
        return _glob.glob(pattern)
    rest = "/".join(parts[lit:])
    if not rest:
        return [str(base)] if exists(base) else []
    return [str(q) for q in glob(base, rest)]
