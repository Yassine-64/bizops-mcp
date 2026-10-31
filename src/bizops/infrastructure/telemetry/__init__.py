"""Register one global tracer provider. The Anthropic SDK and the bizops spans both emit into it, so a model
call and the control-plane work it triggers share one trace.

Exporter: OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set (the standard variable), otherwise one JSON line per
span appended to <data_dir>/traces.jsonl."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult


class JsonLinesExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self.path.open("a") as f:
            for s in spans:
                ctx = s.get_span_context()
                assert ctx is not None
                row: dict[str, Any] = {
                    "trace_id": f"{ctx.trace_id:032x}",
                    "span_id": f"{ctx.span_id:016x}",
                    "parent_id": f"{s.parent.span_id:016x}" if s.parent else None,
                    "name": s.name,
                    "start_ns": s.start_time,
                    "end_ns": s.end_time,
                    "status": s.status.status_code.name,
                    "attributes": dict(s.attributes or {}),
                    "events": [{"name": e.name, "attributes": dict(e.attributes or {})} for e in s.events],
                }
                f.write(json.dumps(row, default=str) + "\n")
        return SpanExportResult.SUCCESS


def configure_tracing(data_dir: Path, service: str = "bizops") -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(JsonLinesExporter(data_dir / "traces.jsonl")))
    trace.set_tracer_provider(provider)
    return provider


__all__ = ["JsonLinesExporter", "configure_tracing"]
