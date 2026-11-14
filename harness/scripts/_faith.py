"""Faithfulness records and the gate (RFC-030 R2).

A faithfulness record is written once by `evh faithfulness`: a replay at the recorded versions over every item,
compared with production's arm by the adapter's `same(a, b)`. A disagreement whose cause is outside the system is
named in the exceptions beside it (appended, who and when), never edited into the record. The records and where they
are (data/faithfulness/) are model/faithfulness.

The gate: a replay, or a candidate from it, is scored against a reference or label set only when the latest record of
its code record and dataset agrees on every item but those named, and was made with the same items, deployments and
adapter (its support modules included). Otherwise a person may pass `--unfaithful`, and the run says so everywhere.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from typing import Any

from evaluation_harness import _common
from evaluation_harness.model import faithfulness as model_faithfulness


def unnamed(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """A record's disagreements no exception names."""
    named = {e.get("item_id") for e in rec.get("exceptions") or []}
    return [d for d in rec.get("disagreements") or [] if d.get("item_id") not in named]


def compare(
    items: list[str],
    replay: dict[str, str],
    failed: dict[str, str],
    production: dict[str, str],
    same: Any,
    commit_of: dict[str, str],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Counts and disagreements, item by item in `items` order."""
    counts = {"items": len(items), "agree": 0, "differ": 0, "replay_errors": 0, "production_missing": 0}
    out: list[dict[str, Any]] = []
    for iid in items:
        c = commit_of.get(iid)
        if iid not in production:
            counts["production_missing"] += 1
            out.append(
                {
                    "item_id": iid,
                    "kind": "production-missing",
                    "commit": c,
                    "production": None,
                    "replay": replay.get(iid),
                }
            )
        elif iid in failed:
            counts["replay_errors"] += 1
            out.append(
                {
                    "item_id": iid,
                    "kind": "replay-error",
                    "commit": c,
                    "production": production[iid],
                    "replay": None,
                    "error": failed[iid],
                }
            )
        else:
            try:
                ok = bool(same(production[iid], replay.get(iid, "")))
            except Exception as exc:  # noqa: BLE001 - an adapter's same() that raises is a disagreement, said
                ok = False
                out.append(
                    {
                        "item_id": iid,
                        "kind": "differ",
                        "commit": c,
                        "production": production[iid],
                        "replay": replay.get(iid),
                        "error": f"same() raised {type(exc).__name__}: {exc}"[:300],
                    }
                )
                counts["differ"] += 1
                continue
            if ok:
                counts["agree"] += 1
            else:
                counts["differ"] += 1
                out.append(
                    {
                        "item_id": iid,
                        "kind": "differ",
                        "commit": c,
                        "production": production[iid],
                        "replay": replay.get(iid),
                    }
                )
    return counts, out


def gate(
    model_id: str,
    dataset_id: str,
    items_sha256: str | None,
    versions_sha256: str,
    adapter_sha256: str | None,
) -> dict[str, Any]:
    """{faithful, record, counts, unnamed, why}: whether the newest record made with this adapter (its support
    modules included) lets a replay be scored, and why not. Records made with another adapter (a stand-in being fixed,
    a second replay of the same system) never stand in for this one's."""
    rec = model_faithfulness.latest(model_id, dataset_id, adapter_sha256)
    if rec is None:
        other = model_faithfulness.latest(model_id, dataset_id)
        why = (
            f"record {model_id}/{other['n']} was made with another adapter or other support modules, and none with these"
            if other is not None
            else f"no faithfulness record of {model_id} on {dataset_id}"
        )
        return {"faithful": False, "record": None, "why": f"{why}: run evh faithfulness"}
    ref = f"{model_id}/{rec['n']}"
    moved = [
        what
        for what, have, want in (
            ("other items", rec.get("items_sha256"), items_sha256),
            ("other deployed versions in the code record", rec.get("versions_sha256"), versions_sha256),
        )
        if have != want
    ]
    left = unnamed(rec)
    out = {
        "faithful": not moved and not left,
        "record": ref,
        "counts": rec.get("counts"),
        "unnamed": len(left),
        "named": len(rec.get("exceptions") or []),
    }
    if moved:
        out["why"] = f"record {ref} was made with {' and '.join(moved)}: run evh faithfulness again"
    elif left:
        c = rec.get("counts") or {}
        out["why"] = (
            f"record {ref}: {len(left)} of {c.get('items')} item(s) disagree with production and are not named "
            f"({', '.join(d['item_id'] for d in left[:5])})"
        )
    return out


def said(state: dict[str, Any] | None) -> str:
    """One line for a run's faithfulness, as pages and commands show it."""
    if not state:
        return ""
    c = state.get("counts") or {}
    if state.get("faithful"):
        named = f", {state['named']} named" if state.get("named") else ""
        return f"faithful replay ({state.get('record')}: {c.get('agree')} of {c.get('items')} agree{named})"
    return f"unfaithful replay: {state.get('why') or 'no faithfulness record'}"


def state_now(m: dict[str, Any]) -> dict[str, Any] | None:
    """A finished run's faithfulness as the records stand now, from what its fingerprint names; None for a run that
    is not a replay."""
    fp = m.get("fingerprint") or {}
    code = (fp.get("deployment") or {}).get("code") or {}
    if not code.get("record"):
        return None
    return gate(
        str(code["record"]),
        str(m.get("dataset_id")),
        (fp.get("data") or {}).get("items_sha256"),
        str(code.get("versions_sha256")),
        ((fp.get("instrument") or {}).get("adapter") or {}).get("sha256"),
    )


def allow_scoring(m: dict[str, Any], what: str, unfaithful: bool) -> dict[str, Any] | None:
    """The gate for a finished replay run about to be scored or promoted: its state when the records let it, else
    refused unless a person passes --unfaithful (then who, recorded). None for a run that is not a replay."""
    st = state_now(m)
    if st is None or st["faithful"]:
        return st
    if not unfaithful:
        _common.die(
            f"{m.get('run_id')}: {said(st)}.\n  {what} a replay needs a faithfulness record that agrees with "
            "production (RFC-030), or a person's --unfaithful.",
            "not-allowed",
        )
    from evaluation_harness._actor import require_named  # noqa: PLC0415

    who = require_named(f"{what} an unfaithful replay")
    if who["type"] != "person":
        _common.die(
            f"an agent cannot pass --unfaithful; {what} an unfaithful replay is a person's decision",
            "not-allowed",
        )
    return {**st, "unfaithful_by": who}
