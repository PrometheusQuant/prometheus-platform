"""Logging estructurado con ``structlog``.

Cada evento lleva ``timestamp`` (UTC, ISO-8601), ``level``, ``event`` y ``environment``. En
``paper`` y ``live`` se emite JSON, una línea por evento, listo para auditoría y para cargarlo
en el stack de observabilidad; en ``dev`` se emite en formato legible.

Si se pasa un ``Notifier``, los eventos ERROR y CRITICAL se reenvían también como alerta
(``ops/alerting.py``), ya con los secretos enmascarados.

Los secretos se enmascaran antes de renderizar: cualquier ``SecretStr`` y cualquier campo cuyo
nombre sugiera un secreto. Es una segunda barrera; la primera es no loguear secretos.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, TextIO, cast

import structlog
from pydantic import SecretStr
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger

from prometheus_platform.domain.ports import Notifier
from prometheus_platform.ops.alerting import AlertForwarder
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


# Formatos conocidos de credenciales en texto libre.
_TOKEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),  # Anthropic / OpenAI
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}"),  # GitHub
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # bot de Telegram
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    # 64 alfanuméricos con mayúsculas (formato de las claves de Binance; un SHA-256 en hex no).
    re.compile(r"\b(?=[A-Za-z0-9]{64}\b)(?=[A-Za-z0-9]*[A-Z])[A-Za-z0-9]{64}\b"),
]
# Asignaciones cuyo nombre sugiere un secreto (mismo criterio que para los campos del log).
_ASSIGNMENT = re.compile(
    r"(?P<key>\b[\w.-]*(?:" + "|".join(_SENSITIVE_KEY_PARTS) + r")[\w.-]*)"
    r"(?P<sep>[\"']?\s*[:=]\s*[\"']?)(?P<value>[^\s\"',;]+)",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    """Enmascara secretos en texto libre (p. ej. transcripciones exportadas)."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)

    def _mask(match: re.Match[str]) -> str:
        value = match.group("value")
        if value == REDACTED or not value.strip("*"):
            return match.group(0)
        return f"{match.group('key')}{match.group('sep')}{REDACTED}"

    return _ASSIGNMENT.sub(_mask, text)


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


def configure_logging(
    settings: Settings, stream: TextIO | None = None, notifier: Notifier | None = None
) -> None:
    """Configura structlog para todo el proceso. Llamar una vez, al arrancar."""
    output = stream if stream is not None else sys.stderr
    renderer: Processor
    if settings.environment is Environment.DEV:
        renderer = structlog.dev.ConsoleRenderer(colors=output.isatty())
    else:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_environment(settings.environment),
        structlog.processors.format_exc_info,
        redact_secrets,
    ]
    if notifier is not None:
        processors.append(AlertForwarder(notifier))
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        logger_factory=structlog.WriteLoggerFactory(file=output),
        cache_logger_on_first_use=False,
    )


def get_logger(**initial_values: Any) -> FilteringBoundLogger:
    """Logger con contexto inicial, p. ej. ``get_logger(component="ingest")``."""
    return cast(FilteringBoundLogger, structlog.get_logger(**initial_values))
