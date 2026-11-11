"""Faithfulness records and the gate (RFC-030 R2).

`data/faithfulness/<model_id>/<n>.json` is written once by `evh faithfulness`: a replay at the recorded versions over
every item, compared with production's arm by the adapter's `same(a, b)`. A disagreement whose cause is outside the
system is named in `<n>.exceptions.jsonl` beside it (appended, who and when), never edited into the record.

The gate: a replay, or a candidate from it, is scored against a reference or label set only when the latest record of
its code record and dataset agrees on every item but those named, and was made with the same items, deployments and
adapter (its support modules included). Otherwise a person may pass `--unfaithful`, and the run says so everywhere.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import json
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store


def records_dir(model_id: str) -> Path:
    """data/faithfulness/<model_id>/."""
    return _common.DATA / "faithfulness" / model_id


def numbers(model_id: str) -> list[int]:
    """The record numbers written for a code record, ascending."""
    d = records_dir(model_id)
    if not _store.is_dir(d):
        return []
    return sorted(int(p.stem) for p in _store.iterdir(d) if p.suffix == ".json" and p.stem.isdigit())


def load(model_id: str, n: int) -> dict[str, Any]:
    """Record n, with its named exceptions under `exceptions`."""
    p = records_dir(model_id) / f"{n}.json"
    if not _store.is_file(p):
        _common.die(
            f"no faithfulness record {model_id}/{n} (made: {numbers(model_id) or 'none'})", "not-found"
        )
    rec = _common.read_json(p)
    rec["exceptions"] = exceptions(model_id, n)
    return rec


def exceptions(model_id: str, n: int) -> list[dict[str, Any]]:
    """The disagreements named for record n, in the order they were named."""
    p = records_dir(model_id) / f"{n}.exceptions.jsonl"
    if not _store.is_file(p):
        return []
    out = []
    for line in _store.read_text(p, encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def latest(model_id: str, dataset_id: str, adapter_sha256: Any = ...) -> dict[str, Any] | None:
    """The newest record of a code record on a dataset (made with this adapter, when one is given), or None."""
    for n in reversed(numbers(model_id)):
        rec = _common.read_json(records_dir(model_id) / f"{n}.json")
        if rec.get("dataset_id") == dataset_id and (
            adapter_sha256 is ... or rec.get("adapter_sha256") == adapter_sha256
        ):
            rec["exceptions"] = exceptions(model_id, n)
            return rec
    return None


def write(rec: dict[str, Any]) -> int:
    """Write a new record under the next number (never over one); returns the number."""
    for _ in range(50):
        n = (numbers(rec["model_id"]) or [0])[-1] + 1
        body = {**rec, "n": n}
        data = (json.dumps(body, indent=2, sort_keys=True) + "\n").encode()
        if _store.create_new(records_dir(rec["model_id"]) / f"{n}.json", data):
            return n
    _common.die(f"faithfulness {rec['model_id']}: could not take a record number", "failed")
    return 0  # pragma: no cover - die exits


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
    rec = latest(model_id, dataset_id, adapter_sha256)
    if rec is None:
        other = latest(model_id, dataset_id)
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
