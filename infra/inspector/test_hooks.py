#!/usr/bin/env python3
"""This deployment's inspector hooks (hooks.py) with the real OpenTelemetry SDK: a reader's request
is a span; static files, Docker's health check and the collector's scrape are not, and /metrics
still counts every route.

    PYTHONPATH=harness/.build/vendor python infra/inspector/test_hooks.py
    make budget-check        (vendors the SDKs, then runs this)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
raise SystemExit(summary())
