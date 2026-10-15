"""MBPP+: can a system write a Python function that passes the tests? Scored by running it.

One item is one MBPP task: a one-sentence instruction and one example assertion (which
gives the function's name and signature). The system writes the function; the scorer
extracts it from the reply, runs it IN A SANDBOX against MBPP's original tests (`base`) and
against EvalPlus's extended tests (`plus`), and records pass/fail for each.

WHAT THIS EXPERIMENT BREAKS THAT THE OTHER SIX DID NOT
  1. The referee is a test suite, not an annotator. Every earlier experiment ended up
     adjudicating disputed gold labels; here a wrong answer is one that raises or returns
     the wrong value, and anyone can rerun the check.
  2. The scorer EXECUTES model output. That is a new capability and a new refusal, both in
     sandbox.py: never execute outside the sandbox, and prove the sandbox holds (network,
     writes, timeouts) at warm-up, before any model is called.
  3. Two answers per item from one reply: `pass_base` and `pass_plus`. The gap between
     them is how much weak tests flatter a model -- the EvalPlus finding, measured per arm.

THE ARMS
  litellm   a hosted model, shown EvalPlus's instruct prompt (prompt.txt), temperature 0.
  local     Qwen2.5-Coder-Instruct (0.5B to 32B) via transformers, greedy, on CPU or a GPU, with
            EvalPlus's chat template and response prefix -- the setup behind the published
            numbers this experiment calibrates against.

SCORING, IN ORDER
  extract   the fenced ```python block that defines the entry point; else the first fenced
            block; else the whole reply. `code_found` records whether a block was fenced.
  sanitise  keep imports, functions, classes and assignments at the top level; drop the
            rest (example calls, prints, `if __name__` blocks), as EvalPlus does. A reply
            that is not valid Python scores 0 with `syntax_ok` 0.
  execute   base tests, then -- only if base passes -- plus tests, each in a fresh
            sandboxed process. `pass_plus` therefore means base AND plus, EvalPlus's
            definition. A timeout scores 0 and is recorded in `timeout`, so a slow machine
            is visible rather than mistaken for wrong code.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402
import sandbox  # noqa: E402
from codehash import code_digest  # noqa: E402

#: Wall-clock limits per sandboxed execution. Set from canonical_check.py's timings on a
#: 4-core CPU: the slowest canonical solution's plus suite takes a fraction of these, so a
#: timeout is the code's doing, not the machine's.
BASE_TIMEOUT_S = 10.0
PLUS_TIMEOUT_S = 30.0

#: EvalPlus's response prefix for instruct models (evalplus/provider/utility.py). The local
#: arms continue from it, inside an open ```python fence; hosted arms cannot be prefilled
#: portably and get the instruction alone, which is also what EvalPlus does for API models.
RESPONSE_PREFIX = ("Below is a Python script with a self-contained function that solves the "
                   "problem and passes corresponding tests:\n```python\n")


@dataclass
class Result:
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


# ── the prompt ───────────────────────────────────────────────────────────────
_PROMPT_CACHE: Dict[str, str] = {}


def _template(params: Dict[str, Any]) -> str:
    path = (HERE / str(params.get("prompt_file") or "prompt.txt")).resolve()
    if str(path) not in _PROMPT_CACHE:
        if not path.is_file():
            raise SystemExit(f"prompt file not found: {path}")
        _PROMPT_CACHE[str(path)] = path.read_text(encoding="utf-8").strip()
    return _PROMPT_CACHE[str(path)]


def problem(text: str) -> str:
    """EvalPlus's MBPP+ problem string: the instruction and one example, in a docstring."""
    d = json.loads(text)
    return f'"""\n{d["prompt"]}\n{d["example_test"]}\n"""\n'


def user_message(text: str, params: Dict[str, Any]) -> str:
    return _template(params).replace("{problem}", problem(text).strip()) + "\n"


def _prompt_sha256(params: Dict[str, Any]) -> str:
    return hashlib.sha256(_template(params).encode()).hexdigest()


# ── the hosted arms ──────────────────────────────────────────────────────────
def _as_dict(obj: Any) -> Any:
    if obj is None:
        return None
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001 -- forensics must not break a paid run
                pass
    if isinstance(obj, dict):
        return obj
    try:
        return dict(vars(obj))
    except Exception:  # noqa: BLE001
        return str(obj)


