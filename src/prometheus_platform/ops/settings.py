"""Configuración tipada y validada por entorno.

Se lee de variables de entorno con prefijo ``PQ_`` y, en desarrollo, de un archivo ``.env``
(ver ``.env.example``). Las invariantes de seguridad se validan al arrancar: un proceso con
una configuración peligrosa o incompleta falla antes de hacer nada.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    PAPER = "paper"
    LIVE = "live"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
MAX_LEVERAGE_CAP = 2.0  # ningún entorno puede configurar más apalancamiento que esto


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
    # Zona horaria IANA en la que se muestran las alertas a las personas (los logs siguen en UTC).
    alert_timezone: str = "America/La_Paz"

    # Límites de riesgo (PQ-53). Valores conservadores para paper trading con < 1.000 USD.
    risk_max_notional_symbol_usd: float = Field(default=500.0, gt=0, allow_inf_nan=False)
    risk_max_notional_total_usd: float = Field(default=1_000.0, gt=0, allow_inf_nan=False)
    risk_max_leverage: float = Field(default=1.0, gt=0, le=MAX_LEVERAGE_CAP, allow_inf_nan=False)
    risk_hard_leverage: float = Field(default=1.5, gt=0, le=MAX_LEVERAGE_CAP, allow_inf_nan=False)
    risk_max_daily_loss: float = Field(default=0.02, gt=0, lt=1, allow_inf_nan=False)
    risk_max_hedge_imbalance: float = Field(default=0.15, gt=0, lt=1, allow_inf_nan=False)
    risk_imbalance_grace_seconds: int = Field(default=300, ge=0)

    # Registro de ensayos compartido (PQ-112): cada carril escribe en su archivo.
    research_lane: str = "david"
    research_author: str = ""  # vacío: se toma de `git config user.name`
    research_ledger_dir: Path = Path("docs/estrategias/ensayos")

    @field_validator("alert_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Zona horaria desconocida: {value!r} (usa un nombre IANA)") from exc
        return value

    @field_validator("research_lane")
    @classmethod
    def _check_lane(cls, value: str) -> str:
        if not value.isidentifier():
            raise ValueError(
                f"PQ_RESEARCH_LANE debe ser un nombre simple (p. ej. david): {value!r}"
            )
        return value

    @property
    def alert_tz(self) -> ZoneInfo:
        return ZoneInfo(self.alert_timezone)

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
        if self.risk_hard_leverage < self.risk_max_leverage:
            raise ValueError("PQ_RISK_HARD_LEVERAGE debe ser >= PQ_RISK_MAX_LEVERAGE")
        if self.risk_max_notional_symbol_usd > self.risk_max_notional_total_usd:
            raise ValueError("El nocional por símbolo no puede superar al nocional total")
        if self.environment is Environment.PAPER and not self.binance_testnet:
            raise ValueError("El paper trading solo opera en testnet: PQ_BINANCE_TESTNET=true")
        return self


def _has_value(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


def load_settings() -> Settings:
    """Carga y valida la configuración. Lanza ``pydantic.ValidationError`` si es inválida."""
    return Settings()
