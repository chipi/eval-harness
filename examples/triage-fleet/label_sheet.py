#!/usr/bin/env python3
"""The owner's labelling sheet for the triage decisions: what to confirm before verdicts.jsonl exists.

    python examples/triage-fleet/label_sheet.py orrery-triage-items.jsonl --out sheet/

Writes sheet/label_sheet.md (to read) and sheet/issues.csv and sheet/items.csv (to answer in). Test
signals are left out.

Part A, one row per issue the fleet filed that was closed: the owner's close comment, the verdict
proposed from it (fixed, noise, duplicate, unknown) and the label that gives the decisions linked
to it (fixed -> file or escalate, noise -> dismiss). The owner answers `yes` or writes the right verdict.

Part B, one row per `exact` decision no confirmed issue verdict reaches: what production decided,
and what happened afterwards. The owner answers `yes` (production was right) or writes the label.

Nothing here decides a label: an answered sheet is what verdicts.jsonl is written from, each row
marked owner-issue-verdict or owner-item-label.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

FIXED = re.compile(
    r"\bfixed (in|by)\b|since the fix|no [\w ]*event since|verified on prod: no |none since from fixed builds"
    r"|^(handled|resolved)\b|now caught",
    re.I,
)
#: "Duplicate of #557", "Same root cause as #447": the other issue's verdict, one or two hops away.
SAME_AS = re.compile(r"(?:duplicate of|same root cause as) #(\d+)", re.I)
NOISE = re.compile(r"\bnoise\b|not \w+ code|staging bundle|low-signal rollup|closing \(readiness", re.I)
#: fixed: it should not have been dismissed (filing or escalating it were both right).
LABEL_OF = {"fixed": "file/escalate", "noise": "dismiss"}


def reaches(li: dict) -> bool:
    """Whether an issue's verdict labels this decision: the decision that filed it, or an earlier one
    on the same fingerprint (a missed problem). Not a decision made while it was open (production
    was right not to file it again: outcomes.yaml skips those too), and not a match on the title
    alone: one title ("Importing a module script failed") links up to 37 fingerprints."""
    rel = li.get("relation")
    return rel == "created_by_this_decision" or (
        rel == "created_later" and li.get("matched_by") == "fingerprint"
    )


def close_comments(issue: dict) -> list[str]:
    """The comments beside the issue's closes, the person's own first."""
    cs = [
        e["comment"]
        for e in issue.get("close_reopen_events") or []
        if e.get("type") == "closed" and (e.get("comment") or {}).get("text")
    ]
    return [c["text"] for c in cs if not c.get("fleet_comment")] + [
        c["text"] for c in cs if c.get("fleet_comment")
    ]


def proposed_verdict(issue: dict) -> str:
    """fixed, noise, duplicate, open or unknown, from the close comments (GitHub's close reason is
    COMPLETED on nearly every close, so it says nothing)."""
    if issue.get("state") == "OPEN":
        return "open"
    text = " ".join(close_comments(issue))
    m = SAME_AS.search(text)
    if m:
        return f"same as #{m.group(1)}"
    if FIXED.search(text):
        return "fixed"
    if NOISE.search(text):
        return "noise"
    return "duplicate" if issue.get("duplicate_of") else "unknown"


def resolved(verdicts: dict[int, str], n: int) -> str:
    """The verdict of issue n, following "same as #m" up to two hops."""
    v = verdicts.get(n, "unknown")
    for _ in range(2):
        m = re.fullmatch(r"same as #(\d+)", v)
        if not m:
            break
        v = verdicts.get(int(m.group(1)), "unknown")
    return v


def _short(s: object, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def build(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """(issue rows, item rows, counts)."""
    issues: dict[int, dict] = {}
    linked: dict[int, list[tuple[dict, dict]]] = defaultdict(list)
    for r in rows:
        for li in (r.get("outcome") or {}).get("linked_issues") or []:
            issues.setdefault(li["number"], li)
            linked[li["number"]].append((li, r))
    verdicts = {n: proposed_verdict(li) for n, li in issues.items()}
    a = []
    for n in sorted(issues):
        li = issues[n]
        if li.get("state") != "CLOSED":
            continue
        v = verdicts[n]
        r_v = resolved(verdicts, n)
        reached = [r for x, r in linked[n] if reaches(x)]
        disp = Counter((r.get("fleet_decision") or {}).get("disposition") or "none" for r in reached)
        cc = close_comments(li)
        a.append(
            {
                "issue": n,
                "title": _short(li.get("title"), 90),
                "closed_at": (li.get("closed_at") or "")[:10],
                "reopens": li.get("reopen_count", 0),
                "close_comment": _short(cc[0] if cc else "", 300),
                "proposed_verdict": v if v == r_v else f"{v} ({r_v})",
                "label_for_linked": LABEL_OF.get(r_v, ""),
                "decisions_reached": len(reached),
                "production_decided": ", ".join(f"{k} {c}" for k, c in sorted(disp.items())),
                "answer": "",
            }
        )
    labelled_by_issue = {
        r["id"] for x in a if x["label_for_linked"] for li, r in linked[x["issue"]] if reaches(li)
    }
    b = []
    for r in rows:
        prov = r.get("provenance") or {}
        if prov.get("evidence_level") != "exact" or r["id"] in labelled_by_issue:
            continue
        fd, sig, out = r.get("fleet_decision") or {}, r.get("signal") or {}, r.get("outcome") or {}
        rels = Counter(li.get("relation") for li in out.get("linked_issues") or [])
        b.append(
            {
                "id": r["id"],
                "alert": _short(sig.get("alertname"), 70),
                "summary": _short(sig.get("summary"), 120),
                "production_decided": fd.get("disposition")
                or ("none (the triager failed)" if r.get("decision_kind") == "triager_failure" else "none"),
                "reason": _short(fd.get("reason"), 160),
                "seen_again": len(out.get("later_decisions_same_fingerprint") or []),
                "issues": ", ".join(f"{k} {c}" for k, c in sorted(rels.items())) or "none",
                "answer": "",
            }
        )
    counts = {
        "decisions": len(rows),
        "issues_linked": len(issues),
        "issues_closed": len(a),
        "verdicts": dict(Counter(resolved(verdicts, x["issue"]) for x in a)),
        "decisions_labelled_by_issue": len(labelled_by_issue),
        "exact_items_to_label": len(b),
    }
    return a, b, counts


def _md_table(rows: list[dict], keys: list[str]) -> str:
    def cell(v: object) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")

    head = "| " + " | ".join(keys) + " |\n|" + "---|" * len(keys) + "\n"
    return head + "".join("| " + " | ".join(cell(r[k]) for k in keys) + " |\n" for r in rows)


def main() -> int:
    """Write the sheet."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("items", type=Path, help="the decisions file (JSONL)")
    ap.add_argument("--out", type=Path, required=True, help="a directory for the sheet")
    args = ap.parse_args()
    rows = [json.loads(x) for x in args.items.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if not r.get("is_test_signal")]
    a, b, counts = build(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (("issues.csv", a), ("items.csv", b)):
        with (args.out / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]) if data else ["answer"])
            w.writeheader()
            w.writerows(data)
    v = counts["verdicts"]
    md = (
        "# Triage decisions: the owner's labelling sheet\n\n"
        f"From {args.items.name}: {counts['decisions']} decisions (test signals left out), "
        f"{counts['issues_linked']} linked issues, {counts['issues_closed']} of them closed.\n\n"
        "Answer in `issues.csv` and `items.csv`, column `answer`: `yes`, or the right value. "
        "Nothing is labelled until you answer.\n\n"
        f"## A. Closed issues ({len(a)}): is the proposed verdict right?\n\n"
        f"Proposed from your close comment: {', '.join(f'{k} {c}' for k, c in sorted(v.items()))}. "
        "A verdict labels the decisions it reaches: the one that filed the issue, and earlier ones on the "
        "same fingerprint (fixed -> file or escalate, noise -> dismiss). Decisions made while it was open, and "
        "matches on the title alone, are not labelled by it. "
        f"Confirmed as proposed, they label {counts['decisions_labelled_by_issue']} decisions. "
        "`same as #N` takes that issue's verdict (shown in brackets). `duplicate` and `unknown` "
        "label nothing until you say what they are.\n\n"
        + _md_table(
            a,
            [
                "issue",
                "title",
                "close_comment",
                "proposed_verdict",
                "label_for_linked",
                "decisions_reached",
                "production_decided",
            ],
        )
        + f"\n## B. Exact decisions no issue verdict reaches ({len(b)}): was production right?\n\n"
        "`exact`: the probe answers are what the model saw. If yes, production's decision is the label; "
        "if not, write file, dismiss, escalate or cleanup.\n\n"
        + _md_table(b, ["id", "alert", "summary", "production_decided", "reason", "seen_again", "issues"])
    )
    (args.out / "label_sheet.md").write_text(md, encoding="utf-8")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
