"""A run's outputs, read and written only here (RFC-024), in the project's runs store (RFC-025).

The files store (the default) keeps one file per run, `outputs.jsonl`:

    {"item_id": "t00042", "text": "...the output, exactly...", "sha256": "<sha256 of the text's UTF-8 bytes>"}

The sqlite store (`runs: {store: sqlite}` in config.yaml, or EVAL_RUNS_STORE=sqlite) keeps the same rows in one
database, `data/runs.sqlite`, table `outputs (run, item_id, text, sha256)`, `run` being the run's directory under
data/. Either way:

A measured run adds an output per item as it is produced (`writer`), synced or committed before the next, so a stopped
run keeps every finished output and `--resume` reads them back; a torn last line (a kill mid-append) is not an output,
so that item is called again. `finish` rewrites them in dataset order when the run completes. A derived run (a
re-score, a judging, a sheet import) writes no outputs of its own: `output()` and `outputs()` follow its
`derived.from_dir` (else `derived.from`) to the run whose they are. Every module reads outputs through this one: a
test fails on an `outputs/` path built anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from evaluation_harness import _common

FILE = "outputs.jsonl"
#: The checkpoint of rows a pass appends as it goes (a crashed run has no predictions.jsonl yet); deleted by finish().
ROWS = "rows.partial.jsonl"
#: The sqlite store's database, in the project's data directory.
DB = "runs.sqlite"
SCHEMA_VERSION = "1"
_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_NAMES: dict[str, list[Path]] = {}


def sha256(text: str) -> str:
    """The sha256 of an output's UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line(item_id: str, text: str) -> str:
    return json.dumps({"item_id": item_id, "text": text, "sha256": sha256(text)}, ensure_ascii=False)


