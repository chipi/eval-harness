"""A run's outputs and rows, read and written only here (RFC-024), in the project's store (RFC-025).

The files store (the default) keeps one file per run, `outputs.jsonl`:

    {"item_id": "t00042", "text": "...the output, exactly...", "sha256": "<sha256 of the text's UTF-8 bytes>"}

The sqlite store (`store: sqlite` in config.yaml, or EVAL_STORE=sqlite) keeps the same rows in the project's one
database (`_store`, data/project.sqlite), table `outputs (run, item_id, text, sha256)`, `run` being the run's
directory under data/. Either way:

A measured run adds an output per item as it is produced (`writer`), synced or committed before the next, so a stopped
run keeps every finished output and `--resume` reads them back; a torn last line (a kill mid-append) is not an output,
so that item is called again. `finish` rewrites them in dataset order when the run completes. A derived run (a
re-score, a judging, a sheet import) writes no outputs of its own: `output()` and `outputs()` follow its
`derived.from_dir` (else `derived.from`) to the run whose they are. Every module reads outputs through this one: a
test fails on an `outputs/` path built anywhere else.

A run's rows (one JSON object per item: its scores, cost, tokens, `_meta`) are its `predictions.jsonl` in the files
store and table `rows (run, partial, n, item_id, row)` in the sqlite one, each line's exact text kept, so `rows_text`
is the same bytes in either. `partial` rows are the pass's checkpoint (`rows.partial.jsonl`), appended per item and
dropped by `finish`. `_runs.item_rows` and `write_rows` are how every module reads and writes them; a test fails on a
`predictions.jsonl` path built anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from evaluation_harness import _common, _store

FILE = "outputs.jsonl"
#: The folder of <item>.txt a run had before 0.8.0 (`evh run-migrate` moves it into FILE).
OLD_DIR = "outputs"
#: The checkpoint of rows a pass appends as it goes (a crashed run has no predictions.jsonl yet); deleted by finish().
ROWS = "rows.partial.jsonl"
#: A run's rows in the files store.
PREDICTIONS = "predictions.jsonl"
SCHEMA_VERSION = "1"
_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_NAMES: dict[str, list[Path]] = {}
#: How much rows text a process keeps read, per cache: the runs read last, by the size of their rows (one run's are
#: a few kilobytes or a few megabytes). Unbounded, a warm catalog-serve kept every committed run's rows (94,650 of
#: them) after reading each once, 48 MB more under --warm; bounded at 128 runs, still 29 MB (budget-check,
#: 2026-11-06). At 8 MB its RSS and cached answers are the base's again.
ROWS_KEPT_BYTES = 8_000_000


def _text_size(value: Any) -> int:
    """The rows text an entry holds: (stamp, text), (text, index), or text."""
    if isinstance(value, tuple):
        value = next((x for x in value if isinstance(x, str)), "")
    return len(value) if isinstance(value, str) else 0


class _Kept(OrderedDict):
    """A dict that keeps the entries read or written last, up to `ROWS_KEPT_BYTES` of rows text."""

    def __init__(self) -> None:
        super().__init__()
        self.bytes = 0

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return default

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self:
            self.bytes -= _text_size(self[key])
        super().__setitem__(key, value)
        self.bytes += _text_size(value)
        self.move_to_end(key)
        while self.bytes > ROWS_KEPT_BYTES and len(self) > 1:
            _k, old = self.popitem(last=False)
            self.bytes -= _text_size(old)

    def __delitem__(self, key: Any) -> None:
        self.bytes -= _text_size(self[key])
        super().__delitem__(key)

    def pop(self, key: Any, *default: Any) -> Any:
        if key in self:
            value = self[key]
            del self[key]
            return value
        if default:
            return default[0]
        raise KeyError(key)

    def clear(self) -> None:
        super().clear()
        self.bytes = 0


_ROWS_CACHE: _Kept = _Kept()  # {(rows path, errors): ((mtime_ns, size), its text)}
#: {run dir: (its rows text, {item_id: its first row line})}, valid while rows_text returns that same text.
_ROWS_INDEX: _Kept = _Kept()


def sha256(text: str) -> str:
    """The sha256 of an output's UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line(item_id: str, text: str) -> str:
    return json.dumps({"item_id": item_id, "text": text, "sha256": sha256(text)}, ensure_ascii=False)


def _forget_rows(path: Path) -> None:
    for k in [k for k in _ROWS_CACHE if k[0] == str(path)]:
        _ROWS_CACHE.pop(k, None)


def _item_of(line: str) -> str | None:
    """A row line's item id, None when it has none (or is not JSON)."""
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return str(row["item_id"]) if isinstance(row, dict) and row.get("item_id") is not None else None


