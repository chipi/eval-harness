"""Format 7, RFC-033: a run's per-item results as a model. The run's settings move onto the run, the provider's billing
object is kept to what is read, the rows are canonical text, and in a SQLite project they move into the results tables.

It reads the stored rows as format 6 kept them, not through the model: each score's `predictions.jsonl` (the files
store), or the lines of table `rows` a SQLite project of format 6 holds, and the run's run.json. The key names, the slim,
the kept usage keys and the tables below are frozen copies of `model/results.py`'s and `_outputs.py`'s as they are
written here; this file imports nothing from `model/`.

- Run settings. For each run, a setting (`generation_config`, `generation_requested`, `encoder_window`) that every row
  of every score of the run holds with one value (canonical JSON) goes to run.json's `call` and leaves the rows. A
  run whose rows differ keeps the setting in its rows; a run that already has a `call` (an interrupted migration) has
  the rows that hold its value cleaned, and rows that hold another value keep it.
- Usage. `_meta.usage` keeps `cost`, `prompt_tokens`, `completion_tokens`, and when nonzero `cached_tokens` and
  `cache_write_tokens` (both read from `prompt_tokens_details`); a `usage` that is not an object is left as it is.
  A usage with no `cost` gets none.
- Rows canonical: `json.dumps(row, sort_keys=True)` and a newline. A score whose rows come out as they went in is not
  written again.
- A SQLite project keeps a score's rows in tables (score sets, metrics, per-item values, a run's call facts: the
  "SQLite tables" of RFC-033). Those a project holds in table `rows`, the lines of format 6 (or of the build of this
  step that kept them there), are written into the new tables in one transaction, score sets in the order of their
  run's time (run.json's `started_at`, else `created_at`; a run with neither first), then their key: a set's id is its
  place in that order, and the metrics are numbered as met. The checkpoints are copied as they are, and `rows`
  dropped. `unfinished` says whether a project still holds it: such a project is at format 7 already when it kept the
  lines in `rows` under this step's first build, and `evh migrate` runs the step again for it (nothing else changes:
  the run settings and usage were done).

`--dry-run` prints each count; nothing is written. Refused, writing nothing: a run.json whose `call` is not an object,
rows that are not UTF-8, and a line of a score's rows that is not a JSON object with an `item_id` (the store refuses to
write one: correct the file first).
"""

from __future__ import annotations

import datetime
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _outputs, _store
from evaluation_harness._common import jsonl_lines

NUMBER = 7
ABOUT = "RFC-033: the run's settings once in run.json, the provider's usage slimmed, rows canonical, SQLite's results tables"

RUN_SETTINGS = ("generation_config", "generation_requested", "encoder_window")
#: What a call's facts are: `CALL_META` as format 7 names it, less the run's settings.
CALL_FACTS = (
    "provider",
    "response_model",
    "usage",
    "finish_reason",
    "reasoning_tokens_reported",
    "system_fingerprint",
    "resumed_from_disk",
)
ROW_BITS = 20
SCORE_SET = re.compile(r"(runs/[^/]+)/scores/[^/]+")
DDL = (
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
    (
        "CREATE TABLE IF NOT EXISTS rows_partial (run TEXT NOT NULL, n INTEGER NOT NULL, line TEXT NOT NULL,"
        " PRIMARY KEY (run, n))"
    ),
    "CREATE INDEX IF NOT EXISTS score_rows_item ON score_rows (item_id)",
    (
        "CREATE TABLE IF NOT EXISTS outputs (run TEXT NOT NULL, item_id TEXT NOT NULL, text TEXT NOT NULL,"
        " sha256 TEXT NOT NULL, PRIMARY KEY (run, item_id))"
    ),
)


def _slim(usage: Any) -> Any:
    """`usage` with only `cost`, `prompt_tokens`, `completion_tokens`, and when nonzero `cached_tokens` and
    `cache_write_tokens` (from `prompt_tokens_details`, or already at the top: slimming twice gives the same)."""
    if not isinstance(usage, dict):
        return usage
    out = {k: usage[k] for k in ("cost", "prompt_tokens", "completion_tokens") if k in usage}
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    for k in ("cached_tokens", "cache_write_tokens"):
        v = usage.get(k) or details.get(k)
        if v:
            out[k] = v
    return out


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _time(doc: Any) -> float:
    """A run's time from its run.json document: `started_at`, else `created_at`, as seconds since the epoch (a time with
    no zone is UTC); minus infinity when it has neither as an ISO time, so that run is first."""
    if isinstance(doc, dict):
        for field in ("started_at", "created_at"):
            v = doc.get(field)
            if isinstance(v, str):
                try:
                    t = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    continue
                return (t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)).timestamp()
    return float("-inf")


