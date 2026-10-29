"""The prod MCP server's observability: this deployment's layer over `evh mcp --hooks`.

    mcp_server.py --http ... --hooks /srv/evals/current/inspector/mcp_hooks.py

The harness calls start, request (after every tool call) and error, and serves `routes`; what they
do is this file's business, not the harness's (`evh mcp` on a laptop uses none of it):

  - errors to GlitchTip, through the Sentry SDK, environment prod, release sha-<7>, when
    MCP_SENTRY_DSN is set (the GlitchTip project for the MCP server, not the inspector's);
  - one OpenTelemetry span per tool call, service evals-mcp, namespace evals, when
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set;
  - /metrics, always: calls per tool and outcome and their latency, the process's memory, in the
    Prometheus text format, on the loopback port only (Caddy forwards nothing but /mcp to it);
  - one Umami event per tool call, `mcp:<tool>`, on the site's own Umami website (its id in
    mcp_umami.json, which render.sh writes from site/analytics.json: public), POSTed to
    UMAMI_SEND_URL (Umami's /api/send on the tailnet, so the deploy renders it: no tailnet name is
    committed), in the background so a slow Umami never delays an answer. The event carries the
    tool, how it ended and how long it took; never an argument's value. Umami counts a visitor as
    a hash of the address and the user agent (homelab, 2026-10-29), so it is told the caller's
    address (X-Forwarded-For) and one fixed browser-like user agent: an agent library's own
    (python-httpx, node-fetch) reads to Umami as a bot, and its events are dropped without an error.

Settings come from the environment, else from /srv/evals/observability.env (KEY=VALUE lines, on
the box, never in the repository). A part whose SDK or setting is missing is off; the server
answers as before.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE, NAMESPACE, ENVIRONMENT, HOST = "evals-mcp", "evals", "prod", "evals.humancopilot.eu"
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
#: The user agent Umami is told (see the module docstring): browser-shaped, so Umami keeps the event.
UA = "Mozilla/5.0 (X11; Linux x86_64) evals-mcp"

_lock = threading.Lock()
_count: dict = {}  # (tool, outcome) -> calls
_hist: dict = {}  # tool -> [count per bucket..., +Inf count, sum of seconds]
_errors = [0]
_umami_sent = [0, 0]  # sent, failed
_state: dict = {"tracer": None, "sentry": False, "umami": None, "started": time.time()}


def _settings() -> dict:
    out: dict = {}
    f = Path(os.environ.get("EVALS_OBS_ENV", "/srv/evals/observability.env"))
    if f.is_file():
        for line in f.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                out[k.strip()] = v.strip().strip('"').strip("'")
    keys = ("MCP_SENTRY_DSN", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "UMAMI_SEND_URL")
    out.update({k: v for k, v in os.environ.items() if k in keys})
    return out


def _release() -> str:
    f = HERE.parent / "RELEASE"
    sha = f.read_text().strip() if f.is_file() else ""
    return f"sha-{sha[:7]}" if sha else "unknown"


def start(info: dict) -> None:
    s, release = _settings(), _release()
    if s.get("MCP_SENTRY_DSN"):
        try:
            import sentry_sdk  # noqa: PLC0415

            sentry_sdk.init(
                dsn=s["MCP_SENTRY_DSN"],
                environment=ENVIRONMENT,
                release=release,
                server_name=SERVICE,
                traces_sample_rate=0.0,
                default_integrations=False,
            )
            _state["sentry"] = True
        except Exception as exc:  # noqa: BLE001
            print(f"hooks: GlitchTip off: {type(exc).__name__}: {exc}", flush=True)
    if s.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        try:
            from opentelemetry import trace  # noqa: PLC0415
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: PLC0415
            from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
            from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": SERVICE,
                        "service.namespace": NAMESPACE,
                        "deployment.environment": ENVIRONMENT,
                        "service.version": release,
                    }
                )
            )
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=s["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]))
            )
            trace.set_tracer_provider(provider)
            import atexit  # noqa: PLC0415

            atexit.register(provider.shutdown)
            _state["tracer"] = trace.get_tracer(SERVICE)
        except Exception as exc:  # noqa: BLE001
            print(f"hooks: traces off: {type(exc).__name__}: {exc}", flush=True)
    umami = HERE / "mcp_umami.json"
    cfg = json.loads(umami.read_text()) if umami.is_file() else {}
    if s.get("UMAMI_SEND_URL", "").startswith("https://") and cfg.get("website_id"):
        _state["umami"] = {"send_url": s["UMAMI_SEND_URL"], "website_id": cfg["website_id"]}
    print(
        f"hooks: {release}; GlitchTip {'on' if _state['sentry'] else 'off'}, traces "
        f"{'on' if _state['tracer'] else 'off'}, Umami {'on' if _state['umami'] else 'off'}, /metrics on",
        flush=True,
    )


def _outcome(info: dict) -> str:
    if info.get("refused"):
        return f"refused:{info['refused']}"
    return "ok" if info.get("exit") == 0 else "error"


def request(info: dict) -> None:
    tool, outcome, secs = info.get("tool", ""), _outcome(info), (info.get("ms") or 0) / 1000
    with _lock:
        _count[(tool, outcome)] = _count.get((tool, outcome), 0) + 1
        h = _hist.setdefault(tool, [0] * (len(BUCKETS) + 2))
        for i, b in enumerate(BUCKETS):
            if secs <= b:
                h[i] += 1
        h[len(BUCKETS)] += 1
        h[-1] += secs
    tracer = _state["tracer"]
    if tracer is not None:
        end = time.time_ns()
        span = tracer.start_span(f"mcp {tool}", start_time=end - int(secs * 1e9))
        span.set_attribute("mcp.tool", tool)
        span.set_attribute("mcp.outcome", outcome)
        span.set_attribute("mcp.argument_names", ",".join(info.get("args") or []))
        if outcome == "error":
            from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=end)
    if _state["umami"] is not None:
        threading.Thread(target=_umami, args=(info, outcome), daemon=True).start()


def _umami(info: dict, outcome: str) -> None:
    """One event on the site's Umami website, as its script would send it: POST /api/send."""
    cfg = _state["umami"]
    tool = info.get("tool", "")
    body = {
        "type": "event",
        "payload": {
            "website": cfg["website_id"],
            "hostname": HOST,
            "url": f"/mcp/{tool}",
            "title": f"MCP {tool}",
            "name": f"mcp:{tool}",
            "data": {"tool": tool, "outcome": outcome, "ms": info.get("ms") or 0},
        },
    }
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if info.get("client"):
        headers["X-Forwarded-For"] = info["client"]
    req = urllib.request.Request(  # noqa: S310 -- an https URL the deploy rendered
        cfg["send_url"], data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5):  # noqa: S310  # nosec B310
            pass
        with _lock:
            _umami_sent[0] += 1
    except Exception:  # noqa: BLE001 -- analytics never break or slow a call
        with _lock:
            _umami_sent[1] += 1


