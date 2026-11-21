"""The activity page as data (RFC-032 step 8): runs, spend and tokens in a period by dataset, by arm and by kind, each
against the period before. `evh activity-show`, the activity page's numbers and `GET /activity` read it."""

from __future__ import annotations

from datetime import date
from typing import Any

from evaluation_harness import catalog_build as cb
from evaluation_harness import catalog_periods as cp
from evaluation_harness.model import period_views


def _busiest(per: dict, prefix: str) -> list[str]:
    """What moved most against the period before first, up or down (as the page sorts), then the busiest; for all
    time, with no period before, the busiest."""
    ks = [k for k in per if k.startswith(prefix)]

    def moved(k: str) -> int:
        prev = per[k]["runs_prev"]
        return 0 if prev is None else abs(per[k]["runs"] - prev)

    return sorted(ks, key=lambda k: (-moved(k), -per[k]["runs"], -per[k]["usd"], k))


def activity(
    A, by_ds: dict, period: str = cp.DEFAULT, arms: int = 20, today: date | None = None
) -> dict[str, Any]:
    """The period's runs, spend and tokens: {"period": the line saying it, "by_dataset": [{"dataset", **numbers}],
    "by_arm": {"active", "rows": [{"arm", **numbers}]}, "by_kind": [{"kind", "name", **numbers}]}; `numbers` are
    `catalog_periods.in_period`'s (new, runs, usd, tokens, each with its `_prev`). The arms are the `arms` that moved
    most; "active" counts every arm that ran, spent or used tokens in the period."""
    per = period_views.rows_in(A, by_ds, cb.period_activity(A, by_ds), period, today)
    rows = per["rows"]
    active = [k for k in _busiest(rows, "a:") if rows[k]["runs"] or rows[k]["usd"] or rows[k]["tokens"]]
    names = dict(cb.SPEND_KINDS)
    return {
        "period": per["line"],
        "by_dataset": [{"dataset": k[2:], **rows[k]} for k in _busiest(rows, "d:")],
        "by_arm": {"active": len(active), "rows": [{"arm": k[2:], **rows[k]} for k in active[:arms]]},
        "by_kind": [
            {"kind": k[2:], "name": names[k[2:]], **rows[k]}
            for k in sorted(k for k in rows if k.startswith("k:"))
        ],
    }
