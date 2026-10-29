"""Prove the MCP server's own error path reaches GlitchTip: one labelled exception, sent the way a
failing call sends it (mcp_hooks.start, then mcp_hooks.error), and its event id printed so the reader
can find it and delete it. Run inside the evals-mcp container, where the release's hooks, settings
and SDK are:

    docker exec evals-mcp python /srv/evals/current/inspector/mcp_probe.py "homelab-probe evals-mcp <UTC time>"

Exit 0 with the event id; exit 1 when GlitchTip is off (no MCP_SENTRY_DSN) or nothing was sent.
"""

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(
            'usage: mcp_probe.py "<label, e.g. homelab-probe evals-mcp 2026-10-29T16:00Z>"', file=sys.stderr
        )
        return 2
    label = sys.argv[1].strip()[:120]
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("mcp_hooks", here / "mcp_hooks.py")
    hooks = importlib.util.module_from_spec(spec)
    sys.modules["mcp_hooks"] = hooks
    spec.loader.exec_module(hooks)
    hooks.start({"tools": ["probe"], "public": True, "transport": "probe"})
    if not hooks._state["sentry"]:
        print(
            "GlitchTip is off for evals-mcp (no MCP_SENTRY_DSN in its settings): nothing sent",
            file=sys.stderr,
        )
        return 1
    import sentry_sdk  # noqa: PLC0415 -- vendored beside the hooks, in the container only

    try:
        raise RuntimeError(label)
    except RuntimeError as exc:
        hooks.error(exc, {"tool": "probe"})
    event = sentry_sdk.last_event_id()
    sentry_sdk.flush(timeout=10)
    if not event:
        print("no event id: the SDK did not send the probe", file=sys.stderr)
        return 1
    print(f"sent {label!r} to GlitchTip project evals-mcp: event {event}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