class Store(Protocol):
    """Where runs' outputs live; every method takes the run's directory."""

    name: str

    def has(self, run_dir: Path) -> bool:
        """Whether the run itself holds outputs here."""
        ...

    def read(self, run_dir: Path) -> dict[str, str]:
        """{item_id: text} of the run's own outputs; {} when it has none."""
        ...

    def rows(self, run_dir: Path) -> list[dict[str, Any]]:
        """The run's own outputs as stored (item_id, text, sha256), in order."""
        ...

    def add(self, run_dir: Path, item_id: str, text: str) -> None:
        """One item's output, on disk before this returns."""
        ...

    def write_all(self, run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
        """The run's whole outputs at once, in `order`, atomically; items not in `texts` left out."""
        ...

    def delete(self, run_dir: Path) -> None:
        """The run's outputs gone from here."""
        ...


class FileStore:
    """Each run's outputs in its own `outputs.jsonl`."""

    name = "files"

    def has(self, run_dir: Path) -> bool:
        """Whether the run itself holds outputs here."""
        return (Path(run_dir) / FILE).is_file()

    def read(self, run_dir: Path) -> dict[str, str]:
        """{item_id: text}, a torn last line skipped; kept for the process by path and mtime."""
        path = Path(run_dir) / FILE
        if not path.is_file():
            return {}
        key, mtime = str(path), path.stat().st_mtime
        hit = _CACHE.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
        out: dict[str, str] = {}
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a torn final line from a kill mid-append: that item is not done
                if (
                    isinstance(row, dict)
                    and isinstance(row.get("item_id"), str)
                    and isinstance(row.get("text"), str)
                ):
                    out[row["item_id"]] = row["text"]
        _CACHE[key] = (mtime, out)
        return out

    def rows(self, run_dir: Path) -> list[dict[str, Any]]:
        """The run's own outputs as stored (item_id, text, sha256), in order."""
        p = Path(run_dir) / FILE
        if not p.is_file():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def add(self, run_dir: Path, item_id: str, text: str) -> None:
        """One item's output, on disk before this returns."""
        path = Path(run_dir) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_line(item_id, text) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def write_all(self, run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
        """The run's whole outputs at once, in `order`, atomically; items not in `texts` left out."""
        path = Path(run_dir) / FILE
        body = "".join(_line(item, texts[item]) + "\n" for item in order if item in texts)
        _common.write_text_atomic(path, body)
        _CACHE.pop(str(path), None)

    def delete(self, run_dir: Path) -> None:
        """The run's outputs gone from here."""
        path = Path(run_dir) / FILE
        path.unlink(missing_ok=True)
        _CACHE.pop(str(path), None)


class SqliteStore:
    """Every run's outputs in one database, write-ahead logged: readers never block the writer, and a crash keeps
    every committed output. One committed insert per output; insertion order is the order outputs are read in."""

    name = "sqlite"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._cache: dict[str, dict[str, str]] = {}
        self._version: int | None = None

    def key(self, run_dir: Path) -> str:
        """The run's directory under data/ (what `derived.from_dir` names); an absolute path outside it."""
        d = Path(run_dir).resolve()
        try:
            return d.relative_to(_common.DATA.resolve()).as_posix()
        except ValueError:
            return d.as_posix()

    def _db(self, create: bool) -> sqlite3.Connection | None:
        if self._conn is None:
            if not create and not self.path.is_file():
                return None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=60, isolation_level=None, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS outputs (run TEXT NOT NULL, item_id TEXT NOT NULL, text TEXT NOT NULL,"
                " sha256 TEXT NOT NULL, PRIMARY KEY (run, item_id))"
            )
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
            self._conn = conn
        return self._conn

    def _fresh(self, conn: sqlite3.Connection) -> None:
        """Drop the cache when another connection (another process) has committed since it was filled."""
        v = conn.execute("PRAGMA data_version").fetchone()[0]
        if v != self._version:
            self._cache.clear()
            self._version = v

    def has(self, run_dir: Path) -> bool:
        """Whether the run itself holds outputs here."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return False
            self._fresh(conn)
            k = self.key(run_dir)
            if self._cache.get(k):
                return True
            return conn.execute("SELECT 1 FROM outputs WHERE run = ? LIMIT 1", (k,)).fetchone() is not None

    def read(self, run_dir: Path) -> dict[str, str]:
        """{item_id: text} of the run's own outputs; {} when it has none."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return {}
            self._fresh(conn)
            k = self.key(run_dir)
            if k not in self._cache:
                cur = conn.execute("SELECT item_id, text FROM outputs WHERE run = ? ORDER BY rowid", (k,))
                self._cache[k] = dict(cur.fetchall())
            return self._cache[k]

    def rows(self, run_dir: Path) -> list[dict[str, Any]]:
        """The run's own outputs as stored (item_id, text, sha256), in order."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return []
            cur = conn.execute(
                "SELECT item_id, text, sha256 FROM outputs WHERE run = ? ORDER BY rowid", (self.key(run_dir),)
            )
            return [{"item_id": i, "text": t, "sha256": s} for i, t, s in cur.fetchall()]

    def runs(self) -> list[str]:
        """Every run (its key) the database holds outputs for."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return []
            return [r[0] for r in conn.execute("SELECT DISTINCT run FROM outputs ORDER BY run")]

    def add(self, run_dir: Path, item_id: str, text: str) -> None:
        """One item's output, on disk before this returns."""
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            k = self.key(run_dir)
            conn.execute(
                "INSERT OR REPLACE INTO outputs VALUES (?, ?, ?, ?)", (k, item_id, text, sha256(text))
            )
            self._cache.pop(k, None)

    def write_all(self, run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
        """The run's whole outputs at once, in `order`, atomically; items not in `texts` left out."""
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            k = self.key(run_dir)
            rows = [(k, item, texts[item], sha256(texts[item])) for item in order if item in texts]
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM outputs WHERE run = ?", (k,))
                conn.executemany("INSERT INTO outputs VALUES (?, ?, ?, ?)", rows)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            self._cache.pop(k, None)

    def delete(self, run_dir: Path) -> None:
        """The run's outputs gone from here."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return
            k = self.key(run_dir)
            conn.execute("DELETE FROM outputs WHERE run = ?", (k,))
            self._cache.pop(k, None)

    def close(self) -> None:
        """The connection closed and the cache dropped."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._cache.clear()
            self._version = None


def db_runs(db: Path) -> list[str]:
    """The runs (keys under the data directory) a runs database holds outputs for; [] when there is none."""
    if not Path(db).is_file():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    try:
        return [r[0] for r in conn.execute("SELECT DISTINCT run FROM outputs ORDER BY run")]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def db_copy(db: Path, dst: Path, drop: Callable[[str], bool]) -> int:
    """A consistent copy of a runs database (a run writing meanwhile included up to its last commit) at `dst`, one
    file, without the runs `drop` names, rebuilt so their texts are in none of its pages; how many runs it dropped."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    out = sqlite3.connect(str(dst), isolation_level=None)
    try:
        src.backup(out)
        out.execute(
            "PRAGMA secure_delete=ON"
        )  # a deleted text is zeroed even where the build's default is off
        gone = [k for (k,) in out.execute("SELECT DISTINCT run FROM outputs") if drop(k)]
        out.executemany("DELETE FROM outputs WHERE run = ?", [(k,) for k in gone])
        out.execute("PRAGMA journal_mode=DELETE")
        out.execute("VACUUM")
    finally:
        src.close()
        out.close()
    return len(gone)


_FILES = FileStore()
_SQLITE: dict[str, SqliteStore] = {}


def store_named(name: str) -> Store:
    """The files store, or the sqlite store of the current data directory."""
    if name == "files":
        return _FILES
    path = _common.DATA / DB
    return _SQLITE.setdefault(str(path.resolve()), SqliteStore(path))


def store() -> Store:
    """The project's runs store (`_common.runs_store()`)."""
    return store_named(_common.runs_store())


def reset() -> None:
    """Forget every cache and close the database (after a migration, or a test that changed the data directory)."""
    _CACHE.clear()
    _NAMES.clear()
    for s in _SQLITE.values():
        s.close()
    _SQLITE.clear()


def _runs_named(name: str) -> list[Path]:
    """Every run directory with this name under the project's runs trees (data/runs*, and EVAL_RUNS_DIR)."""
    if not _NAMES:
        roots = {*sorted(p for p in _common.DATA.glob("runs*") if p.is_dir()), _common.RUNS}
        for root in roots:
            if not root.is_dir():
                continue
            for depth in ("*", "*/*", "*/*/*"):
                for d in root.glob(depth):
                    if d.is_dir() and any((d / f).is_file() for f in ("metrics.json", "run.json", FILE)):
                        _NAMES.setdefault(d.name, []).append(d)
    return _NAMES.get(name, [])


def _derived_from(d: Path) -> str | None:
    """The run a derived run names in `derived.from`, None for a measured run (or an unreadable record)."""
    m = d / "metrics.json"
    try:
        frm = (
            (json.loads(m.read_text(encoding="utf-8")).get("derived") or {}).get("from")
            if m.is_file()
            else None
        )
    except ValueError:
        return None
    return str(frm) if frm else None


def _from_dir(d: Path) -> Path | None:
    """The source's exact directory a derived run recorded (`derived.from_dir`, under the data directory), if any."""
    m = d / "metrics.json"
    try:
        rel = (
            (json.loads(m.read_text(encoding="utf-8")).get("derived") or {}).get("from_dir")
            if m.is_file()
            else None
        )
    except ValueError:
        return None
    return _common.DATA / rel if rel else None


def own(run_dir: Path) -> bool:
    """Whether the run itself holds outputs in the project's store (not through a source)."""
    return store().has(Path(run_dir))


def source(run_dir: Path) -> Path | None:
    """The run directory that holds this run's outputs: its own, or (a derived run) its source's, followed as far as
    it goes; None when there is none."""
    st = store()
    seen: set[Path] = set()
    d = Path(run_dir)
    while d not in seen:
        seen.add(d)
        if st.has(d):
            return d
        frm = _derived_from(d)
        if not frm:
            return None
        exact = _from_dir(d)
        if exact is not None:
            if exact.resolve() == d.resolve():
                return None
            d = exact
            continue
        cands = [c for c in _runs_named(Path(str(frm)).name) if c.resolve() != d.resolve()]
        with_outputs = [c for c in cands if st.has(c)]
        # The measured run first (no `derived.from` of its own), never a derived run of the same name that kept its own
        # (different) outputs; then the one directly under data/runs; then by path.
        pick = sorted(
            with_outputs,
            key=lambda c: (_derived_from(c) is not None, c.parent != _common.DATA / "runs", str(c)),
        )
        pick = pick or cands
        if not pick:
            return None
        d = pick[0]
    return None


def outputs(run_dir: Path) -> dict[str, str]:
    """{item_id: text} of a run (its source's for a derived run); {} when it has none."""
    src = source(run_dir)
    return dict(store().read(src)) if src else {}


def output(run_dir: Path, item_id: str) -> str | None:
    """One item's output, or None when the run has none for it."""
    src = source(run_dir)
    return store().read(src).get(item_id) if src else None


def old_layout(run_dir: Path) -> bool:
    """Whether a run is still in the layout before 0.8.0 (an `outputs/` folder of <item>.txt): `evh run-migrate` moves it."""
    return (Path(run_dir) / "outputs").is_dir()


def has_outputs(run_dir: Path) -> bool:
    """Whether the run (or its source) has outputs."""
    return source(run_dir) is not None


def signature(run_dir: Path) -> str:
    """V5's digest of what a run wrote: each output as `<item_id>.txt` and its bytes, by item id (the value the
    per-item files gave). Runs without outputs share "<no-outputs>": what they wrote cannot tell them apart."""
    outs = outputs(run_dir)
    if not outs:
        return "<no-outputs>"
    h = hashlib.sha256()
    for item in sorted(outs, key=lambda i: f"{i}.txt"):
        h.update(f"{item}.txt".encode() + b"\0" + outs[item].encode("utf-8") + b"\x1e")
    return h.hexdigest()


class Writer:
    """Adds a run's outputs as they are produced; each is on disk (synced, or committed) before the next item."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._store = store()

    def add(self, item_id: str, text: str) -> None:
        """One item's output, appended and synced."""
        self._store.add(self.run_dir, item_id, text)


def writer(run_dir: Path) -> Writer:
    """The run's appending writer."""
    return Writer(run_dir)


def write_all(run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
    """The run's whole outputs at once, in `order` (the dataset's), atomically: items not in `texts` are left out."""
    store().write_all(Path(run_dir), texts, order)


def finish(run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
    """A completed run: its outputs in dataset order, the row checkpoint gone (predictions.jsonl has the rows)."""
    write_all(run_dir, texts, order)
    (Path(run_dir) / ROWS).unlink(missing_ok=True)


def count(run_dir: Path) -> int:
    """How many outputs a run has written so far."""
    return len(store().read(Path(run_dir)))


def lines(run_dir: Path) -> list[dict[str, Any]]:
    """The run's own outputs as written (item_id, text, sha256), for a release or a check that needs the sha256."""
    return store().rows(Path(run_dir))
