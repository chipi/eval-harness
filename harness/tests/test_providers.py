#!/usr/bin/env python3
"""The bundled adapter's hosted providers read their own key and address. $0, no network.

    python tests/test_providers.py

`provider: openrouter` read OPENAI_API_KEY and called OpenAI's address unless the arm set both
`base_url` and `api_key_env`; with only OPENROUTER_API_KEY set it failed, and with
OPENAI_API_KEY also set it would have sent the call to OpenAI. A fake `openai` module records
what each provider was built with.
"""

import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))
from _check import check, summary  # noqa: E402

seen: dict = {}


class _Resp:
    def __init__(self):
        msg = types.SimpleNamespace(content="ok")
        self.choices = [types.SimpleNamespace(message=msg, finish_reason="stop")]
        self.usage = _Usage()


class _Usage:
    """Like the SDK's usage object: model_dump() is what billed() reads (OpenRouter's cost)."""

    prompt_tokens, completion_tokens = 3, 1

    def model_dump(self):
        return {"prompt_tokens": 3, "completion_tokens": 1, "cost": 2.5e-06}


class _OpenAI:
    def __init__(self, api_key=None, base_url=None):
        seen.update(api_key=api_key, base_url=base_url)
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        seen["kw"] = kw
        return _Resp()


fake = types.ModuleType("openai")
fake.OpenAI = _OpenAI  # type: ignore[attr-defined]
sys.modules["openai"] = fake
import adapter  # noqa: E402

for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
    os.environ.pop(k, None)
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
os.environ["OPENAI_API_KEY"] = "sk-openai-test-key"
adapter.call_system("text", {"provider": "openrouter", "model": "m"})
check(
    "openrouter: an OPENAI_API_KEY in the environment does not send the call to OpenAI",
    seen.get("api_key") == "sk-or-test-key" and "openrouter.ai" in (seen.get("base_url") or ""),
)
adapter.call_system("text", {"provider": "openai", "model": "gpt-x"})
check(
    "openai: OPENAI_API_KEY and the SDK's default address",
    seen.get("api_key") == "sk-openai-test-key" and seen.get("base_url") is None,
)
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
os.environ.pop("OPENROUTER_API_KEY")
try:
    adapter.call_system("text", {"provider": "openrouter", "model": "m"})
    msg = ""
except SystemExit as exc:
    msg = str(exc)
check("openrouter: a missing key names OPENROUTER_API_KEY", "OPENROUTER_API_KEY" in msg, msg)

sys.exit(summary())
