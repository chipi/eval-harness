"""The triage fleet's adapter: replay a triage decision through the fleet's own code.

An item is `{signal, probes}`: the signal the agent received and the answer to every probe it could
ask, as of the decision's time. `call_system` hands both to the fleet's `investigate(signal,
probe_table=probes)`, so the model asks for probes and gets the frozen answers, and the fleet's own
gates run as in production. The output is the decision as JSON.

The fleet's code comes from a checkout named by TRIAGE_FLEET_SRC (the signal-fleet folder of the
fleet's repository, at a recorded commit). Before the fleet's config is imported, its own tracing is
switched off (SF_OBSERV_DISABLED), its trace ids are disabled, and every model call is tagged
`evh-eval`, so the gateway's Langfuse log tells evaluation traffic from production's.

params:
  provider   "gateway" (the fleet's model gateway, OpenAI-style; URL and key from the environment:
             SF_OPENROUTER_URL, OPENROUTER_API_KEY) or "stub" (no model: a fixed decision, offline,
             for wiring the path through)
  model      the gateway alias, e.g. fleet-triage-pro, or a local server's model tag (gpt-oss:20b)
  url        optional: the chat-completions URL for this arm, e.g. a self-hosted Ollama
             (http://127.0.0.1:11434/v1/chat/completions); default SF_OPENROUTER_URL. A local server
             takes any key.
  machine    optional: where a self-hosted model runs (x3, dgx, mac), recorded with the run
  call_timeout_s   optional: each model call's time limit, in place of the fleet's own 90 s (a self-hosted
             model on slow hardware takes longer than production's budget; the run records the value)
  reasoning_effort   optional: sent with every model call (e.g. "none": a reasoning model answers without
             thinking first). The fleet sends none, so each model reasons at its server's default
  max_tokens optional: a cap on each reply's tokens. The fleet sends none, so a reply is unbounded
  usd_per_mtok_in, usd_per_mtok_out   the model's prices, for cost (the fleet knows only its own)
  stub_disposition   with provider stub: the decision it always reaches (default dismiss)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from evaluation_harness.adapter import Result  # noqa: E402

PRIMARY_METRIC = "triage_cost"
#: What one missed real problem costs, in false alarms (owner, 2026-10-30): 5 decides; 3 and 10 show whether
#: the ranking depends on the number. A false alarm costs 1; a right decision 0.
MISS_PRICE, MISS_PRICES_SHOWN = 5, (3, 10)
METRIC_DIRECTIONS = {
    "false_dismiss": "lower",
    "false_alarm": "lower",
    "silent_drop": "lower",
    "escalated": "lower",
    "table_miss": "lower",
    "no_decision": "lower",
    "deferred": "lower",
    "triage_cost": "lower",
    "triage_cost_p3": "lower",
    "triage_cost_p10": "lower",
    "model_triage_cost": "lower",
    "model_false_dismiss": "lower",
    "model_false_alarm": "lower",
    "model_escalated": "lower",
}
#: The fleet's gates write their reason first; the decision the model made before a gate changed it.
GATE_PREFIX = {
    "dismiss gate:": "dismiss",
    "edge gate:": "dismiss",
    "cleanup gate:": "cleanup",
    "intent gate:": "file",
}
TRANSIENT_MARKERS = ("triager call failed",)
DISPOSITIONS = ("file", "dismiss", "escalate", "cleanup")

_FLEET: dict[str, Any] = {}


def _fleet() -> Any:
    """The fleet's triage module, imported once, with its tracing off and every call tagged."""
    if "triage" in _FLEET:
        return _FLEET["triage"]
    src = os.environ.get("TRIAGE_FLEET_SRC", "")
    mvp = Path(src) / "mvp" if src else None
    if mvp is None or not (mvp / "triage.py").is_file():
        raise RuntimeError(
            f"TRIAGE_FLEET_SRC must name the fleet's signal-fleet folder (with mvp/triage.py); got {src!r}"
        )
    os.environ["SF_OBSERV_DISABLED"] = "1"
    os.environ.setdefault("OPENROUTER_API_KEY", "unset")
    sys.path.insert(0, str(mvp))
    import observ  # noqa: PLC0415
    import triage  # noqa: PLC0415

    observ.new_trace_id = lambda *a, **k: None
    real_post = triage.post_json

    def tagged(url: str, body: dict, *a: Any, **k: Any) -> Any:
        body = {
            **body,
            "metadata": {**(body.get("metadata") or {}), "tags": ["evh-eval"], "trace_name": "evh-eval"},
        }
        if _FLEET.get("timeout"):  # an arm's call_timeout_s, over the fleet's own (90 s)
            k["timeout"] = _FLEET["timeout"]
        body.update(_FLEET.get("body_extra") or {})  # an arm's reasoning_effort / max_tokens
        # Each call measured for `evh arm-smoke` (RFC-020): time, tokens, reasoning, how it ended.
        rec: dict[str, Any] = {}
        t0 = time.monotonic()
        try:
            resp = real_post(url, body, *a, **k)
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"[:160]
            raise
        else:
            choice = (resp.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            usage = resp.get("usage") or {}
            rec.update(
                tokens_out=usage.get("completion_tokens"),
                reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
                reasoning_chars=len(msg.get("reasoning") or msg.get("reasoning_content") or ""),
                finish_reason=choice.get("finish_reason"),
                answered=bool((msg.get("content") or "").strip()),
            )
            return resp
        finally:
            rec["s"] = round(time.monotonic() - t0, 2)
            _FLEET.setdefault("calls", []).append(rec)

    triage.post_json = tagged
    real_gate = triage._gate

    def gate(d: dict, *a: Any, **k: Any) -> Any:
        # the model's own decision, before the fleet's deterministic gates may change it
        _FLEET["model_disposition"] = d.get("disposition")
        return real_gate(d, *a, **k)

    triage._gate = gate
    _FLEET["triage"] = triage
    _FLEET["real_call"] = triage._call
    return triage


#: The fleet modules a replay runs: what the decision depends on besides the model.
FLEET_MODULES = ("triage.py", "probes.py", "guards.py", "config.py")


def fingerprint(params: dict[str, Any]) -> dict[str, Any]:
    """What the replay is, for the run's fingerprint: the fleet's code by content, its commit when
    TRIAGE_FLEET_COMMIT or the arm's `fleet_commit` names it (the checkout's git is not read: a pinned checkout
    is often an extracted archive), and the sha256 of the system prompt it sends, which the harness keeps as a
    setting. The model is the deployment's, not declared here."""
    import hashlib  # noqa: PLC0415

    triage = _fleet()
    mvp = Path(triage.__file__).parent
    code = hashlib.sha256()
    for name in FLEET_MODULES:
        f = mvp / name
        code.update(name.encode() + b"\0" + (f.read_bytes() if f.is_file() else b""))
    commit = os.environ.get("TRIAGE_FLEET_COMMIT") or params.get("fleet_commit")
    return {
        "id": params.get("model") or params.get("provider"),
        "fleet_code_sha256": code.hexdigest(),
        "fleet_commit": commit,
        "prompt_sha256": hashlib.sha256(triage._sys().encode()).hexdigest(),
    }


def _stub_call(disposition: str):
    """A stand-in for the model: asks for one probe, then decides `disposition` citing it."""

    def call(messages: list, trace_id: Any = None, step: Any = None) -> tuple:
        del trace_id, step  # the fleet's _call signature, passed by keyword; a stand-in uses neither
        if len(messages) <= 2:
            return json.dumps({"action": "probe", "probe": "occurrence_history", "probe_args": {}}), {}
        decision = {"action": "decide", "disposition": disposition, "reason": "stub", "certainty": "low"}
        if disposition == "dismiss":
            decision["dismissal_evidence"] = "stub: occurrence_history"
        if disposition == "escalate":
            decision["question"] = "stub"
        if disposition == "cleanup":
            decision["marker"] = "stub"
        if disposition == "file":
            decision["file"] = {
                "work_type": "bug",
                "title": "stub",
                "symptom": "stub",
                "area": "stub",
                "evidence": ["stub"],
                "acceptance": [],
            }
        return json.dumps(decision), {"prompt_tokens": 1000, "completion_tokens": 100}

    return call


def call_system(text: str, params: dict[str, Any]) -> Result:
    """Replay one decision; the output is the fleet's decision as JSON."""
    item = json.loads(text)
    triage = _fleet()
    import config  # noqa: PLC0415  (the fleet's config, on sys.path once _fleet() ran)

    provider = params.get("provider", "gateway")
    if provider == "stub":
        triage._call = _stub_call(params.get("stub_disposition", "dismiss"))
    elif provider == "gateway":
        triage._call = _FLEET["real_call"]
        config.TRIAGE_MODEL = params["model"]
        _FLEET.setdefault("default_url", config.OPENROUTER_URL)
        config.OPENROUTER_URL = params.get("url") or _FLEET["default_url"]
        _FLEET["timeout"] = params.get("call_timeout_s")
        _FLEET["body_extra"] = {k: params[k] for k in ("reasoning_effort", "max_tokens") if k in params}
    else:
        raise ValueError(f"provider {provider!r}: gateway or stub")
    t0 = time.monotonic()
    _FLEET["model_disposition"] = None
    _FLEET["calls"] = []
    deferred = None
    try:
        out = triage.investigate(item["signal"], probe_table=item["probes"])
    except triage.TriageDeferred as first:
        # The fleet defers a failed model call to its next cycle. At temperature 0 some failures repeat
        # exactly: Ollama's "token repeat limit reached" (ministral-3:14b on Metal), a reasoning loop that
        # outlasts the call limit (gemma4:12b). Production would defer that signal every cycle. One more
        # attempt tells a flake from that; the same failure twice is recorded as no decision (fleet gap F8).
        try:
            out = triage.investigate(item["signal"], probe_table=item["probes"])
        except triage.TriageDeferred as again:
            if str(again) != str(first):
                raise
            deferred, out = str(again), None
    no_decision = out is None
    if no_decision:
        # The fleet's own gap (F7): investigate() falls off its loop and returns None when the model's reply
        # is empty on the last turn (a reasoning model's answer cut off). Production would then fail on it.
        # The replay records it, and a repeated deferral, as the fleet's own "no terminal decision", which
        # score() counts as wrong on both sides (owner, 2026-10-31), never as the escalation it falls back to.
        out = {
            "disposition": "escalate",
            "reason": f"no terminal decision: {deferred} (twice)"
            if deferred
            else "no terminal decision: the model's last reply was empty",
            "question": "triager did not reach a disposition",
            "_meta": {},
        }
    out["model_disposition"] = _FLEET["model_disposition"] or out.get("disposition")
    ms = (time.monotonic() - t0) * 1000
    meta = out.get("_meta") or {}
    usage = meta.get("usage") or {}
    tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    cost = (tin * pin + tout * pout) / 1e6 if None not in (tin, tout, pin, pout) else None
    return Result(
        output=json.dumps({k: v for k, v in out.items() if k != "_meta"}, sort_keys=True),
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost,
        latency_ms=ms,
        extra={
            "n_probes": float(meta.get("n_probes") or 0),
            "table_miss": float(bool(meta.get("table_miss"))),
            "no_decision": float(no_decision),
            "deferred": float(deferred is not None),
        },
        meta={
            "model": meta.get("model"),
            "prompt_sha": meta.get("prompt_sha"),
            "gates": meta.get("gates"),
            "calls": list(_FLEET.get("calls") or []),
        },
    )


def _label(reference: str) -> tuple[str | None, str | None]:
    """(disposition, correct_autonomous) from a bare label or a JSON reference."""
    text = reference.strip()
    if text.startswith("{"):
        d = json.loads(text)
        return d.get("disposition"), d.get("correct_autonomous")
    return text, None


def model_disposition(out: dict) -> str | None:
    """The model's own decision, before the fleet's gates: recorded by call_system, or read back from
    the reason a gate wrote first (outputs from before it was recorded, and production's ledger)."""
    if out.get("model_disposition"):
        return out["model_disposition"]
    reason = str(out.get("reason") or "")
    return next((d for p, d in GATE_PREFIX.items() if reason.startswith(p)), out.get("disposition"))


def score(output: str, reference: str | None) -> dict[str, float]:
    """Per item, as the fleet decided (after its gates): `escalated` always; with a reference,
    `correct`, `false_dismiss`, `false_alarm`, `silent_drop`. And the same as the model decided, before
    the gates: `model_escalated`, `model_correct`, `model_false_dismiss`, `model_false_alarm`.
    Unlabelled items carry no reference key at all, so they never count."""
    out = json.loads(output) or {}
    if str(out.get("reason") or "").startswith(NO_DECISION):
        # No decision (owner, 2026-10-31): a failure never helps. Production delivers nothing, so the
        # fleet's fallback escalation is not credited: a miss on a real problem, a false alarm on noise.
        row = _no_decision(reference)
        row.update({f"model_{k}": v for k, v in row.items() if k != "silent_drop"})
    else:
        row = _score(out.get("disposition"), reference)
        row.update(
            {f"model_{k}": v for k, v in _score(model_disposition(out), reference).items() if k != "silent_drop"}
        )
    if "false_dismiss" in row or "false_alarm" in row:
        # The combined cost (owner, 2026-10-30): a missed real problem costs MISS_PRICE false alarms.
        row["triage_cost"] = _cost(row, "", MISS_PRICE)
        for p in MISS_PRICES_SHOWN:
            row[f"triage_cost_p{p}"] = _cost(row, "", p)
        row["model_triage_cost"] = _cost(row, "model_", MISS_PRICE)
    return row


def _cost(row: dict, prefix: str, price: float) -> float:
    """One decision's cost: `price` for a missed real problem, 1 for a false alarm, 0 when right."""
    return price * row.get(f"{prefix}false_dismiss", 0.0) + row.get(f"{prefix}false_alarm", 0.0)


#: How the replay's own fallback names a decision the fleet never reached (adapter.run).
NO_DECISION = "no terminal decision"


def _no_decision(reference: str | None) -> dict[str, float]:
    """A decision never reached: wrong whatever the label, a miss when the problem was real and a false alarm
    when it was noise; never escalated, since production delivered nothing."""
    row = {"escalated": 0.0}
    if reference is None:
        return row
    want, _ = _label(reference)
    want = "dismiss" if want == "not-file" else want
    if want not in (*DISPOSITIONS, "file-or-escalate"):
        return row
    row["correct"] = 0.0
    if want in ("file", "escalate", "file-or-escalate"):
        row["false_dismiss"] = 1.0
    if want in ("dismiss", "cleanup"):
        row["false_alarm"] = 1.0
    return row


def _score(got: str | None, reference: str | None) -> dict[str, float]:
    row = {"escalated": float(got == "escalate")}
    if reference is None:
        return row
    want, autonomous = _label(reference)
    if want == "not-file":
        want = "dismiss"
    # A real problem (its issue was fixed): filing it and escalating it are both right.
    ok = ("file", "escalate") if want == "file-or-escalate" else (want,)
    if want not in (*DISPOSITIONS, "file-or-escalate"):
        return row
    row["correct"] = float(got in ok)
    if want in ("file", "escalate", "file-or-escalate"):
        row["false_dismiss"] = float(got in ("dismiss", "cleanup"))
    if want in ("dismiss", "cleanup"):
        row["false_alarm"] = float(got in ("file", "escalate"))
    if autonomous == "escalate":
        row["silent_drop"] = float(got == "dismiss")
    return row
