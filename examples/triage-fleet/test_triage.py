#!/usr/bin/env python3
"""The triage example's own checks: the scorer's rules, the importer on a synthetic export, and the
adapter through the fleet's code with a stand-in model (only where TRIAGE_FLEET_SRC names a checkout).

    TRIAGE_FLEET_SRC=/path/to/signal-fleet python examples/triage-fleet/test_triage.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "harness"))
sys.path.insert(0, str(HERE))
import adapter  # noqa: E402
import importer  # noqa: E402
from evaluation_harness import _importers  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def out(d):
    return json.dumps({"disposition": d})


# ── the scorer ─────────────────────────────────────────────────────────────────────────────
check(
    "no reference: only escalated, nothing else counted",
    adapter.score(out("dismiss"), None) == {"escalated": 0.0},
)
check(
    "label file, arm dismissed: a false dismissal, not a false alarm",
    adapter.score(out("dismiss"), "file\n") == {"escalated": 0.0, "correct": 0.0, "false_dismiss": 1.0},
)
check(
    "label dismiss, arm escalated: a false alarm",
    adapter.score(out("escalate"), "dismiss") == {"escalated": 1.0, "correct": 0.0, "false_alarm": 1.0},
)
check("not-file counts as dismiss", adapter.score(out("dismiss"), "not-file")["correct"] == 1.0)
check(
    "JSON reference with correct_autonomous=escalate: a dismissal is a silent drop",
    adapter.score(out("dismiss"), json.dumps({"disposition": "escalate", "correct_autonomous": "escalate"}))[
        "silent_drop"
    ]
    == 1.0,
)
check(
    "an unknown label scores nothing but escalated", adapter.score(out("file"), "maybe") == {"escalated": 0.0}
)

# ── the importer ───────────────────────────────────────────────────────────────────────────
row = {
    "id": "glitchtip:X-1@2026-10-01T00:00:00Z",
    "signal": {"summary": "TypeError"},
    "probes": {"event_detail:{}": "stack"},
    "fleet_decision": {
        "ts": "2026-10-01T00:00:00Z",
        "disposition": "dismiss",
        "stage": "propose",
        "model": "m",
        "fingerprint": "glitchtip:X-1",
    },
    "provenance": {"evidence_level": "exact"},
    "outcome": {
        "filed_issue": {
            "number": 7,
            "filed_at": "2026-10-03T00:00:00Z",
            "github": {"state": "CLOSED", "labels": [], "close_events": [{"comment": "Fixed in v0.8.0"}]},
        },
        "later_decisions_same_fingerprint": [{"disposition": "file", "ts": "2026-10-03T00:00:00Z"}],
    },
    "ground_truth": {"disposition": None},
}
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "x.jsonl"
    p.write_text(json.dumps(row) + "\n")
    recs = list(importer.Importer({}).records({"path": str(p)}))
r0 = recs[0]
check("importer: a well-formed record", not _importers.problems(r0), _importers.problems(r0))
check("importer: the body is only what the agent sees", set(r0["body"]) == {"signal", "probes"})
o = r0["outcome"]
check(
    "importer: the verdict from the close comment; filing two days later",
    o["issue_verdict"] == "fixed"
    and o["days_to_filing"] == 2.0
    and o["later_file_within_14d"]
    and not o["test_signal"],
    o,
)
noise = {
    "state": "CLOSED",
    "close_events": [{"comment": "Stale-candidate review: external browser noise, not orrery code"}],
}
check("importer: a noise close comment", importer.verdict_of(noise) == "noise")
check(
    "importer: a close with no comment is unknown, whatever its reason",
    importer.verdict_of({"state": "CLOSED", "state_reason": "COMPLETED"}) == "unknown",
)

# ── the adapter through the fleet's code (stand-in model) ──────────────────────────────────
if (
    os.environ.get("TRIAGE_FLEET_SRC")
    and (Path(os.environ["TRIAGE_FLEET_SRC"]) / "mvp" / "triage.py").is_file()
):
    res = adapter.call_system(json.dumps(r0["body"]), {"provider": "stub", "stub_disposition": "escalate"})
    got = json.loads(res.output)
    check("adapter: the fleet decides, through its gates", got.get("disposition") == "escalate", got)
    check(
        "adapter: tokens recorded, cost unpriced without prices",
        res.tokens_in == 1000 and res.cost_usd is None,
    )
else:
    print("  --   adapter through the fleet: skipped (TRIAGE_FLEET_SRC names no checkout)")

sys.exit(summary())
