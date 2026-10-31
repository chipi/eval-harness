#!/usr/bin/env python3
"""verdicts.jsonl, the published labels, from the answered labelling sheet.

    python examples/triage-fleet/write_verdicts.py decisions.jsonl --sheet sheet/ --out verdicts.jsonl

One line per label: {id, label, source, issue, detail, note}. `source` says who decided:
  owner-issue-verdict  the owner's verdict on an issue (sheet part A), carried to the decisions it
                       reaches: the one that filed it, and earlier ones on its fingerprint
  owner-item-label     the owner's label on an exact decision (part B): his own answer, or production's
                       decision where the labeller agreed with it, which he accepted for those rows
  outcome-mapping      computed from what happened afterwards (outcomes.yaml): shown, never deciding
  fixture              the fleet's own earlier hand labels, carried by fingerprint
A decision can have one owner row and rows of the other sources. Labels: file, dismiss, escalate,
cleanup, and file-or-escalate (an issue fixed later: filing and escalating were both right).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "harness"))
from evaluation_harness.reference_from_outcomes import load_rules, matches  # noqa: E402
from importer import _t, close_comments, issue_verdicts, outcome_fields, own_issue, resolved  # noqa: E402

LABEL_OF = {"fixed": "file-or-escalate", "noise": "dismiss"}
LABELS = ("file", "dismiss", "escalate", "cleanup", "file-or-escalate")


def _csv(p: Path) -> list[dict]:
    return list(csv.DictReader(p.open(encoding="utf-8")))


def owner_issue_rows(rows: list[dict], answers: list[dict]) -> list[dict]:
    """Part A: each confirmed issue verdict, on the decisions it reaches."""
    verdicts = issue_verdicts(rows)
    confirmed = {}
    for a in answers:
        ans = (a.get("answer") or "").strip().lower()
        if not ans:
            continue
        v = resolved(verdicts, int(a["issue"])) if ans == "yes" else ans
        confirmed[int(a["issue"])] = (v, a["proposed_verdict"] if ans == "yes" else f"owner: {ans}")
    out = []
    for r in rows:
        li = own_issue(r)
        if not li or li["number"] not in confirmed:
            continue
        v, detail = confirmed[li["number"]]
        if v not in LABEL_OF:
            continue
        cc = close_comments(li)
        out.append(
            {
                "id": r["id"],
                "label": LABEL_OF[v],
                "source": "owner-issue-verdict",
                "issue": li["number"],
                "detail": f"{detail}; {li.get('relation')}",
                "note": (cc[0] if cc else "")[:300],
            }
        )
    return out


def owner_item_rows(answers: list[dict]) -> list[dict]:
    """Part B: the owner's label, or production's where the labeller agreed and he accepted it."""
    out = []
    for a in answers:
        ans = (a.get("answer") or "").strip().lower()
        prod = a["production_decided"].split(" ")[0]
        if ans in LABELS:
            label, detail = ans, f"owner's label; {a.get('labeller', '')} proposed {a.get('model_label')}"
        elif a.get("agrees_with_production") == "yes" and prod in LABELS:
            label, detail = (
                prod,
                f"production's decision, {a.get('labeller', '')} agreed; accepted by the owner",
            )
        else:
            continue
        out.append(
            {
                "id": a["id"],
                "label": label,
                "source": "owner-item-label",
                "issue": None,
                "detail": detail,
                "note": "",
            }
        )
    return out


def other_rows(rows: list[dict], rules_path: Path) -> list[dict]:
    """The outcome mapping and the fixture labels, each marked as such."""
    rules = load_rules(rules_path)
    verdicts = issue_verdicts(rows)
    out = []
    for r in rows:
        o = outcome_fields(r, verdicts)
        # the decision's age when the item was built (frozen_at), as reference-from-outcomes reads it
        decided, frozen = _t((r.get("fleet_decision") or {}).get("ts")), _t(r.get("frozen_at"))
        age = (frozen - decided).total_seconds() / 86400 if decided and frozen else None
        for rule in rules:
            if matches(rule, o, age):
                if rule.get("label"):
                    out.append(
                        {
                            "id": r["id"],
                            "label": rule["label"],
                            "source": "outcome-mapping",
                            "issue": o.get("issue_number"),
                            "detail": json.dumps(
                                {k: v for k, v in rule.items() if k != "label"}, sort_keys=True
                            ),
                            "note": "",
                        }
                    )
                break
        gt = (r.get("ground_truth") or {}).get("disposition")
        if gt:
            out.append(
                {
                    "id": r["id"],
                    "label": gt,
                    "source": "fixture",
                    "issue": None,
                    "detail": "",
                    "note": ((r.get("ground_truth") or {}).get("notes") or "").strip()[:300],
                }
            )
    return out


def main() -> int:
    """Write verdicts.jsonl."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("items", type=Path, help="the decisions file (JSONL)")
    ap.add_argument("--sheet", type=Path, required=True, help="the answered sheet's directory")
    ap.add_argument("--rules", type=Path, default=HERE / "outcomes.yaml")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = [json.loads(x) for x in args.items.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if not r.get("is_test_signal")]
    part_b = args.sheet / "items_model.csv"
    if not part_b.is_file():
        raise SystemExit(f"{part_b} is missing: run label_with_model.py, and answer its disagreements, first")
    a = owner_issue_rows(rows, _csv(args.sheet / "issues.csv"))
    b = owner_item_rows(_csv(part_b))
    dup = {x["id"] for x in a} & {x["id"] for x in b}
    if dup:
        raise SystemExit(f"{len(dup)} decision(s) labelled in both parts, e.g. {sorted(dup)[:3]}")
    unanswered = [x["id"] for x in _csv(part_b) if x["id"] not in {y["id"] for y in b}]
    if unanswered:
        raise SystemExit(f"{len(unanswered)} part B row(s) have no label yet, e.g. {unanswered[:3]}")
    allrows = a + b + other_rows(rows, args.rules)
    args.out.write_text(
        "".join(json.dumps(x, sort_keys=True, ensure_ascii=False) + "\n" for x in allrows), encoding="utf-8"
    )
    by: dict[str, dict[str, int]] = {}
    for x in allrows:
        by.setdefault(x["source"], {}).setdefault(x["label"], 0)
        by[x["source"]][x["label"]] += 1
    print(json.dumps({"rows": len(allrows), "by_source": by}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
