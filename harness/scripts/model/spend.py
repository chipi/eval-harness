"""What judging cost (RFC-032 step 8): counted from the stored verdicts, once, for every view of it. A judge's calls are no
run: each verdict under judge-verdicts/<scorer>/<judging set>/<judge>/ records its own cost_usd and whether the provider
reported it (`cost_known`). `evh cost-report` reads `judge_costs` (per scorer, judging set and judge) and the catalog's
spend chart `judge_spend` (per day), from the same `verdicts`: `billed` is what the provider reported, `estimated` what
the scorer's price table says of the calls it did not, never added to each other."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness.model import scorers as _scorers


def number(v: Any) -> float | None:
    """A JSON number as a float; None for anything else (a boolean is no number)."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def token_total(tin: Any, tout: Any) -> int | None:
    """Tokens in plus out, or None when neither was reported (unknown is not 0)."""
    vals = [number(x) for x in (tin, tout)]
    return int(sum(x for x in vals if x is not None)) if any(x is not None for x in vals) else None


def _json(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def verdicts(data: Path | None = None) -> list[dict[str, Any]]:
    """Every stored verdict's cost, in file order: {scorer, set, judge, dataset (the judging set's, "" when the set is
    no longer there), day, cost (USD, or None when it records none), known (the provider reported it), tokens (in plus
    out, or None)}. From the project's data or another data directory's."""
    datasets: dict[str, str] = {}
    out = []
    for scorer, set_id, judge, f in _scorers.verdict_files(data):
        if set_id not in datasets:
            datasets[set_id] = str(_json(_scorers.judging_set_file(set_id, data)).get("dataset_id") or "")
        v = _json(f)
        out.append(
            {
                "scorer": scorer,
                "set": set_id,
                "judge": judge,
                "dataset": datasets[set_id],
                "day": (v.get("created_at") or "")[:10],
                "cost": number(v.get("cost_usd")),
                "known": bool(v.get("cost_known", True)),
                "tokens": token_total(v.get("tokens_in"), v.get("tokens_out")),
            }
        )
    return out


def judge_costs(dataset_id: str | None = None, data: Path | None = None) -> list[dict[str, Any]]:
    """What judging cost: one row per scorer, judging set and judge, sorted, {scorer, set, dataset, judge, verdicts,
    billed, estimated, estimated_verdicts}. A verdict whose provider reported no cost is counted at the scorer's price
    table (`cost_known` false): that is `estimated`, never added to `billed`. With `dataset_id`, only the judging sets of
    that dataset (a set names its dataset); a set no longer on disk has no dataset, so only an unfiltered report counts
    its verdicts."""
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for v in verdicts(data):
        if dataset_id and v["dataset"] != dataset_id:
            continue
        row = rows.setdefault(
            (v["scorer"], v["set"], v["judge"]),
            {
                "scorer": v["scorer"],
                "set": v["set"],
                "dataset": v["dataset"],
                "judge": v["judge"],
                "verdicts": 0,
                "billed": 0.0,
                "estimated": 0.0,
                "estimated_verdicts": 0,
            },
        )
        row["verdicts"] += 1
        if v["known"]:
            row["billed"] += v["cost"] or 0.0
        else:
            row["estimated"] += v["cost"] or 0.0
            row["estimated_verdicts"] += 1
    return [
        {**r, "billed": round(r["billed"], 8), "estimated": round(r["estimated"], 8)}
        for _k, r in sorted(rows.items())
    ]


def judge_spend(data: Path | None = None) -> list[dict[str, Any]]:
    """What judging cost per day, scorer and judging set (the catalog's spend chart): {at, usd (billed), estimated_usd
    (priced on the scorer's table: not in usd), tokens, kind "judge", dataset, what (the scorer)}, sorted. A figure is
    None when no verdict of the day records it (unknown is not 0); a day with none of the three is left out."""
    days: dict[tuple[str, str, str], dict[str, Any]] = {}
    for v in verdicts(data):
        if v["cost"] is None and v["tokens"] is None:
            continue
        acc = days.setdefault(
            (v["day"], v["scorer"], v["set"]),
            {"billed": None, "estimated": None, "tokens": None, "dataset": v["dataset"]},
        )
        if v["cost"] is not None:
            key = "billed" if v["known"] else "estimated"
            acc[key] = (acc[key] or 0.0) + v["cost"]
        if v["tokens"] is not None:
            acc["tokens"] = (acc["tokens"] or 0) + v["tokens"]
    return [
        {
            "at": day,
            "usd": round(a["billed"], 8) if a["billed"] is not None else None,
            "estimated_usd": round(a["estimated"], 8) if a["estimated"] is not None else None,
            "tokens": a["tokens"],
            "kind": "judge",
            "dataset": a["dataset"],
            "what": scorer,
        }
        for (day, scorer, _set), a in sorted(days.items())
    ]
