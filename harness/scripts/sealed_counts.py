#!/usr/bin/env python3
"""Counts over a held-out side, for safety only, never to judge effect (RFC-031 H2).

    evh sealed-counts --dataset-id triage_v1_test [--by disposition,gate] [--capture fleet_live]

Per UTC day (the split's time key) and per value of each allowed field: how many held-out items (and, with
`--capture`, how many of a capture's records on the held-out side of the boundary: what arrived since the split, the
live watch). The fields allowed are the ones the side was sealed with (`dataset-split --seal --count-by`, extended by a
person with `evh dataset-seal-counts`), not chosen by whoever reads the counts: the fleet left out the signal class on
purpose, as what tuning would read. No id or text is printed, and no minimum count hides a small one (one dropped
error is news). A project's own derived counts come from `exposure.counts_hook` in config.yaml (`file.py:fn`, called
with the records, returning (day, name, n) rows). Reading counts is not a read of any item: nothing is recorded.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from collections import Counter, defaultdict
from typing import Any

from evaluation_harness import _exposure, _jsonout, _seal
from evaluation_harness._common import die, evh_prog, load_dataset, load_module
from evaluation_harness._importers import parse_time

SAID = "for safety only, never to judge effect (RFC-031): counts, no item"


def allowed(dataset_id: str) -> list[str]:
    """The fields a held-out side's counts may be grouped by."""
    s = _seal.record_of(dataset_id).get("sealed") or {}
    return list(s.get("count_by") or []) + [
        x["field"] for x in s.get("count_by_added") or [] if x.get("field")
    ]


def _dig(d: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _value(v: Any) -> str:
    if v is None or v == "":
        return "(none)"
    if isinstance(v, (dict, list)):
        die(
            "a counted field holds a value that is not one word (a mapping or a list): not counted",
            "invalid-file",
        )
    text = str(v)
    if len(text) > 60 or "\n" in text:
        die(
            "a counted field holds text, not a category: not counted (count by a field of categories)",
            "not-allowed",
        )
    return text


def main() -> int:
    """Count."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="the held-out side")
    ap.add_argument(
        "--by", help="the allowed fields to group by, comma-separated (default: every allowed one)"
    )
    ap.add_argument(
        "--capture", help="also count this capture's records on the held-out side of the boundary"
    )
    ap.add_argument("--no-day", action="store_true", help="totals only, not per day")
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("sealed-counts", args.json, live=sys.stderr):
        if not _exposure.applies(args.dataset_id):
            die(f"{args.dataset_id} is not a held-out side (no seal)", "not-allowed")
        ok = allowed(args.dataset_id)
        by = [f.strip() for f in (args.by or "").split(",") if f.strip()] or ok
        refused = [f for f in by if f not in ok]
        if refused:
            die(
                f"{', '.join(refused)}: not a field this held-out side may be counted by (allowed: "
                f"{', '.join(ok) or 'none'}). A person adds one with evh dataset-seal-counts",
                "not-allowed",
            )
        doc = load_dataset(args.dataset_id)
        split = doc.get("split") or {}
        key = split.get("key") if split.get("split_by") == "time" else None
        boundary = parse_time(split.get("at")) if split.get("at") else None
        groups: list[tuple[str, list[tuple[str, dict]]]] = []
        groups.append(
            (
                "held-out items",
                [
                    (str((it.get("fields") or {}).get(key) or "") if key else "", it.get("fields") or {})
                    for it in doc["items"]
                ],
            )
        )
        records: list[dict] = []
        if args.capture:
            if boundary is None:
                die(
                    "--capture needs a side split at a time boundary (dataset-split --split-by time --at T)",
                    "not-allowed",
                )
            from evaluation_harness.dataset_from_capture import load_capture  # noqa: PLC0415

            _cdoc, recs = load_capture(args.capture)
            records = [
                r for r in recs if (t := parse_time(r.get("created_at"))) is not None and t >= boundary
            ]
            groups.append(
                (
                    f"capture {args.capture} since the boundary",
                    [(str(r.get("created_at") or ""), r.get("fields") or {}) for r in records],
                )
            )
        print(f"{args.dataset_id}: {SAID}")
        out: dict[str, Any] = {}
        for name, rows in groups:
            per_day: dict[str, Counter] = defaultdict(Counter)
            for when, fields in rows:
                t = parse_time(when) if when else None
                day = "all" if args.no_day or t is None else t.date().isoformat()
                per_day[day]["n"] += 1
                for f in by:
                    per_day[day][f"{f}={_value(_dig(fields, f))}"] += 1
            print(f"{name}: {len(rows)}")
            for day in sorted(per_day):
                c = per_day[day]
                print(
                    f"  {day}  n={c['n']}  " + "  ".join(f"{k}:{v}" for k, v in sorted(c.items()) if k != "n")
                )
            out[name] = {d: dict(c) for d, c in per_day.items()}
        hook = _exposure_counts_hook()
        if hook is not None:
            extra: dict[str, Counter] = defaultdict(Counter)
            for day, label, n in hook(records or [], doc["items"]) or []:
                extra[str(day)][str(label)] += int(n)
            print("the project's own counts:")
            for day in sorted(extra):
                print(f"  {day}  " + "  ".join(f"{k}:{v}" for k, v in sorted(extra[day].items())))
            out["project"] = {d: dict(c) for d, c in extra.items()}
        _jsonout.value("counts", out)
        _jsonout.value("said", SAID)
        return 0


def _exposure_counts_hook():
    from evaluation_harness.exposure_check import settings  # noqa: PLC0415

    spec = settings().get("counts_hook")
    if not spec:
        return None
    from evaluation_harness import _common  # noqa: PLC0415

    path, _, fn = str(spec).rpartition(":")
    if not path or not fn:
        die(f"exposure.counts_hook {spec!r}: path/to/file.py:function", "invalid-file")
    return getattr(load_module((_common.ROOT / path).resolve(), "evh_sealed_counts_hook"), fn)


if __name__ == "__main__":
    raise SystemExit(main())
