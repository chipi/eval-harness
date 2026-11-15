"""A run's outputs and rows, read and written only here (RFC-024), in the project's store (RFC-025).

The files store keeps one file per run, `outputs.jsonl`:

    {"item_id": "t00042", "text": "...the output, exactly...", "sha256": "<sha256 of the text's UTF-8 bytes>"}

The sqlite store (`store: sqlite` in config.yaml, or EVAL_STORE=sqlite) keeps the same rows in the project's one
database (`_store`, data/project.sqlite), table `outputs (run, item_id, text, sha256)`, `run` being the run's
directory under data/. Either way:

A measured run adds an output per item as it is produced (`writer`), synced or committed before the next, so a stopped
run keeps every finished output and `--resume` reads them back; a torn last line (a kill mid-append) is not an output,
so that item is called again. `finish` rewrites them in dataset order when the run completes. A score (RFC-032 step 4:
`runs/<id>/scores/<key>/`) writes no outputs of its own: `output()` and `outputs()` of a score read its run's. Every
module reads outputs through this one: a test fails on an `outputs/` path built anywhere else.

A score's rows (one JSON object per item: its scores, cost, tokens, `_meta`) are its `predictions.jsonl` in the files
store and table `rows (run, partial, n, item_id, row)` in the sqlite one, keyed by the score's directory. `rows` reads
them as parsed dicts and `put_rows` writes dicts (RFC-033 step c): the stores keep canonical lines (`row_line`), and
`rows_text` is those lines derived from the dicts. A line that is not a JSON object with an `item_id` is refused at
write (`invalid-file`), in both stores; the files store's reader stays tolerant of a hand-edited file and `malformed`
names its lines. `partial` rows are the pass's checkpoint (`rows.partial.jsonl`, keyed by the run's directory), kept
verbatim text, a torn last line allowed: appended per item (`append_partial`) and dropped by `finish`.
`_runs.item_rows` and `write_rows` are how every module reads and writes them; a test fails on a `predictions.jsonl`
path built anywhere else. A row is written as `model.results.prepare` leaves it (RFC-033): its usage slimmed, the run
settings its run's run.json `call` holds taken off. The dicts `rows` returns are the cache's own, shared: a caller that
changes a row copies it first.
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
from evaluation_harness.model import results as _results

FILE = "outputs.jsonl"
#: The folder of <item>.txt a run had before 0.8.0 (`evh migrate` moves it into FILE).
OLD_DIR = "outputs"
#: The checkpoint of rows a pass appends as it goes (a crashed run has no predictions.jsonl yet); deleted by finish().
ROWS = "rows.partial.jsonl"
#: A run's rows in the files store.
PREDICTIONS = "predictions.jsonl"
SCHEMA_VERSION = "1"
_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
#: How much rows a process keeps read, per cache: the runs read last, by what they hold (a run's rows are a few
#: kilobytes or a few megabytes of text, and their parsed dicts weigh DICT_FACTOR times that). Unbounded, a warm
#: catalog-serve kept every committed run's rows (94,650 of them) after reading each once; bounded, its RSS and cached
#: answers are the base's again (budget-check, RFC-033 step c).
ROWS_KEPT_BYTES = 8_000_000
#: What the parsed dicts of a rows text weigh, in times its length: measured with tracemalloc over a seventh of this
#: repository's score sets (13,295 rows, 9.1 MB of text, 44.0 MB of dicts: 4.85x), 2026-11-15.
DICT_FACTOR = 5


class _Held:
    """A run's rows as the cache keeps them: the parsed dicts and the text derived from them, together (so what is
    indexed by one stays valid for the other). `rows` is None for a checkpoint, which is only text, kept verbatim."""

    __slots__ = ("_text", "lossy", "rows", "size", "stamp")

    def __init__(
        self,
        rows: list[dict[str, Any]] | None,
        size: int,
        stamp: Any = None,
        text: str | None = None,
        lossy: bool = False,
    ) -> None:
        self.rows = rows
        self.size = size  # the length of the text the rows were parsed from
        self.stamp = stamp
        self._text = text
        self.lossy = lossy  # read past bytes that are not UTF-8 or lines that are no row: only a tolerant read may use it

    def text(self) -> str:
        """The rows' canonical text (a checkpoint's: verbatim), made once."""
        if self._text is None:
            assert self.rows is not None
            self._text = "".join(row_line(r) for r in self.rows)
        return self._text

    def weight(self) -> int:
        """What this holds, in bytes: the dicts (their text's size times DICT_FACTOR), and the text if made."""
        w = self.size * DICT_FACTOR if self.rows is not None else 0
        if self._text is not None:
            w += len(self._text)
        return w


class _Index:
    """One run's item index: the line of each item's first row, valid while the file is as it was (its stamp)."""

    __slots__ = ("lines", "size", "stamp")

    def __init__(self, lines: dict[str, str], size: int, stamp: Any) -> None:
        self.lines = lines
        self.size = size  # the length of the text the lines were cut from: they copy it once
        self.stamp = stamp

    def weight(self) -> int:
        return self.size


class _Kept(OrderedDict):
    """A dict that keeps the entries read or written last, up to `ROWS_KEPT_BYTES` of what they hold (`_Held.weight`)."""

    def __init__(self) -> None:
        super().__init__()
        self.bytes = 0
        self._w: dict[Any, int] = {}

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return default

    def _evict(self) -> None:
        while self.bytes > ROWS_KEPT_BYTES and len(self) > 1:
            k, _old = self.popitem(last=False)
            self.bytes -= self._w.pop(k)

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self:
            self.bytes -= self._w.pop(key)
        super().__setitem__(key, value)
        self._w[key] = value.weight()
        self.bytes += self._w[key]
        self.move_to_end(key)
        self._evict()

    def reweigh(self, key: Any) -> None:
        """The entry at `key` grew (its text or index was made after it was kept)."""
        if key in self:
            w = self[key].weight()
            self.bytes += w - self._w[key]
            self._w[key] = w
            self._evict()

    def __delitem__(self, key: Any) -> None:
        self.bytes -= self._w.pop(key)
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
        self._w.clear()


_ROWS_CACHE: _Kept = (
    _Kept()
)  # {rows path: its _Held, valid while the file's (mtime_ns, size) is the held stamp}
#: {rows path: its _Index}: apart from the rows, which weigh DICT_FACTOR times their text and so go sooner than an index
#: (one item asked of every run of a comparison, item after item, must not read every run again each time: 29 runs, 200
#: items, 14 s against 3.5 s with the index among the rows at 8 MB).
_ROWS_INDEX: _Kept = _Kept()


def sha256(text: str) -> str:
    """The sha256 of an output's UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line(item_id: str, text: str) -> str:
    return json.dumps({"item_id": item_id, "text": text, "sha256": sha256(text)}, ensure_ascii=False)


def _forget_rows(path: Path) -> None:
    _ROWS_CACHE.pop(str(path), None)
    _ROWS_INDEX.pop(str(path), None)


def _item_of(line: str) -> str | None:
    """A row line's item id, None when it has none (or is not JSON)."""
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return str(row["item_id"]) if isinstance(row, dict) and row.get("item_id") is not None else None


def is_row(row: Any) -> bool:
    """Whether `row` is what a score set's line is: a JSON object with an `item_id`."""
    return isinstance(row, dict) and isinstance(row.get("item_id"), str)


def parse_rows(text: str, where: str, strict: bool = True) -> tuple[list[dict[str, Any]], int]:
    """(the JSON objects of a rows text, how many lines it skipped). A line that is not JSON raises ValueError naming
    `where` and the line unless `strict` is False, when it is skipped with the lines that are JSON but no object (a
    torn last line, a hand-edited file: a statistical test must not quietly drop an item, a page that shows a run may)."""
    out: list[dict[str, Any]] = []
    skipped = 0
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            if strict:
                raise ValueError(f"{where}:{n}: not JSON ({exc})") from exc
            skipped += 1
            continue
        if isinstance(row, dict):
            out.append(row)
        else:
            skipped += 1
    return out, skipped


def _lines_of(run_dir: Path, rows: Iterable[dict[str, Any]]) -> list[str]:
    """The canonical lines of a score set's rows; a row that is no JSON object with an `item_id` refused."""
    out = []
    for n, row in enumerate(rows, 1):
        if not is_row(row):
            _common.die(
                f"{Path(run_dir) / PREDICTIONS}: row {n} is not a JSON object with an item_id; a score set's rows are "
                "objects, one per item, each naming its item",
                "invalid-file",
            )
        out.append(row_line(row))
    return out


_ABSENT = _Held(None, 0)  # kept for a run that has no rows: asked again, the database is not


def _rows_of(held: _Held, where: Path) -> list[dict[str, Any]]:
    """The dicts of a held entry: a score's rows (a list of its own, the dicts shared), a checkpoint's parsed, a torn
    line skipped."""
    if held.rows is None:
        return parse_rows(held.text(), str(where), strict=False)[0]
    return list(held.rows)


def _text_of(cache: _Kept, key: Any, held: _Held) -> str:
    """The text of a held entry, kept with it from now on (and weighed)."""
    made = held._text is None
    text = held.text()
    if made:
        cache.reweigh(key)
    return text


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

    def rows(
        self, run_dir: Path, partial: bool = False, errors: str = "strict"
    ) -> list[dict[str, Any]] | None:
        """A score's rows as parsed dicts, in order (the checkpoint's, a torn line skipped, with `partial`); None when it
        has none. A line that is not JSON raises ValueError, bytes that are not UTF-8 UnicodeDecodeError, unless
        `errors` says `replace`: then they are skipped. The dicts are shared: copy a row before changing it."""
        ...

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """A score's rows as canonical lines, derived from the dicts (the checkpoint's: verbatim, with `partial`);
        None when it has none."""
        ...

    def has_rows(self, run_dir: Path) -> bool:
        """Whether the run has its rows (not the checkpoint's), without reading them."""
        ...

    def stored_text(self, run_dir: Path, errors: str = "strict") -> str | None:
        """A score's rows as the store holds them, line by line as they were written: what a migration or a check of
        the stored data reads; None when it has none."""
        ...

    def put_rows(self, run_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
        """A score's rows replaced by `rows` at once, atomically, as canonical lines. A row that is not a JSON object
        with an `item_id` is refused (`invalid-file`), writing nothing."""
        ...

    def put_partial(self, run_dir: Path, text: str) -> None:
        """The run's checkpoint replaced by `text`, verbatim, at once, atomically."""
        ...

    def append_row(self, run_dir: Path, line: str) -> None:
        """One line (its newline included) added to the run's checkpoint, on disk before this returns. Verbatim: the
        checkpoint is the one place a torn last line is allowed."""
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

    def _held(self, run_dir: Path, partial: bool, errors: str) -> _Held | None:
        path = self._rows_path(run_dir, partial)
        try:
            st = path.stat()
        except OSError:
            return None
        key, stamp = str(path), (st.st_mtime_ns, st.st_size)
        hit = _ROWS_CACHE.get(key)
        if hit is not None and hit.stamp == stamp and (errors != "strict" or not hit.lossy):
            return hit
        raw = path.read_bytes()
        lossy = False
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            if errors == "strict":
                raise
            text, lossy = raw.decode("utf-8", errors=errors), True
        if partial:
            held = _Held(None, len(text), stamp, text=text, lossy=lossy)
        else:
            rows, skipped = parse_rows(text, str(path), strict=errors == "strict")
            held = _Held(rows, len(text), stamp, lossy=lossy or skipped > 0)
        _ROWS_CACHE[key] = held
        return held

    def rows(
        self, run_dir: Path, partial: bool = False, errors: str = "strict"
    ) -> list[dict[str, Any]] | None:
        """A score's rows as parsed dicts, in order (the checkpoint's, a torn line skipped, with `partial`); None when it
        has none. A line that is not JSON raises ValueError, bytes that are not UTF-8 UnicodeDecodeError, unless
        `errors` says `replace`: then they are skipped. The dicts are shared: copy a row before changing it."""
        held = self._held(run_dir, partial, errors)
        return None if held is None else _rows_of(held, self._rows_path(run_dir, partial))

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """A score's rows as canonical lines, derived from the dicts (the checkpoint's: verbatim, with `partial`);
        None when it has none."""
        held = self._held(run_dir, partial, errors)
        return None if held is None else _text_of(_ROWS_CACHE, str(self._rows_path(run_dir, partial)), held)

    def has_rows(self, run_dir: Path) -> bool:
        """Whether the run has its rows (not the checkpoint's), without reading them."""
        return self._rows_path(run_dir, False).is_file()

    def _index(self, run_dir: Path) -> _Index | None:
        """The line of each item's first row, made once per state of the file (a hand-edited file's lines that are no
        row are left out); None when the run has no rows."""
        path = self._rows_path(run_dir, False)
        try:
            st = path.stat()
        except OSError:
            return None
        key, stamp = str(path), (st.st_mtime_ns, st.st_size)
        hit = _ROWS_INDEX.get(key)
        if hit is None or hit.stamp != stamp:
            text = path.read_bytes().decode("utf-8", errors="replace")
            lines: dict[str, str] = {}
            for line in text.splitlines():
                i = _item_of(line)
                if i is not None:
                    lines.setdefault(i, line)
            hit = _ROWS_INDEX[key] = _Index(lines, len(text), stamp)
        return hit

    def stored_text(self, run_dir: Path, errors: str = "strict") -> str | None:
        """A score's rows as the file holds them, line by line as they were written; None when it has none."""
        try:
            return self._rows_path(run_dir, False).read_bytes().decode("utf-8", errors=errors)
        except OSError:
            return None

    def put_rows(self, run_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
        """A score's rows replaced by `rows` at once, atomically, as canonical lines. A row that is not a JSON object
        with an `item_id` is refused (`invalid-file`), writing nothing."""
        path = self._rows_path(run_dir, False)
        _common.write_text_atomic(path, "".join(_lines_of(run_dir, rows)))
        _forget_rows(path)

    def put_partial(self, run_dir: Path, text: str) -> None:
        """The run's checkpoint replaced by `text`, verbatim, at once, atomically."""
        path = self._rows_path(run_dir, True)
        _common.write_text_atomic(path, text)
        _forget_rows(path)

    def append_row(self, run_dir: Path, line: str) -> None:
        """One line (its newline included) added to the run's checkpoint, on disk before this returns. Verbatim: the
        checkpoint is the one place a torn last line is allowed."""
        path = self._rows_path(run_dir, True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        _forget_rows(path)

    def drop_rows(self, run_dir: Path, partial: bool = False) -> None:
        """The run's rows (or its checkpoint) gone from here."""
        path = self._rows_path(run_dir, partial)
        path.unlink(missing_ok=True)
        _forget_rows(path)


def ensure_tables(conn: sqlite3.Connection) -> None:
    """The per-item tables in the project's database (a release is sealed with them, so a read-only open finds them)."""
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
        self._ready: dict[int, bool] = {}  # {id(connection): whether it has the tables}

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
            # Read-only, nothing is created: a release made without runs has no such tables, and no outputs.
            if _store.readonly():
                have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                self._ready[id(conn)] = {"outputs", "rows"} <= have
            else:
                ensure_tables(conn)
                self._ready[id(conn)] = True
        return conn if conn is not None and self._ready[id(conn)] else None

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
            _store.wrote()

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
                conn.execute("COMMIT")
            except BaseException:
                if (
                    conn.in_transaction
                ):  # a failed COMMIT too: never leave the shared connection in a transaction
                    conn.execute("ROLLBACK")
                raise
            self._cache.pop(k, None)
            _store.wrote()

    def delete(self, run_dir: Path) -> None:
        """The run's outputs gone from here."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.delete(run_dir)
        _store.require_writable()
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return
            k = self.key(run_dir)
            conn.execute("DELETE FROM outputs WHERE run = ?", (k,))
            self._cache.pop(k, None)
            _store.wrote()

    def _held(self, run_dir: Path, partial: bool, errors: str) -> _Held | None:
        """The run's rows as kept, read from the database when not (the caller holds the lock and has made it fresh)."""
        conn = self._db(create=False)
        if conn is None:
            return None
        self._fresh(conn)
        ck = (self.key(run_dir), partial)
        hit = self._rows.get(ck)
        if hit is None or (errors == "strict" and hit.lossy):
            got = conn.execute(
                "SELECT row FROM rows WHERE run = ? AND partial = ? ORDER BY n", (ck[0], int(partial))
            ).fetchall()
            if not got:
                hit = _ABSENT
            else:
                text = "".join(r[0] for r in got)
                if partial:
                    hit = _Held(None, len(text), text=text)
                else:
                    where = str(Path(run_dir) / PREDICTIONS)
                    rows, skipped = parse_rows(text, where, strict=errors == "strict")
                    hit = _Held(rows, len(text), lossy=skipped > 0)
            self._rows[ck] = hit
        return None if hit is _ABSENT else hit

    def rows(
        self, run_dir: Path, partial: bool = False, errors: str = "strict"
    ) -> list[dict[str, Any]] | None:
        """A score's rows as parsed dicts, in order (the checkpoint's, a torn line skipped, with `partial`); None when it
        has none. A line that is not JSON raises ValueError unless `errors` says `replace`: then it is skipped. The
        dicts are shared: copy a row before changing it."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.rows(run_dir, partial, errors)
        with self._lock:
            held = self._held(run_dir, partial, errors)
            return (
                None if held is None else _rows_of(held, Path(run_dir) / (ROWS if partial else PREDICTIONS))
            )

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """A score's rows as canonical lines, derived from the dicts (the checkpoint's: verbatim, with `partial`);
        None when it has none."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.rows_text(run_dir, partial, errors)
        with self._lock:
            held = self._held(run_dir, partial, errors)
            return None if held is None else _text_of(self._rows, (self.key(run_dir), partial), held)

    def has_rows(self, run_dir: Path) -> bool:
        """Whether the run has its rows (not the checkpoint's), without reading them."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.has_rows(run_dir)
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return False
            self._fresh(conn)
            k = self.key(run_dir)
            hit = self._rows.get((k, False))
            if hit is not None:
                return hit is not _ABSENT
            return (
                conn.execute("SELECT 1 FROM rows WHERE run = ? AND partial = 0 LIMIT 1", (k,)).fetchone()
                is not None
            )

    def stored_text(self, run_dir: Path, errors: str = "strict") -> str | None:
        """A score's rows as the database holds them, line by line as they were written; None when it has none."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.stored_text(run_dir, errors)
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return None
            got = conn.execute(
                "SELECT row FROM rows WHERE run = ? AND partial = 0 ORDER BY n", (self.key(run_dir),)
            ).fetchall()
            return "".join(r[0] for r in got) if got else None

    def _replace(self, run_dir: Path, partial: bool, vals: list[tuple[Any, ...]]) -> None:
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            k = self.key(run_dir)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM rows WHERE run = ? AND partial = ?", (k, int(partial)))
                conn.executemany("INSERT INTO rows VALUES (?, ?, ?, ?, ?)", vals)
                conn.execute("COMMIT")
            except BaseException:
                if (
                    conn.in_transaction
                ):  # a failed COMMIT too: never leave the shared connection in a transaction
                    conn.execute("ROLLBACK")
                raise
            self._rows.pop((k, partial), None)
            _store.wrote()

    def put_rows(self, run_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
        """A score's rows replaced by `rows` at once, atomically, as canonical lines. A row that is not a JSON object
        with an `item_id` is refused (`invalid-file`), writing nothing."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.put_rows(run_dir, rows)
        rows = list(rows)
        lines = _lines_of(run_dir, rows)
        k = self.key(run_dir)
        self._replace(
            run_dir,
            False,
            [(k, 0, 0, None, "")]
            + [(k, 0, n, r["item_id"], ln) for n, (r, ln) in enumerate(zip(rows, lines, strict=True), 1)],
        )

    def put_partial(self, run_dir: Path, text: str) -> None:
        """The run's checkpoint replaced by `text`, verbatim, at once, atomically."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.put_partial(run_dir, text)
        k = self.key(run_dir)
        self._replace(
            run_dir,
            True,
            [(k, 1, 0, None, "")]
            + [(k, 1, n, _item_of(ln), ln) for n, ln in enumerate(text.splitlines(keepends=True), 1)],
        )

    def append_row(self, run_dir: Path, line: str) -> None:
        """One line (its newline included) added to the run's checkpoint, on disk before this returns. Verbatim: the
        checkpoint is the one place a torn last line is allowed."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.append_row(run_dir, line)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            k = self.key(run_dir)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("INSERT OR IGNORE INTO rows VALUES (?, 1, 0, NULL, '')", (k,))
                conn.execute(
                    "INSERT INTO rows SELECT ?, 1, MAX(n) + 1, ?, ? FROM rows WHERE run = ? AND partial = 1",
                    (k, _item_of(line), line, k),
                )
                conn.execute("COMMIT")
            except BaseException:
                if (
                    conn.in_transaction
                ):  # a failed COMMIT too: never leave the shared connection in a transaction
                    conn.execute("ROLLBACK")
                raise
            self._rows.pop((k, True), None)
            _store.wrote()

    def drop_rows(self, run_dir: Path, partial: bool = False) -> None:
        """The run's rows (or its checkpoint) gone from here."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.drop_rows(run_dir, partial)
        _store.require_writable()
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return
            k = self.key(run_dir)
            conn.execute("DELETE FROM rows WHERE run = ? AND partial = ?", (k, int(partial)))
            self._rows.pop((k, partial), None)
            _store.wrote()

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
    _SQLITE.close()
    _store.close()


def own(run_dir: Path) -> bool:
    """Whether the run itself holds outputs in the project's store (not through a source)."""
    return store().has(Path(run_dir))


def source(run_dir: Path) -> Path | None:
    """The run directory that holds these outputs: a score's run's, a run's own; None when it has none."""
    d = Path(run_dir)
    if d.parent.name == "scores":  # runs/<id>/scores/<key> (model/runs)
        d = d.parent.parent
    return d if store().has(d) else None


def outputs(run_dir: Path) -> dict[str, str]:
    """{item_id: text} of a run (its source's for a derived run); {} when it has none."""
    src = source(run_dir)
    return dict(store().read(src)) if src else {}


def output(run_dir: Path, item_id: str) -> str | None:
    """One item's output, or None when the run has none for it."""
    src = source(run_dir)
    return store().read(src).get(item_id) if src else None


def old_layout(run_dir: Path) -> bool:
    """Whether a run is still in the layout before 0.8.0 (an `outputs/` folder of <item>.txt): `evh migrate` moves it."""
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


def rows(run_dir: Path, partial: bool = False, errors: str = "strict") -> list[dict[str, Any]] | None:
    """A score's rows as parsed dicts, in order (with `partial`, the checkpoint's, a torn line skipped); None when it has
    none. A line that is not JSON raises ValueError naming the file and the line, bytes that are not UTF-8
    UnicodeDecodeError, unless `errors` is `replace` (a page that shows a run may): then they are skipped. The dicts
    are the cache's own: copy a row before changing it."""
    return store().rows(Path(run_dir), partial, errors)


def rows_text(run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
    """A score's rows as canonical lines (`row_line` of each dict `rows` gives; the checkpoint's, with `partial`:
    verbatim); None when it has none. For a caller that wants text: a cache key, a comparison with what a write
    would leave (`rows_as_written`)."""
    return store().rows_text(Path(run_dir), partial, errors)


def malformed(run_dir: Path) -> list[int]:
    """The numbers of the lines of a score's stored rows that are not a JSON object with an `item_id`: what a
    hand-edited file in the files store holds (a write refuses them, the reader skips them)."""
    text = store().stored_text(Path(run_dir), errors="replace")
    out = []
    for n, line in enumerate((text or "").splitlines(), 1):
        if not line.strip():
            continue
        try:
            ok = is_row(json.loads(line))
        except ValueError:
            ok = False
        if not ok:
            out.append(n)
    return out


def has_rows(run_dir: Path) -> bool:
    """Whether a run has its rows (a finished pass, or a derived run's)."""
    return store().has_rows(Path(run_dir))


def _call_of(score_dir: Path) -> dict[str, Any] | None:
    """The run settings of the run a score is of (run.json `call`); None for a directory that is no score's, or a run
    that holds none."""
    d = Path(score_dir)
    if d.parent.name != "scores":
        return None
    try:
        rec = json.loads(_store.read_text(d.parent.parent / "run.json", encoding="utf-8"))
    except (OSError, ValueError):
        return None
    call = rec.get("call") if isinstance(rec, dict) else None
    return call if isinstance(call, dict) else None


def prepared(score_dir: Path, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """`rows` as `write_rows` writes them in the score at `score_dir`: usage slimmed, the run's settings taken off."""
    call = _call_of(score_dir)
    return [
        _results.prepare(r, call) if isinstance(r, dict) else r for r in rows
    ]  # a non-row is the store's refusal


def rows_as_written(score_dir: Path, rows: Iterable[dict[str, Any]]) -> str:
    """The text `write_rows` writes for `rows` in the score at `score_dir`: what a caller compares with what is held."""
    return "".join(row_line(r) for r in prepared(score_dir, rows))


def write_rows(run_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
    """A score's rows, all at once, atomically."""
    store().put_rows(Path(run_dir), prepared(run_dir, rows))


def append_partial(run_dir: Path, row: dict[str, Any]) -> None:
    """One row added to the run's checkpoint, on disk before the next item. Its usage is slimmed; the run settings stay,
    the run's `call` not being known until the pass ends."""
    store().append_row(Path(run_dir), row_line(_results.slim_row(row)))


def item_across(run_dirs: Iterable[Path], item_id: str) -> dict[Path, dict[str, Any]]:
    """{run_dir: its row for this item} over many runs: one query in the sqlite store, each run's rows indexed once in
    the files store (the index kept apart from the rows: `_ROWS_INDEX`). A run without a row for the item is left out."""
    dirs = [Path(d) for d in run_dirs]
    st = store()
    out: dict[Path, dict[str, Any]] = {}
    if isinstance(st, SqliteStore):
        for d, line in st.item_across(dirs, item_id).items():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out[d] = row
        dirs = [d for d in dirs if _store.rel(d) is None]  # outside data/: the disk's
    for d in dirs:
        index = _FILES._index(d)
        found = None if index is None else index.lines.get(item_id)
        if found is not None:
            try:
                row = json.loads(found)
            except ValueError:
                continue
            if isinstance(row, dict):
                out[d] = row
    return out
