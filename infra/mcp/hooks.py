"""The MCP server's observability: this deployment's layer over `evh mcp --hooks`, on the box (prod) or on a
workstation (dev, `make mcp-dev`; hooks_env.py says which and how they differ).

    mcp_server.py --http ... --hooks /srv/evals/current/inspector/mcp_hooks.py

The harness calls start, request (after every tool call) and error, and serves `routes`; what they
do is this file's business, not the harness's (`evh mcp` on a laptop uses none of it):

  - errors to GlitchTip, through the Sentry SDK, environment prod or dev (dev: tag worktree), release sha-<7>, the
    service a tag: in prod the MCP server's own project (MCP_SENTRY_DSN), in dev the one dev project (SENTRY_DSN);
  - in dev, a log line per tool call and per error to VictoriaLogs (EVALS_LOGS_URL), labelled with the worktree;
  - one OpenTelemetry span per tool call, service evals-mcp, namespace evals, when
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set;
  - /metrics, always: calls per tool and outcome and their latency, the process's memory, in the
    Prometheus text format, on the loopback port only (Caddy forwards nothing but /mcp to it);
  - in prod only, one Umami event per tool call, `mcp:<tool>`, on the site's own Umami website (its id in
    mcp_umami.json, which render.sh writes from site/analytics.json: public), POSTed to
    UMAMI_SEND_URL (Umami's /api/send on the tailnet, so the deploy renders it: no tailnet name is
    committed), in the background so a slow Umami never delays an answer. The event carries the
    tool, how it ended and how long it took; never an argument's value. Umami counts a visitor as
    a hash of the address and the user agent (homelab, 2026-10-29), so it is told the caller's
    address (X-Forwarded-For) and one fixed browser-like user agent: an agent library's own
    (python-httpx, node-fetch) reads to Umami as a bot, and its events are dropped without an error.

Settings come from the environment, else from the mode's file (hooks_env.py: /srv/evals/observability.env on the box,
~/.config/evals/observability-dev.env on a workstation; never in the repository). A part whose SDK or setting is missing
is off; the server answers as before.
"""

from __future__ import annotations

import importlib.util
import json
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE, NAMESPACE, HOST = "evals-mcp", "evals", "evals.humancopilot.eu"
KEYS = (
    "MCP_SENTRY_DSN",
    "SENTRY_DSN",
    "SENTRY_DSN_FILE",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "UMAMI_SEND_URL",
    "EVALS_LOGS_URL",
)
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
#: The user agent Umami is told (see the module docstring): browser-shaped, so Umami keeps the event.
UA = "Mozilla/5.0 (X11; Linux x86_64) evals-mcp"

_lock = threading.Lock()
_count: dict = {}  # (tool, outcome) -> calls
_hist: dict = {}  # tool -> [count per bucket..., +Inf count, sum of seconds]
_errors = [0]
_umami_sent = [0, 0]  # sent, failed
_state: dict = {
    "tracer": None,
    "sentry": False,
    "umami": None,
    "logs": None,
    "env": "prod",
    "started": time.time(),
    "tools": frozenset(),
}
#: Umami events waiting to be sent, by one worker thread: a bounded queue, so a slow or absent Umami
#: never grows threads or memory (an event that does not fit is dropped and counted).
_events: queue.Queue = queue.Queue(maxsize=256)


def _env_module():
    """hooks_env.py: beside this file when deployed (render.sh), infra/inspector/ in the repository."""
    if "evals_hooks_env" not in sys.modules:
        f = HERE / "hooks_env.py"
        if not f.is_file():
            f = HERE.parent / "inspector" / "hooks_env.py"
        spec = importlib.util.spec_from_file_location("evals_hooks_env", f)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["evals_hooks_env"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["evals_hooks_env"]


hooks_env = _env_module()


def start(info: dict) -> None:
    # The tools this server offers: anything else a client names is counted as "unknown".
    _state["tools"] = frozenset(info.get("tools") or ())
    env = hooks_env.mode()
    if env == "off":
        print(
            "hooks: EVALS_ENV is neither prod nor dev: GlitchTip, traces, logs and Umami off, /metrics on",
            flush=True,
        )
        return
    _state["env"], release = env, hooks_env.release(HERE.parent / "RELEASE", env)
    s = hooks_env.settings(env, KEYS)
    worktree = hooks_env.worktree() if env == "dev" else ""
    dsn = s.get("SENTRY_DSN" if env == "dev" else "MCP_SENTRY_DSN", "")
    refused = hooks_env.dsn_refused(dsn, env) if dsn else ""
    if refused:
        print(f"hooks: GlitchTip off: {refused}", flush=True)
    elif dsn:
        try:
            import sentry_sdk  # noqa: PLC0415

            sentry_sdk.init(
                dsn=dsn,
                environment=env,
                release=release,
                server_name=SERVICE,
                traces_sample_rate=0.0,
                default_integrations=False,
                # A call's frames hold its arguments; GlitchTip gets the error, never their values.
                include_local_variables=False,
            )
            sentry_sdk.set_tag("service", SERVICE)
            if worktree:
                sentry_sdk.set_tag("worktree", worktree)
            _state["sentry"] = True
        except Exception as exc:  # noqa: BLE001
            print(f"hooks: GlitchTip off: {type(exc).__name__}: {exc}", flush=True)
    if env == "dev" and s.get("EVALS_LOGS_URL"):
        _state["logs"] = hooks_env.LogPush(
            s["EVALS_LOGS_URL"], {"service": SERVICE, "environment": env, "worktree": worktree}
        )
    if s.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: PLC0415
            from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
            from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": SERVICE,
                        "service.namespace": NAMESPACE,
                        "deployment.environment": env,
                        "service.version": release,
                        **({"worktree": worktree} if worktree else {}),
                    }
                )
            )
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=s["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]))
            )
            # Kept to these hooks, never the process's global provider: the MCP SDK opens its own span
            # per request named by what the client sent (a tool name as long as the body), and a
            # global provider exported them all, beside the one span per call made here.
            import atexit  # noqa: PLC0415

            atexit.register(provider.shutdown)
            _state["tracer"] = provider.get_tracer(SERVICE)
        except Exception as exc:  # noqa: BLE001
            print(f"hooks: traces off: {type(exc).__name__}: {exc}", flush=True)
    # The site's analytics count prod's callers only: a dev run is not a visit.
    umami = HERE / "mcp_umami.json"
    cfg = json.loads(umami.read_text(encoding="utf-8")) if umami.is_file() else {}
    if env == "prod" and s.get("UMAMI_SEND_URL", "").startswith("https://") and cfg.get("website_id"):
        _state["umami"] = {"send_url": s["UMAMI_SEND_URL"], "website_id": cfg["website_id"]}
        threading.Thread(target=_umami_worker, daemon=True, name="umami").start()
    print(
        f"hooks: {env}{f' ({worktree})' if worktree else ''}, {release}; GlitchTip "
        f"{'on' if _state['sentry'] else 'off'}, traces {'on' if _state['tracer'] else 'off'}, "
        + (
            f"logs {'on' if _state['logs'] else 'off'}"
            if env == "dev"
            else f"Umami {'on' if _state['umami'] else 'off'}"
        )
        + ", /metrics on",
        flush=True,
    )
    if _state["logs"]:
        _state["logs"].log(f"{SERVICE} started", release=release)


