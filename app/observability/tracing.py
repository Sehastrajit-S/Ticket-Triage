"""OpenTelemetry + Langfuse instrumentation.

Both backends are optional: with no OTLP endpoint configured we still emit
spans to a console exporter (useful for local dev), and Langfuse is a
complete no-op unless LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are set.
"""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Callable
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import Status, StatusCode

from app.config import get_settings

settings = get_settings()

_resource = Resource.create({"service.name": "ticket-triage-agent"})
_provider = TracerProvider(resource=_resource)

if settings.otel_exporter_otlp_endpoint:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
else:
    # Synchronous (not batched) so spans flush immediately in short-lived local/dev/test processes.
    _provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("ticket-triage")


_langfuse_client = None
if settings.langfuse_public_key and settings.langfuse_secret_key:
    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:  # pragma: no cover - Langfuse is best-effort
        _langfuse_client = None


def get_langfuse():
    """Returns the Langfuse client, or None if not configured."""
    return _langfuse_client


F = TypeVar("F", bound=Callable[..., Any])


def traced(span_name: str) -> Callable[[F], F]:
    """Wraps a sync or async callable in an OTel span (+ Langfuse event if configured).

    Records latency_ms and success/failure on the span; re-raises any exception
    after marking the span as errored so callers retain normal control flow.
    """

    def decorator(fn: F) -> F:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        result = await fn(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        span.record_exception(exc)
                        raise
                    finally:
                        latency_ms = int((time.perf_counter() - start) * 1000)
                        span.set_attribute("latency_ms", latency_ms)
                        if _langfuse_client is not None:
                            try:
                                _langfuse_client.event(name=span_name, metadata={"latency_ms": latency_ms})
                            except Exception:
                                pass

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            with tracer.start_as_current_span(span_name) as span:
                try:
                    result = fn(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise
                finally:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    span.set_attribute("latency_ms", latency_ms)
                    if _langfuse_client is not None:
                        try:
                            _langfuse_client.event(name=span_name, metadata={"latency_ms": latency_ms})
                        except Exception:
                            pass

        return sync_wrapper  # type: ignore[return-value]

    return decorator
