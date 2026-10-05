"""In-memory OpenTelemetry span collector for local inspection and visual tree rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


@dataclass
class RecordedSpan:
    """Captured span representation for in-memory analysis and CLI visualization."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    start_time_ns: int
    end_time_ns: int
    duration_ms: float
    attributes: dict[str, Any] = field(default_factory=dict)
    status_code: str = "OK"
    status_description: Optional[str] = None


class InMemorySpanCollector(SpanExporter):
    """OpenTelemetry SpanExporter that records spans into an in-memory buffer."""

    def __init__(self) -> None:
        self._spans: list[RecordedSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Record exported spans into local memory list."""
        for s in spans:
            trace_id = format(s.context.trace_id, "032x")
            span_id = format(s.context.span_id, "016x")
            parent_id = format(s.parent.span_id, "016x") if s.parent else None

            start_ns = s.start_time or 0
            end_ns = s.end_time or start_ns
            duration_ms = round((end_ns - start_ns) / 1_000_000, 2)

            attrs = dict(s.attributes) if s.attributes else {}
            status = s.status.status_code.name if s.status else "UNSET"
            status_desc = s.status.description if s.status else None

            self._spans.append(
                RecordedSpan(
                    name=s.name,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_id,
                    start_time_ns=start_ns,
                    end_time_ns=end_ns,
                    duration_ms=duration_ms,
                    attributes=attrs,
                    status_code=status,
                    status_description=status_desc,
                )
            )
        return SpanExportResult.SUCCESS

    def get_spans(self) -> list[RecordedSpan]:
        """Return all recorded spans in start-time order."""
        return sorted(self._spans, key=lambda s: s.start_time_ns)

    def clear(self) -> None:
        """Clear all captured spans."""
        self._spans.clear()

    def shutdown(self) -> None:
        """Shutdown collector."""
        self.clear()
