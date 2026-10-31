"""The triage fleet's importer: one record per triage decision, from the fleet's own export.

The fleet's build script (signal-fleet/datasets/build_orrery_items.py) reads its ledger, GlitchTip,
the Victoria stores, Langfuse and GitHub, and writes one JSON line per decision; the published copy
is chipi-nbgd/orrery-triage on Hugging Face. This importer turns a line into a record for
`evh capture`:

  id          the occurrence id
  body        {signal, probes}: exactly what the agent can see, nothing about what happened next
  fields      evidence_level, decision_kind, fleet_disposition, fleet_model, stage, fingerprint,
              decision_date, and `labelled` (yes/no: the owner labelled it, in the query's `verdicts` file)
  created_at  when the fleet decided
  outcome     FLAT fields the reference rules read (RFC-019 §5: the project computes them):
                issue_number, issue_relation, issue_verdict (fixed / noise / duplicate / open /
                unknown, from the owner's close comments), issue_state_reason, is_escalation_issue,
                is_config_followup, issue_predates_decision, days_to_filing, reopened, seen_again,
                later_file_within_14d, test_signal, decision_kind, fleet_disposition, fixture_label

The decision's issue is the linked issue whose verdict reaches it (`reaches`): the one it filed, or
one filed later on its fingerprint. Title-only matches never carry a verdict: one title links up to
37 fingerprints.

    evh capture --importer examples/triage-fleet/importer.py:Importer \\
        --query '{"path": "decisions.jsonl", "verdicts": "verdicts.jsonl"}' --capture orrery_2026_10
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

FIXED = re.compile(
    r"\bfixed (in|by)\b|since the fix|no [\w ]*event since|verified on prod: no |none since from fixed builds"
    r"|^(handled|resolved)\b|now caught",
    re.I,
)
NOISE = re.compile(r"\bnoise\b|not \w+ code|staging bundle|low-signal rollup|closing \(readiness", re.I)
#: "Duplicate of #557", "Same root cause as #447": the other issue's verdict, one or two hops away.
SAME_AS = re.compile(r"(?:duplicate of|same root cause as) #(\d+)", re.I)


def _t(s: Any) -> dt.datetime | None:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def close_comments(issue: dict) -> list[str]:
    """The comments beside the issue's closes, the person's own before the fleet's."""
    cs = [
        e["comment"]
        for e in issue.get("close_reopen_events") or []
        if e.get("type") == "closed" and (e.get("comment") or {}).get("text")
    ]
    return [c["text"] for c in cs if not c.get("fleet_comment")] + [
        c["text"] for c in cs if c.get("fleet_comment")
    ]


def proposed_verdict(issue: dict) -> str:
    """fixed, noise, duplicate, open, unknown, or "same as #N", from the close comments. GitHub's
    close reason is COMPLETED on nearly every close, so it is not a verdict here."""
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


def reaches(li: dict) -> bool:
    """Whether an issue's verdict labels this decision: the decision that filed it, or an earlier one
    on the same fingerprint (a missed problem). Not a decision made while it was open (production
    was right not to file it again), and not a match on the title alone."""
    rel = li.get("relation")
    return rel == "created_by_this_decision" or (
        rel == "created_later" and li.get("matched_by") == "fingerprint"
    )


def issue_verdicts(rows: list[dict]) -> dict[int, str]:
    """Every linked issue's proposed verdict, by number."""
    out: dict[int, str] = {}
    for r in rows:
        for li in (r.get("outcome") or {}).get("linked_issues") or []:
            out.setdefault(li["number"], proposed_verdict(li))
    return out


def own_issue(row: dict) -> dict | None:
    """The issue whose verdict reaches this decision: the one it filed, else the first one filed
    later on its fingerprint."""
    lis = [li for li in (row.get("outcome") or {}).get("linked_issues") or [] if reaches(li)]
    lis.sort(key=lambda li: (li.get("relation") != "created_by_this_decision", li.get("created_at") or ""))
    return lis[0] if lis else None


def outcome_fields(row: dict, verdicts: dict[int, str]) -> dict:
    """The flat outcome fields for one decision."""
    fd, out = row.get("fleet_decision") or {}, row.get("outcome") or {}
    decided = _t(fd.get("ts"))
    li = own_issue(row) or {}
    later = out.get("later_decisions_same_fingerprint") or []
    filed = _t(li.get("created_at"))
    days_to_filing = round((filed - decided).total_seconds() / 86400, 3) if filed and decided else None
    later_file = any(
        x.get("disposition") == "file" and decided and 0 <= ((t - decided).total_seconds() / 86400) <= 14
        for x in later
        if (t := _t(x.get("ts")))
    )
    labels = li.get("labels") or []
    gt = row.get("ground_truth") or {}
    return {
        "issue_number": li.get("number"),
        "issue_relation": li.get("relation"),
        "issue_verdict": resolved(verdicts, li["number"]) if li else None,
        "issue_state_reason": li.get("state_reason"),
        "is_escalation_issue": "triage-fleet/escalated" in labels,
        "is_config_followup": "config-enhancement" in labels and fd.get("disposition") == "dismiss",
        "issue_predates_decision": any(
            x.get("relation") == "existing_at_decision" and x.get("matched_by") == "fingerprint"
            for x in out.get("linked_issues") or []
        ),
        "days_to_filing": days_to_filing,
        "reopened": bool(li.get("reopen_count")),
        "seen_again": bool(later),
        "later_file_within_14d": later_file,
        "test_signal": bool(row.get("is_test_signal")),
        "decision_kind": row.get("decision_kind"),
        "fleet_disposition": fd.get("disposition"),
        "fixture_label": gt.get("disposition"),
    }


class Importer:
    """Records from the fleet's per-decision export (JSON lines)."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def records(self, query: dict) -> Iterator[dict]:
        """One record per line of the query's `path`."""
        rows = [
            json.loads(x) for x in Path(query["path"]).read_text(encoding="utf-8").splitlines() if x.strip()
        ]
        verdicts = issue_verdicts(rows)  # a comment can name another issue: all of them first
        owner = set()
        if query.get("verdicts"):
            for x in Path(query["verdicts"]).read_text(encoding="utf-8").splitlines():
                v = json.loads(x) if x.strip() else {}
                if str(v.get("source", "")).startswith("owner-"):
                    owner.add(v["id"])
        for row in rows:
            fd = row.get("fleet_decision") or {}
            prov = row.get("provenance") or {}
            ts = fd.get("ts") or prov.get("decision_time")
            yield {
                "id": row["id"],
                "body": {"signal": row.get("signal"), "probes": row.get("probes")},
                "fields": {
                    "evidence_level": prov.get("evidence_level"),
                    "decision_kind": row.get("decision_kind"),
                    "fleet_disposition": fd.get("disposition"),
                    "fleet_model": fd.get("model"),
                    "stage": fd.get("stage") or "",
                    "fingerprint": fd.get("fingerprint"),
                    "decision_date": str(ts)[:10] if ts else None,
                    **({"labelled": "yes" if row["id"] in owner else "no"} if query.get("verdicts") else {}),
                },
                "created_at": ts,
                "source": {"system": "signal-fleet"},
                "outcome": outcome_fields(row, verdicts),
            }
