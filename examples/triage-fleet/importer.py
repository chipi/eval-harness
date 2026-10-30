"""The triage fleet's importer: one record per triage decision, from the fleet's own export.

The fleet's build script (signal-fleet, committed there) reads its ledger, GlitchTip, the Victoria
stores, Langfuse and GitHub, and writes one JSON line per decision. This importer turns a line into
a record for `evh capture`:

  id          the occurrence id
  body        {signal, probes}: exactly what the agent can see, nothing about what happened next
  fields      evidence_level, fleet_disposition, fleet_model, stage, fingerprint, decision_date
  created_at  when the fleet decided
  outcome     FLAT fields the reference rules read (RFC-019 §5: the project computes them):
                issue_number, issue_verdict (fixed / noise / duplicate / open / unknown: from the close
                comment when the export carries it), issue_state_reason, is_escalation_issue,
                is_config_followup, issue_predates_decision, days_to_filing, reopened,
                seen_again, later_file_within_14d, test_signal, and the fixture labels

    evh capture --importer examples/triage-fleet/importer.py:Importer \\
        --query '{"path": "orrery-triage-items.jsonl"}' --capture orrery_2026_10
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

FIXED = re.compile(r"\bfixed (in|by)\b|since the fix|no [\w ]*event since|verified on prod: no ", re.I)
NOISE = re.compile(r"\bnoise\b|not \w+ code|staging bundle|low-signal rollup|closing \(readiness", re.I)


def _t(s: Any) -> dt.datetime | None:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def verdict_of(github: dict) -> str:
    """The issue's verdict from the person's close comment, when the export carries one; else from
    its state. GitHub's close reason alone is not a verdict here: it is COMPLETED on nearly every close."""
    if github.get("duplicate_of"):
        return "duplicate"
    if github.get("state") == "OPEN":
        return "open"
    comments = [str(e.get("comment") or "") for e in github.get("close_events") or []]
    text = " ".join(comments)
    if FIXED.search(text):
        return "fixed"
    if NOISE.search(text):
        return "noise"
    return "unknown"


def outcome_fields(row: dict) -> dict:
    """The flat outcome fields for one decision."""
    fd, out = row.get("fleet_decision") or {}, row.get("outcome") or {}
    decided = _t(fd.get("ts"))
    fi = out.get("filed_issue") or {}
    gh = fi.get("github") or {}
    later = out.get("later_decisions_same_fingerprint") or []
    filed = _t(fi.get("filed_at"))
    days_to_filing = round((filed - decided).total_seconds() / 86400, 3) if filed and decided else None
    later_file = any(
        x.get("disposition") == "file"
        and (_t(x.get("ts")) or decided)
        and decided
        and 0 <= ((_t(x.get("ts")) - decided).total_seconds() / 86400) <= 14
        for x in later
        if _t(x.get("ts"))
    )
    gt = row.get("ground_truth") or {}
    return {
        "issue_number": fi.get("number"),
        "issue_verdict": verdict_of(gh) if fi else None,
        "issue_state_reason": gh.get("state_reason"),
        "is_escalation_issue": "triage-fleet/escalated" in (gh.get("labels") or []),
        "is_config_followup": "config-enhancement" in (gh.get("labels") or [])
        and fd.get("disposition") == "dismiss",
        "issue_predates_decision": bool(filed and decided and (filed - decided).total_seconds() < -60),
        "days_to_filing": days_to_filing,
        "reopened": bool(gh.get("reopen_count")),
        "seen_again": bool(later),
        "later_file_within_14d": later_file,
        "test_signal": not fd.get("stage"),
        "fleet_disposition": fd.get("disposition"),
        "fixture_label": gt.get("disposition"),
        "fixture_correct_autonomous": gt.get("correct_autonomous"),
    }


class Importer:
    """Records from the fleet's per-decision export (JSON lines)."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def records(self, query: dict) -> Iterator[dict]:
        """One record per line of the query's `path`."""
        path = Path(query["path"])
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                fd = row.get("fleet_decision") or {}
                prov = row.get("provenance") or {}
                ts = fd.get("ts") or prov.get("decision_time")
                yield {
                    "id": row["id"],
                    "body": {"signal": row.get("signal"), "probes": row.get("probes")},
                    "fields": {
                        "evidence_level": prov.get("evidence_level"),
                        "fleet_disposition": fd.get("disposition"),
                        "fleet_model": fd.get("model"),
                        "stage": fd.get("stage") or "",
                        "fingerprint": fd.get("fingerprint"),
                        "decision_date": str(ts)[:10] if ts else None,
                    },
                    "created_at": ts,
                    "source": {"system": "signal-fleet"},
                    "outcome": outcome_fields(row),
                }
