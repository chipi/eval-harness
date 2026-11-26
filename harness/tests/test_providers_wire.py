#!/usr/bin/env python3
"""The hosted providers on the wire: `evh run` of a one-item system against a local fake of each API. $0, no network.

    python tests/test_providers_wire.py

test_providers.py swaps the `openai` and `anthropic` modules for fakes, so what the real SDKs put on the wire was never
looked at, and every run made so far went through a LiteLLM proxy. Here the real SDKs call a server on 127.0.0.1 that
speaks each provider's wire format (OpenAI chat completions, Anthropic messages with `x-api-key` and
`anthropic-version`, OpenRouter's OpenAI-compatible API with its `usage.cost`, a LiteLLM proxy's /v1), reached through
the provider's base-URL setting (the system's `base_url`, or the provider's own variable). Each run is asserted on the
request (path, auth header, body) and on what the run records (output, tokens, cost and its basis, finish reason); a
429 and a 500 are retried (the SDK's own retries, then the core's) and the item still lands; a 401 stops the item, is
not retried, and names the key variable and never its value, even when the server echoes the key back.

What this cannot show: the real endpoints' current fields. The fake answers the fields the code reads, as the
providers' documentation gave them when it was written.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
import _cli  # noqa: E402
import _runstore  # noqa: E402
import _tmp  # noqa: E402
from evaluation_harness import _format, _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

proj = Path(_tmp.mkdtemp(prefix="evh-providers-wire-"))
KEYS = {
    "OPENAI_API_KEY": "sk-test-not-printed-openai",
    "ANTHROPIC_API_KEY": "sk-test-not-printed-anthropic",
    "OPENROUTER_API_KEY": "sk-test-not-printed-openrouter",
    "LITELLM_API_KEY": "sk-test-not-printed-litellm",
}
env = {
    k: v
    for k, v in os.environ.items()
    if not k.startswith(("OPENAI_", "ANTHROPIC_", "OPENROUTER_", "LITELLM_", "EVAL_JUDGE_", "EVAL_"))
}
env.update(
    KEYS,
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-providers-wire",
    EVAL_MAX_RETRIES="3",
    EVAL_RETRY_MAX_DELAY="1",
    EVAL_MAX_COST_USD="1",
    # anything that is not the fake would need the network: a dead proxy makes it fail at once, never reach a provider
    HTTPS_PROXY="http://127.0.0.1:9",
    HTTP_PROXY="http://127.0.0.1:9",
    NO_PROXY="127.0.0.1,localhost",
)
for k in ("EVAL_DATA_DIR",):
    env.pop(k, None)
if os.environ.get("EVAL_STORE"):
    env["EVAL_STORE"] = os.environ["EVAL_STORE"]


def evh(*args, **extra):
    return _cli.run(proj, {**env, **extra}, *args)


# ── the fake ─────────────────────────────────────────────────────────────────────────────────────────────────
OPENAI_OK = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "gpt-test-2026-01-01",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "A fox jumps."}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}
OPENROUTER_OK = {
    **OPENAI_OK,
    "model": "vendor/model-test",
    "provider": "FakeHost",
    "usage": {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "cost": 0.000123,
        "completion_tokens_details": {"reasoning_tokens": 2},
    },
}
ANTHROPIC_OK = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test-2026",
    "content": [{"type": "text", "text": "A fox jumps."}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 13, "output_tokens": 9},
}


def with_(base, **kw):
    out = json.loads(json.dumps(base))
    for k, v in kw.items():
        if k == "finish":
            out["choices"][0]["finish_reason"] = v
        elif k == "stop":
            out["stop_reason"] = v
    return out


class Fake(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.requests: list[dict] = []
        self.script: list[tuple[int, dict, dict]] = []  # (status, body, headers) answered first, in order
        self.ok: dict = {}
        self.lock = threading.Lock()

    def reset(self, ok, script=()):
        with self.lock:
            self.requests, self.script, self.ok = [], list(script), ok


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = None
        srv = self.server
        assert isinstance(srv, Fake)
        with srv.lock:
            srv.requests.append(
                {"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body}
            )
            status, reply, headers = srv.script.pop(0) if srv.script else (200, srv.ok, {})
        raw = json.dumps(reply).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)


fake = Fake()
threading.Thread(target=fake.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{fake.server_address[1]}"
FAST = {"retry-after-ms": "5"}  # the SDKs wait this long before their own retry
RATE = (
    429,
    {"error": {"message": "Rate limit reached", "type": "rate_limit_error", "code": "rate_limit"}},
    FAST,
)
RATE_A = (
    429,
    {"type": "error", "error": {"type": "rate_limit_error", "message": "Rate limit reached"}},
    FAST,
)
BOOM = (500, {"error": {"message": "The server had an error", "type": "server_error"}}, FAST)
BOOM_A = (500, {"type": "error", "error": {"type": "api_error", "message": "Internal server error"}}, FAST)

# ── the project: one item, one system per scenario ───────────────────────────────────────────────────────────
try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
    (proj / "raw").mkdir()
    (proj / "raw" / "one.txt").write_text("The quick brown fox jumps over the lazy dog.", encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", "one_v1", "--source-dir", "raw")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "one_v1")
    check(
        "setup: a one-item dataset is frozen and materialized",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )

    n_system = 0

    def run(provider, ok, script=(), *, base_url=True, extra_env=None, **params):
        """`evh run` of a one-item system of `provider` against the fake; (the run, what the fake saw, the first row)."""
        global n_system
        n_system += 1
        sid = f"{provider}{n_system}_v1"
        params = {
            "provider": provider,
            "model": "model-under-test",
            "max_tokens": 321,
            "temperature": 0.3,
            "prompt": "Summarise this.",
            **params,
        }
        if base_url:
            params["base_url"] = base_url if isinstance(base_url, str) else BASE + PATH[provider]
        body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
        _runstore.write_text(proj, f"systems/{sid}.yaml", f"system_id: {sid}\nparams:\n{body}")
        fake.reset(ok, script)
        res = evh(
            "run", "--system", sid, "--dataset", "one_v1", "--run-id", f"run_{sid}", **(extra_env or {})
        )
        with _runstore._InProject(proj) as data:
            sd = model_runs.first_score(data / "runs" / f"run_{sid}")
            rows = _runstore.rows(sd) if sd else []
        return res, list(fake.requests), (rows[0] if rows else {})

    PATH = {"openai": "/v1", "anthropic": "", "openrouter": "/api/v1", "litellm": ""}

    def row_meta(row):
        return row.get("_meta") or {}

    def text_of(sid_run):
        with _runstore._InProject(proj) as data:
            return _outputs.output(data / "runs" / sid_run, "one")

    COMMON_BODY = {"model": "model-under-test", "max_tokens": 321, "temperature": 0.3}
    PROMPT = "Summarise this.\n\nThe quick brown fox jumps over the lazy dog."
    WIRE: dict[str, tuple[str, str, dict]] = {  # provider: (request path, auth header, the fake's answer)
        "openai": ("/v1/chat/completions", "authorization", OPENAI_OK),
        "anthropic": ("/v1/messages", "x-api-key", ANTHROPIC_OK),
        "openrouter": ("/api/v1/chat/completions", "authorization", OPENROUTER_OK),
        "litellm": ("/v1/chat/completions", "authorization", OPENAI_OK),
    }
    KEYVAR = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "litellm": "LITELLM_API_KEY",
    }
    PRICES = {"usd_per_mtok_in": 2.0, "usd_per_mtok_out": 10.0}

    for prov, (path, _auth, ok) in WIRE.items():
        key = KEYS[KEYVAR[prov]]
        extra: dict = {"reasoning_effort": "low"} if prov in ("openrouter", "litellm") else {}
        if prov == "openrouter":
            extra["provider_routing"] = {"order": ["FakeHost"]}
        res, reqs, row = run(prov, ok, **PRICES, **extra)
        out_text = (res.stdout or "") + (res.stderr or "")
        check(
            f"{prov}: the run succeeds and made one request",
            res.returncode == 0 and len(reqs) == 1,
            (res.returncode, len(reqs), out_text[-400:]),
        )
        q: dict = reqs[0] if reqs else {"path": "", "headers": {}, "body": {}}
        h, b = q["headers"], q["body"] or {}
        check(f"{prov}: the request's path is the API's ({path})", q["path"] == path, q["path"])
        if prov == "anthropic":
            # the header that carries the key is the installed SDK's choice (x-api-key up to 1.x, a bearer token in 2.x)
            sent = [h[k] for k in ("x-api-key",) if k in h] + [
                h["authorization"][7:] for k in ("authorization",) if h.get(k, "").startswith("Bearer ")
            ]
            from anthropic._client import ANTHROPIC_API_VERSION

            check(
                f"anthropic: the key (ANTHROPIC_API_KEY) goes in one auth header, once; anthropic-version is the SDK's ({ANTHROPIC_API_VERSION})",
                sent == [key] and h.get("anthropic-version") == ANTHROPIC_API_VERSION,
                {k: v for k, v in h.items() if k in ("x-api-key", "anthropic-version", "authorization")},
            )
            check(
                "anthropic: body is model, max_tokens, one user message, temperature (a system prompt is not sent)",
                b == {**COMMON_BODY, "messages": [{"role": "user", "content": PROMPT}]},
                b,
            )
        else:
            check(
                f"{prov}: Authorization is Bearer <the key of {KEYVAR[prov]}>",
                h.get("authorization") == f"Bearer {key}",
                h.get("authorization"),
            )
            want = {**COMMON_BODY, "messages": [{"role": "user", "content": PROMPT}]}
            if prov == "openrouter":
                want |= {
                    "usage": {"include": True},
                    "reasoning_effort": "low",
                    "provider": {"order": ["FakeHost"]},
                }
            if prov == "litellm":
                want |= {"reasoning_effort": "low", "allowed_openai_params": ["reasoning_effort"]}
            check(
                f"{prov}: body is model, one user message, max_tokens, temperature"
                + (", and what the provider adds" if want.keys() - COMMON_BODY.keys() - {"messages"} else ""),
                b == want,
                b,
            )
        for other in KEYS.values():
            if other != key:
                check(f"{prov}: no other provider's key is sent", other not in json.dumps(h), prov)
        usage = ok["usage"]
        tin, tout = (
            (usage["input_tokens"], usage["output_tokens"])
            if prov == "anthropic"
            else (usage["prompt_tokens"], usage["completion_tokens"])
        )
        check(
            f"{prov}: the run records the output text and the tokens in and out",
            text_of(f"run_{prov}{n_system}_v1") == "A fox jumps."
            and row.get("tokens_in") == tin
            and row.get("tokens_out") == tout,
            (row, text_of(f"run_{prov}{n_system}_v1")),
        )
        meta = row_meta(row)
        if prov == "openrouter":
            check(
                "openrouter: the cost is what it billed (usage.cost), not the price table's, and its host and model are kept",
                row.get("cost_usd") == 0.000123
                and "cost_basis" not in meta
                and meta.get("provider") == "FakeHost"
                and meta.get("response_model") == "vendor/model-test"
                and row.get("reasoning_tokens", 2) == 2,
                row,
            )
        else:
            want_cost = round(tin / 1e6 * 2.0 + tout / 1e6 * 10.0, 8)
            check(
                f"{prov}: no bill in the answer, the cost is the price table's, and the run says so",
                row.get("cost_usd") == want_cost and meta.get("cost_basis") == "price table",
                row,
            )
        want_finish = "stop" if prov != "anthropic" else "end_turn"
        check(
            f"{prov}: the finish reason is recorded as the provider gave it",
            meta.get("finish_reason") == want_finish,
            meta,
        )

        # a 429 three times (the SDK's own tries), a 500 three times, then the answer: the core's retry carries it
        rate, boom = (RATE_A, BOOM_A) if prov == "anthropic" else (RATE, BOOM)
        res, reqs, row = run(prov, ok, [rate] * 3 + [boom] * 3, **PRICES, **extra)
        said = (res.stdout or "") + (res.stderr or "")
        check(
            f"{prov}: a 429 and a 500 are retried, and the item lands (7 requests)",
            res.returncode == 0
            and len(reqs) == 7
            and text_of(f"run_{prov}{n_system}_v1") == "A fox jumps."
            and row.get("failed") == 0.0
            and "RateLimitError" in said
            and "InternalServerError" in said,
            (res.returncode, len(reqs), said[-600:]),
        )

        # a 401 that echoes the key back: not retried, the variable is named, the value is shown nowhere
        denied: tuple[int, dict, dict] = (
            401,
            {"error": {"message": f"Incorrect API key provided: {key}", "type": "invalid_request_error"}},
            {},
        )
        if prov == "anthropic":
            denied = (
                401,
                {
                    "type": "error",
                    "error": {"type": "authentication_error", "message": f"invalid x-api-key {key}"},
                },
                {},
            )
        res, reqs, row = run(prov, ok, [denied] * 5, **PRICES, **extra)
        said = (res.stdout or "") + (res.stderr or "")
        check(
            f"{prov}: a 401 is one request, not retried, and the run does not report a success",
            len(reqs) == 1
            and res.returncode != 0
            and "ERROR (not-configured)" in said
            and "transient" not in said,
            (res.returncode, len(reqs), said[-500:]),
        )
        check(f"{prov}: a 401 names the key variable {KEYVAR[prov]}", KEYVAR[prov] in said, said[-600:])
        check(
            f"{prov}: a 401 shows the key's value nowhere in what the command printed",
            key not in said,
            said[-600:],
        )
        leaked = [str(p) for p in proj.rglob("*") if p.is_file() and key.encode() in p.read_bytes()]
        check(f"{prov}: nor in anything the run wrote into the project", not leaked, leaked[:3])

    # the provider's own address variable, instead of the system's base_url (openrouter has none: only base_url)
    for prov, var, tail in (
        ("openai", "OPENAI_BASE_URL", "/v1"),
        ("anthropic", "ANTHROPIC_BASE_URL", ""),
        ("litellm", "LITELLM_BASE_URL", ""),
    ):
        path, auth, ok = WIRE[prov]
        res, reqs, row = run(prov, ok, base_url=False, extra_env={var: BASE + tail}, **PRICES)
        check(
            f"{prov}: {var} sends the call to the fake, the same path and key",
            res.returncode == 0
            and len(reqs) == 1
            and reqs[0]["path"] == path
            and KEYS[KEYVAR[prov]] in json.dumps(reqs[0]["headers"]),
            (res.returncode, [q["path"] for q in reqs], ((res.stdout or "") + (res.stderr or ""))[-300:]),
        )
    res, reqs, row = run("litellm", OPENAI_OK, base_url=BASE + "/v1", **PRICES)
    check(
        "litellm: an address that already ends in /v1 is not given a second one",
        [q["path"] for q in reqs] == ["/v1/chat/completions"],
        [q["path"] for q in reqs],
    )

    # a reply cut at max_tokens: recorded as "length" for both shapes, and the run says so
    for prov, kw in (("openai", {"finish": "length"}), ("anthropic", {"stop": "max_tokens"})):
        res, reqs, row = run(prov, with_(WIRE[prov][2], **kw), **PRICES)
        said = (res.stdout or "") + (res.stderr or "")
        check(
            f"{prov}: a reply cut at max_tokens is recorded as finish_reason length, and the run warns",
            row_meta(row).get("finish_reason") == "length" and "max_tokens" in said,
            (row_meta(row), said[-500:]),
        )

    # a key variable named by the system is the one read, and the one a 401 names
    denied = (401, {"error": {"message": "Incorrect API key provided: sk-test-not-printed-other"}}, {})
    res, reqs, row = run(
        "openai",
        OPENAI_OK,
        [denied],
        extra_env={"EVH_TEST_OTHER_KEY": "sk-test-not-printed-other"},
        api_key_env="EVH_TEST_OTHER_KEY",
        **PRICES,
    )
    said = (res.stdout or "") + (res.stderr or "")
    check(
        "api_key_env: the named variable's value is sent, and a 401 names that variable, never its value",
        reqs
        and reqs[0]["headers"].get("authorization") == "Bearer sk-test-not-printed-other"
        and "EVH_TEST_OTHER_KEY" in said
        and "sk-test-not-printed-other" not in said
        and res.returncode != 0,
        said[-400:],
    )
finally:
    fake.shutdown()
sys.exit(summary())