def _rel(p: Path) -> str:
    return p.relative_to(_common.DATA).as_posix()


def _dump_like(text: str, doc: Any) -> Any:
    """How run.json was written: the first of the layouts the harness writes that gives `text` back from its parsed
    document. Returns a function that writes a document that way (indent 2, keys in order, when none does)."""
    for sort in (False, True):
        for ascii_ in (False, True):
            kw: dict[str, Any] = {"indent": 2, "sort_keys": sort, "ensure_ascii": ascii_}
            if json.dumps(doc, **kw) + "\n" == text:
                return lambda d, kw=kw: json.dumps(d, **kw) + "\n"
    return lambda d: json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def _lines(text: str) -> list[tuple[str, Any]]:
    """(line, its row or None) for each line of a rows text; a row is a JSON object."""
    out = []
    for line in jsonl_lines(text):
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        out.append((line, row if isinstance(row, dict) else None))
    return out


def _held(run: Path, refused: list[str]) -> tuple[Any, dict[str, Any], str | None]:
    """(run.json's document, its `call`, its text); (None, {}, None) when it has none."""
    p = run / "run.json"
    if not _store.is_file(p):
        return None, {}, None
    text = _store.read_text(p, encoding="utf-8")
    try:
        doc = json.loads(text)
    except ValueError:
        return None, {}, None
    if not isinstance(doc, dict):
        return None, {}, None
    call = doc.get("call", {})
    if not isinstance(call, dict):
        refused.append(f"{_rel(p)}: `call` is not an object")
        return None, {}, None
    return doc, call, text


# ── the rows as format 6 kept them in SQLite ────────────────────────────────────────────────────────────────────────
def _legacy() -> Any:
    """The project's database when it still holds the lines of format 6 (table `rows`); None otherwise."""
    if not _store.sqlite():
        return None
    conn = _store.connect(create=False)
    if conn is None:
        return None
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return conn if "rows" in have else None


def unfinished() -> bool:
    """Whether the project is a SQLite project that still keeps a score's rows in table `rows`."""
    return _legacy() is not None


def _legacy_text(conn: Any, key: str) -> str | None:
    """A score's lines in table `rows`, as written (n = 0 is the marker that the rows exist, an empty set's too)."""
    got = conn.execute("SELECT row FROM rows WHERE run = ? AND partial = 0 ORDER BY n", (key,)).fetchall()
    return "".join(r[0] for r in got) if got else None


def _groups(refused: list[str], legacy: Any) -> list[tuple[Path | None, list[Path]]]:
    """[(a run's directory, its score directories)] in the order they are read; a score set that is not of a run (a
    scratch one) is its own group with no run."""
    runs_dir = _common.DATA / "runs"
    out: list[tuple[Path | None, list[Path]]] = []
    if legacy is None:
        for run in sorted(_store.iterdir(runs_dir)) if _store.is_dir(runs_dir) else []:
            if not _store.is_dir(run):
                continue
            sdir = run / "scores"
            out.append((run, sorted(_store.iterdir(sdir)) if _store.is_dir(sdir) else []))
        return out
    by_run: dict[str, list[Path]] = {}
    loose: list[Path] = []
    for (key,) in legacy.execute("SELECT DISTINCT run FROM rows WHERE partial = 0 ORDER BY run"):
        m = SCORE_SET.fullmatch(key)
        if m:
            by_run.setdefault(m.group(1), []).append(_common.DATA / key)
        else:
            loose.append(_common.DATA / key)
    for run in sorted(_store.iterdir(runs_dir)) if _store.is_dir(runs_dir) else []:
        if _store.is_dir(run):
            out.append((run, by_run.pop(_rel(run), [])))
    loose += [
        sd for sds in by_run.values() for sd in sds
    ]  # a run whose folder holds no file: no run.json to read
    out += [(None, [sd]) for sd in sorted(loose)]
    return out