class Store(Protocol):
    """Where runs' outputs live; every method takes the run's directory."""

    name: str

    def has(self, run_dir: Path) -> bool:
        """Whether the run itself holds outputs here."""
        ...

    def read(self, run_dir: Path) -> dict[str, str]:
        """{item_id: text} of the run's own outputs; {} when it has none."""
        ...

    def lines(self, run_dir: Path) -> list[dict[str, Any]]:
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

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """The run's rows exactly as written (the checkpoint's with `partial`); None when it has none. Bytes that
        are not UTF-8 raise, unless `errors` says otherwise (`replace`)."""
        ...

    def put_rows(self, run_dir: Path, text: str, partial: bool = False) -> None:
        """The run's rows replaced by `text` at once, atomically."""
        ...

    def append_row(self, run_dir: Path, line: str, partial: bool = True) -> None:
        """One row line (its newline included) added, on disk before this returns."""
        ...

    def drop_rows(self, run_dir: Path, partial: bool = False) -> None:
        """The run's rows (or its checkpoint) gone from here."""
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

    def lines(self, run_dir: Path) -> list[dict[str, Any]]:
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

    @staticmethod
    def _rows_path(run_dir: Path, partial: bool) -> Path:
        return Path(run_dir) / (ROWS if partial else PREDICTIONS)

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """The run's rows exactly as written (the checkpoint's with `partial`); None when it has none."""
        path = self._rows_path(run_dir, partial)
        try:
            st = path.stat()
        except OSError:
            return None
        key, stamp = (str(path), errors), (st.st_mtime_ns, st.st_size)
        hit = _ROWS_CACHE.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
        text = path.read_bytes().decode("utf-8", errors=errors)
        _ROWS_CACHE[key] = (stamp, text)
        return text

    def put_rows(self, run_dir: Path, text: str, partial: bool = False) -> None:
        """The run's rows replaced by `text` at once, atomically."""
        path = self._rows_path(run_dir, partial)
        _common.write_text_atomic(path, text)
        _forget_rows(path)

    def append_row(self, run_dir: Path, line: str, partial: bool = True) -> None:
        """One row line (its newline included) added, on disk before this returns."""
        path = self._rows_path(run_dir, partial)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def drop_rows(self, run_dir: Path, partial: bool = False) -> None:
        """The run's rows (or its checkpoint) gone from here."""
        path = self._rows_path(run_dir, partial)
        path.unlink(missing_ok=True)
        _forget_rows(path)


