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
    adapter.score(out("dismiss"), None) == {"escalated": 0.0, "model_escalated": 0.0},
)
check(
    "label file, arm dismissed: a false dismissal, not a false alarm",
    {
        k: v
        for k, v in adapter.score(out("dismiss"), "file\n").items()
        if not k.startswith(("model_", "triage_cost"))
    }
    == {"escalated": 0.0, "correct": 0.0, "false_dismiss": 1.0},
)
check(
    "label dismiss, arm escalated: a false alarm",
    {
        k: v
        for k, v in adapter.score(out("escalate"), "dismiss").items()
        if not k.startswith(("model_", "triage_cost"))
    }
    == {"escalated": 1.0, "correct": 0.0, "false_alarm": 1.0},
)
check("not-file counts as dismiss", adapter.score(out("dismiss"), "not-file")["correct"] == 1.0)
check(
    "file-or-escalate: an escalation is correct, a dismissal is a false dismissal",
    {
        k: v
        for k, v in adapter.score(out("escalate"), "file-or-escalate").items()
        if not k.startswith(("model_", "triage_cost"))
    }
    == {"escalated": 1.0, "correct": 1.0, "false_dismiss": 0.0}
    and adapter.score(out("file"), "file-or-escalate")["correct"] == 1.0
    and adapter.score(out("dismiss"), "file-or-escalate")["false_dismiss"] == 1.0,
)
check(
    "JSON reference with correct_autonomous=escalate: a dismissal is a silent drop",
    adapter.score(out("dismiss"), json.dumps({"disposition": "escalate", "correct_autonomous": "escalate"}))[
        "silent_drop"
    ]
    == 1.0,
)
check(
    "an unknown label scores nothing but escalated",
    adapter.score(out("file"), "maybe") == {"escalated": 0.0, "model_escalated": 0.0},
)
c_miss = adapter.score(out("dismiss"), "file-or-escalate")
c_alarm = adapter.score(out("file"), "dismiss")
c_right = adapter.score(out("dismiss"), "dismiss")
check(
    "the combined cost: a miss costs 5 (3 and 10 shown), a false alarm 1, a right decision 0",
    (c_miss["triage_cost"], c_miss["triage_cost_p3"], c_miss["triage_cost_p10"]) == (5.0, 3.0, 10.0)
    and c_alarm["triage_cost"] == 1.0
    and c_right["triage_cost"] == 0.0,
    (c_miss, c_alarm, c_right),
)
check("the combined cost: unlabelled, none", "triage_cost" not in adapter.score(out("file"), None))
gated = json.dumps(
    {"disposition": "escalate", "reason": "dismiss gate: no independent corroborating probe — x"}
)
s_g = adapter.score(gated, "dismiss")
check(
    "pre-gate: the model's dismissal a gate escalated is right for the model, a false alarm for the fleet",
    s_g["false_alarm"] == 1.0 and s_g["model_correct"] == 1.0 and s_g["model_false_alarm"] == 0.0,
    s_g,
)
rec = json.dumps({"disposition": "escalate", "model_disposition": "file", "reason": "intent gate: x"})
check("pre-gate: a recorded model_disposition wins", adapter.score(rec, "file")["model_correct"] == 1.0)

# ── the importer ───────────────────────────────────────────────────────────────────────────


def issue(n, relation, matched_by="fingerprint", comment="", state="CLOSED", **kw):
    ev = [{"type": "closed", "comment": {"text": comment, "fleet_comment": False}}] if comment else []
    return {
        "number": n,
        "relation": relation,
        "matched_by": matched_by,
        "state": state,
        "labels": [],
        "close_reopen_events": ev,
        **kw,
    }


def decision(i, disposition, linked, ts="2026-10-01T00:00:00Z", later=(), **kw):
    return {
        "id": f"orrery-X-{i}-{ts}",
        "signal": {"summary": "TypeError"},
        "probes": {"event_detail:{}": "stack"},
        "fleet_decision": {
            "ts": ts,
            "disposition": disposition,
            "stage": "propose",
            "model": "m",
            "fingerprint": f"glitchtip:X-{i}",
        },
        "provenance": {"evidence_level": "exact"},
        "decision_kind": "model",
        "is_test_signal": False,
        "outcome": {"linked_issues": linked, "later_decisions_same_fingerprint": list(later)},
        "ground_truth": {"disposition": None},
        **kw,
    }


