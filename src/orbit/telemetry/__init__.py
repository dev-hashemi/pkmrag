"""Telemetry and distributed tracing subsystem for Project Orbit."""

from __future__ import annotations

from orbit.telemetry.collector import InMemorySpanCollector, RecordedSpan
from orbit.telemetry.spans import SpanLike, trace_span, traced
from orbit.telemetry.tracer import (
    get_memory_collector,
    get_tracer,
    is_telemetry_active,
    setup_telemetry,
    shutdown_telemetry,
)
from orbit.telemetry.views import render_trace_tree

__all__ = [
    "InMemorySpanCollector",
    "RecordedSpan",
    "SpanLike",
    "get_memory_collector",
    "get_tracer",
    "is_telemetry_active",
    "render_trace_tree",
    "setup_telemetry",
    "shutdown_telemetry",
    "trace_span",
    "traced",
]
