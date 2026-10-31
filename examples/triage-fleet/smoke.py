"""Smoke-test an arm's model set-up before its full run: a few decisions, every model call measured.

    TRIAGE_FLEET_SRC=... python examples/triage-fleet/smoke.py configs/local/<arm>.yaml [--items 3]

It replays the first decisions of the arm's dataset through the fleet's code with the arm's own
settings, the way `evh experiment-run` would, but writes no run. For every model call it records
the time, the tokens out, whether the model reasoned (and how much), whether a JSON answer came
back, and why the reply ended. Then it flags what makes a full run slow, unbounded or unfair:

  reasoning      the model reasons by default; set `reasoning_effort` on purpose (none, or low)
  slow call      a call used more than half of the arm's call limit
  long reply     more than 300 tokens out in one call (a decision is 60-400)
  cut off        the reply hit `max_tokens` (finish_reason length): raise the cap
  no answer      an empty reply, a failed or timed-out call, or no decision in the end

A clean smoke prints SMOKE PASS; any flag prints SMOKE CHECK with the flags, and the arm's
settings to revisit. MODELS.md records each model's settings and the smoke behind them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LONG_REPLY = 300


def flags_for(calls: list[dict[str, Any]], decisions: list[dict[str, Any]], limit_s: float) -> list[str]:
    """The smoke's verdict from its measurements: one line per thing to revisit."""
    out = []
    reasoned = [c for c in calls if c.get("reasoning_chars", 0) > 0]
    if reasoned:
        out.append(
            f"reasoning: {len(reasoned)} of {len(calls)} calls reasoned (set reasoning_effort on purpose)"
        )
    slow = [c for c in calls if c.get("s", 0) > limit_s / 2]
    if slow:
        out.append(
            f"slow call: {len(slow)} call(s) over half the {limit_s:.0f} s limit (max {max(c['s'] for c in slow):.1f} s)"
        )
    long = [c for c in calls if (c.get("tokens_out") or 0) > LONG_REPLY]
    if long:
        out.append(
            f"long reply: {len(long)} call(s) over {LONG_REPLY} tokens (max {max(c['tokens_out'] for c in long)})"
        )
    cut = [c for c in calls if c.get("finish") == "length"]
    if cut:
        out.append(f"cut off: {len(cut)} reply(ies) hit max_tokens")
    bad = [c for c in calls if c.get("error") or not c.get("content_chars")]
    nod = [d for d in decisions if d.get("no_decision") or d.get("error")]
    if bad or nod:
        out.append(
            f"no answer: {len(bad)} empty or failed call(s), {len(nod)} decision(s) without a decision"
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("config", help="the arm's config (a path, or relative to examples/triage-fleet)")
    ap.add_argument("--items", type=int, default=3, help="how many decisions to replay (default 3)")
    args = ap.parse_args()

    import yaml  # noqa: PLC0415  (the harness's own dependency)

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        cfg_path = HERE / args.config
    cfg = yaml.safe_load(cfg_path.read_text())
    params = cfg["params"]
    harness = HERE.parents[1] / "harness"
    ds = json.loads((harness / "data/datasets" / f"{cfg['dataset_id']}.json").read_text())
    mat = harness / "data/materialized" / cfg["dataset_id"]
    os.environ.setdefault("OPENROUTER_API_KEY", "local")

    sys.path.insert(0, str(HERE))
    import adapter  # noqa: PLC0415

    triage = adapter._fleet()
    real_post = triage.post_json
    calls: list[dict[str, Any]] = []

    def measured(url: str, body: dict, *a: Any, **k: Any) -> Any:
        t0 = time.monotonic()
        rec: dict[str, Any] = {}
        try:
            resp = real_post(url, body, *a, **k)
        except urllib.error.HTTPError as e:
            rec["error"] = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:160]}"
            raise
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:160]
            raise
        else:
            ch = (resp.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            rec.update(
                content_chars=len(msg.get("content") or ""),
                reasoning_chars=len(msg.get("reasoning") or msg.get("reasoning_content") or ""),
                tokens_out=(resp.get("usage") or {}).get("completion_tokens"),
                finish=ch.get("finish_reason"),
            )
            return resp
        finally:
            rec["s"] = round(time.monotonic() - t0, 1)
            calls.append(rec)

    triage.post_json = measured
    limit = float(params.get("call_timeout_s") or 90)
    decisions = []
    print(
        f"smoke: {cfg['config_id']}  model {params.get('model')}  limit {limit:.0f} s"
        f"  reasoning_effort {params.get('reasoning_effort', '(server default)')}  max_tokens {params.get('max_tokens', '(none)')}"
    )
    for it in ds["items"][: args.items]:
        text = (mat / f"{it['item_id']}.json").read_text()
        first = len(calls)
        t0 = time.monotonic()
        d: dict[str, Any] = {"item": it["item_id"]}
        try:
            r = adapter.call_system(text, params)
            d.update(
                no_decision=bool(r.extra.get("no_decision")),
                disposition=json.loads(r.output).get("disposition"),
            )
        except Exception as e:  # noqa: BLE001  (a smoke reports every failure, it does not stop on one)
            d["error"] = f"{type(e).__name__}: {e}"[:160]
        d["s"] = round(time.monotonic() - t0, 1)
        decisions.append(d)
        print(f"  {it['item_id'][:46]:<46} {d['s']:>6.1f} s  {d.get('disposition') or d.get('error')}")
        for c in calls[first:]:
            print(
                f"      call {c['s']:>6.1f} s  out {c.get('tokens_out')!s:>5} tok  reasoning {c.get('reasoning_chars', 0):>6} ch"
                f"  answer {c.get('content_chars', 0):>5} ch  end {c.get('finish') or c.get('error')}"
            )
    flags = flags_for(calls, decisions, limit)
    print("SMOKE PASS" if not flags else "SMOKE CHECK")
    for f in flags:
        print(f"  - {f}")
    return 0 if not flags else 1


if __name__ == "__main__":
    raise SystemExit(main())