rows = [
    # missed, then filed two days later on the same fingerprint, fixed
    decision(
        1,
        "dismiss",
        [issue(7, "created_later", comment="Fixed in v0.8.0", created_at="2026-10-03T00:00:00Z")],
        later=[{"disposition": "file", "ts": "2026-10-03T00:00:00Z"}],
    ),
    # filed it, closed as the same as #7: takes #7's verdict
    decision(2, "file", [issue(8, "created_by_this_decision", comment="Duplicate of #7 - same alert")]),
    # only a title match on a noise issue: no verdict reaches it
    decision(3, "dismiss", [issue(9, "created_later", matched_by="title", comment="external browser noise")]),
    # decided while an issue on its fingerprint was open
    decision(4, "dismiss", [issue(7, "existing_at_decision")]),
    decision(5, "cleanup", [], is_test_signal=True),
]
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "x.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    recs = {r["id"].split("-")[2]: r for r in importer.Importer({}).records({"path": str(p)})}
r1 = recs["1"]
check("importer: a well-formed record", not _importers.problems(r1), _importers.problems(r1))
check("importer: the body is only what the agent sees", set(r1["body"]) == {"signal", "probes"})
check("importer: decision_kind is a field", r1["fields"]["decision_kind"] == "model")
o = r1["outcome"]
check(
    "importer: a missed problem: the later issue's verdict, filing two days later",
    o["issue_number"] == 7
    and o["issue_verdict"] == "fixed"
    and o["days_to_filing"] == 2.0
    and o["later_file_within_14d"]
    and not o["test_signal"],
    o,
)
check("importer: 'Duplicate of #7' takes #7's verdict", recs["2"]["outcome"]["issue_verdict"] == "fixed")
check(
    "importer: a title-only match carries no verdict",
    recs["3"]["outcome"]["issue_number"] is None and recs["3"]["outcome"]["issue_verdict"] is None,
)
check(
    "importer: an issue open at the decision is recorded, not its verdict",
    recs["4"]["outcome"]["issue_predates_decision"] and recs["4"]["outcome"]["issue_verdict"] is None,
)
check("importer: is_test_signal carried", recs["5"]["outcome"]["test_signal"] is True)
check(
    "importer: a noise close comment",
    importer.proposed_verdict(
        issue(1, "x", comment="Stale-candidate review: external browser noise, not orrery code")
    )
    == "noise",
)
check(
    "importer: a close with no comment is unknown, whatever its reason",
    importer.proposed_verdict({"state": "CLOSED", "state_reason": "COMPLETED"}) == "unknown",
)
check(
    "importer: the person's comment is read before the fleet's",
    importer.close_comments(
        {
            "close_reopen_events": [
                {"type": "closed", "comment": {"text": "fleet", "fleet_comment": True}},
                {"type": "closed", "comment": {"text": "person", "fleet_comment": False}},
            ]
        }
    )
    == ["person", "fleet"],
)

# ── the adapter through the fleet's code (stand-in model) ──────────────────────────────────
if (
    os.environ.get("TRIAGE_FLEET_SRC")
    and (Path(os.environ["TRIAGE_FLEET_SRC"]) / "mvp" / "triage.py").is_file()
):
    res = adapter.call_system(json.dumps(r1["body"]), {"provider": "stub", "stub_disposition": "escalate"})
    got = json.loads(res.output)
    check("adapter: the fleet decides, through its gates", got.get("disposition") == "escalate", got)
    check(
        "adapter: tokens recorded, cost unpriced without prices",
        res.tokens_in == 1000 and res.cost_usd is None,
    )

    real_stub, calls = adapter._stub_call, {"n": 0}

    def failing(_disposition, fail_first_only=False):
        inner = real_stub("dismiss")

        def call(messages, trace_id=None, step=None):
            calls["n"] += 1
            if fail_first_only and calls["n"] > 1:
                return inner(messages, trace_id=trace_id, step=step)
            raise RuntimeError("prediction aborted, token repeat limit reached")

        return call

    adapter._stub_call = failing
    res = adapter.call_system(json.dumps(r1["body"]), {"provider": "stub"})
    got = json.loads(res.output)
    check(
        "adapter: the same deferral twice is no decision (an escalation)",
        got.get("disposition") == "escalate"
        and res.extra["deferred"] == 1.0
        and res.extra["no_decision"] == 1.0
        and calls["n"] == 2,
        (got, res.extra, calls),
    )
    calls["n"] = 0
    adapter._stub_call = lambda d: failing(d, fail_first_only=True)
    res = adapter.call_system(json.dumps(r1["body"]), {"provider": "stub"})
    check(
        "adapter: a deferral that clears on the next attempt is the model's decision",
        res.extra["deferred"] == 0.0 and res.extra["no_decision"] == 0.0,
        res.extra,
    )
    adapter._stub_call = real_stub

    import http.server
    import threading

    seen: list = []

    class Fake(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            reply = {"action": "decide", "disposition": "escalate", "reason": "r", "question": "q"}
            data = json.dumps(
                {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
    res = adapter.call_system(
        json.dumps(r1["body"]),
        {"provider": "gateway", "model": "m", "url": url, "reasoning_effort": "none", "max_tokens": 512},
    )
    reported = res.meta.get("calls") or []
    check(
        "adapter: each model call is reported for evh arm-smoke (time, how it ended, answered)",
        len(reported) == 1 and reported[0].get("answered") is True and "s" in reported[0],
        reported,
    )
    check(
        "adapter: reasoning_effort and max_tokens reach the model call",
        seen and seen[-1].get("reasoning_effort") == "none" and seen[-1].get("max_tokens") == 512,
        seen[-1] if seen else None,
    )
    adapter.call_system(json.dumps(r1["body"]), {"provider": "gateway", "model": "m", "url": url})
    check(
        "adapter: an arm without them sends the fleet's request unchanged",
        "reasoning_effort" not in seen[-1] and "max_tokens" not in seen[-1],
        seen[-1],
    )
    srv.shutdown()
else:
    print("  --   adapter through the fleet: skipped (TRIAGE_FLEET_SRC names no checkout)")

sys.exit(summary())
