"""The period a view is read for (RFC-032 step 8): a window counted from today (`catalog_periods.PERIODS`), the line that
says it, and each row's numbers in it with the trend against the period before. The overview, the arms, the metrics and
the activity views, and their resources, read it."""

from __future__ import annotations

from datetime import date

from evaluation_harness import catalog_build as cb
from evaluation_harness import catalog_periods as cp


def span(key: str, today: date, first: str) -> dict:
    """The period `key`: its label, what trends compare with, its first and last day (`since`, `until`) and the
    period before (`prev`, None for all time)."""
    b = cp.bounds(key, today, first)
    label, against = next((lb, ag) for k, lb, ag in cp.PERIODS if k == key)
    return {
        "key": key,
        "label": label,
        "against": against,
        "since": b["since"],
        "until": b["until"],
        "prev": list(b["prev"]) if b["prev"] else None,
    }


def says(s: dict) -> str:
    """The line that names a period and what its trends compare with."""
    return f"{s['label']}, {s['since']} to {s['until']}" + (
        f"; ▲▼ against {s['against']}, {s['prev'][0]} to {s['prev'][1]}" if s["prev"] else ""
    )


def rows_in(A, by_ds: dict, rows: dict, key: str | None, today: date | None = None) -> dict:
    """{"rows": each row's period numbers, "line": the line that says the period}, or empty without a period."""
    if not key:
        return {"rows": {}, "line": ""}
    today = today or date.today()
    first = cb.window(A, by_ds)["first"]
    return {"rows": cp.in_period(rows, key, today, first), "line": says(span(key, today, first))}
