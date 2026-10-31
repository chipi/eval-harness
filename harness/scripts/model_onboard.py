#!/usr/bin/env python3
"""Onboard a model once, for every experiment (RFC-020): probe it and write what was found into its record.

    evh model-onboard <model_id> --deployment <id>        an LLM: probes through the deployment's endpoint
    evh model-onboard <model_id> --config <arm.yaml>      an ML model or a baseline: through an arm that runs it
                                                          (--deployment names the deployment it is written to)

An LLM is probed task-independently, through the endpoint its record gives for that deployment (a built-in
provider: an OpenAI-shaped server such as Ollama or vLLM, LiteLLM, OpenRouter, Anthropic):

  build         the digest the server reports for the tag (Ollama), against the record's
  reasoning     whether it reasons at the server's default; whether the record's settings turn it off
  format        whether a JSON answer comes back as valid JSON, with the record's settings
  speed         tokens out per second
  determinism   the same request twice, the same answer or not
  cut off       a reply that hits the probe's own cap (a task's caps and call limits are its arms', checked by
                `evh arm-smoke`)

An ML model or a baseline is onboarded through an arm that runs it: `evh arm-smoke`'s checks on two
items, with the facts its adapter reports (device, precision, load time).

ONBOARD PASS (exit 0) or ONBOARD CHECK with the flags (exit 1). The deployment's `onboarding`, `digest` and
`checked_at`, and the record's `capabilities` are written; its settings are never changed: a person
chooses them, and records why.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from evaluation_harness import _models
from evaluation_harness._common import DATA, die, now

PROBE = (
    "Answer with one JSON object and nothing else, in the form "
    '{"answer": "yes" or "no", "reason": "<one short sentence>"}. Question: is 17 a prime number?'
)
#: The settings a model record holds: how the model is asked to behave, whatever the task. A reply cap or a
#: call limit is a task's, so it is set by the arm (RFC-020, review E6).
CALL_PARAMS = ("reasoning_effort", "reasoning")
PROBE_MAX_TOKENS = 1024


def ollama_digest(base_url: str, tag: str) -> str | None:
    """The digest an Ollama server reports for a tag (its /api/tags), or None when it is not Ollama or lacks it."""
    root = base_url.rstrip("/").removesuffix("/v1")
    if not root.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(root + "/api/tags", timeout=10) as r:  # noqa: S310 — http(s) only, checked above  # nosec B310
            tags = json.load(r)
    except Exception:  # noqa: BLE001  (not an Ollama server, or not reachable: no digest to report)
        return None
    for m in tags.get("models") or []:
        if m.get("name") == tag or m.get("model") == tag:
            return m.get("digest")
    return None


def _call(params: dict[str, Any]) -> tuple[Any, float]:
    from evaluation_harness._providers import complete  # noqa: PLC0415

    t0 = time.perf_counter()
    c = complete(PROBE, params, role="arm", max_tokens=int(params.get("max_tokens") or PROBE_MAX_TOKENS))
    return c, time.perf_counter() - t0


def _reasoned(c: Any) -> bool:
    return bool((c.reasoning_tokens or 0) > 0 or (c.meta or {}).get("reasoning_chars"))


#: Facts of one deployment, never of the model: an older record that holds them at its top loses them.
DEPLOYMENT_FACTS = ("deterministic", "tokens_per_s")


def probe_llm(rec: dict[str, Any], dep: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """(report, flags, capabilities) of an LLM through one deployment's endpoint."""
    ep = dep.get("endpoint") or {}
    if not ep.get("provider") or not ep.get("model"):
        die(f"{rec['model_id']}: deployment {dep.get('id')!r} has no endpoint (provider, model) to probe")
    base = {k: ep[k] for k in ("provider", "base_url", "model", "api_key_env") if ep.get(k)}
    settings = {k: v for k, v in (rec.get("settings") or {}).items() if k in CALL_PARAMS}
    flags: list[str] = []
    report: dict[str, Any] = {"endpoint": {k: v for k, v in base.items() if k != "api_key_env"}}

    if dep.get("tag") and ep.get("base_url"):
        found = ollama_digest(ep["base_url"], dep["tag"])
        report["digest_found"] = found
        if (
            found
            and dep.get("digest")
            and not found.startswith(dep["digest"])
            and not dep["digest"].startswith(found)
        ):
            flags.append(f"build: {dep['id']} serves {found[:12]}, the record says {dep['digest'][:12]}")

    default, s_default = _call({**base, "max_tokens": 4096})
    report["default"] = {
        "s": round(s_default, 2),
        "tokens_out": default.tokens_out,
        "reasoned": _reasoned(default),
        "finish": default.finish_reason,
    }
    chosen, s_chosen = _call({**base, **settings})
    report["chosen"] = {
        "s": round(s_chosen, 2),
        "tokens_out": chosen.tokens_out,
        "reasoned": _reasoned(chosen),
        "finish": chosen.finish_reason,
        "settings": settings,
    }
    again, _ = _call({**base, **settings})
    try:
        json.loads(chosen.text.strip().removeprefix("```json").removesuffix("```").strip())
        valid_json = True
    except ValueError:
        valid_json = False
    deterministic = again.text == chosen.text
    # The model's own facts. Determinism and speed belong to a deployment (one machine's build and
    # hardware), so they stay in its onboarding report.
    caps: dict[str, Any] = {"reasons": report["default"]["reasoned"]}
    if report["default"]["reasoned"]:
        if "reasoning_effort" in settings or "reasoning" in settings:
            caps["reasoning_off"] = (
                None
                if report["chosen"]["reasoned"]
                else ", ".join(
                    f"{k}: {settings[k]}" for k in ("reasoning_effort", "reasoning") if k in settings
                )
            )
        if report["chosen"]["reasoned"]:
            flags.append(
                "reasoning: it still reasons with the record's settings"
                if settings.get("reasoning_effort") or settings.get("reasoning")
                else "reasoning: it reasons by default and the record sets no reasoning_effort"
            )
    if chosen.tokens_out and s_chosen:
        report["tokens_per_s"] = round(chosen.tokens_out / s_chosen, 1)
    caps["json_mode"] = valid_json
    if not valid_json:
        flags.append("format: the JSON probe's answer is not valid JSON")
    if chosen.finish_reason == "length":
        flags.append(f"cut off: the probe's reply hit its {PROBE_MAX_TOKENS}-token cap")
    if not (chosen.text or "").strip():
        flags.append("no answer: an empty reply with the record's settings")
    report["deterministic"] = deterministic
    report["json_valid"] = valid_json
    return report, flags, caps


