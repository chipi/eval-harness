"""Hosted models: one way to call them, for the systems under test and for the judges alike.

    complete(prompt, params, role="arm" | "judge", max_tokens=...) -> Completion
    problems(params, role)  -> what stops a call before it is made (judge-score checks first)

`params["provider"]` names where the call goes, and nothing else does:

  provider    calls                                                  reads
  openai      OpenAI, or any OpenAI-compatible endpoint (`base_url`)   OPENAI_API_KEY, OPENAI_BASE_URL
  anthropic   Anthropic                                              ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL
  openrouter  OpenRouter, asked for what it billed                   OPENROUTER_API_KEY
  litellm     your own LiteLLM proxy (`model` is the proxy's name)   LITELLM_API_KEY, LITELLM_BASE_URL

Every provider takes `model`, `base_url` and `api_key_env` (another variable to read the key
from), `temperature` (default 0) and `max_tokens`; the OpenAI-shaped ones also pass
`reasoning`, `reasoning_effort` and `provider_routing` in the request body.

KEYS BY ROLE. A judge reads every variable as `EVAL_JUDGE_<NAME>` first and falls back to
`<NAME>`, so judging can run on its own keys (its own budget and spend log) or share the
experiments' with no setting at all. A credential is where a call is billed, not what was
measured: `api_key_env` is left out of every identity hash (`identity_params`).

COST. What the provider billed when the response carries it (`usage.cost`), else the
config's prices (`usd_per_mtok_in` / `usd_per_mtok_out`) times the tokens, else unknown
(None), never zero.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple

ROLES = ("arm", "judge")
JUDGE_PREFIX = "EVAL_JUDGE_"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
#: Params that say which credential pays for a call. They never enter an identity hash: the
#: same model asked the same way is the same measurement whichever key was used.
CREDENTIAL_PARAMS = ("api_key_env",)
#: Request-body fields an OpenAI-shaped provider passes through, and their name on the wire.
_BODY_PARAMS = {
    "reasoning": "reasoning",
    "reasoning_effort": "reasoning_effort",
    "provider_routing": "provider",
}


class Spec(NamedTuple):
    """What a provider reads: its key's variable, and where its address comes from."""

    key_env: str
    base_env: str | None  # a variable that may set the address
    base_default: str | None  # the address when neither params nor that variable set one
    base_required: bool  # no default: the address must be given
    base_suffix: str  # appended to the address (a LiteLLM proxy serves its API under /v1)
    shape: str  # "openai" or "anthropic": which client and request


SPECS: dict[str, Spec] = {
    "openai": Spec("OPENAI_API_KEY", "OPENAI_BASE_URL", None, False, "", "openai"),
    "anthropic": Spec("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", None, False, "", "anthropic"),
    "openrouter": Spec("OPENROUTER_API_KEY", None, OPENROUTER_URL, False, "", "openai"),
    "litellm": Spec("LITELLM_API_KEY", "LITELLM_BASE_URL", None, True, "/v1", "openai"),
}
PROVIDERS = tuple(SPECS)


@dataclass
class Completion:
    """What one call returned, and what it cost. Unknown is None, never 0."""

    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    billed: bool = False
    finish_reason: str | None = None
    reasoning_tokens: int | None = None
    response_model: str | None = None
    upstream_provider: str | None = None
    usage: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


class Route(NamedTuple):
    """Where one call goes, and with which credential (named, for messages and env-check)."""

    provider: str
    key_var: str
    key: str | None
    base_var: str | None
    base_url: str | None


#: A param whose name says it holds a secret: api_key, apikey, access_token, client_secret,
#: password, auth, bearer, credential. `max_tokens` and `tokens_*` are counts, not secrets.
_SECRET_NAME = re.compile(
    r"(^|_)(api_?key|secret|password|passwd|token|auth(orization)?|bearer|credentials?)($|_)", re.IGNORECASE
)


def secret_params(params: dict[str, Any]) -> list[str]:
    """The params that look like a credential written into the config (a literal key), not the
    name of the variable that holds one (`api_key_env`)."""
    return sorted(
        k
        for k, v in params.items()
        if k not in CREDENTIAL_PARAMS and _SECRET_NAME.search(k) and isinstance(v, str) and v
    )


def shown_params(params: dict[str, Any]) -> dict[str, Any]:
    """`params` as a page or the CLI may show them: no `api_key_env`, and a literal credential
    replaced by "(hidden)"."""
    hidden = set(secret_params(params))
    return {k: ("(hidden)" if k in hidden else _shown(v)) for k, v in identity_params(params).items()}