def _reasoning_tokens(usage: Any) -> Optional[int]:
    """Reasoning tokens billed, or None when the provider did not say (None is not 0)."""
    d = _as_dict(usage)
    if not isinstance(d, dict):
        return None
    details = d.get("completion_tokens_details") or d.get("output_tokens_details") or {}
    if not isinstance(details, dict):
        details = _as_dict(details) if details else {}
    if isinstance(details, dict):
        for k in ("reasoning_tokens", "reasoning", "thinking_tokens"):
            if isinstance(details.get(k), int):
                return details[k]
    return None


def _billed(usage: Any) -> Optional[float]:
    """What the provider billed for this call; it outranks the price table (see the
    summarisation adapter for why: the table was wrong by 0.67x-3.21x per arm)."""
    d = usage if isinstance(usage, dict) else (
        usage.model_dump() if hasattr(usage, "model_dump") else None)
    if not isinstance(d, dict):
        return None
    c = d.get("cost")
    if c is None:
        c = (d.get("cost_details") or {}).get("upstream_inference_cost")
    try:
        return round(float(c), 10) if c is not None else None
    except (TypeError, ValueError):
        return None


def _price(params: Dict[str, Any], tin: Optional[int], tout: Optional[int]) -> Optional[float]:
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


def _litellm(text: str, params: Dict[str, Any]) -> Result:
    client, route = gateway.client(params)
    extra_body = gateway.extra_body(params, route)
    content = text if params.get("_raw_message") else user_message(text, params)
    max_tokens = int(params.get("max_tokens", 2048))
    resp = client.chat.completions.create(
        model=route["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        **({"extra_body": extra_body} if extra_body else {}),
    )
    usage = getattr(resp, "usage", None)
    ti = getattr(usage, "prompt_tokens", None)
    to = getattr(usage, "completion_tokens", None)
    finish = getattr(resp.choices[0], "finish_reason", None)
    # Code cut off mid-function fails its tests and would read as "this model cannot
    # code"; finish_reason says it was the token ceiling instead.
    truncated = finish == "length" or (to is not None and to >= max_tokens * 0.98)
    reasoning = _reasoning_tokens(usage)
    billed = _billed(usage)
    return Result(
        output=(resp.choices[0].message.content or "").strip(),
        tokens_in=ti,
        tokens_out=to,
        cost_usd=billed if billed is not None else _price(params, ti, to),
        extra={"truncated": 1.0 if truncated else 0.0,
               **({"reasoning_tokens": float(reasoning)} if reasoning is not None else {})},
        meta={"usage": _as_dict(usage), "finish_reason": finish,
              "response_model": getattr(resp, "model", None),
              "reasoning_tokens_reported": reasoning is not None,
              "provider": (getattr(resp, "provider", None)
                           or (getattr(resp, "model_extra", None) or {}).get("provider"))},
    )


# ── the local arms ───────────────────────────────────────────────────────────
_LM: Any = None
_LM_KEY: Optional[tuple] = None
_DEVICE: Optional[str] = None


def _device(params: Dict[str, Any]) -> str:
    """`device` from the config: cpu (the default), cuda, mps, or auto (cuda, then mps,
    then cpu). Greedy decoding is deterministic per device, not across devices, so the
    device used is recorded in the fingerprint, not assumed."""
    import torch  # noqa: PLC0415

    want = str(params.get("device") or "cpu").lower()
    if want == "auto":
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(torch.backends, "mps", None)
        return "mps" if mps is not None and mps.is_available() else "cpu"
    return want


def _lm(params: Dict[str, Any]) -> Any:
    global _LM, _LM_KEY, _DEVICE
    key = (params.get("model"), params.get("revision"), params.get("precision"), params.get("device"))
    if _LM_KEY != key:
        import torch  # noqa: PLC0415
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415
        from hf_identity import apply_precision  # noqa: PLC0415

        torch.manual_seed(0)
        kw = {"revision": params["revision"]} if params.get("revision") else {}
        tok = AutoTokenizer.from_pretrained(params["model"], **kw)
        model = AutoModelForCausalLM.from_pretrained(params["model"], **kw).eval()
        apply_precision(model, params.get("precision"))
        _DEVICE = _device(params)
        model.to(_DEVICE)
        _LM, _LM_KEY = (tok, model), key
    return _LM


def _local(text: str, params: Dict[str, Any]) -> Result:
    """Greedy decoding from EvalPlus's chat prompt plus its response prefix, which leaves
    the model inside an open ```python fence; generation stops at the closing fence."""
    import torch  # noqa: PLC0415

    tok, model = _lm(params)
    chat = [{"role": "user", "content": user_message(text, params)}]
    prompt = tok.apply_chat_template(chat, tokenize=False, add_generation_prompt=True) + RESPONSE_PREFIX
    enc = tok(prompt, return_tensors="pt").to(model.device)
    max_new = int(params.get("max_new_tokens", 768))
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                             stop_strings=["```"], tokenizer=tok,
                             pad_token_id=tok.pad_token_id or tok.eos_token_id)
    new = out[0][enc["input_ids"].shape[1]:]
    body = tok.decode(new, skip_special_tokens=True)
    return Result(output="```python\n" + body, tokens_in=int(enc["input_ids"].shape[1]),
                  tokens_out=int(new.shape[0]), cost_usd=0.0,
                  extra={"truncated": 1.0 if new.shape[0] >= max_new else 0.0})


