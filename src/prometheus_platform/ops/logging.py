"""Logging estructurado con ``structlog``.

Cada evento lleva ``timestamp`` (UTC, ISO-8601), ``level``, ``event`` y ``environment``. En
``paper`` y ``live`` se emite JSON, una línea por evento, listo para auditoría y para cargarlo
en el stack de observabilidad; en ``dev`` se emite en formato legible.

Los secretos se enmascaran antes de renderizar: cualquier ``SecretStr`` y cualquier campo cuyo
nombre sugiera un secreto. Es una segunda barrera; la primera es no loguear secretos.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, TextIO, cast

import structlog
from pydantic import SecretStr
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger

from prometheus_platform.ops.settings import Environment, Settings

REDACTED = "**********"
_SENSITIVE_KEY_PARTS = ("secret", "token", "password", "api_key", "apikey")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: REDACTED if isinstance(k, str) and _is_sensitive_key(k) else _redact(v)
            for k, v in value.items()
        }
    return value


def redact_secrets(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Procesador de structlog que enmascara secretos, también en diccionarios anidados."""
    return cast(EventDict, _redact(event_dict))


def _add_environment(environment: Environment) -> Processor:
    def processor(
        _logger: WrappedLogger, _method: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event_dict.setdefault("environment", environment.value)
        return event_dict

    return processor


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configura structlog para todo el proceso. Llamar una vez, al arrancar."""
    output = stream if stream is not None else sys.stderr
    renderer: Processor
    if settings.environment is Environment.DEV:
        renderer = structlog.dev.ConsoleRenderer(colors=output.isatty())
    else:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_environment(settings.environment),
            structlog.processors.format_exc_info,
            redact_secrets,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        logger_factory=structlog.WriteLoggerFactory(file=output),
        cache_logger_on_first_use=False,
    )


def get_logger(**initial_values: Any) -> FilteringBoundLogger:
    """Logger con contexto inicial, p. ej. ``get_logger(component="ingest")``."""
    return cast(FilteringBoundLogger, structlog.get_logger(**initial_values))