def main() -> int:
    """Onboard one deployment (or an arm's model); exit 0 on ONBOARD PASS, 1 on ONBOARD CHECK."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("model_id")
    ap.add_argument(
        "--deployment", help="the deployment to probe and write: an `id` in the record's deployments"
    )
    ap.add_argument("--config", type=Path, help="an arm that runs the model (an ML model or a baseline)")
    args = ap.parse_args()
    import yaml  # noqa: PLC0415

    rec = _models.find(DATA, args.model_id)
    if rec is None:
        die(
            f"no model record {args.model_id!r}: write data/models/{args.model_id}.yaml first (model_id, kind, aliases)"
        )
    path = _models.records_dir(DATA) / f"{args.model_id}.yaml"
    print(f"model-onboard: {args.model_id} ({rec.get('kind')})")
    if rec.get("kind") == "llm":
        deployments = rec.get("deployments") or []
        dep = (
            _models.deployment_of(rec, args.deployment)
            if args.deployment
            else (deployments[0] if len(deployments) == 1 else None)
        )
        if dep is None:
            die(
                f"--deployment: one of {', '.join(x.get('id', '?') for x in deployments) or '(no deployments in the record)'}"
            )
        report, flags, caps = probe_llm(rec, dep)
        d, c = report["default"], report["chosen"]
        print(f"  {dep['id']} ({dep['where']}): {report['endpoint']}")
        if "digest_found" in report:
            print(
                f"  build: the server reports {str(report['digest_found'])[:12]}, the record {str(dep.get('digest'))[:12]}"
            )
        print(
            f"  default settings: {d['s']} s, {d['tokens_out']} tokens out, reasoned: {d['reasoned']}, end {d['finish']}"
        )
        print(
            f"  record's settings {c['settings'] or '(none)'}: {c['s']} s, {c['tokens_out']} tokens out, reasoned: {c['reasoned']}, end {c['finish']}"
        )
        print(
            f"  JSON valid: {report['json_valid']}  deterministic: {report['deterministic']}  tokens/s: {report.get('tokens_per_s')}"
        )
        found = report.get("digest_found")
        if (
            found
            and dep.get("digest")
            and not (found.startswith(dep["digest"]) or dep["digest"].startswith(found))
        ):
            # A different build behind the same tag (flagged above): the record takes the build it found, and
            # its history keeps the one it replaced.
            rec.setdefault("history", []).append(
                {
                    "at": now()[:10],
                    "what": f"deployment {dep['id']}: digest",
                    "from": dep["digest"],
                    "to": found,
                    "why": "model-onboard found a different build on the server",
                }
            )
        if found:
            dep["digest"] = found
        dep["checked_at"] = now()
        kept = {k: v for k, v in (rec.get("capabilities") or {}).items() if k not in DEPLOYMENT_FACTS}
        rec["capabilities"] = {
            **kept,
            **{k: v for k, v in caps.items() if v is not None or k == "reasoning_off"},
        }
        where = dep["where"]
    else:
        if not args.config:
            die(
                f"{args.model_id} is {rec.get('kind')}: onboard it through an arm that runs it (--config <arm.yaml>)"
            )
        import subprocess  # noqa: PLC0415

        cmd = [
            _sys.executable,
            str(Path(__file__).with_name("arm_smoke.py")),
            "--config",
            str(args.config),
            "--items",
            "2",
            "--no-record",
        ]
        out = subprocess.run(cmd, capture_output=True, text=True)
        print(out.stdout.rstrip())
        flags = [ln.strip()[2:] for ln in out.stdout.splitlines() if ln.startswith("  - ")]
        report = {"via_arm": str(args.config), "smoke": out.stdout[-4000:]}
        where = "via " + args.config.stem
        deployments = rec.setdefault("deployments", [])
        dep = _models.deployment_of(rec, args.deployment) if args.deployment else None
        if args.deployment and dep is None:
            dep = {"id": args.deployment, "where": "local"}
            deployments.append(dep)
        elif dep is None and len(deployments) == 1:
            dep = deployments[0]
        elif dep is None:
            dep = {"id": "local", "where": "local"}
            deployments.append(dep)
    status = "pass" if not flags else "check"
    dep["onboarding"] = {"status": status, "at": now(), "where": where, "flags": flags, "report": report}
    path.write_text(yaml.safe_dump(rec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print("ONBOARD PASS" if not flags else "ONBOARD CHECK")
    for f in flags:
        print(f"  - {f}")
    print(f"  written into data/models/{args.model_id}.yaml (deployment {dep['id']})")
    return 0 if not flags else 1


if __name__ == "__main__":
    raise SystemExit(main())