def _outcome(info: dict) -> str:
    if info.get("refused"):
        return f"refused:{info['refused']}"
    return "ok" if info.get("exit") == 0 else "error"


def _tool(info: dict) -> str:
    """A tool name safe for a label, a span and an event: one the server offers, else "unknown"."""
    t = str(info.get("tool") or "")
    return t if t in _state["tools"] else "unknown"


def request(info: dict) -> None:
    tool, outcome, secs = _tool(info), _outcome(info), (info.get("ms") or 0) / 1000
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
        span.set_attribute("mcp.argument_names", ",".join(info.get("args") or [])[:400])
        if outcome == "error":
            from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=end)
    if _state["logs"]:
        _state["logs"].log(
            f"mcp {tool} {outcome} {info.get('ms') or 0:.0f}ms",
            level="error" if outcome == "error" else "info",
            tool=tool,
            outcome=outcome,
            ms=info.get("ms") or 0,
            args=",".join(info.get("args") or [])[:400],
        )
    # Analytics count calls the server answered; a refused one (rate, busy, a bad argument) is not a
    # visit, and sending it would let a flood through to the shared Umami.
    if _state["umami"] is not None and not info.get("refused"):
        try:
            _events.put_nowait((tool, outcome, info.get("ms") or 0, str(info.get("client") or "")[:64]))
        except queue.Full:
            with _lock:
                _umami_sent[1] += 1


def _umami_worker() -> None:
    while True:
        _umami(*_events.get())


def _umami(tool: str, outcome: str, ms: int, client: str) -> None:
    """One event on the site's Umami website, as its script would send it: POST /api/send."""
    cfg = _state["umami"]
    body = {
        "type": "event",
        "payload": {
            "website": cfg["website_id"],
            "hostname": HOST,
            "url": f"/mcp/{tool}",
            "title": f"MCP {tool}",
            "name": f"mcp:{tool}",
            "data": {"tool": tool, "outcome": outcome, "ms": ms},
        },
    }
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if client:
        headers["X-Forwarded-For"] = client
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
    if _state["logs"]:
        _state["logs"].log(f"{type(exc).__name__}: {exc}", level="error", tool=_tool(info))
    if _state["sentry"]:
        import sentry_sdk  # noqa: PLC0415

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("tool", _tool(info))
            sentry_sdk.capture_exception(exc)


def _rss_bytes() -> int:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _view_cache_lines(prefix: str) -> list[str]:
    """The model's view cache (RFC-032 P1), as {prefix}_view_cache_*: what it did since the process started and what
    it holds against its budget. Nothing when an internal moved: the metric goes, the answers stay."""
    try:
        from evaluation_harness.model import view_cache  # noqa: PLC0415

        st = view_cache.stats()
    except Exception:  # noqa: BLE001
        return []
    lines = [
        (
            f"# HELP {prefix}_view_cache_events_total What the view cache did: a hit, a miss (computed), a wait for "
            "another call's computation, an eviction for room, an invalidation (the data changed)."
        ),
        f"# TYPE {prefix}_view_cache_events_total counter",
    ]
    lines += [
        f'{prefix}_view_cache_events_total{{event="{e}"}} {st[e]}'
        for e in ("hit", "miss", "wait", "eviction", "invalidation")
    ]
    for name, what in (("entries", "Views kept."), ("weight", "What the views kept weigh (per-item scores)."),
                       ("budget", "The most they may weigh (EVH_VIEW_CACHE_VALUES).")):  # fmt: skip
        lines += [f"# HELP {prefix}_view_cache_{name} {what}", f"# TYPE {prefix}_view_cache_{name} gauge",
                  f"{prefix}_view_cache_{name} {st[name]}"]  # fmt: skip
    return lines


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
    lines += _view_cache_lines("evals_mcp")
    return 200, "text/plain; version=0.0.4; charset=utf-8", ("\n".join(lines) + "\n").encode()


routes = {"/metrics": metrics}
