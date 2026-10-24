#!/usr/bin/env python3
"""Report what is configured, before a sweep discovers it the expensive way.

Never prints a key. Length and shape only — enough to tell "set" from "set to
the placeholder" from "not set", which is the distinction that actually costs
you a failed run halfway through.

    make env-check
"""

from __future__ import annotations

import argparse
import os

from _common import DOTENV_LOADED, ROOT, env_float, env_int, in_checkout

PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")


def _probe(base: str) -> str:
    """Is the proxy actually up? A sweep should not be how you find out."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    try:
        with urllib.request.urlopen(base.rstrip("/") + "/health/liveliness", timeout=4) as r:  # noqa: S310 — the operator's own gateway URL  # nosec B310
            return f"yes ({r.status})"
    except urllib.error.HTTPError as exc:
        return f"responded {exc.code} — up, but that endpoint is not there"
    except Exception as exc:  # noqa: BLE001
        return f"NO — {type(exc).__name__}: {exc}"


def main() -> int:
    """Report configured environment variables before a sweep."""
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    env_file = ROOT / ".env"
    # DOTENV_LOADED is the count from the FIRST load, at import. Calling
    # load_dotenv() again here would report 0 — everything is already in the
    # environment by then — which read as "your .env did nothing".
    print(
        f".env: {'loaded ' + str(DOTENV_LOADED) + ' var(s)' if env_file.is_file() else 'NOT PRESENT'}"
        f"   ({env_file})"
    )
    if not env_file.is_file():
        print("      create it with the keys your providers read, one NAME=value per line\n")

    print("\nLiteLLM proxy (one key, many providers)")
    base = os.environ.get("LITELLM_BASE_URL", "")
    lkey = os.environ.get("LITELLM_API_KEY", "")
    proxy_ready = bool(base and lkey)
    print(f"  LITELLM_BASE_URL       {base or 'not set'}")
    print(
        "  LITELLM_API_KEY        " + (f"set ({len(lkey)} chars, ends …{lkey[-4:]})" if lkey else "not set")
    )
    if proxy_ready:
        print(f"  reachable?             {_probe(base)}")

    print("\ndirect provider keys (only needed without a proxy)")
    any_key = False
    for name in PROVIDER_KEYS:
        raw = os.environ.get(name, "")
        if not raw:
            state = "not set"
        elif len(raw) < 20:
            state = f"SET BUT SUSPICIOUS ({len(raw)} chars — placeholder?)"
        else:
            any_key = True
            state = f"set ({len(raw)} chars, ends …{raw[-4:]})"
        print(f"  {name:22} {state}")
    if not any_key and not proxy_ready:
        print("\n  No usable credential. `provider: echo` still works offline —")
        print("  that is enough to prove the plumbing, not to evaluate a model.")
    any_key = any_key or proxy_ready

    # Which route the worked examples' hosted arms will take (examples/_shared/gateway.py):
    # the proxy when it is configured, else OpenRouter directly with one key.
    orkey = os.environ.get("OPENROUTER_API_KEY", "")
    route = (
        "proxy (your LiteLLM)"
        if base.startswith("http") and lkey
        else "direct to OpenRouter (examples/models.json maps the aliases)"
        if len(orkey) >= 20
        else "NONE — hosted example arms will refuse to start"
    )
    # The worked examples live in a checkout of this repository; a pinned project has none.
    if in_checkout():
        print(f"\n  hosted example arms →  {route}")

    print("\nsystem under test")
    ref = os.environ.get("EVAL_BUILD_REF", "")
    print(f"  EVAL_BUILD_REF         {ref or '(unset — falls back to this tree’s git SHA)'}")

    print("\nspend and retries")
    cap = env_float("EVAL_MAX_COST_USD")
    print(
        "  EVAL_MAX_COST_USD      "
        + (f"${cap:.2f} — mid-run abort" if cap else "NONE — a sweep can bill without limit")
    )
    print(f"  EVAL_MAX_RETRIES       {env_int('EVAL_MAX_RETRIES', 3)}")
    print(f"  EVAL_RETRY_MAX_DELAY   {env_int('EVAL_RETRY_MAX_DELAY', 60)}s — backoff cap")
    # EVAL_CONCURRENCY was reported here and read by NOTHING: a knob that printed a value
    # and changed no behaviour. The sweep is sequential. This project has already lost two
    # arms to the same shape — EVAL_MAX_RETRIES was documented and honoured only by the
    # bundled adapter, so raising it on the real example was a no-op and an arm was thrown
    # away as "the model cannot do the task". Do not advertise a setting until it is wired.

    if cap is None and any_key:
        # Only a failure when it can actually cost something. A fresh drop-in
        # with no keys runs `provider: echo` offline, where a cap is moot —
        # failing there would train people to ignore this command.
        print("\n  A provider key is set and EVAL_MAX_COST_USD is NOT.")
        print("  The cap is the only thing between a wrong price and an unbounded bill.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
