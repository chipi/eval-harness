#!/usr/bin/env python3
"""Report what is configured, before a sweep discovers it the expensive way.

Never prints a key. Length and shape only — enough to tell "set" from "set to
the placeholder" from "not set", which is the distinction that actually costs
you a failed run halfway through.

    make env-check
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import os

from evaluation_harness import _providers
from evaluation_harness._common import DOTENV_LOADED, ROOT, env_float, env_int, in_checkout


def _state(raw: str, secret: bool) -> str:
    """A key by length and last four characters, never itself; an address as written."""
    if not secret:
        return raw
    if len(raw) < 20:
        return f"SET BUT SUSPICIOUS ({len(raw)} chars)"
    return f"set ({len(raw)} chars, ends …{raw[-4:]})"


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

    print(
        "\nhosted providers (a config's `provider:`): an arm reads <NAME>, a judge EVAL_JUDGE_<NAME>"
        "\nfirst and the arms' <NAME> when that is not set"
    )
    print(f"  {'provider':11} {'variable':20} {'arms':34} judges")
    ready: dict[str, list[str]] = {"arm": [], "judge": []}
    probed: set[str] = set()
    for name, spec in _providers.SPECS.items():
        for var in (spec.key_env, spec.base_env):
            if var is None:
                continue
            secret = var == spec.key_env
            arm = os.environ.get(var, "")
            own = os.environ.get(_providers.JUDGE_PREFIX + var, "")
            arm_s = (
                _state(arm, secret)
                if arm
                else ("not set" if secret or spec.base_required else "not set (the default address)")
            )
            judge_s = (
                f"own: {_state(own, secret)}"
                if own
                else ("the arms'" if arm else ("not set" if secret else arm_s))
            )
            print(f"  {name if secret else '':11} {var:20} {arm_s:34} {judge_s}")
        for role in ready:
            if not _providers.problems({"provider": name, "model": "-"}, role):
                ready[role].append(name)
        if spec.base_required:
            for role in ready:
                url = _providers.env(spec.base_env or "", role)[1] or ""
                if url.startswith("http") and url not in probed and name in ready[role]:
                    probed.add(url)
                    print(f"  {'':11} {'reachable?':20} {url}  {_probe(url)}")
    for role, label in (("arm", "arms"), ("judge", "judges")):
        print(f"  {label} can call: {', '.join(ready[role]) or 'none'}")
    # A local server (or Ollama's port) is called with no key: it bills nothing, so it is no reason for a cap.
    local = {
        (role, name)
        for role in ready
        for name in ready[role]
        if _providers.route({"provider": name, "model": "-"}, role).key == _providers.NO_KEY
    }
    if local:
        print(f"  {', '.join(sorted({n for _r, n in local}))}: a local server, called with no key")
    any_key = any((role, name) not in local for role in ready for name in ready[role])
    if not any_key and not local:
        print("\n  No usable credential. `provider: echo` (arms) and `provider: fake` (judges) work")
        print("  offline: that proves the plumbing, not a model.")

    # Which route the worked examples' hosted arms will take (examples/_shared/gateway.py):
    # the proxy when it is configured, else OpenRouter directly with one key.
    base = os.environ.get("LITELLM_BASE_URL", "")
    lkey = os.environ.get("LITELLM_API_KEY", "")
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