def error(exc: BaseException, info: dict) -> None:
    with _lock:
        _errors[0] += 1
    if _state["sentry"]:
        import sentry_sdk  # noqa: PLC0415

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("tool", info.get("tool", ""))
            sentry_sdk.capture_exception(exc)


def _rss_bytes() -> int:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def metrics(query: str) -> tuple:
    """The Prometheus text format, for the box's collector."""
    lines = [
        "# HELP evals_mcp_calls_total Tool calls answered, by tool and outcome.",
        "# TYPE evals_mcp_calls_total counter",
    ]
    with _lock:
        count, hist, errors, sent = (
            dict(_count),
            {k: list(v) for k, v in _hist.items()},
            _errors[0],
            list(_umami_sent),
        )
    for (tool, outcome), n in sorted(count.items()):
        lines.append(f'evals_mcp_calls_total{{tool="{tool}",outcome="{outcome}"}} {n}')
    lines += [
        "# HELP evals_mcp_call_seconds How long a tool call took, by tool.",
        "# TYPE evals_mcp_call_seconds histogram",
    ]
    for tool, h in sorted(hist.items()):
        for i, b in enumerate(BUCKETS):
            lines.append(f'evals_mcp_call_seconds_bucket{{tool="{tool}",le="{b}"}} {h[i]}')
        lines.append(f'evals_mcp_call_seconds_bucket{{tool="{tool}",le="+Inf"}} {h[len(BUCKETS)]}')
        lines.append(f'evals_mcp_call_seconds_count{{tool="{tool}"}} {h[len(BUCKETS)]}')
        lines.append(f'evals_mcp_call_seconds_sum{{tool="{tool}"}} {h[-1]:.3f}')
    lines += [
        "# HELP evals_mcp_errors_total Errors the server raised (sent to GlitchTip when on).",
        "# TYPE evals_mcp_errors_total counter",
        f"evals_mcp_errors_total {errors}",
        "# HELP evals_mcp_umami_events_total Umami events, by result.",
        "# TYPE evals_mcp_umami_events_total counter",
        f'evals_mcp_umami_events_total{{result="sent"}} {sent[0]}',
        f'evals_mcp_umami_events_total{{result="failed"}} {sent[1]}',
        "# HELP evals_mcp_resident_memory_bytes The process's resident memory.",
        "# TYPE evals_mcp_resident_memory_bytes gauge",
        f"evals_mcp_resident_memory_bytes {_rss_bytes()}",
        "# HELP evals_mcp_start_time_seconds When the process started.",
        "# TYPE evals_mcp_start_time_seconds gauge",
        f"evals_mcp_start_time_seconds {_state['started']:.0f}",
    ]
    return 200, "text/plain; version=0.0.4; charset=utf-8", ("\n".join(lines) + "\n").encode()


routes = {"/metrics": metrics}
