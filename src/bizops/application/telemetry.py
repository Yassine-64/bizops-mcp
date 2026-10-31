"""Tracing through the OpenTelemetry API (a no-op until a provider is registered). Attributes are identifiers,
names, decisions, counts and timings only: arguments, results and customer text never enter a span."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span

Primitive = str | int | float | bool

tracer = trace.get_tracer("bizops")


def _clean(attrs: dict[str, Primitive | None]) -> dict[str, Primitive]:
    return {f"bizops.{k}": v for k, v in attrs.items() if v is not None}


@contextmanager
def span(name: str, **attrs: Primitive | None) -> Iterator[Span]:
    with tracer.start_as_current_span(name, attributes=_clean(attrs)) as s:
        yield s


def annotate(**attrs: Primitive | None) -> None:
    trace.get_current_span().set_attributes(_clean(attrs))


def event(name: str, **attrs: Primitive | None) -> None:
    trace.get_current_span().add_event(name, _clean(attrs))


__all__ = ["annotate", "event", "span", "tracer"]