class SqliteStore:
    """A project's outputs and rows in its one database (`_store`: data/project.sqlite), write-ahead logged: readers
    never block the writer, and a crash keeps every committed output. One committed insert per output and row;
    insertion order is the order they are read in. A run is its key, its directory under data/; `_store.rmtree` of
    that directory removes them with its files."""

    name = "sqlite"

    def __init__(self) -> None:
        self._lock = _store._LOCK  # the one connection's lock (_store)
        self._cache: dict[str, dict[str, str]] = {}
        self._rows: _Kept = _Kept()  # {(run key, partial): its rows text}
        self._version: int | None = None
        self._ready: set[int] = set()

    @staticmethod
    def key(run_dir: Path) -> str:
        """The run's directory under data/ (what `derived.from_dir` names). A run elsewhere (a scratch folder outside
        the project) is not the project's data: it is the disk's, as every path outside data/ is (`_store`)."""
        k = _store.rel(run_dir)
        if k is None:
            raise ValueError(
                f"{run_dir}: not under the project's data/, where every run is in the sqlite store"
            )
        return k

    def _db(self, create: bool) -> sqlite3.Connection | None:
        conn = _store.connect(create=create)
        if conn is not None and id(conn) not in self._ready:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS outputs (run TEXT NOT NULL, item_id TEXT NOT NULL, text TEXT NOT NULL,"
                " sha256 TEXT NOT NULL, PRIMARY KEY (run, item_id))"
            )
            # n = 0 is the marker that the rows were written (an empty predictions.jsonl is a run's rows too);
            # every line, its newline included, from n = 1 in order.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS rows (run TEXT NOT NULL, partial INTEGER NOT NULL, n INTEGER NOT NULL,"
                " item_id TEXT, row TEXT NOT NULL, PRIMARY KEY (run, partial, n))"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS rows_item ON rows (item_id, run) WHERE partial = 0")
            self._ready.add(id(conn))
        return conn

    def _fresh(self, conn: sqlite3.Connection) -> None:
        """Drop the cache when another connection (another process) has committed since it was filled."""
        v = conn.execute("PRAGMA data_version").fetchone()[0]
        if v != self._version:
            self._cache.clear()
            self._rows.clear()
            self._version = v

    def forget_under(self, key: str) -> None:
        """What is kept of the run at `key`, and of every run under it, forgotten (_store.rmtree deleted them)."""
        under = key + "/"
        for k in [k for k in self._cache if k == key or k.startswith(under)]:
            self._cache.pop(k, None)
        for k in [k for k in self._rows if k[0] == key or k[0].startswith(under)]:
            self._rows.pop(k, None)

    def _forget(self, k: str) -> None:
        self._cache.pop(k, None)
        self._rows.pop((k, False), None)
        self._rows.pop((k, True), None)

    def has(self, run_dir: Path) -> bool:
        """Whether the run itself holds outputs here."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.has(run_dir)
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
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.read(run_dir)
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

    def lines(self, run_dir: Path) -> list[dict[str, Any]]:
        """The run's own outputs as stored (item_id, text, sha256), in order."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.lines(run_dir)
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

    def row_runs(self) -> list[tuple[str, bool]]:
        """Every (run, partial) the database holds rows for."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return []
            got = conn.execute("SELECT DISTINCT run, partial FROM rows ORDER BY run, partial").fetchall()
            return [(r, bool(pt)) for r, pt in got]

    def add(self, run_dir: Path, item_id: str, text: str) -> None:
        """One item's output, on disk before this returns."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.add(run_dir, item_id, text)
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
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.write_all(run_dir, texts, order)
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
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.delete(run_dir)
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return
            k = self.key(run_dir)
            conn.execute("DELETE FROM outputs WHERE run = ?", (k,))
            self._cache.pop(k, None)

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """The run's rows exactly as written (the checkpoint's with `partial`); None when it has none."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.rows_text(run_dir, partial, errors)
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return None
            self._fresh(conn)
            ck = (self.key(run_dir), partial)
            if ck not in self._rows:
                got = conn.execute(
                    "SELECT row FROM rows WHERE run = ? AND partial = ? ORDER BY n", (ck[0], int(partial))
                ).fetchall()
                self._rows[ck] = "".join(r[0] for r in got) if got else None
            return self._rows[ck]

    def put_rows(self, run_dir: Path, text: str, partial: bool = False) -> None:
        """The run's rows replaced by `text` at once, atomically."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.put_rows(run_dir, text, partial)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            k = self.key(run_dir)
            lines = text.splitlines(keepends=True)
            vals = [(k, int(partial), 0, None, "")] + [
                (k, int(partial), n, _item_of(line), line) for n, line in enumerate(lines, 1)
            ]
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM rows WHERE run = ? AND partial = ?", (k, int(partial)))
                conn.executemany("INSERT INTO rows VALUES (?, ?, ?, ?, ?)", vals)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            self._rows.pop((k, partial), None)

    def append_row(self, run_dir: Path, line: str, partial: bool = True) -> None:
        """One row line (its newline included) added, on disk before this returns."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.append_row(run_dir, line, partial)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            k = self.key(run_dir)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("INSERT OR IGNORE INTO rows VALUES (?, ?, 0, NULL, '')", (k, int(partial)))
                conn.execute(
                    "INSERT INTO rows SELECT ?, ?, MAX(n) + 1, ?, ? FROM rows WHERE run = ? AND partial = ?",
                    (k, int(partial), _item_of(line), line, k, int(partial)),
                )
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            self._rows.pop((k, partial), None)

    def drop_rows(self, run_dir: Path, partial: bool = False) -> None:
        """The run's rows (or its checkpoint) gone from here."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.drop_rows(run_dir, partial)
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return
            k = self.key(run_dir)
            conn.execute("DELETE FROM rows WHERE run = ? AND partial = ?", (k, int(partial)))
            self._rows.pop((k, partial), None)

    def item_across(self, run_dirs: list[Path], item_id: str) -> dict[Path, str]:
        """{run_dir: its row line} for one item, in one query."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return {}
            keys = {self.key(d): Path(d) for d in run_dirs if _store.rel(d) is not None}  # the rest: files
            out: dict[Path, str] = {}
            for k, line in conn.execute(
                "SELECT run, row FROM rows WHERE item_id = ? AND partial = 0 ORDER BY run, n", (item_id,)
            ):
                if k in keys and keys[k] not in out:
                    out[keys[k]] = line
            return out

    def close(self) -> None:
        """The caches dropped (the connection is `_store`'s)."""
        with self._lock:
            self._cache.clear()
            self._rows.clear()
            self._version = None
            self._ready.clear()


_FILES = FileStore()
_SQLITE = SqliteStore()
_store.ON_REMOVE.append(_SQLITE.forget_under)


def store_named(name: str) -> Store:
    """The files store, or the sqlite store (the project's database)."""
    return _FILES if name == "files" else _SQLITE


def store() -> Store:
    """The project's store (`_common.store()`)."""
    return store_named(_common.store())


def reset() -> None:
    """Forget every cache and close the database (after a migration, or a test that changed the data directory)."""
    _CACHE.clear()
    _ROWS_CACHE.clear()
    _ROWS_INDEX.clear()
    _common._STORE_SEEN.clear()  # the store setting is read again (a test that rewrites config.yaml)
    _NAMES.clear()
    _SQLITE.close()
    _store.close()


def _runs_named(name: str) -> list[Path]:
    """Every run directory with this name under the project's runs trees (data/runs*, and EVAL_RUNS_DIR)."""
    if not _NAMES:
        roots = {*sorted(p for p in _store.glob(_common.DATA, "runs*") if _store.is_dir(p)), _common.RUNS}
        for root in roots:
            if not _store.is_dir(root):
                continue
            for depth in ("*", "*/*", "*/*/*"):
                for d in _store.glob(root, depth):
                    if _store.is_dir(d) and any(
                        _store.is_file(d / f) for f in ("metrics.json", "run.json", FILE)
                    ):
                        _NAMES.setdefault(d.name, []).append(d)
    return _NAMES.get(name, [])


def _derived_from(d: Path) -> str | None:
    """The run a derived run names in `derived.from`, None for a measured run (or an unreadable record)."""
    m = d / "metrics.json"
    try:
        frm = (
            (json.loads(_store.read_text(m, encoding="utf-8")).get("derived") or {}).get("from")
            if _store.is_file(m)
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
            (json.loads(_store.read_text(m, encoding="utf-8")).get("derived") or {}).get("from_dir")
            if _store.is_file(m)
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
    return _store.is_dir(Path(run_dir) / OLD_DIR)


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
        _store.mkdir(self.run_dir, parents=True, exist_ok=True)
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
    """A completed run: its outputs in dataset order, the row checkpoint gone (its rows are written)."""
    write_all(run_dir, texts, order)
    store().drop_rows(Path(run_dir), partial=True)


def count(run_dir: Path) -> int:
    """How many outputs a run has written so far."""
    return len(store().read(Path(run_dir)))


def lines(run_dir: Path) -> list[dict[str, Any]]:
    """The run's own outputs as written (item_id, text, sha256), for a release or a check that needs the sha256."""
    return store().lines(Path(run_dir))


def row_line(row: dict[str, Any]) -> str:
    """A row as a line of a run's rows: JSON, keys sorted, its newline."""
    return json.dumps(row, sort_keys=True) + "\n"


def rows_text(run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
    """A run's rows exactly as written (with `partial`, its checkpoint's); None when it has none. Bytes that are not
    UTF-8 raise UnicodeDecodeError unless `errors` is `replace` (a page that shows a run may)."""
    return store().rows_text(Path(run_dir), partial, errors)


def has_rows(run_dir: Path) -> bool:
    """Whether a run has its rows (a finished pass, or a derived run's)."""
    return rows_text(run_dir) is not None


def write_rows(run_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
    """A run's rows, all at once, atomically."""
    store().put_rows(Path(run_dir), "".join(row_line(r) for r in rows))


def append_partial(run_dir: Path, row: dict[str, Any]) -> None:
    """One row added to the run's checkpoint, on disk before the next item."""
    store().append_row(Path(run_dir), row_line(row), partial=True)


def item_across(run_dirs: Iterable[Path], item_id: str) -> dict[Path, dict[str, Any]]:
    """{run_dir: its row for this item} over many runs: one query in the sqlite store, each run's rows read in the
    files store. A run without a row for the item is left out."""
    dirs = [Path(d) for d in run_dirs]
    st = store()
    lines: dict[Path, str] = {}
    if isinstance(st, SqliteStore):
        lines = st.item_across(dirs, item_id)
        dirs = [d for d in dirs if _store.rel(d) is None]  # outside data/: the disk's
    if dirs:
        for d in dirs:
            text = _FILES.rows_text(d) or ""
            hit = _ROWS_INDEX.get(str(d))
            if hit is None or hit[0] is not text:
                index: dict[str, str] = {}
                for line in text.splitlines():
                    i = _item_of(line)
                    if i is not None:
                        index.setdefault(i, line)
                hit = _ROWS_INDEX[str(d)] = (text, index)
            if item_id in hit[1]:
                lines[d] = hit[1][item_id]
    out: dict[Path, dict[str, Any]] = {}
    for d, line in lines.items():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out[d] = row
    return out
