#!/usr/bin/env python3
"""The hosted providers: one layer for the arms and the judges, keys by role. $0, no network.

    python tests/test_providers.py

Fake `openai` and `anthropic` modules record what each call was built with. Before one layer:
`provider: openrouter` read OPENAI_API_KEY and called OpenAI's address unless the arm set both
`base_url` and `api_key_env`; a judge ignored its declared `provider:` and went wherever the
environment's proxy or OpenRouter key pointed; the judge panel called only Anthropic, priced
Sonnet in code, and ran its fake judge when the key was missing.
"""

import json
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness._check import check, summary

seen: dict = {}


class _Usage:
    """Like the SDK's usage object: model_dump() is what billed() reads (OpenRouter's cost)."""

    prompt_tokens, completion_tokens = 3, 1

    def model_dump(self):
        return {
            "prompt_tokens": 3,
            "completion_tokens": 1,
            "completion_tokens_details": {"reasoning_tokens": 7},
            "cost": 2.5e-06,
        }


class _Resp:
    def __init__(self):
        msg = types.SimpleNamespace(content='{"scores": {"accuracy": 4}}')
        self.choices = [types.SimpleNamespace(message=msg, finish_reason="stop")]
        self.usage = _Usage()
        self.model = "upstream/model-1"
        self.provider = "SomeHost"


class _OpenAI:
    def __init__(self, api_key=None, base_url=None, **opts):
        seen.clear()
        seen.update(sdk="openai", api_key=api_key, base_url=base_url, opts=opts)
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        seen["kw"] = kw
        return _Resp()


class _Anthropic:
    def __init__(self, api_key=None, base_url=None, **opts):
        seen.clear()
        seen.update(sdk="anthropic", api_key=api_key, base_url=base_url, opts=opts)
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        seen["kw"] = kw
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text='{"scores": {"accuracy": 4}}')],
            usage=types.SimpleNamespace(input_tokens=10, output_tokens=20),
            stop_reason="max_tokens",
            model="claude-x",
        )


fake_openai = types.ModuleType("openai")
fake_openai.OpenAI = _OpenAI  # type: ignore[attr-defined]
fake_anthropic = types.ModuleType("anthropic")
fake_anthropic.Anthropic = _Anthropic  # type: ignore[attr-defined]
sys.modules["openai"] = fake_openai
sys.modules["anthropic"] = fake_anthropic

from evaluation_harness import _fingerprint, _providers, adapter, judging, panel_judges  # noqa: E402

VARS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENROUTER_API_KEY",
    "LITELLM_API_KEY",
    "LITELLM_BASE_URL",
    "MY_KEY",
)


def clear() -> None:
    for v in VARS:
        os.environ.pop(v, None)
        os.environ.pop("EVAL_JUDGE_" + v, None)


def refused(fn) -> str:
    try:
        fn()
    except SystemExit as exc:
        return str(exc)
    return ""


clear()

