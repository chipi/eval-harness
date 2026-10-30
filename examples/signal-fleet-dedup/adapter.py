"""The fleet's de-duplication stage as a system under test: no model, the fleet's own pure functions.

An item is one scrubbed error signal (chipi-nbgd/signal-fleet-dedup). `call_system` runs it through the
functions the fleet's filing stage applies before any model sees it:

  operational   triage.operational_class: an operational state (cost cap, budget, rate limit), never filed
  test          sources._is_test_signal: a test or synthetic signal, suppressed
  low_signal    filing.low_signal: folded into the low-signal rollup instead of its own issue
  norm_key      filing.normalized_key: the key two occurrences of one logical bug share

The output is those four as JSON. The reference is the same output from the fleet's code at a pinned
commit (evh reference-create --from-run), so `key_match` and `class_match` below 1 mean the fleet's
current code de-duplicates differently from the pinned one: a regression guard, not a quality score.

The fleet's code comes from TRIAGE_FLEET_SRC (the signal-fleet folder at a recorded commit).
params:
  fleet_commit   the commit TRIAGE_FLEET_SRC holds, recorded with the run
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

PRIMARY_METRIC = "key_match"
METRIC_DIRECTIONS = {"key_match": "higher", "class_match": "higher"}

_FLEET: dict[str, Any] = {}


def _fleet() -> tuple:
    """(filing, sources, triage) from the fleet's checkout, imported once, its tracing off."""
    if "filing" in _FLEET:
        return _FLEET["filing"], _FLEET["sources"], _FLEET["triage"]
    src = os.environ.get("TRIAGE_FLEET_SRC", "")
    mvp = Path(src) / "mvp" if src else None
    if mvp is None or not (mvp / "filing.py").is_file():
        raise RuntimeError(f"TRIAGE_FLEET_SRC must name the fleet's signal-fleet folder; got {src!r}")
    os.environ["SF_OBSERV_DISABLED"] = "1"
    os.environ.setdefault("OPENROUTER_API_KEY", "unset")
    sys.path.insert(0, str(mvp))
    import filing  # noqa: PLC0415
    import sources  # noqa: PLC0415
    import triage  # noqa: PLC0415

    _FLEET.update(filing=filing, sources=sources, triage=triage)
    return filing, sources, triage


def classify(signal: dict) -> dict:
    """The four answers of the filing stage for one signal."""
    filing, sources, triage = _fleet()
    r = signal.get("raw") or {}
    m = r.get("metadata") or {}
    return {
        "operational": bool(triage.operational_class(signal)),
        "test": bool(
            sources._is_test_signal(signal.get("alertname"), r.get("culprit"), r.get("shortId"), m.get("value"), m.get("type"))
        ),
        "low_signal": bool(filing.low_signal(signal)),
        "norm_key": filing.normalized_key(signal) or signal.get("fingerprint"),
    }


def call_system(text: str, params: dict[str, Any]) -> Result:
    """The filing stage's answers for one signal, as JSON."""
    del params  # the code under test is TRIAGE_FLEET_SRC; params only record its commit
    t0 = time.monotonic()
    out = classify(json.loads(text))
    return Result(output=json.dumps(out, sort_keys=True), latency_ms=(time.monotonic() - t0) * 1000)


def score(output: str, reference: str | None) -> dict[str, float]:
    """key_match: the same norm_key as the pinned code; class_match: the same three flags."""
    if reference is None:
        return {}
    got, want = json.loads(output), json.loads(reference)
    return {
        "key_match": float(got.get("norm_key") == want.get("norm_key")),
        "class_match": float(all(got.get(k) == want.get(k) for k in ("operational", "test", "low_signal"))),
    }
