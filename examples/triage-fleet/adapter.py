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
  model      the gateway alias, e.g. fleet-triage-pro
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

PRIMARY_METRIC = "false_dismiss"
METRIC_DIRECTIONS = {
    "false_dismiss": "lower",
    "false_alarm": "lower",
    "silent_drop": "lower",
    "escalated": "lower",
    "table_miss": "lower",
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
            "TRIAGE_FLEET_SRC must name the fleet's signal-fleet folder (with mvp/triage.py); "
            f"got {src!r}"
        )
    os.environ["SF_OBSERV_DISABLED"] = "1"
    os.environ.setdefault("OPENROUTER_API_KEY", "unset")
    sys.path.insert(0, str(mvp))
    import observ  # noqa: PLC0415
    import triage  # noqa: PLC0415

    observ.new_trace_id = lambda *a, **k: None
    real_post = triage.post_json

    def tagged(url: str, body: dict, *a: Any, **k: Any) -> Any:
        body = {**body, "metadata": {**(body.get("metadata") or {}), "tags": ["evh-eval"], "trace_name": "evh-eval"}}
        return real_post(url, body, *a, **k)

    triage.post_json = tagged
    _FLEET["triage"] = triage
    _FLEET["real_call"] = triage._call
    return triage


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
            decision["file"] = {"work_type": "bug", "title": "stub", "symptom": "stub", "area": "stub",
                                "evidence": ["stub"], "acceptance": []}
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
    else:
        raise ValueError(f"provider {provider!r}: gateway or stub")
    t0 = time.monotonic()
    out = triage.investigate(item["signal"], probe_table=item["probes"])
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
        extra={"n_probes": float(meta.get("n_probes") or 0), "table_miss": float(bool(meta.get("table_miss")))},
        meta={"model": meta.get("model"), "prompt_sha": meta.get("prompt_sha"), "gates": meta.get("gates")},
    )


def _label(reference: str) -> tuple[str | None, str | None]:
    """(disposition, correct_autonomous) from a bare label or a JSON reference."""
    text = reference.strip()
    if text.startswith("{"):
        d = json.loads(text)
        return d.get("disposition"), d.get("correct_autonomous")
    return text, None


def score(output: str, reference: str | None) -> dict[str, float]:
    """Per item: `escalated` always; with a reference, `correct`, `false_dismiss`, `false_alarm`,
    `silent_drop`. Unlabelled items carry no reference key at all, so they never count."""
    got = (json.loads(output) or {}).get("disposition")
    row = {"escalated": float(got == "escalate")}
    if reference is None:
        return row
    want, autonomous = _label(reference)
    if want == "not-file":
        want = "dismiss"
    if want not in DISPOSITIONS:
        return row
    row["correct"] = float(got == want)
    if want in ("file", "escalate"):
        row["false_dismiss"] = float(got in ("dismiss", "cleanup"))
    if want in ("dismiss", "cleanup"):
        row["false_alarm"] = float(got in ("file", "escalate"))
    if autonomous == "escalate":
        row["silent_drop"] = float(got == "dismiss")
    return row
