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
store, canonical lines (`row_line`); in the sqlite one they are a model of tables (RFC-033 step d), keyed by the score
set's directory: `score_sets`, `score_rows` (the item, its `_meta` and `_extra`, and the fields that are not numbers),
`score_values` (every numeric field, one row each, its metric named in `metrics`) and `call_facts` (what a run's call to
one item was, held once for every score set of the run). `rows` reads them as parsed dicts and `put_rows` writes dicts: a
row read back is the row written (the same dict, keys sorted), and `rows_text` is its canonical lines derived from the
dicts, so both stores give one text. A line that is not a JSON object with an `item_id` is refused at write
(`invalid-file`), in both stores; the files store's reader stays tolerant of a hand-edited file and `malformed` names its
lines. `partial` rows are the pass's checkpoint (`rows.partial.jsonl`, in sqlite table `rows_partial`, keyed by the
run's directory), kept verbatim text, a torn last line allowed: appended per item (`append_partial`) and dropped by
`finish`. `_runs.item_rows` and `write_rows` are how every module reads and writes them; a test fails on a
`predictions.jsonl` path built anywhere else. A row is written as `model.results.prepare` leaves it (RFC-033): its usage
slimmed, the run settings its run's run.json `call` holds taken off. The dicts `rows` returns are the cache's own,
shared: a caller that changes a row copies it first (`EVH_FREEZE_ROWS=1` makes a test fail on one that does not).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import sqlite3
from collections import OrderedDict
from collections.abc import Iterable
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from typing import Any, Protocol

from evaluation_harness import _common, _store
from evaluation_harness._common import jsonl_lines
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
#: answers are the base's again (budget-check, RFC-033 step c). Measured again on the tables (step d), at 2, 8, 32 and
#: 128 MB, `make budget-check`'s peak was 95, 101, 125 and 138 MB on files and 102, 99, 109 and 110 on sqlite, and
#: neither the cold answers (0.26-0.47 s) nor the cached ones (0.4-0.7 ms) moved: a command or a request reads a set once
#: (711 reads of 711 sets in `arm-list`), so a larger bound only holds memory. 8 MB keeps what one command reads twice.
ROWS_KEPT_BYTES = 8_000_000
#: What the parsed dicts of a rows text weigh, in times its length: measured with tracemalloc over a seventh of this
#: repository's score sets (13,295 rows, 9.1 MB of text, 44.0 MB of dicts: 4.85x), 2026-11-15. The sqlite store has no
#: text to measure: its estimate of one is 0.96x the real (`read_set`), and the dicts it builds weigh 3.84x the estimate
#: with `_meta` and `_extra`, 1.97x without (`meta=False`), measured the same way.
DICT_FACTOR = 5
SQLITE_DICT_FACTOR = 4
SQLITE_LIGHT_FACTOR = 2


#: Set to `1` (the suite does: tests/self_test.py, tools/store_matrix.py), every row the cache holds is frozen: a change
#: to it raises a TypeError where it is made, so a view or a command that changes a row it shares with every other
#: reader fails its test, at its own line. A copy of a frozen row (`copy.deepcopy`, `dict(row)`, `{**row}`) is a plain
#: dict. The one a caller finds out about late, in a server that lives on, is the one this catches (RFC-033 step d).
FREEZE_ENV = "EVH_FREEZE_ROWS"
_FROZEN = f"a row the cache shares was changed ({FREEZE_ENV}=1): copy it (copy.deepcopy) before changing it"


def _no(self: Any, *args: Any, **kwargs: Any) -> Any:
    raise TypeError(_FROZEN)


