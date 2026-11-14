"""The catalog's home page as data (RFC-032 step 8): the period, the tiles with their trends, each goal's decision at a
glance, the measured runs per day, the spend, what each dataset has, and what was recorded. `evh overview`, the home
page's numbers and `GET /overview` read it; each is the computation the others share, rendered."""

from __future__ import annotations

from datetime import date
from typing import Any

from evaluation_harness import catalog_build as cb
from evaluation_harness import catalog_periods as cp
from evaluation_harness.model import goal_views as gv
from evaluation_harness.model import period_views


def overview(A, by_ds: dict, period: str = cp.DEFAULT, today: date | None = None) -> dict[str, Any]:
    """The home page for `period`: {"period", "tiles", "goals", "first", "activity", "spend", "coverage", "events",
    "item_word"}. `goals` is each goal's answer on a dataset at a glance (the decision itself is `goal_views`' leaderboard),
    `activity` the measured runs per day by dataset, `spend` each unit's per-day spend by name, and `events` what was
    recorded since the period began; each None when nothing is recorded with a date."""
    w = cb.window(A, by_ds)
    rounds_fn = getattr(A, "rounds", None)
    data = cp.home_data(A, by_ds, w["spend"], A.goals(), rounds_fn() if callable(rounds_fn) else [])
    today = today or date.today()
    p = period_views.span(period, today, data["first"])
    since, until = p["since"], p["until"]
    out: dict[str, Any] = {
        "period": p,
        "tiles": cp.tiles(data, period, today),
        "goals": [
            {
                **{k: v for k, v in r.items() if k not in ("dec", "retired")},
                "goal": r["goal"]["goal_id"],
                "verdict": cb.glance_verdict(r),
            }
            for r in gv.glance(A, by_ds)
        ],
        "first": data["first"],
        "item_word": A.item_word,
        "activity": None,
        "spend": None,
        "coverage": [{**c, "goals": [g["goal_id"] for g in c["goals"]]} for c in cb.coverage(A, by_ds)],
        "events": None,
    }
    if data["first"]:
        counts = {
            ds: {d: n for d, n in per.items() if d <= until}
            for ds, per in cb.activity_counts(by_ds, since).items()
            if any(d <= until for d in per)
        }
        out["activity"] = counts
        out["spend"] = {
            unit: {
                name: {d: v for d, v in days_.items() if d <= until}
                for name, days_ in cb.spend_by_day(w["spend"], since, unit).items()
                if any(d <= until for d in days_)
            }
            for unit in cb.SPEND_UNITS
        }
    if since:
        out["events"] = [
            {"at": x["at"], "what": cb.plain(x["html"]), "kind": x["kind"]}
            for x in w["events"]
            if x["at"][:10] >= since
        ]
    return out
