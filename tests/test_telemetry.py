"""Unit tests for the Orbit telemetry and distributed tracing subsystem."""

from __future__ import annotations

import io
from collections.abc import Generator

import pytest
from rich.console import Console

from orbit.telemetry import (
    RecordedSpan,
    get_memory_collector,
    is_telemetry_active,
    render_trace_tree,
    setup_telemetry,
    shutdown_telemetry,
    trace_span,
    traced,
)
from orbit.telemetry.spans import _NoOpSpan


@pytest.fixture(autouse=True)
def clean_telemetry() -> Generator[None, None, None]:
    """Ensure clean telemetry state before and after each test."""
    shutdown_telemetry()
    yield
    shutdown_telemetry()


def test_noop_span_when_telemetry_inactive() -> None:
    """When telemetry is not configured, trace_span yields NoOpSpan with zero overhead."""
    assert not is_telemetry_active()
    assert get_memory_collector() is None

    with trace_span("test.noop", attributes={"key": "val"}) as span:
        assert isinstance(span, _NoOpSpan)
        span.set_attribute("dynamic", 123)
        span.set_attributes({"another": True})
        span.record_exception(ValueError("error"))

    @traced(name="test.traced_func")
    def compute(a: int, b: int) -> int:
        return a + b

    assert compute(3, 4) == 7


def test_in_memory_span_collector_recording() -> None:
    """InMemorySpanCollector records hierarchical span executions and attributes."""
    setup_telemetry(enable_memory_collector=True)
    assert is_telemetry_active()

    collector = get_memory_collector()
    assert collector is not None

    with trace_span("orbit.test_root", attributes={"root_attr": "hello"}):
        with trace_span("orbit.test_child", attributes={"mode": "hybrid"}) as child_s:
            child_s.set_attribute("candidates.count", 42)

    spans = collector.get_spans()
    assert len(spans) == 2

    # Spans are exported on end: child finishes before root
    child_span = next(s for s in spans if s.name == "orbit.test_child")
    root_span = next(s for s in spans if s.name == "orbit.test_root")

    assert child_span.attributes["mode"] == "hybrid"
    assert child_span.attributes["candidates.count"] == 42
    assert root_span.attributes["root_attr"] == "hello"

    assert child_span.parent_span_id == root_span.span_id
    assert root_span.parent_span_id is None
    assert child_span.trace_id == root_span.trace_id
    assert child_span.duration_ms >= 0.0
    assert root_span.duration_ms >= child_span.duration_ms

    collector.clear()
    assert len(collector.get_spans()) == 0


def test_trace_span_records_exception() -> None:
    """trace_span captures exception without swallowing it."""
    setup_telemetry(enable_memory_collector=True)
    collector = get_memory_collector()
    assert collector is not None

    with pytest.raises(RuntimeError, match="boom"):
        with trace_span("orbit.test_error"):
            raise RuntimeError("boom")

    spans = collector.get_spans()
    assert len(spans) == 1
    assert spans[0].status_code == "ERROR"
    assert spans[0].status_description is not None
    assert "boom" in spans[0].status_description


def test_traced_decorator_with_active_telemetry() -> None:
    """@traced decorator works seamlessly when telemetry is active."""
    setup_telemetry(enable_memory_collector=True)
    collector = get_memory_collector()
    assert collector is not None

    @traced(name="orbit.multiply")
    def multiply(x: int, y: int) -> int:
        return x * y

    result = multiply(6, 7)
    assert result == 42

    spans = collector.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "orbit.multiply"


def test_render_trace_tree_output() -> None:
    """render_trace_tree formats a hierarchy into a visual tree."""
    out_buf = io.StringIO()
    test_console = Console(file=out_buf, width=120, force_terminal=False)

    # Empty spans
    render_trace_tree([], console=test_console)
    assert "No execution trace recorded" in out_buf.getvalue()

    # Populated spans
    sample_spans = [
        RecordedSpan(
            name="orbit.search",
            trace_id="trace-001",
            span_id="span-root",
            parent_span_id=None,
            start_time_ns=1_000_000_000,
            end_time_ns=1_100_000_000,
            duration_ms=100.0,
            attributes={"cache.hit": False, "mode": "hybrid", "pruned_by_graph": 15},
            status_code="OK",
        ),
        RecordedSpan(
            name="lancedb.dense_search",
            trace_id="trace-001",
            span_id="span-child-1",
            parent_span_id="span-root",
            start_time_ns=1_010_000_000,
            end_time_ns=1_050_000_000,
            duration_ms=40.0,
            attributes={"candidates.count": 25},
            status_code="OK",
        ),
    ]

    out_buf2 = io.StringIO()
    test_console2 = Console(file=out_buf2, width=120, force_terminal=False)
    render_trace_tree(sample_spans, console=test_console2)
    rendered = out_buf2.getvalue()

    assert "orbit.search" in rendered
    assert "lancedb.dense_search" in rendered
    assert "100.00ms" in rendered
    assert "40.00ms" in rendered
