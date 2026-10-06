"""OpenTelemetry TracerProvider lifecycle and configuration."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

from pkmrag.telemetry.collector import InMemorySpanCollector

logger = logging.getLogger("pkmrag.telemetry")

_tracer_provider: Optional[TracerProvider] = None
_memory_collector: Optional[InMemorySpanCollector] = None
_is_active: bool = False


def is_telemetry_active() -> bool:
    """Check if active telemetry provider is registered."""
    return _is_active


def get_memory_collector() -> Optional[InMemorySpanCollector]:
    """Return active in-memory collector if configured."""
    return _memory_collector


def setup_telemetry(
    service_name: str = "project-orbit",
    enable_memory_collector: bool = False,
    otlp_endpoint: Optional[str] = None,
    otlp_headers: Optional[str] = None,
) -> TracerProvider:
    """Initialize OpenTelemetry TracerProvider with configured exporters."""
    global _tracer_provider, _memory_collector, _is_active

    if _is_active and _tracer_provider is not None:
        if enable_memory_collector and _memory_collector is None:
            _memory_collector = InMemorySpanCollector()
            _tracer_provider.add_span_processor(SimpleSpanProcessor(_memory_collector))
        return _tracer_provider

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if enable_memory_collector:
        _memory_collector = InMemorySpanCollector()
        provider.add_span_processor(SimpleSpanProcessor(_memory_collector))

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            headers_dict: dict[str, str] = {}
            if otlp_headers:
                for item in otlp_headers.split(","):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        headers_dict[k.strip()] = v.strip()

            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=headers_dict,
            )
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except Exception as e:
            # Strictly write warnings to stderr — NEVER to stdout in MCP mode!
            sys.stderr.write(f"[WARN] Failed to configure OTLP trace exporter: {e}\n")

    # Register provider internally and reset OpenTelemetry global provider cleanly
    trace._TRACER_PROVIDER = provider
    _tracer_provider = provider
    _is_active = True
    return provider


def shutdown_telemetry() -> None:
    """Flush and shut down active tracer provider and exporters."""
    global _tracer_provider, _memory_collector, _is_active
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception:
            pass
        _tracer_provider = None

    trace._TRACER_PROVIDER = None
    _memory_collector = None
    _is_active = False


def get_tracer(name: str = "project-orbit") -> trace.Tracer:
    """Get an OpenTelemetry Tracer instance."""
    if _tracer_provider is not None:
        return _tracer_provider.get_tracer(name)
    return trace.get_tracer(name)