#: A URL that carries a credential in it: scheme://user:password@host.
_URL_USERINFO = re.compile(r"^([a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)


def _shown(v: Any) -> Any:
    """A param's value as shown: a URL's user and password, and a nested secret-named key
    (`headers: {Authorization: ...}`), replaced by "(hidden)"."""
    if isinstance(v, str):
        return _URL_USERINFO.sub(r"\1(hidden)@", v)
    if isinstance(v, dict):
        return {k: ("(hidden)" if _SECRET_NAME.search(str(k)) else _shown(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_shown(x) for x in v]
    return v


def identity_params(params: dict[str, Any]) -> dict[str, Any]:
    """`params` without the credential fields: what an identity hash may cover."""
    return {k: v for k, v in params.items() if k not in CREDENTIAL_PARAMS}


def env(name: str, role: str) -> tuple[str, str | None]:
    """(the variable read, its value). A judge reads EVAL_JUDGE_<name> first."""
    if role == "judge" and os.environ.get(JUDGE_PREFIX + name):
        return JUDGE_PREFIX + name, os.environ[JUDGE_PREFIX + name]
    return name, os.environ.get(name) or None


def _either(name: str, role: str) -> str:
    """How a missing variable is named to this role: a judge may set either."""
    return f"{JUDGE_PREFIX}{name} or {name}" if role == "judge" else name


#: Ollama's port: a server there takes any key, on this machine or another one on the network.
OLLAMA_PORT = 11434


def keyless(base: str | None) -> bool:
    """Whether an OpenAI-shaped address needs no key: on this machine (localhost, 127.x, ::1) or Ollama's port."""
    if not base:
        return False
    from urllib.parse import urlparse  # noqa: PLC0415

    u = urlparse(base)
    host = (u.hostname or "").lower()
    return host in ("localhost", "::1") or host.startswith("127.") or u.port == OLLAMA_PORT


def route(params: dict[str, Any], role: str) -> Route:
    """Where `params` would be sent, resolved without calling anything. Missing pieces are None
    (`problems` says which); an unknown provider is a ValueError."""
    provider = params.get("provider")
    if provider not in SPECS:
        raise ValueError(f"unknown provider {provider!r}; one of {', '.join(PROVIDERS)}")
    spec = SPECS[provider]
    key_var, key = env(str(params.get("api_key_env") or spec.key_env), role)
    base_var: str | None
    base: str | None
    if params.get("base_url"):
        base_var, base = "base_url", str(params["base_url"])
    elif spec.base_env:
        base_var, base = env(spec.base_env, role)
    else:
        base_var, base = None, None
    base = base or spec.base_default
    if provider == "openai" and not key and keyless(base):
        # A local server, or Ollama anywhere, takes any key and the client only wants one present: asking a
        # newcomer for OPENAI_API_KEY to reach their own Ollama was a step with no purpose (owner, 2026-10-31).
        key_var, key = "(none: a local server)", "not-needed"
    # An address given with the suffix already (a LiteLLM proxy written as http://host:4000/v1, as its own docs
    # show it) keeps one: appending again sent every call to /v1/v1, which the proxy answers 404.
    if base and spec.base_suffix and not base.rstrip("/").endswith(spec.base_suffix):
        base = base.rstrip("/") + spec.base_suffix
    return Route(provider, key_var, key, base_var, base)


def problems(params: dict[str, Any], role: str) -> list[str]:
    """Why a call with `params` cannot be made, before any is: [] when it can."""
    provider = params.get("provider")
    if provider not in SPECS:
        return [f"unknown provider {provider!r}; one of {', '.join(PROVIDERS)}"]
    out = [] if params.get("model") else [f"provider {provider}: params name no model"]
    spec, r = SPECS[provider], route(params, role)
    if not r.key:
        named = str(params.get("api_key_env") or spec.key_env)
        out.append(f"provider {provider}: {_either(named, role)} is not set")
    if spec.base_required and not (r.base_url or "").startswith("http"):
        out.append(
            f"provider {provider}: {_either(spec.base_env or 'base_url', role)} is not set to the "
            "proxy's address (e.g. http://127.0.0.1:4001)"
        )
    if spec.shape == "anthropic":
        unsupported = sorted(k for k in _BODY_PARAMS if params.get(k) is not None)
        if unsupported:
            out.append(
                f"provider anthropic: {', '.join(unsupported)} is an OpenAI-shaped field Anthropic does not take"
            )
    return out


def billed(usage: Any) -> float | None:
    """What the provider billed for this call; it outranks the price table, which has been
    wrong by 0.67x-3.76x per arm."""
    d = usage if isinstance(usage, dict) else (usage.model_dump() if hasattr(usage, "model_dump") else None)
    if not isinstance(d, dict):
        return None
    c = d.get("cost")
    if c is None:
        c = (d.get("cost_details") or {}).get("upstream_inference_cost")
    try:
        return round(float(c), 10) if c is not None else None
    except (TypeError, ValueError):
        return None


def price(params: dict[str, Any], tin: int | None, tout: int | None) -> float | None:
    """Cost from the per-million-token prices a config declares; None when anything is
    missing (unpriced, never free). The fallback for a call the provider did not bill."""
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


def as_dict(obj: Any) -> Any:
    """A provider object as plain data, for the record; never raises."""
    if obj is None or isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001 -- forensics must not break a paid run
                pass
    try:
        return dict(vars(obj))
    except Exception:  # noqa: BLE001
        return str(obj)


def reasoning_tokens(usage: Any) -> int | None:
    """Reasoning tokens billed, or None when the provider did not say (None is not 0)."""
    d = as_dict(usage)
    if not isinstance(d, dict):
        return None
    details = d.get("completion_tokens_details") or d.get("output_tokens_details") or {}
    if not isinstance(details, dict):
        details = as_dict(details) if details else {}
    if isinstance(details, dict):
        for k in ("reasoning_tokens", "reasoning", "thinking_tokens"):
            if isinstance(details.get(k), int):
                return details[k]
    return None


def _cost(params: dict[str, Any], usage: Any, tin: int | None, tout: int | None) -> tuple[float | None, bool]:
    bill = billed(usage)
    return (bill, True) if bill is not None else (price(params, tin, tout), False)


def _client_kw(params: dict[str, Any]) -> dict[str, Any]:
    """The client's own options from the params: `call_timeout_s`, the arm's call limit (seconds), as the
    SDK's `timeout`. Unset, the SDK's default stands (10 minutes for both)."""
    limit = params.get("call_timeout_s")
    return {"timeout": float(limit)} if limit else {}


def _openai_shaped(prompt: str, params: dict[str, Any], r: Route) -> Completion:
    from openai import OpenAI  # noqa: PLC0415

    body = {_BODY_PARAMS[k]: params[k] for k in _BODY_PARAMS if params.get(k) is not None}
    if r.provider == "openrouter":
        body["usage"] = {"include": True}  # OpenRouter returns what it billed only when asked
    if r.provider == "litellm":
        # A LiteLLM proxy refuses a parameter its model group does not list (UnsupportedParamsError, e.g.
        # reasoning_effort on most hosted groups) unless the request names it: then it is passed to the upstream.
        asked = [k for k in ("reasoning", "reasoning_effort") if k in body]
        if asked:
            body["allowed_openai_params"] = asked
    resp = OpenAI(api_key=r.key, base_url=r.base_url, **_client_kw(params)).chat.completions.create(
        model=params["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=int(params["max_tokens"]),
        messages=[{"role": "user", "content": prompt}],
        extra_body=body or None,
    )
    usage = getattr(resp, "usage", None)
    tin, tout = getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
    cost, was_billed = _cost(params, usage, tin, tout)
    choice = resp.choices[0]
    # A server that returns the model's reasoning beside its answer (Ollama, vLLM: `reasoning` or
    # `reasoning_content`) says whether it reasoned even when its usage does not count reasoning tokens.
    extra = getattr(choice.message, "model_extra", None) or {}
    said = extra.get("reasoning") or extra.get("reasoning_content") or ""
    return Completion(
        meta={"reasoning_chars": len(said)} if said else {},
        text=choice.message.content or "",
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost,
        billed=was_billed,
        finish_reason=getattr(choice, "finish_reason", None),
        reasoning_tokens=reasoning_tokens(usage),
        response_model=getattr(resp, "model", None),
        upstream_provider=getattr(resp, "provider", None)
        or (getattr(resp, "model_extra", None) or {}).get("provider"),
        usage=as_dict(usage),
    )


def _anthropic(prompt: str, params: dict[str, Any], r: Route) -> Completion:
    import anthropic  # noqa: PLC0415

    msg = anthropic.Anthropic(api_key=r.key, base_url=r.base_url, **_client_kw(params)).messages.create(
        model=params["model"],
        max_tokens=int(params["max_tokens"]),
        messages=[{"role": "user", "content": prompt}],
        # The SDK dropped the `temperature` keyword in 1.x; the body carries it, so the request
        # is the same one every SDK version sends.
        extra_body={"temperature": float(params.get("temperature", 0.0))},
    )
    usage = getattr(msg, "usage", None)
    tin, tout = getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
    cost, was_billed = _cost(params, usage, tin, tout)
    stop = getattr(msg, "stop_reason", None)
    return Completion(
        text="".join(b.text for b in msg.content if b.type == "text"),
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost,
        billed=was_billed,
        # Anthropic's "max_tokens" is OpenAI's "length": the output stopped at the cap.
        finish_reason="length" if stop == "max_tokens" else stop,
        response_model=getattr(msg, "model", None),
        upstream_provider="anthropic",
        usage=as_dict(usage),
    )


_SHAPES: dict[str, Callable[[str, dict[str, Any], Route], Completion]] = {
    "openai": _openai_shaped,
    "anthropic": _anthropic,
}


def complete(prompt: str, params: dict[str, Any], *, role: str, max_tokens: int) -> Completion:
    """One call to the hosted model `params` names, as one user message. `max_tokens` is the
    caller's default when params set none. Anything `problems` finds stops it before the call."""
    if role not in ROLES:
        raise ValueError(f"role {role!r} is not one of {ROLES}")
    found = problems(params, role)
    if found:
        raise SystemExit(
            "; ".join(found) + ". Set it in the project's .env or the environment; `evh env-check` "
            "shows what each role reads."
        )
    params = {**params, "max_tokens": params.get("max_tokens", max_tokens)}
    return _SHAPES[SPECS[params["provider"]].shape](prompt, params, route(params, role))
