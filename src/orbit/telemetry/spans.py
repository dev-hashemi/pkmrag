"""Lightweight context managers and decorators for OpenTelemetry span tracing."""

from __future__ import annotations

import functools
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional, TypeVar, cast

from opentelemetry import trace

from orbit.telemetry.tracer import get_tracer, is_telemetry_active

F = TypeVar("F", bound=Callable[..., Any])


class SpanLike:
    """Unified interface for both active OpenTelemetry and no-op spans."""

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a key-value attribute on the span."""
        raise NotImplementedError

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        """Set multiple key-value attributes on the span."""
        raise NotImplementedError

    def record_exception(self, exception: BaseException) -> None:
        """Record an exception on the span."""
        raise NotImplementedError


class _NoOpSpan(SpanLike):
    """Ultra-low overhead no-op span used when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass


class _ActiveSpan(SpanLike):
    """Wrapper around an active OpenTelemetry span."""

    def __init__(self, span: trace.Span) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span.is_recording():
            self._span.set_attribute(key, value)

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        if self._span.is_recording():
            for k, v in attributes.items():
                self._span.set_attribute(k, v)

    def record_exception(self, exception: BaseException) -> None:
        if self._span.is_recording():
            self._span.record_exception(exception)
            self._span.set_status(trace.StatusCode.ERROR, str(exception))


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[dict[str, Any]] = None,
) -> Generator[SpanLike, None, None]:
    """Context manager wrapping a code block in an OpenTelemetry trace span."""
    if not is_telemetry_active():
        yield _NoOpSpan()
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        wrapped = _ActiveSpan(span)
        if attributes:
            for k, v in attributes.items():
                wrapped.set_attribute(k, v)
        try:
            yield wrapped
        except BaseException as exc:
            wrapped.record_exception(exc)
            raise


def traced(
    name: Optional[str] = None,
    attributes: Optional[dict[str, Any]] = None,
) -> Callable[[F], F]:
    """Decorator wrapping a function call in an OpenTelemetry span."""

    def decorator(fn: F) -> F:
        span_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, attributes=attributes):
                return fn(*args, **kwargs)

        return cast(F, wrapper)

    return decorator
