"""Composición del runner de paper trading con el bróker simulado (PQ-54).

Une los adaptadores concretos (API pública de Binance, bróker simulado, diario JSONL y kill-switch
en disco) con la configuración del proceso. La CLI (`pq paper run`) solo llama a ``build``.
"""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import httpx

from prometheus_platform.adapters.binance_public_market import BinancePublicMarket
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.domain.ports import Clock
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.ops.settings import Environment, Settings
from prometheus_platform.portfolio_risk.kill_switch import FLAG_NAME, KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskLimits, RiskManager
from prometheus_platform.research.carry_evaluation import costs_for

JOURNAL_FILE = "diario.jsonl"
HEARTBEAT_FILE = "heartbeat.json"
BROKER_STATE_FILE = "broker-simulado.json"
LOCK_FILE = "runner.lock"
log = get_logger(component="paper_compose")


class RunnerAlreadyRunningError(RuntimeError):
    """Otro ``pq paper run`` opera sobre la misma carpeta: dos procesos duplicarían las órdenes."""


@dataclass(frozen=True, slots=True)
class PaperPaths:
    root: Path

    @property
    def journal(self) -> Path:
        return self.root / JOURNAL_FILE

    @property
    def kill_switch(self) -> Path:
        return self.root / FLAG_NAME

    @property
    def heartbeat(self) -> Path:
        return self.root / HEARTBEAT_FILE

    @property
    def broker_state(self) -> Path:
        return self.root / BROKER_STATE_FILE

    @property
    def lock(self) -> Path:
        return self.root / LOCK_FILE


@contextmanager
def single_instance(paths: PaperPaths) -> Iterator[None]:
    """Un solo runner por carpeta. El bloqueo lo libera el sistema si el proceso muere."""
    paths.root.mkdir(parents=True, exist_ok=True)
    with paths.lock.open("a") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RunnerAlreadyRunningError(
                f"ya hay un runner en {paths.root}: detenlo antes de arrancar otro"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def build(  # noqa: PLR0913 - keyword-only: cada argumento es una pieza de la composición
    *,
    settings: Settings,
    config: RunnerConfig,
    client: httpx.Client,
    clock: Clock,
    paths: PaperPaths,
    capital: Decimal,
) -> PaperRunner:
    if settings.environment is Environment.LIVE:
        raise ValueError("El runner de paper no opera en PQ_ENVIRONMENT=live")
    if not capital.is_finite() or capital <= 0:
        raise ValueError(f"El capital debe ser positivo: {capital}")
    if paths.journal.exists() and not paths.broker_state.exists():
        # El bróker renacería con el capital inicial y contradiría el historial del diario.
        raise ValueError(
            f"Hay diario ({paths.journal}) pero no estado del bróker ({paths.broker_state}): "
            "restáuralo o aparta la carpeta para empezar de cero (runbook de paper trading)"
        )
    limits = RiskLimits.from_settings(settings)
    usable = min(capital * limits.max_leverage, limits.max_notional_total)
    if usable < capital:
        log.warning(
            "paper_capital_capped",
            capital=str(capital),
            usable=str(usable),
            detail="los límites de riesgo acotan el nocional: sube PQ_RISK_MAX_NOTIONAL_*",
        )
    market = BinancePublicMarket(client, clock)
    broker = SimulatedBroker(market, costs_for, clock, paths.broker_state, capital)
    journal = JsonlEventJournal(paths.journal)
    return PaperRunner(
        config=config,
        market=market,
        broker=broker,
        journal=journal,
        kill_switch=KillSwitch(paths.kill_switch, clock, journal, broker),
        risk=RiskManager(limits),
        clock=clock,
        heartbeat_path=paths.heartbeat,
    )
