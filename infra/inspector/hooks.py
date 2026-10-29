"""The prod inspector's observability: this deployment's layer over the harness's --hooks.

    catalog_serve.py --hooks /srv/evals/current/inspector/hooks.py

The harness calls start, request and error and serves `routes`; what they do is this file's
business, not the harness's (a project that runs the harness locally uses none of it):

  - errors to GlitchTip, through the Sentry SDK, environment prod, release sha-<7> (ADR-0010 in
    agentic-ai-homelab), when SENTRY_DSN is set;
  - one OpenTelemetry span per reader's request to the homelab's trace store over OTLP/HTTP,
    service evals-inspector, namespace evals, when OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set. Not
    for static files, Docker's health check (/api/health, every 30 s) or the collector's scrape
    (/metrics, every 60 s): ~4,300 spans a day that would bury the readers' comparisons and tell
    nothing the health status, the scrape's `up` and the logs do not; /metrics still counts them;
  - /metrics, always: requests and their latency per route and status, the inspector's caches,
    the process's memory, in the Prometheus text format, for the box's collector to scrape. Only
    127.0.0.1:8097 serves it: Caddy forwards nothing but /catalog/api/ to the inspector.

Settings come from the environment, else from /srv/evals/observability.env (KEY=VALUE lines, on
the box, never in the repository). The SDKs are vendored beside the package by render.sh
(infra/inspector/requirements.txt). A part whose SDK or setting is missing is off; the inspector
serves as before.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE, NAMESPACE, ENVIRONMENT = "evals-inspector", "evals", "prod"
#: The latency histogram's upper bounds, in seconds (an answer from the cache is a few ms; a
#: comparison computed cold, seconds).
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
#: Routes counted in /metrics but never traced: static files, and the machines' own requests.
UNTRACED = ("static", "/api/health", "/metrics")

_lock = threading.Lock()
_count: dict = {}  # (route, status) -> requests
_hist: dict = {}  # route -> [count per bucket..., +Inf count, sum of seconds]
_errors = [0]
_state: dict = {"tracer": None, "sentry": False, "started": time.time()}


def _settings() -> dict:
    """The environment, over /srv/evals/observability.env (or EVALS_OBS_ENV)."""
    out: dict = {}
    f = Path(os.environ.get("EVALS_OBS_ENV", "/srv/evals/observability.env"))
    if f.is_file():
        for line in f.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                out[k.strip()] = v.strip().strip('"').strip("'")
    out.update(
        {k: v for k, v in os.environ.items() if k in ("SENTRY_DSN", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")}
    )
    return out


def _release() -> str:
    """sha-<7> of this release (render.sh writes the sha to RELEASE beside inspector/)."""
    f = HERE.parent / "RELEASE"
    sha = f.read_text().strip() if f.is_file() else ""
    return f"sha-{sha[:7]}" if sha else "unknown"


def start(info: dict) -> None:
    s, release = _settings(), _release()
    if s.get("SENTRY_DSN"):
        try:
            import sentry_sdk  # noqa: PLC0415

            sentry_sdk.init(
                dsn=s["SENTRY_DSN"],
                environment=ENVIRONMENT,
                release=release,
                server_name=SERVICE,
                traces_sample_rate=0.0,
                default_integrations=False,
                # A request's frames hold its parameters; GlitchTip gets the error, never their values.
                include_local_variables=False,
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
            # Spans leave in batches every few seconds: send what is left when the process ends
            # (a container stop is SIGTERM, which by default skips atexit, so it exits cleanly).
            import atexit  # noqa: PLC0415
            import signal  # noqa: PLC0415

            atexit.register(provider.shutdown)
            if (
                threading.current_thread() is threading.main_thread()
                and signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
            ):
                signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
            _state["tracer"] = trace.get_tracer(SERVICE)
        except Exception as exc:  # noqa: BLE001
            print(f"hooks: traces off: {type(exc).__name__}: {exc}", flush=True)
    print(
        f"hooks: {release}; GlitchTip {'on' if _state['sentry'] else 'off'}, traces "
        f"{'on' if _state['tracer'] else 'off'}, /metrics on",
        flush=True,
    )


def request(info: dict) -> None:
    route, status, secs = info["route"], int(info["status"]), info["ms"] / 1000
    with _lock:
        _count[(route, status)] = _count.get((route, status), 0) + 1
        h = _hist.setdefault(route, [0] * (len(BUCKETS) + 2))
        for i, b in enumerate(BUCKETS):
            if secs <= b:
                h[i] += 1
        h[len(BUCKETS)] += 1
        h[-1] += secs
    tracer = _state["tracer"]
    if tracer is not None and route not in UNTRACED:
        end = time.time_ns()
        span = tracer.start_span(f"{info['method']} {route}", start_time=end - int(info["ms"] * 1e6))
        span.set_attribute("http.request.method", info["method"])
        span.set_attribute("http.route", route)
        span.set_attribute("http.response.status_code", status)
        if status >= 500:
            from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=end)


def error(exc: BaseException, info: dict) -> None:
    with _lock:
        _errors[0] += 1
    if _state["sentry"]:
        import sentry_sdk  # noqa: PLC0415

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("route", info.get("route", ""))
            sentry_sdk.capture_exception(exc)


def _rss_bytes() -> int:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _caches() -> dict:
    """The inspector's own caches (the 2026-10-26 OOM grew one of them unbounded)."""
    import sys  # noqa: PLC0415

    out = {}
    try:
        from evaluation_harness import stats  # noqa: PLC0415

        # The server runs as a script (compose: python .../catalog_serve.py): its caches are in
        # __main__, and importing catalog_serve would give an empty second copy.
        main = sys.modules.get("__main__")
        if hasattr(main, "_CACHE"):
            cs = main
        else:
            from evaluation_harness import catalog_serve as cs  # noqa: PLC0415

        out["answers"] = len(cs._CACHE)
        out["scores"] = cs._scores.cache_info().currsize
        out["p_values"] = len(stats._P)
        out["sign_tables"] = len(stats._SIGNS)
    except Exception:  # noqa: BLE001 -- an internal moved: the metric goes, the page stays
        pass
    return out