PROVIDERS = {"litellm": _litellm, "local": _local}


def call_system(text: str, params: Dict[str, Any]) -> Result:
    provider = params.get("provider", "litellm")
    fn = PROVIDERS.get(provider)
    if fn is None:
        raise SystemExit(f"unknown provider {provider!r} -- expected one of {sorted(PROVIDERS)}")
    started = time.perf_counter()
    result = fn(text, params)
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


# ── from a reply to runnable code ────────────────────────────────────────────
_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n(.*?)(?:```|\Z)", re.S)


def extract_code(output: str, entry_point: str) -> tuple[str, bool]:
    """(code, fenced). The fenced block that defines the entry point wins; then the first
    python-ish fenced block; then the whole reply. An unclosed fence (a truncated reply)
    runs to the end."""
    blocks = [(lang.lower(), body) for lang, body in _FENCE.findall(output or "")]
    defines = re.compile(rf"^\s*def\s+{re.escape(entry_point)}\s*\(", re.M)
    for _, body in blocks:
        if defines.search(body):
            return body, True
    for lang, body in blocks:
        if lang in ("", "python", "py", "python3"):
            return body, True
    return output or "", False


_KEEP = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
         ast.Assign, ast.AnnAssign)


def sanitise(code: str) -> Optional[str]:
    """Top-level imports, functions, classes and assignments only, as EvalPlus's sanitiser
    keeps; None when the code is not valid Python. Example calls and prints a model adds
    after its function are dropped: they are not the answer, and an example with a wrong
    expected value would otherwise fail a correct function."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    tree.body = [n for n in tree.body if isinstance(n, _KEEP)]
    return ast.unparse(tree)


# ── the scorer ───────────────────────────────────────────────────────────────
def score(output: str, reference: Optional[str], source: Optional[str] = None) -> Dict[str, float]:
    """pass_base and pass_plus (0/1), plus why a failure happened.

    `timeout` is 1 when either execution ran out of wall-clock time. `syntax_ok` 0 means the
    extracted code never ran. Nothing here executes outside sandbox.execute().
    """
    if reference is None:
        return {}
    gold = json.loads(reference)
    code, fenced = extract_code(output, gold["entry_point"])
    clean = sanitise(code)
    out = {"code_found": 1.0 if fenced else 0.0, "syntax_ok": 0.0 if clean is None else 1.0,
           "pass_base": 0.0, "pass_plus": 0.0, "timeout": 0.0}
    if clean is None:
        return out
    base = sandbox.execute(clean, gold["base_test"], gold.get("imports"), timeout_s=BASE_TIMEOUT_S)
    out["timeout"] = 1.0 if base["status"] == "timeout" else 0.0
    if base["status"] != "pass":
        return out
    out["pass_base"] = 1.0
    plus = sandbox.execute(clean, gold["plus_test"], gold.get("imports"), timeout_s=PLUS_TIMEOUT_S)
    out["timeout"] = 1.0 if plus["status"] == "timeout" else 0.0
    out["pass_plus"] = 1.0 if plus["status"] == "pass" else 0.0
    return out


def scorer_sha256() -> str:
    return code_digest(score, extract_code, sanitise, sandbox.execute, sandbox.backend,
                       sandbox._limits,
                       consts={"_FENCE": _FENCE, "_KEEP": [k.__name__ for k in _KEEP],
                               "BASE_TIMEOUT_S": BASE_TIMEOUT_S, "PLUS_TIMEOUT_S": PLUS_TIMEOUT_S,
                               "RUNNER": sandbox.RUNNER, "_LINUX_SETUP": sandbox._LINUX_SETUP,
                               "_MAC_PROFILE": sandbox._MAC_PROFILE, "LIMITS": sandbox.LIMITS})


# ── warm-up and fingerprint ──────────────────────────────────────────────────
_SAMPLE = json.dumps({"prompt": "Write a function to add two numbers.",
                      "example_test": "assert add(2, 3) == 5"})
_SAMPLE_GOLD = json.dumps({"entry_point": "add", "imports": [],
                           "base_test": "assert add(2, 3) == 5\nassert add(-1, 1) == 0",
                           "plus_test": "for a, b in [(0, 0), (10**9, 1)]:\n    assert add(a, b) == a + b",
                           "canonical": "def add(a, b):\n    return a + b\n"})
_PROBE: Dict[str, str] = {}


def warmup(params: Dict[str, Any]) -> None:
    """Prove the sandbox holds, THEN load the model and prove the endpoint answers.

    The probe comes first on purpose: if this machine cannot confine model code, the run
    must stop before anything is downloaded or paid for.
    """
    global _PROBE
    _PROBE = sandbox.probe(sentinel_dir=HERE)
    got = score("```python\ndef add(a, b):\n    return a + b\n```", _SAMPLE_GOLD)
    bad = score("```python\ndef add(a, b):\n    return a - b\n```", _SAMPLE_GOLD)
    if got["pass_plus"] != 1.0 or bad["pass_base"] != 0.0:
        raise SystemExit(f"scorer self-check failed: right={got} wrong={bad}")
    provider = params.get("provider", "litellm")
    if provider == "local":
        _local(_SAMPLE, {**params, "max_new_tokens": 8})
    elif provider == "litellm":
        _litellm("Warm up.", {**params, "max_tokens": 1, "_raw_message": True})


def _scorer_fp() -> Dict[str, Any]:
    return {"sandbox": sandbox.backend(), "sandbox_probe": _PROBE or None,
            "scorer_sha256": scorer_sha256(), "python": sys.version.split()[0]}


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    provider = params.get("provider", "litellm")
    if provider == "local":
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        key = (params.get("model"), params.get("revision"), params.get("precision"), params.get("device"))
        fp = hf_model_fingerprint(params["model"], revision=params.get("revision"),
                                  device=_DEVICE or str(params.get("device") or "cpu"),
                                  precision=params.get("precision"),
                                  loaded_model=_LM[1] if _LM is not None and _LM_KEY == key else None)
        fp.update({"code_sha256": code_digest(_local, _lm, _device, consts={"RESPONSE_PREFIX": RESPONSE_PREFIX}),
                   "prompt_sha256": _prompt_sha256(params), "decoding": "greedy",
                   "max_new_tokens": int(params.get("max_new_tokens", 768)), **_scorer_fp()})
        return fp
    alias = params.get("model")
    upstream, id_source = gateway.resolve_upstream(alias)
    return {"id": upstream or alias, "alias": alias, "id_source": id_source,
            "revision": None, "revision_source": "api-model-string",
            "endpoint": gateway.endpoint(), "provider_routing": params.get("provider_routing"),
            "temperature": params.get("temperature"), "prompt_sha256": _prompt_sha256(params),
            "reasoning": params.get("reasoning"), **_scorer_fp()}


TRANSIENT_MARKERS = ("model is warming up", "no instances available", "upstream")

#: pass_plus: base AND EvalPlus's extended tests, the number the Qwen2.5-Coder report and
#: the EvalPlus leaderboard publish as "MBPP+". pass_base is MBPP's original tests.
PRIMARY_METRIC = "pass_plus"

METRIC_KINDS = {
    "pass_plus": "quality", "pass_base": "quality",
    # Descriptive: why a failure happened, and what the call cost in tokens.
    "code_found": "descriptive", "syntax_ok": "descriptive", "timeout": "descriptive",
    "truncated": "descriptive", "reasoning_tokens": "descriptive",
}
