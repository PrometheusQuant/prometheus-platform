"""Composición del runner de paper trading con el bróker simulado (PQ-54).

Une los adaptadores concretos (API pública de Binance, bróker simulado, diario JSONL y kill-switch
en disco) con la configuración del proceso. La CLI (`pq paper run`) solo llama a ``build``.
"""

from __future__ import annotations

import fcntl
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from prometheus_platform.adapters.binance_public_market import BinancePublicMarket
from prometheus_platform.adapters.binance_ws_market import (
    StreamCache,
    StreamingMarket,
    StreamWorker,
    connect_websocket,
    stream_urls,
)
from prometheus_platform.adapters.counterparty_signals import PublicCounterpartySignals
from prometheus_platform.adapters.exchange_broker import ExchangeBroker
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.api.paper.watchdog import Watchdog
from prometheus_platform.domain.model import Venue
from prometheus_platform.domain.ports import Broker, Clock, ExecutionPort, Notifier
from prometheus_platform.execution.allocation import StrategyAllocation
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.ops.settings import Environment, Settings
from prometheus_platform.portfolio_risk.kill_switch import FLAG_NAME, KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskLimits, RiskManager
from prometheus_platform.research.carry_evaluation import costs_for
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument, symbol_of

JOURNAL_FILE = "diario.jsonl"
HEARTBEAT_FILE = "heartbeat.json"
BROKER_STATE_FILE = "broker-simulado.json"
LOCK_FILE = "runner.lock"
WATCHDOG_STATE_FILE = "watchdog.json"
log = get_logger(component="paper_compose")


STRATEGY_ID = re.compile(r"[A-Za-z0-9_-]+")  # va en un nombre de archivo


class RunnerAlreadyRunningError(RuntimeError):
    """Otro ``pq paper run`` opera sobre la misma carpeta: dos procesos duplicarían las órdenes."""


PAPER_DIR = "paper"
# Bróker del paper (PQ-52): el simulado o el que ejecuta de verdad en Binance Demo.
BROKERS = ("simulado", "binance-demo")


def paper_dir(data_dir: Path, broker: str = "simulado") -> Path:
    """Carpeta del runner: ``paper`` para el simulado y ``paper-<bróker>`` para los demás.

    Separadas para que el paper simulado 24/7 y el de Binance Demo no compartan diario ni estado.
    """
    if broker not in BROKERS:
        raise ValueError(f"Bróker desconocido: {broker!r} (opciones: {', '.join(BROKERS)})")
    return data_dir / (PAPER_DIR if broker == "simulado" else f"{PAPER_DIR}-{broker}")


