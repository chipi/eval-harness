#!/usr/bin/env python3
"""This deployment's inspector hooks (hooks.py) with the real OpenTelemetry SDK: a reader's request
is a span; static files, Docker's health check and the collector's scrape are not, and /metrics
still counts every route.

    make hooks-check         (vendors the SDKs, then runs this and test_hooks_env.py)
    PYTHONPATH=harness/.build/vendor python infra/inspector/test_hooks.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# The SDKs are this deployment's, not the harness's dependencies (infra/inspector/requirements.txt): they are not in
# the venv. Run without them, this said ModuleNotFoundError and nothing of where they come from.
if importlib.util.find_spec("opentelemetry.sdk") is None:
    print(
        "  FAIL the OpenTelemetry SDK is not importable: run `make hooks-check`, which vendors it into harness/.build/vendor"
    )
    sys.exit(1)

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "harness"))
from evaluation_harness._check import check, summary  # noqa: E402

spec = importlib.util.spec_from_file_location("hooks", HERE / "hooks.py")
assert spec is not None and spec.loader is not None
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
hooks._state["tracer"] = provider.get_tracer("test")

for route in ("/api/compare", "/api/item", "/api/health", "/metrics", "static", "/api/health"):
    hooks.request({"method": "GET", "path": route, "route": route, "status": 200, "ms": 3.0})

spans = sorted(s.name for s in exporter.get_finished_spans())
check(
    "a reader's comparison and item are traced; the health check, the scrape and static files are not",
    spans == ["GET /api/compare", "GET /api/item"],
    spans,
)
counted = sorted({r for (r, _status) in hooks._count})
check(
    "/metrics still counts every route, the untraced ones included",
    counted == ["/api/compare", "/api/health", "/api/item", "/metrics", "static"],
    counted,
)
_code, _ctype, body = hooks.metrics("")
text = body.decode()
wanted = [
    f'evals_inspector_view_cache_events_total{{event="{e}"}}'
    for e in ("hit", "miss", "wait", "eviction", "invalidation")
]
wanted += [f"evals_inspector_view_cache_{g} " for g in ("entries", "weight", "budget")]
check(
    "/metrics gives the view cache's events (hit, miss, wait, eviction, invalidation) and what it holds against its budget",
    all(w in text for w in wanted),
    [w for w in wanted if w not in text],
)
raise SystemExit(summary())
