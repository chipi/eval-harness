#!/usr/bin/env python3
"""How far an outcome rule set labels a dataset now, and what it waits for (the fleet's feedback 31).

    evh label-coverage --dataset-id triage_v1 --capture fleet_2026_11 --map outcomes.yaml

The same rules `evh label-from-capture` applies, read without writing anything: each item is labelled now, skipped
by design, not yet mature (a rule fits it but for `min_age_days`: the date it matures is named), matched by no rule
(with the outcome fields those items lack), or not in the capture. Per rule, the items it takes now and the ones it
will take when they mature. A rule that fits all but its age comes before the one that labels the item today, so
that item's label can still change: it counts as not yet mature, with what it gets today beside it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout
from evaluation_harness._common import evh_prog, load_dataset
from evaluation_harness._importers import parse_time
from evaluation_harness._outcome_rules import load_rules, matches
from evaluation_harness.dataset_from_capture import load_capture

CLASSES = ("labelled", "skipped", "not_mature", "unmatched", "no_record")
SAID = {
    "labelled": "labelled now",
    "skipped": "skipped by design",
    "not_mature": "not yet mature",
    "unmatched": "no rule matches",
    "no_record": "not in the capture",
}


def _rule_text(n: int, r: dict) -> str:
    what = "skip" if r.get("skip") else f"label {r['label']}"
    conds = [k for k in ("when", "unless", "exists", "absent", "range", "min_age_days") if k in r]
    return f"rule {n}: {what}" + (f" ({', '.join(conds)})" if conds else "")


def coverage(dataset_id: str, capture: str, rules: list) -> dict[str, Any]:
    """Each item's class under the rules, the counts per class and per rule, and the maturing dates."""
    ds = load_dataset(dataset_id)
    doc, recs = load_capture(capture)
    by_id = {r["id"]: r for r in recs}
    captured = parse_time(doc.get("captured_at"))
    items: list[dict[str, Any]] = []
    lacking: Counter[str] = Counter()
    for it in ds["items"]:
        iid = it["item_id"]
        rec = by_id.get(iid)
        if rec is None:
            items.append({"item_id": iid, "class": "no_record"})
            continue
        out = rec.get("outcome") if isinstance(rec.get("outcome"), dict) else {}
        t = parse_time(rec.get("created_at"))
        age = (captured - t).total_seconds() / 86400 if captured and t else None
        now = next((n for n, r in enumerate(rules, 1) if matches(r, out, age)), None)
        # The first rule that fits all but its age, before the one that holds today: it takes the item when it
        # matures (a rule with no record date never matures, so it waits on nothing it can name).
        wait = next(
            (
                n
                for n, r in enumerate(rules, 1)
                if (now is None or n < now) and "min_age_days" in r and t is not None
                and matches({k: v for k, v in r.items() if k != "min_age_days"}, out, age)
            ),
            None,
        )  # fmt: skip
        row: dict[str, Any] = {"item_id": iid}
        if wait is not None and t is not None:
            row |= {
                "class": "not_mature",
                "rule": wait,
                "matures": (t + timedelta(days=rules[wait - 1]["min_age_days"])).isoformat(),
                "today": None
                if now is None
                else ("skip" if rules[now - 1].get("skip") else rules[now - 1]["label"]),
            }
        elif now is None:
            row["class"] = "unmatched"
            row["lacks"] = sorted(
                {
                    f
                    for r in rules
                    for f in [*(r.get("when") or {}), *(r.get("exists") or []), *(r.get("range") or {})]
                }
                - {k for k, v in out.items() if v is not None}
            )
            lacking.update(row["lacks"])
        else:
            row |= {"class": "skipped" if rules[now - 1].get("skip") else "labelled", "rule": now}
        items.append(row)
    counts = Counter(r["class"] for r in items)
    per_rule = []
    for n, r in enumerate(rules, 1):
        took = sum(1 for x in items if x.get("rule") == n and x["class"] in ("labelled", "skipped"))
        waits = [x for x in items if x.get("rule") == n and x["class"] == "not_mature"]
        per_rule.append(
            {
                "rule": n,
                "text": _rule_text(n, r),
                "now": took,
                "when_mature": len(waits),
                "first_matures": min((x["matures"] for x in waits), default=None),
                "last_matures": max((x["matures"] for x in waits), default=None),
            }
        )
    return {
        "dataset_id": dataset_id,
        "capture": capture,
        "captured_at": doc.get("captured_at"),
        "items": len(items),
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "rules": per_rule,
        "lacking": dict(lacking.most_common()),
        "by_item": items,
    }


def main() -> int:
    """Report how far an outcome rule set labels a dataset."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--capture", required=True, help="the capture whose records hold the outcomes")
    ap.add_argument(
        "--map", required=True, type=Path, help="the rules (the mapping label-from-capture reads)"
    )
    ap.add_argument(
        "--items", action="store_true", help="also list every item with its class (and maturing date)"
    )
    ap.add_argument(
        "--json", action="store_true", help="the same answer as one JSON object: counts, rules and every item"
    )
    args = ap.parse_args()
    with _jsonout.collect("label-coverage", args.json):
        cov = coverage(args.dataset_id, args.capture, load_rules(args.map))
        print(
            f"{args.dataset_id}: {cov['items']} item(s), rules {args.map.as_posix()} over capture {args.capture}"
            + (f" (captured {cov['captured_at']})" if cov.get("captured_at") else "")
        )
        if not _jsonout.table(["class", "items"], [[SAID[c], cov["counts"][c]] for c in CLASSES]):
            for c in CLASSES:
                print(f"  {SAID[c]:20} {cov['counts'][c]}")
        if cov["lacking"]:
            print("  the unmatched lack: " + ", ".join(f"{f} ({n})" for f, n in cov["lacking"].items()))
        if not _jsonout.table(
            ["rule", "now", "when mature", "first matures", "last matures"],
            [
                [r["text"], r["now"], r["when_mature"], r["first_matures"], r["last_matures"]]
                for r in cov["rules"]
            ],
        ):
            print("by rule:")
            for r in cov["rules"]:
                print(
                    f"  {r['text']}: {r['now']} now"
                    + (
                        f", {r['when_mature']} when mature ({r['first_matures'][:10]} to {r['last_matures'][:10]})"
                        if r["when_mature"]
                        else ""
                    )
                )
        if args.items and not args.json:
            for x in cov["by_item"]:
                extra = (
                    f" rule {x['rule']}, matures {x['matures'][:10]}, today: {x['today'] or 'no label'}"
                    if x["class"] == "not_mature"
                    else (f" rule {x['rule']}" if "rule" in x else "")
                    + (f" lacks {', '.join(x['lacks'])}" if x.get("lacks") else "")
                )
                print(f"  {x['item_id']}  {SAID[x['class']]}{extra}")
        _jsonout.values(cov)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