def plan() -> dict[str, Any]:
    """{"changes": [(run.json path, text, [(rows path, text)])], "counts": Counter, "refused": [...], "text": {score
    key: its rows text as it will be, every one} }; reads only."""
    changes: list[tuple[Path | None, str | None, list[tuple[Path, str]]]] = []
    counts: Counter[str] = Counter()
    refused: list[str] = []
    final: dict[str, str] = {}
    when: dict[str, float] = {}
    store = _outputs.store()
    legacy = _legacy()
    for run, score_dirs in _groups(refused, legacy):
        doc, call, run_text = _held(run, refused) if run is not None else (None, {}, None)
        sets: list[tuple[Path, list[tuple[str, Any]]]] = []
        for sd in score_dirs:
            try:
                text = _legacy_text(legacy, _rel(sd)) if legacy is not None else store.stored_text(sd)
            except UnicodeDecodeError as exc:
                refused.append(f"{_rel(sd)}: its rows are not UTF-8 ({exc.reason})")
                continue
            if text is not None:
                lines = _lines(text)
                bad = [
                    n
                    for n, (_l, row) in enumerate(lines, 1)
                    if row is None or not isinstance(row.get("item_id"), str)
                ]
                if bad:
                    refused.append(
                        f"{_rel(sd)}: line {bad[0]}{f' (and {len(bad) - 1} more)' if len(bad) > 1 else ''} is not a "
                        "JSON object with an item_id"
                    )
                    continue
                sets.append((sd, lines))
        # a setting is the run's when every row of every score holds one value for it
        new_call = dict(call)
        if doc is not None:
            for k in RUN_SETTINGS:
                if k in call:
                    continue
                seen: set[str] = set()
                first: Any = None
                everywhere = bool(sets)
                for _sd, lines in sets:
                    for _line, row in lines:
                        if row is None:
                            continue
                        meta = row.get("_meta")
                        if not isinstance(meta, dict) or k not in meta:
                            everywhere = False
                            break
                        if not seen:
                            first = meta[k]
                        seen.add(_canon(meta[k]))
                        if len(seen) > 1:
                            everywhere = False
                            break
                    if not everywhere:
                        break
                if everywhere and len(seen) == 1:
                    new_call[k] = first
                    counts[f"run setting {k}, runs"] += 1
        run_sets: list[tuple[Path, str]] = []
        for sd, lines in sets:
            out: list[str] = []
            changed = False
            lost = slimmed = False
            for line, row in lines:
                if row is None:
                    out.append(line + "\n")
                    continue
                new = row
                meta = new.get("_meta")
                if isinstance(meta, dict):
                    drop = [
                        k
                        for k in RUN_SETTINGS
                        if k in new_call and k in meta and _canon(meta[k]) == _canon(new_call[k])
                    ]
                    if "usage" in meta:
                        usage = _slim(meta["usage"])
                        if _canon(usage) != _canon(meta["usage"]):
                            counts["usage objects slimmed"] += 1
                            meta = {**meta, "usage": usage}
                            slimmed = True
                        if isinstance(usage, dict) and "cost" not in usage:
                            counts["usage objects without a cost (kept without one)"] += 1
                    if drop:
                        meta = {k: v for k, v in meta.items() if k not in drop}
                        for k in drop:
                            counts[f"run setting {k}, rows"] += 1
                        lost = True
                    new = {**new, "_meta": meta}
                text = _canon(new) + "\n"
                if text != line + "\n":
                    changed = True
                    if new is row or _canon(new) == _canon(row):
                        counts["rows made canonical"] += 1
                out.append(text)
            final[_rel(sd)] = "".join(out)
            when[_rel(sd)] = _time(doc)
            if changed:
                run_sets.append((sd, "".join(out)))
                counts["score sets rewritten"] += 1
                if lost:
                    counts["score sets that lost a run setting"] += 1
                if slimmed:
                    counts["score sets with usage slimmed"] += 1
        call_new = new_call != call
        if call_new and doc is not None and run_text is not None and run is not None:
            new_doc = {**doc, "call": new_call}
            counts["run.json given a call"] += 1
            changes.append((run / "run.json", _dump_like(run_text, doc)(new_doc), run_sets))
        elif run_sets:
            changes.append((run / "run.json" if run is not None else None, None, run_sets))
    if legacy is not None:
        counts["score sets moved into the results tables"] = len(final)
        counts["rows moved into the results tables"] = sum(t.count("\n") for t in final.values())
        counts["checkpoint lines moved"] = legacy.execute(
            "SELECT count(*) FROM rows WHERE partial = 1 AND n > 0"
        ).fetchone()[0]
    return {"changes": changes, "counts": counts, "refused": refused, "text": final, "time": when}