# ── arms: the bundled adapter ────────────────────────────────────────────────
os.environ["OPENROUTER_API_KEY"] = "sk-or-test-key"
r = adapter.call_system("text", {"provider": "openrouter", "model": "mistralai/mistral-small"})
check(
    "openrouter: OPENROUTER_API_KEY and OpenRouter's address, with nothing else set",
    seen.get("api_key") == "sk-or-test-key" and seen.get("base_url") == "https://openrouter.ai/api/v1",
    str({k: v for k, v in seen.items() if k != "kw"}),
)
check("openrouter: asks for the bill", (seen["kw"].get("extra_body") or {}).get("usage") == {"include": True})
check(
    "a reported bill is the cost, and is kept in meta where cost-report reads it",
    r.cost_usd == 2.5e-06 and (r.meta or {}).get("usage") == {"cost": 2.5e-06},
    f"{r.cost_usd} {r.meta}",
)
check(
    "an arm records the model and host that answered, and its reasoning tokens",
    r.meta.get("response_model") == "upstream/model-1"
    and r.meta.get("provider") == "SomeHost"
    and r.extra.get("reasoning_tokens") == 7.0,
    f"{r.meta} {r.extra}",
)
os.environ["OPENAI_API_KEY"] = "sk-openai-test-key"
adapter.call_system("text", {"provider": "openrouter", "model": "m"})
check(
    "openrouter: an OPENAI_API_KEY in the environment does not send the call to OpenAI",
    seen.get("api_key") == "sk-or-test-key" and "openrouter.ai" in (seen.get("base_url") or ""),
)
adapter.call_system("text", {"provider": "openai", "model": "gpt-x"})
check(
    "openai: OPENAI_API_KEY and the SDK's default address, no request body",
    seen.get("api_key") == "sk-openai-test-key"
    and seen.get("base_url") is None
    and not seen["kw"].get("extra_body"),
    str(seen),
)
check("openai: no call limit set, the SDK's own default stands", seen.get("opts") == {}, str(seen))
adapter.call_system("text", {"provider": "openai", "model": "gpt-x", "call_timeout_s": 30})
check(
    "openai: the arm's call_timeout_s is the client's timeout, never sent in the request",
    seen.get("opts") == {"timeout": 30.0} and "call_timeout_s" not in str(seen["kw"]),
    str(seen),
)
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
adapter.call_system("t", {"provider": "anthropic", "model": "claude-x", "call_timeout_s": 45})
os.environ.pop("ANTHROPIC_API_KEY")
check(
    "anthropic: the arm's call_timeout_s is the client's timeout",
    seen.get("opts") == {"timeout": 45.0},
    str(seen),
)
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8000/v1"
adapter.call_system("text", {"provider": "openai", "model": "local"})
check(
    "openai: OPENAI_BASE_URL points it at a compatible endpoint",
    seen.get("base_url") == "http://127.0.0.1:8000/v1",
)
os.environ.pop("OPENAI_BASE_URL")
adapter.call_system(
    "text",
    {
        "provider": "openrouter",
        "model": "m",
        "base_url": "http://127.0.0.1:9/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
)
check(
    "openrouter: an arm's own base_url and api_key_env still win",
    seen.get("base_url") == "http://127.0.0.1:9/v1" and seen.get("api_key") == "sk-openai-test-key",
)
adapter.call_system(
    "t", {"provider": "openai", "model": "m", "reasoning": {"enabled": False}, "provider_routing": {"x": 1}}
)
check(
    "an arm's reasoning and provider_routing reach the request body, as a judge's do",
    seen["kw"].get("extra_body") == {"reasoning": {"enabled": False}, "provider": {"x": 1}},
    str(seen["kw"].get("extra_body")),
)
os.environ.pop("OPENROUTER_API_KEY")
msg = refused(lambda: adapter.call_system("text", {"provider": "openrouter", "model": "m"}))
check("openrouter: a missing key names OPENROUTER_API_KEY", "OPENROUTER_API_KEY" in msg, msg)
check("an arm is not told about judge variables", "EVAL_JUDGE_" not in msg, msg)

os.environ["LITELLM_API_KEY"] = "k-litellm"
msg = refused(lambda: adapter.call_system("t", {"provider": "litellm", "model": "eval-x"}))
check("litellm: no proxy address is refused, naming LITELLM_BASE_URL", "LITELLM_BASE_URL" in msg, msg)
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4001/"
adapter.call_system("t", {"provider": "litellm", "model": "eval-x"})
check(
    "litellm: the proxy's address with /v1, its key, the model as written",
    seen.get("base_url") == "http://127.0.0.1:4001/v1"
    and seen.get("api_key") == "k-litellm"
    and seen["kw"]["model"] == "eval-x",
    str(seen),
)

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
os.environ["MY_KEY"] = "sk-ant-other"
ra = adapter.call_system(
    "t", {"provider": "anthropic", "model": "claude-x", "usd_per_mtok_in": 1, "usd_per_mtok_out": 2}
)
check(
    "anthropic: ANTHROPIC_API_KEY, priced from the config, a max_tokens stop reads as length",
    seen.get("sdk") == "anthropic"
    and seen.get("api_key") == "sk-ant-test"
    and ra.cost_usd == round(10 / 1e6 + 20 * 2 / 1e6, 8)
    and ra.meta.get("finish_reason") == "length",
    f"{seen} {ra}",
)
adapter.call_system(
    "t",
    {"provider": "anthropic", "model": "claude-x", "api_key_env": "MY_KEY", "base_url": "http://a.invalid"},
)
check(
    "anthropic: api_key_env and base_url work as for every other provider",
    seen.get("api_key") == "sk-ant-other" and seen.get("base_url") == "http://a.invalid",
)
msg = refused(
    lambda: adapter.call_system("t", {"provider": "anthropic", "model": "c", "reasoning": {"enabled": True}})
)
check("anthropic: an OpenAI-shaped field is refused, not silently dropped", "reasoning" in msg, msg)

# ── judges: the same layer, keys EVAL_JUDGE_<NAME> first ─────────────────────
jp = {
    "provider": "litellm",
    "model": "eval-judge",
    "max_tokens": 400,
    "usd_per_mtok_in": 1,
    "usd_per_mtok_out": 1,
}
jr = judging.call_judge("judge this", jp)
check(
    "judge: goes where its provider says, sharing the arms' key when it has none of its own",
    seen.get("base_url") == "http://127.0.0.1:4001/v1" and seen.get("api_key") == "k-litellm",
    str(seen),
)
check(
    "judge: records cost, the model and host that answered, and reasoning tokens",
    jr.cost_usd == 2.5e-06
    and jr.meta["response_model"] == "upstream/model-1"
    and jr.meta["provider"] == "SomeHost"
    and jr.extra.get("reasoning_tokens") == 7.0
    and jr.extra.get("truncated") == 0.0,
    f"{jr}",
)
os.environ["EVAL_JUDGE_LITELLM_API_KEY"] = "k-judging"
os.environ["EVAL_JUDGE_LITELLM_BASE_URL"] = "http://judging.invalid"
judging.call_judge("judge this", jp)
check(
    "judge: EVAL_JUDGE_<NAME> is used first (its own key and its own proxy)",
    seen.get("api_key") == "k-judging" and seen.get("base_url") == "http://judging.invalid/v1",
    str(seen),
)
adapter.call_system("t", {"provider": "litellm", "model": "eval-x"})
check(
    "an arm never reads a judge's key",
    seen.get("api_key") == "k-litellm" and seen.get("base_url") == "http://127.0.0.1:4001/v1",
)
os.environ.pop("ANTHROPIC_API_KEY")
msg = refused(lambda: judging.call_judge("x", {"provider": "anthropic", "model": "c"}))
check(
    "judge: a missing key names both variables a judge may set",
    "EVAL_JUDGE_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY" in msg,
    msg,
)
msg = refused(lambda: judging.call_judge("x", {"provider": "openrouterr", "model": "m"}))
check(
    "judge: an unknown provider is refused, naming the four",
    "unknown provider" in msg and "litellm" in msg,
    msg,
)
os.environ["OPENROUTER_API_KEY"] = "sk-or-test-key"
msg = refused(lambda: judging.call_judge("x", {"provider": "anthropic", "model": "c"}))
check("judge: an OpenRouter key does not stand in for the provider the judge names", msg != "", msg)

# ── identity ─────────────────────────────────────────────────────────────────
check(
    "identity: api_key_env is a credential, not part of what is measured",
    _providers.identity_params({"model": "m", "api_key_env": "K", "base_url": "u"})
    == {"model": "m", "base_url": "u"},
)
with tempfile.TemporaryDirectory() as td:
    kw: dict[str, Any] = {
        "root": Path(td),
        "dataset": {"dataset_id": "d", "items": []},
        "reference_id": None,
        "reference_tier": None,
        "config_id": "c",
        "adapter_id": "bundled",
        "adapter_path": None,
    }
    a_fp = _fingerprint.build_fingerprint(params={"provider": "openai", "model": "m"}, **kw)
    b_fp = _fingerprint.build_fingerprint(
        params={"provider": "openai", "model": "m", "api_key_env": "K2"}, **kw
    )
    check(
        "a run's fingerprint does not move when only the key it was paid with changes",
        a_fp["hash"] == b_fp["hash"] and "api_key_env" not in json.dumps(b_fp),
        str(b_fp["settings"]),
    )

# ── the judge panel ──────────────────────────────────────────────────────────
spec = {
    "id": "j1",
    "provider": "anthropic",
    "model": "claude-x",
    "usd_per_mtok_in": 3.0,
    "usd_per_mtok_out": 15.0,
}
msg = refused(lambda: panel_judges.build_judge(spec))
check(
    "panel: a hosted judge with no key stops before any call, never a fake judge in its place",
    "EVAL_JUDGE_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY" in msg and "--use-fake-judge" in msg,
    msg,
)
check(
    "panel: --use-fake-judge is the only way to a fake judge",
    isinstance(panel_judges.build_judge(spec, use_fake=True), panel_judges.FakeJudge),
)
check(
    "panel: a judge named only by a model string is refused (provider and prices are required)",
    "provider" in refused(lambda: panel_judges.build_judge("claude-sonnet-4-6")),  # type: ignore[arg-type]
)
os.environ["EVAL_JUDGE_ANTHROPIC_API_KEY"] = "sk-ant-judging"
pj = panel_judges.build_judge(spec)
assert pj is not None
sc = pj.score(run_id="r", item_id="i", item_content="out", dimensions=["accuracy"])
check(
    "panel: a hosted judge goes through the layer on the judge's own key, priced from its spec",
    seen.get("sdk") == "anthropic"
    and seen.get("api_key") == "sk-ant-judging"
    and sc.total_cost_usd == round(10 * 3 / 1e6 + 20 * 15 / 1e6, 8)
    and sc.per_dimension == {"accuracy": 4},
    f"{seen} {sc}",
)

# A key written into a config is never shown, and is named so experiment-run can refuse it.
params = {"api_key": "sk-1", "api_key_env": "X", "max_tokens": 300, "authorization": "Bearer x", "model": "m"}
check(
    "secret params: a literal key is named; max_tokens and the variable's name are not",
    _providers.secret_params(params) == ["api_key", "authorization"],
    str(_providers.secret_params(params)),
)
shown = _providers.shown_params(params)
check(
    "shown params: literal keys read (hidden), api_key_env is left out, the rest is kept",
    shown == {"api_key": "(hidden)", "max_tokens": 300, "authorization": "(hidden)", "model": "m"},
    str(shown),
)

os.environ["LITELLM_API_KEY"] = "sk-litellm-test"
adapter.call_system(
    "t", {"provider": "litellm", "model": "eval-x", "base_url": "http://gw:4000", "reasoning_effort": "none"}
)
check(
    "litellm: a reasoning setting is named in allowed_openai_params, so the proxy passes it on",
    (seen["kw"].get("extra_body") or {}).get("allowed_openai_params") == ["reasoning_effort"]
    and (seen["kw"].get("extra_body") or {}).get("reasoning_effort") == "none",
    str(seen.get("kw")),
)
adapter.call_system("t", {"provider": "litellm", "model": "eval-x", "base_url": "http://gw:4000"})
check(
    "litellm: without one nothing extra is sent",
    "allowed_openai_params" not in (seen["kw"].get("extra_body") or {}),
    str(seen.get("kw")),
)
os.environ.pop("LITELLM_API_KEY")
check(
    "litellm: an address given with /v1 already is not given a second one",
    _providers.route({"provider": "litellm", "model": "m", "base_url": "http://gw:4000/v1"}, "arm").base_url
    == "http://gw:4000/v1"
    and _providers.route({"provider": "litellm", "model": "m", "base_url": "http://gw:4000/"}, "arm").base_url
    == "http://gw:4000/v1",
)

clear()
sys.exit(summary())