def metrics(query: str) -> tuple:
    """The Prometheus text format, for the box's collector."""
    # No identity labels: the box's collector sets service, namespace, environment and instance
    # (infra/observability/evals.alloy), the way every scrape there does.
    lines = [
        "# HELP evals_inspector_requests_total Requests answered, by route and status.",
        "# TYPE evals_inspector_requests_total counter",
    ]
    with _lock:
        count, hist, errors = dict(_count), {k: list(v) for k, v in _hist.items()}, _errors[0]
    for (route, status), n in sorted(count.items()):
        lines.append(f'evals_inspector_requests_total{{route="{route}",status="{status}"}} {n}')
    lines += [
        "# HELP evals_inspector_request_seconds How long a request took, by route.",
        "# TYPE evals_inspector_request_seconds histogram",
    ]
    for route, h in sorted(hist.items()):
        for i, b in enumerate(BUCKETS):
            lines.append(f'evals_inspector_request_seconds_bucket{{route="{route}",le="{b}"}} {h[i]}')
        lines.append(f'evals_inspector_request_seconds_bucket{{route="{route}",le="+Inf"}} {h[len(BUCKETS)]}')
        lines.append(f'evals_inspector_request_seconds_count{{route="{route}"}} {h[len(BUCKETS)]}')
        lines.append(f'evals_inspector_request_seconds_sum{{route="{route}"}} {h[-1]:.6f}')
    lines += [
        "# HELP evals_inspector_errors_total Requests that raised (answered 500).",
        "# TYPE evals_inspector_errors_total counter",
        f"evals_inspector_errors_total {errors}",
        "# HELP evals_inspector_cache_entries Entries in each of the inspector's caches.",
        "# TYPE evals_inspector_cache_entries gauge",
    ]
    lines += [f'evals_inspector_cache_entries{{cache="{k}"}} {v}' for k, v in sorted(_caches().items())]
    lines += [
        "# HELP evals_inspector_resident_memory_bytes The process's resident memory.",
        "# TYPE evals_inspector_resident_memory_bytes gauge",
        f"evals_inspector_resident_memory_bytes {_rss_bytes()}",
        "# HELP evals_inspector_start_time_seconds When the process started.",
        "# TYPE evals_inspector_start_time_seconds gauge",
        f"evals_inspector_start_time_seconds {_state['started']:.0f}",
    ]
    return 200, "text/plain; version=0.0.4; charset=utf-8", ("\n".join(lines) + "\n").encode()


routes = {"/metrics": metrics}