# ── SQLite: the lines into the results tables (a frozen copy of what `_outputs.write_set` does) ─────────────────────
def _is_value(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return -(1 << 63) <= v < (1 << 63)
    return isinstance(v, float) and math.isfinite(v)


def _write_set(conn: Any, key: str, rows: list[dict[str, Any]]) -> None:
    """One score set's rows into the new tables: its id the next one (the sets come in their order);
    numeric fields as values, `_meta` less the call facts the run already holds for the item (`facts` = 1), `_extra`,
    and every other field as JSON in `rest`."""
    if len(rows) > 1 << ROW_BITS:
        _common.die(f"{key}: {len(rows):,} rows; a score set holds at most {1 << ROW_BITS:,}", "invalid-file")
    sid = (conn.execute("SELECT MAX(id) FROM score_sets").fetchone()[0] or 0) + 1
    conn.execute("INSERT INTO score_sets VALUES (?, ?)", (sid, key))
    base = sid << ROW_BITS
    m = SCORE_SET.fullmatch(key)
    run = m.group(1) if m else None
    held: dict[str, str] = (
        dict(conn.execute("SELECT item_id, meta FROM call_facts WHERE run = ?", (run,))) if run else {}
    )
    split = []
    names: set[str] = set()
    for row in rows:
        vals: list[tuple[str, Any]] = []
        rest: dict[str, Any] = {}
        for k, v in row.items():
            if k in ("item_id", "_meta", "_extra"):
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
    facts_rows, row_out, val_out = [], [], []
    for n, (row, (vals, rest)) in enumerate(zip(rows, split, strict=True)):
        rid = base + n
        item = row["item_id"]
        facts = 0
        meta = None
        if "_meta" in row:
            mt = row["_meta"]
            if run and isinstance(mt, dict):
                have = {k: mt[k] for k in CALL_FACTS if k in mt}
                if have:
                    text = _canon(have)
                    if item not in held:
                        held[item] = text
                        facts_rows.append((run, item, text))
                    if held[item] == text:
                        facts = 1
                        mt = {k: v for k, v in mt.items() if k not in have}
            meta = _canon(mt)
        extra = _canon(row["_extra"]) if "_extra" in row else None
        row_out.append((rid, sid, n, item, facts, meta, extra, _canon(rest) if rest else None))
        val_out += [(rid, metric[k], v) for k, v in sorted(vals, key=lambda kv: metric[kv[0]])]
    conn.executemany("INSERT INTO call_facts VALUES (?, ?, ?)", facts_rows)
    conn.executemany("INSERT INTO score_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row_out)
    conn.executemany("INSERT INTO score_values VALUES (?, ?, ?)", val_out)


def _fill(conn: Any, texts: dict[str, str], when: dict[str, float]) -> None:
    """The results tables made and filled from `texts` ({score key: its rows text}) in the order of `when` ({score key:
    its run's time}) then the key, the checkpoint copied, `rows` dropped: one transaction, all of it or none."""
    with _store._LOCK:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in DDL:
                conn.execute(stmt)
            for key in sorted(texts, key=lambda k: (when[k], k)):
                rows = [json.loads(line) for line in jsonl_lines(texts[key])]
                _write_set(conn, key, rows)
            conn.execute("INSERT INTO rows_partial SELECT run, n, row FROM rows WHERE partial = 1")
            conn.execute("DROP TABLE rows")
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    _store.wrote()
    _vacuum(conn)


def _vacuum(conn: Any) -> None:
    """Give back the pages `rows` held (measured: a format-6 database of 241.8 MB stood at 327.7 MB after the move,
    150 MB of them free, until vacuumed). After the move's commit, so a VACUUM that cannot run (it needs about the
    database's size free on disk) leaves the data moved and only says so."""
    path = _store.db_path()
    before = _store.stat(path).st_size
    try:
        with _store._LOCK:
            conn.execute("VACUUM")
    except Exception as exc:  # noqa: BLE001 - the move is done; the space is what VACUUM would have given back
        print(f"  note: the database was not vacuumed ({exc}); it keeps {before / 1e6:.1f} MB until it is")
        return
    print(f"  vacuumed the database: {before / 1e6:.1f} MB -> {_store.stat(path).st_size / 1e6:.1f} MB")


def run(dry_run: bool) -> None:
    """Hoist the run settings, slim the usage, make the rows canonical, and in a SQLite project move them into the
    results tables; refuse first, writing nothing."""
    p = plan()
    if p["refused"]:
        _common.die("runs this step cannot read:\n  " + "\n  ".join(p["refused"]), "invalid-file")
    legacy = _legacy()
    if not p["changes"] and legacy is None:
        print("  0 changed: already in this format")
        return
    for kind, n in sorted(p["counts"].items()):
        print(f"    {n:>7}  {kind}")
    if dry_run:
        return
    store = _outputs.store()
    for path, text, row_sets in p["changes"]:
        if (
            text is not None and path is not None
        ):  # run.json first: a score's rows only lose a setting once the run holds it
            _common.write_text_atomic(path, text)
        if legacy is not None:
            continue  # the lines go into the tables below, as they will be
        for sd, text in row_sets:
            rows, _skipped = _outputs.parse_rows(text, _rel(sd))
            store.put_rows(sd, rows)
    if legacy is not None:
        _fill(legacy, p["text"], p["time"])
