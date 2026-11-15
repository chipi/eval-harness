#!/usr/bin/env python3
"""A score's rows as parsed dicts, in both stores (RFC-033 step c).

    python tests/test_rows_api.py

`put_rows` takes dicts and each store keeps their canonical lines, so `rows_text` (derived) is the same text in the files
store and the sqlite store; a line that is no JSON object with an `item_id` is refused (`invalid-file`) in both, writing
nothing, by `put_rows` and by `write_rows`; the crash checkpoint is exempt (verbatim, a torn last line allowed, its rows
parsed without the torn line). The files store's reader stays tolerant of a hand-edited file (a strict read names the
line, a tolerant one skips it) and `validate` V28 reports the file. The kept-rows cache keeps the dicts and the text
together (the same objects on a second read, the item index kept with them), weighs what it holds, and drops them when the
rows are written. All of it runs twice: the files store, then the sqlite store.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-rowsapi-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ.pop("EVAL_STORE", None)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness import _format, _outputs, _runs, _store  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

ROWS = [
    {"item_id": "i1", "acc": 1.0, "_meta": {"usage": {"cost": 0.5}}, "_extra": {}},
    {"item_id": "i2", "acc": 0.0, "n": 3, "_extra": {}},
    {"item_id": "i3", "acc": 0.5, "_extra": {}},
]
CANON = "".join(json.dumps(r, sort_keys=True) + "\n" for r in ROWS)
TEXTS: dict[str, str] = {}


def refused(fn) -> str:
    """The refusal `fn` ends in (its message), "" when it did not refuse."""
    try:
        fn()
    except SystemExit as exc:
        return str(exc)
    return ""


def body(store: str) -> None:
    os.environ["EVAL_STORE"] = store
    _outputs.reset()
    sq = store == "sqlite"
    try:
        if _store.exists(proj / "data"):
            _store.rmtree(proj / "data")
        _store.mkdir(proj / "data" / "systems", parents=True)
        _format.stamp(data=proj / "data")
        runs = proj / "data" / "runs"
        d = _runstore.make_run(
            runs,
            "arm_a_v1_x",
            {"system_id": "arm_a_v1", "dataset_id": "ds"},
            scores=[{"scorer": "abcdefabcdef", "reference": "gold.ds", "first": True, "rows": ROWS}],
        )
        sd = model_runs.first_score(d)
        assert sd is not None

        got = _outputs.rows(sd)
        check(
            f"{store}: put_rows' dicts read back as dicts, in order",
            got == ROWS and isinstance(got, list),
            got,
        )
        TEXTS[store] = _outputs.rows_text(sd) or ""
        check(
            f"{store}: rows_text is the canonical line of each dict (row_line)",
            TEXTS[store] == CANON == "".join(_outputs.row_line(r) for r in ROWS),
            TEXTS[store],
        )
        check(
            f"{store}: item_rows yields the rows, and has_rows says so",
            [r["item_id"] for r in _runs.item_rows(sd)] == ["i1", "i2", "i3"] and _outputs.has_rows(sd),
        )
        check(
            f"{store}: a score with no rows has none (None, not an empty list)",
            _outputs.rows(d) is None and _outputs.rows_text(d) is None and not _outputs.has_rows(d),
        )
        _outputs.store().put_rows(sd, [])
        check(
            f"{store}: a score of no rows has an empty list, and its text is empty",
            _outputs.rows(sd) == [] and _outputs.rows_text(sd) == "" and _outputs.has_rows(sd),
        )
        _outputs.store().put_rows(sd, ROWS)

        # ── the refusal: both stores, both ways in ──────────────────────────────────────────────────────────────────
        bads: dict[str, Any] = {
            "a row with no item_id": {"acc": 1.0},
            "a row whose item_id is not a string": {"item_id": 7, "acc": 1.0},
            "a row whose item_id is null": {"item_id": None},
            "a row that is not an object": [1, 2],
        }
        for what, bad in bads.items():
            said = refused(lambda: _outputs.store().put_rows(sd, [ROWS[0], bad]))  # noqa: B023
            check(
                f"{store}: put_rows refuses {what} (invalid-file), naming the file and the row",
                said.startswith("ERROR (invalid-file)") and "predictions.jsonl: row 2" in said,
                said,
            )
            said = refused(lambda: _outputs.write_rows(sd, [bad]))  # noqa: B023
            check(f"{store}: write_rows refuses {what}", said.startswith("ERROR (invalid-file)"), said)
        check(
            f"{store}: a refused write wrote nothing: the score's rows are as they were",
            _outputs.rows(sd) == ROWS and _outputs.rows_text(sd) == CANON,
        )

        # ── the checkpoint is exempt ────────────────────────────────────────────────────────────────────────────────
        _outputs.append_partial(d, {"item_id": "i1", "acc": 1.0})
        _outputs.append_partial(d, {"item_id": "i2", "acc": 0.0})
        st = _outputs.store()
        st.append_row(d, '{"item_id": "i3", "acc": 0.')  # a kill mid-append
        whole = '{"acc": 1.0, "item_id": "i1"}\n{"acc": 0.0, "item_id": "i2"}\n'
        text = _outputs.rows_text(d, partial=True)
        check(
            f"{store}: the checkpoint's text is kept verbatim, a torn last line included",
            text == whole + '{"item_id": "i3", "acc": 0.',
            text,
        )
        check(
            f"{store}: the checkpoint's rows are the lines that parse: the torn one is skipped, nothing raises",
            _outputs.rows(d, partial=True) == [{"acc": 1.0, "item_id": "i1"}, {"acc": 0.0, "item_id": "i2"}],
            _outputs.rows(d, partial=True),
        )
        torn = whole + "not json at all\n[1]\n"
        st.put_partial(d, torn)
        check(
            f"{store}: a checkpoint put as text is kept as given, malformed lines too",
            _outputs.rows_text(d, partial=True) == torn and len(_outputs.rows(d, partial=True) or []) == 2,
        )
        st.drop_rows(d, partial=True)
        check(f"{store}: the checkpoint dropped", _outputs.rows_text(d, partial=True) is None)

        # ── the cache keeps the dicts and the text together ─────────────────────────────────────────────────────────
        _outputs.reset()
        a = _outputs.rows(sd)
        b = _outputs.rows(sd)
        t1 = _outputs.rows_text(sd)
        t2 = _outputs.rows_text(sd)
        check(
            f"{store}: a second read is the cache's: the same dicts, the same text object",
            a is not None and b is not None and all(x is y for x, y in zip(a, b, strict=True)) and t1 is t2,
        )
        cache = _outputs._ROWS_CACHE if not sq else _outputs._SQLITE._rows
        weight_before = cache.bytes
        _outputs._ROWS_CACHE.clear()
        _outputs._SQLITE._rows.clear()
        _outputs.rows(sd)
        small = cache.bytes
        _outputs.rows_text(sd)
        big = cache.bytes
        # the files store knows the text the dicts came from; the database's weight is its estimate of that text's length
        # (`read_set`: the lengths of the stored JSON, plus a fixed part per row and per numeric field)
        conn, key = _store.connect(), _store.rel(sd)
        made = _outputs.read_set(conn, key, {}) if conn is not None and key is not None else None
        held = len(CANON) if not sq else (made[1] if made else -1)
        check(
            f"{store}: the cache weighs the dicts (their text's length times DICT_FACTOR), and the text once it is made",
            small == held * (_outputs.DICT_FACTOR if not sq else _outputs.SQLITE_DICT_FACTOR)
            and big == small + len(CANON),
            (weight_before, small, big, held),
        )
        across = _outputs.item_across([sd], "i2")
        again = _outputs.item_across([sd], "i2")
        check(
            f"{store}: item_across finds the item's row, and no row for an item the run lacks",
            across.get(sd) == ROWS[1] and again.get(sd) == ROWS[1] and not _outputs.item_across([sd], "i9"),
            across,
        )
        if not sq:
            fs = _outputs._FILES
            idx = fs._index(sd)
            _outputs._ROWS_CACHE.clear()
            check(
                f"{store}: the item index is kept apart from the rows: made once, weighed as the text it copies, and it "
                "outlives the rows' eviction",
                idx is not None
                and fs._index(sd) is idx
                and idx.weight() == len(CANON)
                and _outputs._ROWS_INDEX.bytes == len(CANON)
                and set(idx.lines) == {"i1", "i2", "i3"},
                (idx and idx.weight(), _outputs._ROWS_INDEX.bytes),
            )
        if not sq:
            # another process (a pull, an editor) changed the file: the index and the rows are made again from it
            (sd / _outputs.PREDICTIONS).write_text(
                CANON + '{"acc": 1.0, "item_id": "i4"}\n', encoding="utf-8"
            )
            check(
                f"{store}: a file changed outside the store is indexed and read again (its stamp)",
                "i4" in (_outputs._FILES._index(sd) or _outputs._Index({}, 0, None)).lines
                and _outputs.item_across([sd], "i4").get(sd) == {"acc": 1.0, "item_id": "i4"}
                and len(_outputs.rows(sd) or []) == 4,
            )
            _outputs.store().put_rows(sd, ROWS)
        _outputs.store().put_rows(sd, ROWS[:2])
        if not sq:
            check(
                f"{store}: a write drops the index too: the next item_across is the new rows'",
                _outputs._FILES._index(sd) is not idx and not _outputs.item_across([sd], "i3"),
            )
        check(
            f"{store}: a write drops what was kept: the next read is the new rows",
            _outputs.rows(sd) == ROWS[:2]
            and _outputs.rows_text(sd)
            == CANON.splitlines(keepends=True)[0] + CANON.splitlines(keepends=True)[1],
        )
        keep = _outputs.ROWS_KEPT_BYTES
        try:
            _outputs.ROWS_KEPT_BYTES = 10
            _outputs.rows(sd)
            check(f"{store}: a bound below one entry still keeps the last read", len(cache) == 1, len(cache))
        finally:
            _outputs.ROWS_KEPT_BYTES = keep
        _outputs.store().put_rows(sd, ROWS)

        # ── the files store's tolerant reader, and validate's report ────────────────────────────────────────────────
        if sq:
            check(
                f"{store}: a hand-edited file is a files-store matter (the database holds no line it refused)",
                not _outputs.malformed(sd),
            )
            return
        hand = (
            '{"acc": 1.0, "item_id": "i1"}\nnot json\n[1, 2]\n{"acc": 2.0}\n\n{"acc": 0.0, "item_id": "i2"}\n'
        )
        _runstore.put_raw_rows(sd, hand)
        try:
            _outputs.rows(sd)
            raised = ""
        except ValueError as exc:
            raised = str(exc)
        check(
            f"{store}: a strict read of a hand-edited file raises, naming the file and the line",
            "predictions.jsonl:2" in raised and "not JSON" in raised,
            raised,
        )
        check(
            f"{store}: a tolerant read skips what is no row (a line that is no JSON, a JSON that is no object)",
            _outputs.rows(sd, errors="replace")
            == [{"acc": 1.0, "item_id": "i1"}, {"acc": 2.0}, {"acc": 0.0, "item_id": "i2"}],
            _outputs.rows(sd, errors="replace"),
        )
        check(
            f"{store}: a strict read after a tolerant one still raises (the tolerant one is not served to it)",
            "predictions.jsonl:2" in (refused_value(lambda: _outputs.rows(sd))),
        )
        check(
            f"{store}: item_rows(strict=False) names the rows that name an item",
            [r["item_id"] for r in _runs.item_rows(sd, strict=False)] == ["i1", "i2"],
        )
        check(
            f"{store}: malformed names the lines that are no row (not the blank one)",
            _outputs.malformed(sd) == [2, 3, 4],
            _outputs.malformed(sd),
        )
        bad, out = v28()
        check(
            f"{store}: validate V28 reports the file, naming the score set and the lines",
            len(bad) == 1
            and all(f"line {n}: not a JSON object with an item_id" in out for n in (2, 3, 4))
            and "arm_a_v1_x" in out,
            out,
        )
        _outputs.store().put_rows(sd, ROWS)
        bad, out = v28()
        check(f"{store}: V28 passes on rows the store wrote", not bad and "ok   V28" in out, out)
    finally:
        _outputs.reset()


def refused_value(fn) -> str:
    try:
        fn()
    except ValueError as exc:
        return str(exc)
    return ""


def v28():
    vt.problems.clear()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        vt.v28_rows_in_format_7()
    return [p for p in vt.problems if "V28" in p], out.getvalue()


try:
    for s in ("files", "sqlite"):
        body(s)
    check(
        "both stores: every score set's rows_text is the same canonical text",
        TEXTS.get("files") == TEXTS.get("sqlite") == CANON,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
raise SystemExit(summary())