@dataclass(frozen=True, slots=True)
class PaperPaths:
    root: Path

    @property
    def journal(self) -> Path:
        return self.root / JOURNAL_FILE

    @property
    def kill_switch(self) -> Path:
        return self.root / FLAG_NAME

    def strategy_kill_switch(self, strategy_id: str) -> Path:
        """Bandera del kill-switch de una sola estrategia (PQ-83): ``KILL_SWITCH-<id>``."""
        if not STRATEGY_ID.fullmatch(strategy_id):
            raise ValueError(f"strategy_id no válido para un archivo: {strategy_id!r}")
        return self.root / f"{FLAG_NAME}-{strategy_id}"

    def strategy_kill_switches(self) -> dict[str, Path]:
        """Las banderas de estrategia presentes (sin las temporales del rearme)."""
        found = {}
        for path in sorted(self.root.glob(f"{FLAG_NAME}-*")):
            strategy_id = path.name.removeprefix(f"{FLAG_NAME}-")
            if STRATEGY_ID.fullmatch(strategy_id):
                found[strategy_id] = path
        return found

    @property
    def heartbeat(self) -> Path:
        return self.root / HEARTBEAT_FILE

    @property
    def broker_state(self) -> Path:
        return self.root / BROKER_STATE_FILE

    @property
    def lock(self) -> Path:
        return self.root / LOCK_FILE

    @property
    def watchdog_state(self) -> Path:
        return self.root / WATCHDOG_STATE_FILE


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
    notifier: Notifier | None = None,
    strategies: Sequence[StrategyAllocation] = (),
    exchange_caps: Mapping[Venue, Decimal] | None = None,
    market_data: str = "rest",
    broker: str = "simulado",
    execution: ExecutionPort | None = None,
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
    rest = BinancePublicMarket(client, clock)
    market: BinancePublicMarket | StreamingMarket = rest
    if market_data == "stream":  # PQ-80: precios por websocket, con REST de respaldo
        others = (symbol_of(i) for a in strategies for i in a.strategy.instruments)
        symbols = sorted({*config.symbols, *others})
        cache = StreamCache()
        StreamWorker(cache, stream_urls(symbols), connect=connect_websocket, clock=clock).start()
        market = StreamingMarket(rest, cache, clock)
    elif market_data != "rest":
        raise ValueError(f"market_data debe ser rest o stream, no {market_data!r}")
    paper_broker = _broker(
        broker,
        settings=settings,
        config=config,
        clock=clock,
        market=market,
        paths=paths,
        capital=capital,
        execution=execution,
    )
    journal = JsonlEventJournal(paths.journal)
    # Uno por estrategia, sin bróker: cancelar «todas» las órdenes es cosa del global.
    ids = [config.strategy_id, *(a.strategy_id for a in strategies)]
    strategy_kills = {i: KillSwitch(paths.strategy_kill_switch(i), clock, journal) for i in ids}
    return PaperRunner(
        config=config,
        market=market,
        broker=paper_broker,
        journal=journal,
        kill_switch=KillSwitch(paths.kill_switch, clock, journal, paper_broker),
        risk=RiskManager(limits),
        clock=clock,
        heartbeat_path=paths.heartbeat,
        notifier=notifier,
        environment=settings.environment.value,
        strategies=strategies,
        feed=market,  # la API pública también da las velas de las otras estrategias (PQ-116)
        strategy_kills=strategy_kills,
        exchange_caps=exchange_caps,
        counterparty=PublicCounterpartySignals(client, clock),  # PQ-96
    )


def _broker(  # noqa: PLR0913 - keyword-only: las piezas que necesita cada bróker
    kind: str,
    *,
    settings: Settings,
    config: RunnerConfig,
    clock: Clock,
    market: BinancePublicMarket | StreamingMarket,
    paths: PaperPaths,
    capital: Decimal,
    execution: ExecutionPort | None,
) -> Broker:
    if kind == "simulado":
        return SimulatedBroker(market, costs_for, clock, paths.broker_state, capital)
    if kind != "binance-demo":
        raise ValueError(f"Bróker desconocido: {kind!r} (opciones: {', '.join(BROKERS)})")
    gateway = execution or binance_demo_execution(settings, clock)
    exchange = ExchangeBroker(
        gateway, market=market, clock=clock, state_path=paths.broker_state, initial_cash=capital
    )
    instruments = [i for s in config.symbols for i in (spot_instrument(s), perp_instrument(s))]
    gaps = exchange.reconcile(instruments)
    if gaps:  # el libro y el exchange no cuadran: se avisa, la decisión es humana
        log.warning(
            "paper_reconcile_gaps",
            gaps={str(i): {"libro": str(a), "exchange": str(b)} for i, (a, b) in gaps.items()},
        )
    return exchange


def binance_demo_execution(settings: Settings, clock: Clock) -> ExecutionPort:
    """Adaptador de Binance Demo con las claves del ``.env``; lanza si faltan."""
    key, secret = settings.binance_api_key, settings.binance_api_secret
    if key is None or secret is None:
        raise ValueError(
            "El bróker binance-demo necesita PQ_BINANCE_API_KEY y PQ_BINANCE_API_SECRET"
        )
    # Import diferido: CCXT tarda en cargarse y el resto de comandos de la CLI no lo usan.
    from prometheus_platform.adapters.ccxt_execution import CcxtExecution  # noqa: PLC0415

    return CcxtExecution.binance_demo(key.get_secret_value(), secret.get_secret_value(), clock)


def build_watchdog(
    *, settings: Settings, notifier: Notifier | None, clock: Clock, paths: PaperPaths
) -> Watchdog:
    return Watchdog(
        heartbeat_path=paths.heartbeat,
        state_path=paths.watchdog_state,
        notifier=notifier,
        clock=clock,
        max_age=timedelta(minutes=settings.paper_heartbeat_max_age_minutes),
        environment=settings.environment.value,
    )
