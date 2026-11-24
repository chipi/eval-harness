"""The inspector's observability: this deployment's layer over the harness's --hooks, on the box (prod) or on a
workstation (dev, `make serve-dev`; hooks_env.py says which and how they differ).

    catalog_serve.py --hooks /srv/evals/current/inspector/hooks.py

The harness calls start, request and error and serves `routes`; what they do is this file's
business, not the harness's (a project that runs the harness locally uses none of it):

  - errors to GlitchTip, through the Sentry SDK, environment prod or dev (dev: tag worktree), release sha-<7>
    (ADR-0010 in agentic-ai-homelab), the service a tag, when SENTRY_DSN is set;
  - in dev, a log line per request and per error to VictoriaLogs (EVALS_LOGS_URL), labelled with the worktree;
  - one OpenTelemetry span per reader's request to the homelab's trace store over OTLP/HTTP,
    service evals-inspector, namespace evals, when OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set. Not
    for static files, Docker's health check (/api/health, every 30 s) or the collector's scrape
    (/metrics, every 60 s): ~4,300 spans a day that would bury the readers' comparisons and tell
    nothing the health status, the scrape's `up` and the logs do not; /metrics still counts them;
  - /metrics, always: requests and their latency per route and status, the inspector's caches,
    the process's memory, in the Prometheus text format, for the box's collector to scrape. Only
    127.0.0.1:8097 serves it: Caddy forwards nothing but /catalog/api/ to the inspector.

Settings come from the environment, else from the mode's file (hooks_env.py: /srv/evals/observability.env on the box,
~/.config/evals/observability-dev.env on a workstation; never in the repository). The SDKs are vendored beside the
package by render.sh (infra/inspector/requirements.txt). A part whose SDK or setting is missing is off; the inspector
serves as before.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE, NAMESPACE = "evals-inspector", "evals"
KEYS = ("SENTRY_DSN", "SENTRY_DSN_FILE", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "EVALS_LOGS_URL")


def _env_module():
    """hooks_env.py: beside this file when deployed and in the repository (infra/inspector/)."""
    if "evals_hooks_env" not in sys.modules:
        spec = importlib.util.spec_from_file_location("evals_hooks_env", HERE / "hooks_env.py")
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["evals_hooks_env"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["evals_hooks_env"]


hooks_env = _env_module()
#: The latency histogram's upper bounds, in seconds (an answer from the cache is a few ms; a
#: comparison computed cold, seconds).
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
#: Routes counted in /metrics but never traced: static files, and the machines' own requests.
UNTRACED = ("static", "/api/health", "/metrics")

_lock = threading.Lock()
_count: dict = {}  # (route, status) -> requests
_hist: dict = {}  # route -> [count per bucket..., +Inf count, sum of seconds]
_errors = [0]
_state: dict = {"tracer": None, "sentry": False, "logs": None, "env": "prod", "started": time.time()}


def start(info: dict) -> None:
    env = hooks_env.mode()
    if env == "off":
        print(
            "hooks: EVALS_ENV is neither prod nor dev: GlitchTip, traces and logs off, /metrics on",
            flush=True,
        )
        return
    _state["env"], release = env, hooks_env.release(HERE.parent / "RELEASE", env)
    s = hooks_env.settings(env, KEYS)
    worktree = hooks_env.worktree() if env == "dev" else ""
    refused = hooks_env.dsn_refused(s["SENTRY_DSN"], env) if s.get("SENTRY_DSN") else ""
    if refused:
        print(f"hooks: GlitchTip off: {refused}", flush=True)
    elif s.get("SENTRY_DSN"):
        try:
            import sentry_sdk  # noqa: PLC0415

            sentry_sdk.init(
                dsn=s["SENTRY_DSN"],
                environment=env,
                release=release,
                server_name=SERVICE,
                traces_sample_rate=0.0,
                default_integrations=False,
                # A request's frames hold its parameters; GlitchTip gets the error, never their values.
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
                        "deployment.environment": env,
                        "service.version": release,
                        **({"worktree": worktree} if worktree else {}),
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
        f"hooks: {env}{f' ({worktree})' if worktree else ''}, {release}; GlitchTip "
        f"{'on' if _state['sentry'] else 'off'}, traces {'on' if _state['tracer'] else 'off'}"
        f"{', logs ' + ('on' if _state['logs'] else 'off') if env == 'dev' else ''}, /metrics on",
        flush=True,
    )
    if _state["logs"]:
        _state["logs"].log(f"{SERVICE} started", release=release)


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
    if _state["logs"] and route not in UNTRACED:
        _state["logs"].log(
            f"{info['method']} {route} {status} {info['ms']:.0f}ms",
            level="error" if status >= 500 else "info",
            route=route,
            status=status,
            ms=round(info["ms"], 1),
        )


def error(exc: BaseException, info: dict) -> None:
    with _lock:
        _errors[0] += 1
    if _state["logs"]:
        _state["logs"].log(f"{type(exc).__name__}: {exc}", level="error", route=info.get("route", ""))
    if _state["sentry"]:
        import sentry_sdk  # noqa: PLC0415

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("route", info.get("route", ""))
            sentry_sdk.capture_exception(exc)


def _rss_bytes() -> int:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
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
    lines += _view_cache_lines("evals_inspector")
    return 200, "text/plain; version=0.0.4; charset=utf-8", ("\n".join(lines) + "\n").encode()


routes = {"/metrics": metrics}
