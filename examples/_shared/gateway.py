"""Where a hosted arm's request goes, and what it may claim about the model that answered.

Every example config names a model by alias (`eval-claude-sonnet`). Two routes resolve it:

  proxy   LITELLM_BASE_URL + LITELLM_API_KEY. Your own LiteLLM proxy owns the mapping;
          `../litellm.config.yaml` is the one the committed runs used. Identity is read
          back from the proxy's /model/info, so the run records what the proxy ACTUALLY
          routes to, not what a table says it should.
  direct  OPENROUTER_API_KEY alone. The alias is mapped through `../models.json` and the
          request goes straight to OpenRouter -- one key, no proxy, which is the whole
          barrier for someone rerunning these experiments.

The proxy wins when both are configured, so an existing setup behaves exactly as before.
Neither configured is an error that names both, rather than the old "LITELLM_BASE_URL is
not set", which told a newcomer to stand up infrastructure nobody had described.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

OPENROUTER = "https://openrouter.ai/api/v1"
MODELS_FILE = Path(__file__).resolve().parents[1] / "models.json"


def models() -> Dict[str, str]:
    """alias -> upstream id ("openrouter/<vendor>/<model>")."""
    return json.loads(MODELS_FILE.read_text())["aliases"]


def _upstream_for(alias: Optional[str]) -> Optional[str]:
    """An alias from the table, or -- to add a model of your own -- an OpenRouter id as-is."""
    if not alias:
        return None
    if alias in models():
        return models()[alias]
    return f"openrouter/{alias}" if "/" in alias else None


def _proxy_base(params: Dict[str, Any]) -> str:
    return (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/")


def route(params: Dict[str, Any]) -> Dict[str, Any]:
    """{mode, base_url, key, model, endpoint} for this arm, or SystemExit saying how to fix it."""
    alias = params.get("model")
    base = _proxy_base(params)
    if base.startswith("http"):
        key_env = params.get("api_key_env", "LITELLM_API_KEY")
        key = os.environ.get(key_env)
        if not key:
            raise SystemExit(f"{key_env} is not set (LITELLM_BASE_URL is, so the proxy route "
                             "was chosen)")
        return {"mode": "proxy", "base_url": f"{base}/v1", "key": key, "model": alias,
                "endpoint": base}
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        upstream = _upstream_for(alias)
        if not upstream:
            raise SystemExit(f"{alias!r} is neither an alias in examples/models.json nor an "
                             "OpenRouter id (vendor/model), so it cannot be sent to "
                             "OpenRouter directly")
        return {"mode": "direct", "base_url": OPENROUTER, "key": key,
                "model": upstream.removeprefix("openrouter/"), "endpoint": OPENROUTER}
    raise SystemExit(
        f"No route to hosted model {alias!r}. Set ONE of:\n"
        "  OPENROUTER_API_KEY=sk-or-...           one key, no proxy (docs/REPRODUCE.md)\n"
        "  LITELLM_BASE_URL + LITELLM_API_KEY     your own LiteLLM proxy\n"
        "in harness/.env (copy harness/.env.example) or the environment.")


def client(params: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    """An OpenAI-compatible client for this arm, and the route it was built for."""
    from openai import OpenAI  # noqa: PLC0415 - hosted arms only

    r = route(params)
    return OpenAI(api_key=r["key"], base_url=r["base_url"]), r


def extra_body(params: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Any]:
    """Provider knobs that must travel outside the OpenAI schema.

    `reasoning` is the one that matters: building requests from a fixed field list once
    DROPPED it, so configs said reasoning was off and the requests did not. Direct mode
    also asks OpenRouter for usage accounting, which is where billed cost comes from --
    the proxy route already returned it.
    """
    out: Dict[str, Any] = {}
    for passthrough in ("reasoning", "reasoning_effort"):
        if params.get(passthrough) is not None:
            out[passthrough] = params[passthrough]
    # The routing POLICY asked for; the provider actually GOT is recorded per call.
    if params.get("provider_routing") is not None:
        out["provider"] = params["provider_routing"]
    if r["mode"] == "direct":
        out["usage"] = {"include": True}
    return out


_UPSTREAM_CACHE: Dict[str, Tuple[Optional[str], str]] = {}


def resolve_upstream(alias: Optional[str]) -> Tuple[Optional[str], str]:
    """(upstream id or None, how it was established) for the fingerprint.

    Proxy: asked of the proxy, once per process -- what it routes to NOW. A proxy that does
    not answer yields (None, "alias-unresolved"): a run must not claim an identity it did
    not verify, and must not die over provenance either. Direct: the table is the routing,
    so the table is the identity.
    """
    if not alias:
        return None, "alias-unresolved"
    if alias in _UPSTREAM_CACHE:
        return _UPSTREAM_CACHE[alias]
    out: Tuple[Optional[str], str] = (None, "alias-unresolved")
    base = (os.environ.get("LITELLM_BASE_URL") or "").rstrip("/")
    key = os.environ.get("LITELLM_API_KEY")
    if base.startswith("http"):
        if key:
            import urllib.request  # noqa: PLC0415

            try:
                req = urllib.request.Request(base + "/model/info",
                                             headers={"Authorization": "Bearer " + key})
                with urllib.request.urlopen(req, timeout=15) as fh:
                    for entry in (json.load(fh).get("data") or []):
                        if entry.get("model_name") == alias:
                            got = (entry.get("litellm_params") or {}).get("model")
                            out = (got, "proxy-model-info") if got else out
                            break
            except Exception:  # noqa: BLE001 -- provenance is best-effort, the run is not
                pass
    elif os.environ.get("OPENROUTER_API_KEY") and _upstream_for(alias):
        out = (_upstream_for(alias), "models.json" if alias in models() else "config")
    _UPSTREAM_CACHE[alias] = out
    return out


def endpoint() -> Optional[str]:
    """The endpoint a hosted call goes to, for the fingerprint."""
    base = (os.environ.get("LITELLM_BASE_URL") or "").rstrip("/")
    if base.startswith("http"):
        return base
    return OPENROUTER if os.environ.get("OPENROUTER_API_KEY") else None
