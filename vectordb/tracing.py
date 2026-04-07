# vectordb/tracing.py
"""
OpenTelemetry tracing setup for Vector DB.

Controlled by settings:
  OTEL_ENABLED        — bool, default False
  OTEL_SERVICE_NAME   — str,  default "vector-db"
  OTEL_ENDPOINT       — str,  default "" (empty = console exporter)

When OTEL_ENABLED is False this module is a no-op; no OTel packages are
imported so the app works even if the SDK is not installed.

When enabled:
  - FastAPI requests and SQLAlchemy queries are auto-instrumented.
  - Spans are exported via OTLP HTTP when OTEL_ENDPOINT is set,
    otherwise written to stdout (useful for local development).
"""
import structlog

logger = structlog.get_logger(__name__)


def setup_tracing(app, engine, settings) -> None:
    """
    Configure OpenTelemetry tracing.

    Parameters
    ----------
    app      : FastAPI application instance
    engine   : SQLAlchemy Engine
    settings : vectordb.config.Settings
    """
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
        logger.info("otel_exporter", type="otlp", endpoint=settings.otel_endpoint)
    else:
        exporter = ConsoleSpanExporter()
        logger.info("otel_exporter", type="console")

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)

    logger.info("otel_tracing_enabled", service=settings.otel_service_name)
