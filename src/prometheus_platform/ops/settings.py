"""Configuración tipada y validada por entorno.

Se lee de variables de entorno con prefijo ``PQ_`` y, en desarrollo, de un archivo ``.env``
(ver ``.env.example``). Las invariantes de seguridad se validan al arrancar: un proceso con
una configuración peligrosa o incompleta falla antes de hacer nada.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    PAPER = "paper"
    LIVE = "live"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Configuración del proceso. Los secretos son ``SecretStr`` y no se imprimen nunca."""

    model_config = SettingsConfigDict(
        env_prefix="PQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Environment.DEV
    log_level: LogLevel = "INFO"
    data_dir: Path = Path("data")

    binance_api_key: SecretStr | None = None
    binance_api_secret: SecretStr | None = None
    binance_testnet: bool = True

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    @model_validator(mode="after")
    def _check_environment_invariants(self) -> Self:
        if self.environment is Environment.LIVE:
            missing = [
                f"PQ_{name.upper()}"
                for name in ("binance_api_key", "binance_api_secret")
                if not _has_value(getattr(self, name))
            ]
            if missing:
                raise ValueError(f"El entorno live requiere {', '.join(missing)}")
            if self.binance_testnet:
                raise ValueError(
                    "El entorno live no puede usar la testnet: PQ_BINANCE_TESTNET=false"
                )
        if self.environment is Environment.PAPER and not self.binance_testnet:
            raise ValueError("El paper trading solo opera en testnet: PQ_BINANCE_TESTNET=true")
        return self


def _has_value(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


def load_settings() -> Settings:
    """Carga y valida la configuración. Lanza ``pydantic.ValidationError`` si es inválida."""
    return Settings()