class _FrozenDict(dict):
    """A cached row, or a dict in one, as `FREEZE_ENV` keeps it."""

    __slots__ = ()
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _no

    def __copy__(self) -> dict[Any, Any]:
        return dict(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[Any, Any]:
        return {k: copy.deepcopy(v, memo) for k, v in self.items()}

    def __reduce__(self) -> tuple[Any, ...]:
        return dict, (dict(self),)


class _FrozenList(list):
    """A list in a cached row, as `FREEZE_ENV` keeps it."""

    __slots__ = ()
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _no
    append = extend = insert = remove = pop = clear = sort = reverse = _no

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        return [copy.deepcopy(v, memo) for v in self]

    def __reduce__(self) -> tuple[Any, ...]:
        return list, (list(self),)


def _freeze(value: Any) -> Any:
    """`value` (a row, a dict or a list in one) as frozen dicts and lists all the way down."""
    if isinstance(value, dict):
        return _FrozenDict({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return _FrozenList([_freeze(v) for v in value])
    return value


class _Held:
    """A run's rows as the cache keeps them: the parsed dicts and the text derived from them, together (so what is
    indexed by one stays valid for the other). `rows` is None for a checkpoint, which is only text, kept verbatim."""

    __slots__ = ("_text", "factor", "light", "lossy", "rows", "size", "stamp")

    def __init__(
        self,
        rows: list[dict[str, Any]] | None,
        size: int,
        stamp: Any = None,
        text: str | None = None,
        lossy: bool = False,
        light: bool = False,
        factor: int | None = None,
    ) -> None:
        self.rows = (
            [_freeze(r) for r in rows] if rows is not None and os.environ.get(FREEZE_ENV) == "1" else rows
        )
        self.size = size  # the length of the text the rows were parsed from (or, in sqlite, would make)
        self.stamp = stamp
        self._text = text
        self.lossy = lossy  # read past bytes that are not UTF-8 or lines that are no row: only a tolerant read may use it
        self.light = light  # the rows lack `_meta` and `_extra` (`read_set(meta=False)`): only a read that asked so may use it
        self.factor = factor  # what the dicts weigh in times `size`: DICT_FACTOR, or the sqlite store's own

    def text(self) -> str:
        """The rows' canonical text (a checkpoint's: verbatim), made once."""
        if self._text is None:
            assert self.rows is not None
            self._text = "".join(row_line(r) for r in self.rows)
        return self._text

    def weight(self) -> int:
        """What this holds, in bytes: the dicts (their text's size times their factor), and the text if made."""
        w = self.size * (self.factor or DICT_FACTOR) if self.rows is not None else 0
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
    for n, line in enumerate(jsonl_lines(text), 1):
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
    rows = list(rows)
    _check_rows(run_dir, rows)
    return [row_line(r) for r in rows]


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


#: A score set's id is the next free one after the highest (a release's are its position in the order `data-migrate`
#: writes them, the run's start time then the key); a row's id is `score_set * ROWS_PER_SET + n`, under 2^63.
SET_BITS = 43
ROW_BITS = 20
ROWS_PER_SET = 1 << ROW_BITS
#: What a call's facts are (RFC-033): `CALL_META` less the run's own settings. `call_facts` holds them once per run and
#: item; a row whose own are equal to the held ones keeps them out of its `meta`.
CALL_FACTS = tuple(k for k in _results.CALL_META if k not in _results.RUN_SETTINGS)
_KEPT_OUT = ("item_id", "_meta", "_extra")
INT64 = 1 << 63


def _canon(value: Any) -> str:
    """The text the tables keep a JSON value as: keys sorted, as a row's line is."""
    return json.dumps(value, sort_keys=True)


def _is_value(v: Any) -> bool:
    """Whether a top-level field is kept as a number in `score_values`: an int within int64 or a finite float, never a
    bool. Everything else (a bool, None, NaN, an infinity, a larger integer, text, a list) is JSON in `rest`."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return -INT64 <= v < INT64
    return isinstance(v, float) and math.isfinite(v)


def _run_of(key: str) -> str | None:
    m = _store.SCORE_SET.fullmatch(key)
    return m.group(1) if m else None


def _check_rows(run_dir: Path, rows: list[Any]) -> None:
    """A score set's rows refused (`invalid-file`) when one is no JSON object with an `item_id`, or there are more than
    a row id can number."""
    for n, row in enumerate(rows, 1):
        if not is_row(row):
            _common.die(
                f"{Path(run_dir) / PREDICTIONS}: row {n} is not a JSON object with an item_id; a score set's rows are "
                "objects, one per item, each naming its item",
                "invalid-file",
            )
    if len(rows) > ROWS_PER_SET:
        _common.die(
            f"{Path(run_dir) / PREDICTIONS}: {len(rows):,} rows; a score set holds at most {ROWS_PER_SET:,}",
            "invalid-file",
        )


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:  # a failed COMMIT too: never leave the shared connection in a transaction
        conn.execute("ROLLBACK")


def _set_id(conn: sqlite3.Connection, key: str) -> int | None:
    got = conn.execute("SELECT id FROM score_sets WHERE key = ?", (key,)).fetchone()
    return None if got is None else int(got[0])


def _add_set(conn: sqlite3.Connection, key: str) -> int:
    """A new score set, last: the highest id plus one, so a score set added later lands after every other in the tables.
    A database whose highest id has no room for a row's 2^20 numbers above it (one built with hashed ids by an
    earlier build) gives the lowest free id."""
    sid = (conn.execute("SELECT MAX(id) FROM score_sets").fetchone()[0] or 0) + 1
    if sid >= 1 << SET_BITS:
        sid = 1
        while conn.execute("SELECT 1 FROM score_sets WHERE id = ?", (sid,)).fetchone():
            sid += 1
    conn.execute("INSERT INTO score_sets VALUES (?, ?)", (sid, key))
    return sid


def _forget_set(conn: sqlite3.Connection, sid: int) -> None:
    """A score set's rows and values deleted (its id and key stay)."""
    lo = sid << ROW_BITS
    conn.execute("DELETE FROM score_values WHERE row BETWEEN ? AND ?", (lo, lo + ROWS_PER_SET - 1))
    conn.execute("DELETE FROM score_rows WHERE id BETWEEN ? AND ?", (lo, lo + ROWS_PER_SET - 1))


def drop_call_facts(conn: sqlite3.Connection, run: str) -> None:
    """A run's call facts gone once no score set of it is left."""
    conn.execute(
        "DELETE FROM call_facts WHERE run = ? AND NOT EXISTS (SELECT 1 FROM score_sets WHERE key >= ? AND key < ?)",
        (run, run + "/scores/", run + "/scores0"),
    )


def write_set(conn: sqlite3.Connection, key: str, rows: list[dict[str, Any]]) -> None:
    """A score set's rows replaced by `rows`, in the transaction the caller holds (RFC-033). Per row: `item_id`; every
    numeric field in `score_values` (its metric's id from `metrics`, names added in sorted order); `_meta` apart from
    the call facts the run already holds for this item in `meta` (`facts` says they are there); `_extra`; and the rest
    as JSON. Call facts are inserted by the first row of a run's item that has some; a row's own differing facts keep
    its whole `_meta` in `meta`."""
    sid = _set_id(conn, key)
    if sid is None:
        sid = _add_set(conn, key)
    else:
        _forget_set(conn, sid)
    base = sid << ROW_BITS
    run = _run_of(key)
    held: dict[str, str] = (
        dict(conn.execute("SELECT item_id, meta FROM call_facts WHERE run = ?", (run,))) if run else {}
    )
    split: list[tuple[list[tuple[str, Any]], dict[str, Any]]] = []
    names: set[str] = set()
    for row in rows:
        vals: list[tuple[str, Any]] = []
        rest: dict[str, Any] = {}
        for k, v in row.items():
            if k in _KEPT_OUT:
                continue
            if _is_value(v):
                vals.append((k, v))
                names.add(k)
            else:
                rest[k] = v
        split.append((vals, rest))
    metric = dict(conn.execute("SELECT name, id FROM metrics"))
    for name in sorted(names - metric.keys()):
        metric[name] = conn.execute("INSERT INTO metrics (name) VALUES (?)", (name,)).lastrowid
    facts_rows: list[tuple[str, str, str]] = []
    row_out: list[tuple[Any, ...]] = []
    val_out: list[tuple[int, int, Any]] = []
    for n, (row, (vals, rest)) in enumerate(zip(rows, split, strict=True)):
        rid = base + n
        item = row["item_id"]
        facts = 0
        meta: str | None = None
        if "_meta" in row:
            m = row["_meta"]
            if run and isinstance(m, dict):
                have = {k: m[k] for k in CALL_FACTS if k in m}
                if have:
                    text = _canon(have)
                    if item not in held:
                        held[item] = text
                        facts_rows.append((run, item, text))
                    if held[item] == text:
                        facts = 1
                        m = {k: v for k, v in m.items() if k not in have}
            meta = _canon(m)
        extra = _canon(row["_extra"]) if "_extra" in row else None
        row_out.append((rid, sid, n, item, facts, meta, extra, _canon(rest) if rest else None))
        val_out += [(rid, metric[k], v) for k, v in sorted(vals, key=lambda kv: metric[kv[0]])]
    conn.executemany("INSERT INTO call_facts VALUES (?, ?, ?)", facts_rows)
    conn.executemany("INSERT INTO score_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row_out)
    conn.executemany("INSERT INTO score_values VALUES (?, ?, ?)", val_out)


_scan = json.JSONDecoder().scan_once  # type: ignore[attr-defined]  # the C scanner, not in the stubs


def _loads(text: str) -> Any:
    """`json.loads` of a text this module wrote (no whitespace around it, one JSON value): the decoder's scanner itself."""
    return _scan(text, 0)[0]


def _assemble(
    row: dict[str, Any], item: str, facts: str | None, meta: str | None, extra: str | None, rest: str | None
) -> dict[str, Any]:
    """One row from its numeric fields (`row`, a dict this takes over) and what the tables hold of the rest
    (`write_set` undone), keys sorted. `facts` is the item's call facts as held when the row says they are its own; the
    row's own `_meta` keys win over them."""
    row["item_id"] = item
    if rest is not None:
        row.update(_loads(rest))
    if meta is not None:
        m = _loads(meta)
        if facts is not None:
            m = dict(sorted({**_loads(facts), **m}.items()))
        row["_meta"] = m
    if extra is not None:
        row["_extra"] = _loads(extra)
    return {k: row[k] for k in sorted(row)}


def _values(conn: sqlite3.Connection, vals: list[Any], names: dict[int, str]) -> dict[int, dict[str, Any]]:
    """{row id: its numeric fields} from `score_values` rows (row, metric, value) in key order; `names` is the metric
    ids' names, filled from `metrics` for an id it lacks."""
    try:
        return {rid: {names[m]: v for _r, m, v in g} for rid, g in groupby(vals, itemgetter(0))}
    except KeyError:
        names.update(conn.execute("SELECT id, name FROM metrics"))
        return {rid: {names[m]: v for _r, m, v in g} for rid, g in groupby(vals, itemgetter(0))}


def read_set(
    conn: sqlite3.Connection, key: str, names: dict[int, str], meta: bool = True
) -> tuple[list[dict[str, Any]], int] | None:
    """A score set's rows assembled, and the length their text would have (what the cache weighs); None when the set has
    none. `names` is the metric ids' names, kept by the caller and filled from `metrics` for an id it lacks. Without
    `meta` the rows have no `_meta` and no `_extra` (and the call facts are not read): the numbers, the item and the
    fields kept as JSON, for a reader that reads no more (RFC-033 performance plan, step 3)."""
    sid = _set_id(conn, key)
    if sid is None:
        return None
    lo = sid << ROW_BITS
    hi = lo + ROWS_PER_SET - 1
    if meta:
        got = conn.execute(
            "SELECT id, item_id, facts, meta, extra, rest, length(item_id) + coalesce(length(meta), 0)"
            " + coalesce(length(extra), 0) + coalesce(length(rest), 0) FROM score_rows WHERE id BETWEEN ? AND ?"
            " ORDER BY id",
            (lo, hi),
        ).fetchall()
    else:
        got = [
            (rid, item, 0, None, None, rest, len(item) + len(rest or ""))
            for rid, item, rest in conn.execute(
                "SELECT id, item_id, rest FROM score_rows WHERE id BETWEEN ? AND ? ORDER BY id", (lo, hi)
            )
        ]
    run = _run_of(key)
    held: dict[str, str] = {}
    if run and any(r[2] for r in got):
        held = dict(conn.execute("SELECT item_id, meta FROM call_facts WHERE run = ?", (run,)))
    vals = conn.execute(
        "SELECT row, metric, value FROM score_values WHERE row BETWEEN ? AND ? ORDER BY row, metric", (lo, hi)
    ).fetchall()
    by_row = _values(conn, vals, names)
    out: list[dict[str, Any]] = []
    for rid, item, facts, m, extra, rest, _w in got:
        if facts and item not in held:
            raise ValueError(
                f"{key}: the row of {item} has its run's call facts, and the run holds none for it"
            )
        out.append(_assemble(by_row.get(rid) or {}, item, held[item] if facts else None, m, extra, rest))
    return out, sum(r[6] for r in got) + ROW_TEXT * len(got) + VALUE_TEXT * len(vals)


#: What a row's text holds that the tables keep apart, on average: one numeric field (`"name": 0.853, `) and the row's
#: own braces, its `item_id` key and its call facts. The cache weighs a score set by the text its rows would make, as the
#: files store's cache does (calibrated against this repository's rows, step d).
VALUE_TEXT = 28
ROW_TEXT = 24


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
        self, run_dir: Path, partial: bool = False, errors: str = "strict", meta: bool = True
    ) -> list[dict[str, Any]] | None:
        """A score's rows as parsed dicts, in order (the checkpoint's, a torn line skipped, with `partial`); None when it
        has none. A line that is not JSON raises ValueError, bytes that are not UTF-8 UnicodeDecodeError, unless
        `errors` says `replace`: then they are skipped. With `meta` False a store may leave out each row's `_meta` and
        `_extra` (the sqlite store does, not decoding them): for a reader of the numbers. The dicts are shared: copy a
        row before changing it."""
        ...

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """A score's rows as canonical lines, derived from the dicts (the checkpoint's: verbatim, with `partial`);
        None when it has none."""
        ...

    def has_rows(self, run_dir: Path) -> bool:
        """Whether the run has its rows (not the checkpoint's), without reading them."""
        ...

    def stored_text(self, run_dir: Path, errors: str = "strict") -> str | None:
        """A score's rows as the store holds them: the files store's file, line by line as it was written; the sqlite
        store's canonical lines of the rows it gives back (it keeps no text). What a migration or a check of the stored
        data reads; None when it has none."""
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
        for line in jsonl_lines(p.read_text(encoding="utf-8")):
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
        if body:
            _common.write_text_atomic(path, body)
        else:  # no output is no file, as it is no rows in the sqlite store
            path.unlink(missing_ok=True)
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
        self, run_dir: Path, partial: bool = False, errors: str = "strict", meta: bool = True
    ) -> list[dict[str, Any]] | None:
        """A score's rows as parsed dicts, in order (the checkpoint's, a torn line skipped, with `partial`); None when it
        has none. A line that is not JSON raises ValueError, bytes that are not UTF-8 UnicodeDecodeError, unless
        `errors` says `replace`: then they are skipped. The line is parsed whole, so `meta` changes nothing here. The
        dicts are shared: copy a row before changing it."""
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
    for stmt in RESULTS_DDL:
        conn.execute(stmt)


#: A score's per-item results (RFC-033), the tables `write_set` and `read_set` keep. The score set's id follows the
#: order the sets were added; a row's id is `score_set * 2^20 + n`, so a score set's rows are one id range (read,
#: replaced and deleted by that range); `value` has no type affinity, so an integer stays an integer and a float a float.
RESULTS_DDL = (
    "CREATE TABLE IF NOT EXISTS score_sets (id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE)",
    "CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)",
    (
        "CREATE TABLE IF NOT EXISTS call_facts (run TEXT NOT NULL, item_id TEXT NOT NULL, meta TEXT NOT NULL,"
        " PRIMARY KEY (run, item_id)) WITHOUT ROWID"
    ),
    (
        "CREATE TABLE IF NOT EXISTS score_rows (id INTEGER PRIMARY KEY, score_set INTEGER NOT NULL, n INTEGER NOT NULL,"
        " item_id TEXT NOT NULL, facts INTEGER NOT NULL, meta TEXT, extra TEXT, rest TEXT, UNIQUE (score_set, n))"
    ),
    (
        "CREATE TABLE IF NOT EXISTS score_values (row INTEGER NOT NULL, metric INTEGER NOT NULL, value NOT NULL,"
        " PRIMARY KEY (row, metric)) WITHOUT ROWID"
    ),
    # n = 0 is the marker that a checkpoint exists (an empty one is one too); its lines, newline included, follow from n = 1.
    (
        "CREATE TABLE IF NOT EXISTS rows_partial (run TEXT NOT NULL, n INTEGER NOT NULL, line TEXT NOT NULL,"
        " PRIMARY KEY (run, n))"
    ),
    "CREATE INDEX IF NOT EXISTS score_rows_item ON score_rows (item_id)",
)
TABLES = ("outputs", "score_sets", "metrics", "call_facts", "score_rows", "score_values", "rows_partial")


class SqliteStore:
    """A project's outputs and rows in its one database (`_store`: data/project.sqlite), write-ahead logged: readers
    never block the writer, and a crash keeps every committed output. One committed insert per output; a score set's
    rows are written in one transaction (`write_set`). A run is its key, its directory under data/; `_store.rmtree` of
    that directory removes them with its files."""

    name = "sqlite"

    def __init__(self) -> None:
        self._lock = _store._LOCK  # the one connection's lock (_store)
        self._cache: dict[str, dict[str, str]] = {}
        self._rows: _Kept = _Kept()  # {(run key, partial): its rows}
        self._version: int | None = None
        self._ready: dict[int, bool] = {}  # {id(connection): whether it has the tables}
        self._names: dict[int, str] = {}  # {metric id: its name}

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
            have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "rows" in have:  # format 6's table: `evh migrate` (m0007) moves it into the tables above
                _common.die(
                    f"{_store.db_path()} still holds the per-item rows of an older format (table `rows`): run evh migrate",
                    "old-format",
                )
            # Read-only, nothing is created: a release made without runs has no such tables, and no outputs.
            if _store.readonly():
                self._ready[id(conn)] = set(TABLES) <= have
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
        """Every (run, partial) the database holds rows for: each score set, and each run with a checkpoint."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return []
            sets = [(r[0], False) for r in conn.execute("SELECT key FROM score_sets")]
            marks = [(r[0], True) for r in conn.execute("SELECT DISTINCT run FROM rows_partial")]
            return sorted(sets + marks)

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

    def _held(self, run_dir: Path, partial: bool, meta: bool = True) -> _Held | None:
        """The run's rows as kept, read from the database when not (the caller holds the lock and has made it fresh). A
        set kept without its `_meta` and `_extra` is read again for a reader that wants them."""
        conn = self._db(create=False)
        if conn is None:
            return None
        self._fresh(conn)
        ck = (self.key(run_dir), partial)
        hit = self._rows.get(ck)
        if hit is None or (meta and hit.light):
            if partial:
                got = conn.execute(
                    "SELECT line FROM rows_partial WHERE run = ? ORDER BY n", (ck[0],)
                ).fetchall()
                text = "".join(r[0] for r in got)
                hit = _Held(None, len(text), text=text) if got else _ABSENT
            else:
                made = read_set(conn, ck[0], self._names, meta)
                hit = (
                    _ABSENT
                    if made is None
                    else _Held(
                        made[0],
                        made[1],
                        light=not meta,
                        factor=SQLITE_DICT_FACTOR if meta else SQLITE_LIGHT_FACTOR,
                    )
                )
            self._rows[ck] = hit
        return None if hit is _ABSENT else hit

    def rows(
        self, run_dir: Path, partial: bool = False, errors: str = "strict", meta: bool = True
    ) -> list[dict[str, Any]] | None:
        """A score's rows as parsed dicts, in order (the checkpoint's, a torn line skipped, with `partial`); None when it
        has none. The database holds no line a read would raise on, so `errors` changes nothing. Without `meta` the rows
        have no `_meta` and no `_extra`: they are not decoded (what a reader of the numbers saves). The dicts are
        shared: copy a row before changing it."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.rows(run_dir, partial, errors, meta)
        with self._lock:
            held = self._held(run_dir, partial, meta)
            return (
                None if held is None else _rows_of(held, Path(run_dir) / (ROWS if partial else PREDICTIONS))
            )

    def rows_text(self, run_dir: Path, partial: bool = False, errors: str = "strict") -> str | None:
        """A score's rows as canonical lines, derived from the dicts (the checkpoint's: verbatim, with `partial`);
        None when it has none."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.rows_text(run_dir, partial, errors)
        with self._lock:
            held = self._held(run_dir, partial)
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
            return _set_id(conn, k) is not None

    def stored_text(self, run_dir: Path, errors: str = "strict") -> str | None:
        """A score's rows as canonical lines of what the database holds (it keeps no text of a row: these are the lines
        `put_rows` would make of the dicts read back); None when it has none."""
        return self.rows_text(run_dir)

    def put_rows(self, run_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
        """A score's rows replaced by `rows` at once, atomically (one transaction: the set's rows and values deleted, then
        written). A row that is not a JSON object with an `item_id` is refused (`invalid-file`), writing nothing."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.put_rows(run_dir, rows)
        rows = list(rows)
        _check_rows(run_dir, rows)
        k = self.key(run_dir)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            conn.execute("BEGIN IMMEDIATE")
            try:
                write_set(conn, k, rows)
                conn.execute("COMMIT")
            except BaseException:
                _rollback(conn)
                raise
            self._rows.pop((k, False), None)
            _store.wrote()

    def put_partial(self, run_dir: Path, text: str) -> None:
        """The run's checkpoint replaced by `text`, verbatim, at once, atomically."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.put_partial(run_dir, text)
        k = self.key(run_dir)
        with self._lock:
            conn = self._db(create=True)
            assert conn is not None
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM rows_partial WHERE run = ?", (k,))
                conn.executemany(
                    "INSERT INTO rows_partial VALUES (?, ?, ?)",
                    [(k, 0, ""), *[(k, n, ln) for n, ln in enumerate(text.splitlines(keepends=True), 1)]],
                )
                conn.execute("COMMIT")
            except BaseException:
                _rollback(conn)
                raise
            self._rows.pop((k, True), None)
            _store.wrote()

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
                conn.execute("INSERT OR IGNORE INTO rows_partial VALUES (?, 0, '')", (k,))
                conn.execute(
                    "INSERT INTO rows_partial SELECT ?, MAX(n) + 1, ? FROM rows_partial WHERE run = ?",
                    (k, line, k),
                )
                conn.execute("COMMIT")
            except BaseException:
                _rollback(conn)
                raise
            self._rows.pop((k, True), None)
            _store.wrote()

    def drop_rows(self, run_dir: Path, partial: bool = False) -> None:
        """The run's rows (or its checkpoint) gone from here; a run's call facts go with its last score set."""
        if _store.rel(run_dir) is None:  # outside data/: the disk's
            return _FILES.drop_rows(run_dir, partial)
        _store.require_writable()
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return
            k = self.key(run_dir)
            conn.execute("BEGIN IMMEDIATE")
            try:
                if partial:
                    conn.execute("DELETE FROM rows_partial WHERE run = ?", (k,))
                elif (sid := _set_id(conn, k)) is not None:
                    _forget_set(conn, sid)
                    conn.execute("DELETE FROM score_sets WHERE id = ?", (sid,))
                    if run := _run_of(k):
                        drop_call_facts(conn, run)
                conn.execute("COMMIT")
            except BaseException:
                _rollback(conn)
                raise
            self._rows.pop((k, partial), None)
            _store.wrote()

    def item_across(self, run_dirs: list[Path], item_id: str) -> dict[Path, dict[str, Any]]:
        """{run_dir: its row for the item} (the set's first row of it), one query for the item's rows and one per row found."""
        with self._lock:
            conn = self._db(create=False)
            if conn is None:
                return {}
            keys = {self.key(d): Path(d) for d in run_dirs if _store.rel(d) is not None}  # the rest: files
            out: dict[Path, dict[str, Any]] = {}
            found = conn.execute(
                "SELECT s.key, r.id, r.facts, r.meta, r.extra, r.rest FROM score_rows r JOIN score_sets s ON"
                " s.id = r.score_set WHERE r.item_id = ? ORDER BY s.key, r.n",
                (item_id,),
            ).fetchall()
            for k, rid, facts, meta, extra, rest in found:
                if k not in keys or keys[k] in out:
                    continue
                vals = _values(
                    conn,
                    [
                        (rid, m, v)
                        for m, v in conn.execute(
                            "SELECT metric, value FROM score_values WHERE row = ?", (rid,)
                        )
                    ],
                    self._names,
                ).get(rid, {})
                fact = None
                if facts:
                    got = conn.execute(
                        "SELECT meta FROM call_facts WHERE run = ? AND item_id = ?", (_run_of(k), item_id)
                    ).fetchone()
                    if got is None:
                        raise ValueError(
                            f"{k}: the row of {item_id} has its run's call facts, and the run holds none"
                        )
                    fact = got[0]
                out[keys[k]] = _assemble(dict(vals), item_id, fact, meta, extra, rest)
            return out

    def close(self) -> None:
        """The caches dropped (the connection is `_store`'s)."""
        with self._lock:
            self._cache.clear()
            self._rows.clear()
            self._version = None
            self._ready.clear()
            self._names.clear()


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


def rows(
    run_dir: Path, partial: bool = False, errors: str = "strict", meta: bool = True
) -> list[dict[str, Any]] | None:
    """A score's rows as parsed dicts, in order (with `partial`, the checkpoint's, a torn line skipped); None when it has
    none. A line that is not JSON raises ValueError naming the file and the line, bytes that are not UTF-8
    UnicodeDecodeError, unless `errors` is `replace` (a page that shows a run may): then they are skipped. `meta=False`
    is for a caller that reads the item and the numbers and nothing of `_meta` or `_extra`: the sqlite store does not
    decode them (a third of a read), and the rows it gives may lack them; the files store gives them whole. The dicts
    are the cache's own: copy a row before changing it."""
    return store().rows(Path(run_dir), partial, errors, meta)


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
    for n, line in enumerate(jsonl_lines(text or ""), 1):
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
        out.update(st.item_across(dirs, item_id))
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
