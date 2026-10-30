"""Rows to records, for the file importers: which column is what, and a filter.

The query, all keys optional except `path`:
  path        the file (relative to the current directory)
  id          the column holding the record's id (default "id")
  body        the column holding its content; "row" for the whole row (default: "body" when the
              rows have it, else the whole row)
  fields      the columns kept as fields (default: every column but id, body, created_at, outcome)
  created_at  the column holding its time (default "created_at")
  outcome     the column holding what happened afterwards (default "outcome")
  url         a link to the record, with {column} placeholders
  system      the system the records come from (default: the file's name)
  where       {column: value or [values]}: keep only matching rows (compared as text; an empty or
              missing cell is "")
  since/until ISO times: keep rows whose created_at falls in [since, until)
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from evaluation_harness._importers import parse_time


def records(rows: Iterable[dict], query: dict) -> Iterator[dict]:
    """Each row a record, mapped by the query; rows outside `where` or the window are left out, and
    rows the window cannot place (no parsable time) are counted on stderr, never dropped silently."""
    path = Path(query["path"])
    id_col = query.get("id", "id")
    time_col = query.get("created_at", "created_at")
    out_col = query.get("outcome", "outcome")
    where = query.get("where") or {}
    since, until = parse_time(query.get("since")), parse_time(query.get("until"))
    untimed = 0
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"{path}: row {n} is not an object")
        if any(not _matches(row.get(k), v) for k, v in where.items()):
            continue
        t = parse_time(row.get(time_col))
        if (since or until) and t is None:
            untimed += 1
            continue
        if (since and t and t < since) or (until and t and t >= until):
            continue
        body_col = query.get("body", "body" if "body" in row else "row")
        body: Any = dict(row) if body_col == "row" else row.get(body_col)
        skip = {id_col, time_col, out_col} | ({body_col} if body_col != "row" else set())
        keep = query.get("fields")
        fields = {k: row.get(k) for k in (keep if keep is not None else [k for k in row if k not in skip])}
        rid = row.get(id_col)
        yield {
            "id": "" if rid is None else str(rid),
            "body": body,
            "fields": fields,
            "created_at": row.get(time_col),
            "source": {
                "system": query.get("system", path.name),
                "url": query["url"].format_map(_Default(row)) if query.get("url") else None,
            },
            "outcome": row.get(out_col),
        }
    if untimed:
        print(
            f"  note: {untimed} row(s) of {path.name} have no readable {time_col!r} and were left out "
            "of the window",
            file=sys.stderr,
        )


def _matches(value: Any, want: Any) -> bool:
    wants = want if isinstance(want, list) else [want]
    return ("" if value is None else str(value)) in ["" if w is None else str(w) for w in wants]


class _Default(dict):
    def __missing__(self, key: str) -> str:
        return ""
