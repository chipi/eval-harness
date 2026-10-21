#!/usr/bin/env python3
"""The vllm provider sends the local arm's exact prompt and reads the reply the same way.

    examples/code-mbpp-plus/.venv/bin/python examples/code-mbpp-plus/test_vllm_provider.py

Offline: the server is a stand-in, and the tokenizer is Qwen2.5-Coder-1.5B's at its pinned
revision (from the local Hugging Face cache, or downloaded once; a few MB).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter  # noqa: E402

CFG = yaml.safe_load((HERE / "configs" / "arm_qwencoder_15b_n378.yaml").read_text())["params"]
TASK = adapter._SAMPLE
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail and not ok else ""))
    failed += not ok


# 1. The prompt is the transformers path's prompt, byte for byte.
from transformers import AutoTokenizer  # noqa: E402

tok = AutoTokenizer.from_pretrained(CFG["model"], revision=CFG["revision"])
local_prompt = tok.apply_chat_template(
    [{"role": "user", "content": adapter.user_message(TASK, CFG)}],
    tokenize=False, add_generation_prompt=True) + adapter.RESPONSE_PREFIX
check("prompt identical to the local arm's", adapter._vllm_prompt(TASK, CFG) == local_prompt)


# 2. The request is greedy completion with the same stop and budget; the reply is read the
#    way the local arm reads its own.
sent = {}


class _Completions:
    def __init__(self, text, reason):
        self.text, self.reason = text, reason

    def create(self, **kw):
        sent.update(kw)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(text=self.text, finish_reason=self.reason)],
            usage=types.SimpleNamespace(prompt_tokens=50, completion_tokens=12))


def fake_openai(text, reason):
    return lambda **_: types.SimpleNamespace(completions=_Completions(text, reason))


import openai  # noqa: E402

params = {**CFG, "provider": "vllm", "base_url": "http://server:9100/v1"}
openai.OpenAI = fake_openai("def add(a, b):\n    return a + b\n```", "stop")
res = adapter._vllm(TASK, params)
check("greedy, completions endpoint, same stop and budget",
      sent.get("temperature") == 0.0 and sent.get("stop") == ["```"]
      and sent.get("max_tokens") == int(CFG.get("max_new_tokens", 768))
      and sent.get("prompt") == local_prompt
      and sent.get("extra_body", {}).get("include_stop_str_in_output") is True, str(sent)[:200])
check("output carries the opened fence and passes the scorer",
      res.output.startswith("```python\n")
      and adapter.score(res.output, adapter._SAMPLE_GOLD)["pass_plus"] == 1.0, res.output)
check("not truncated on a stop", res.extra.get("truncated") == 0.0)
check("token counts from the server", res.tokens_in == 50 and res.tokens_out == 12)

openai.OpenAI = fake_openai("def add(a, b):\n    retu", "length")
check("truncated when the budget is hit", adapter._vllm(TASK, params).extra.get("truncated") == 1.0)

# 3. Without base_url it refuses rather than guessing a server.
try:
    adapter._vllm(TASK, {**CFG, "provider": "vllm"})
    check("refuses without base_url", False)
except SystemExit:
    check("refuses without base_url", True)

print("vllm provider: " + ("all passed" if not failed else f"{failed} FAILED"))
sys.exit(1 if failed else 0)
