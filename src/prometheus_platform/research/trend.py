"""Motor de backtest de tendencia con volatility targeting (PQ-67, Estrategia 2).

Implementa las reglas del [pre-registro](docs/estrategias/02-tendencia/pre-registro.md), §3-§8,
con las convenciones del carry (`research/backtest.py`):

- **Decisión diaria a las 00:00 UTC** con el `close` de la última vela de 1 h del día.
- **Señal:** ``signo(cierre_t / cierre_{t-L} - 1)``.
- **Volatilidad:** desviación muestral de los últimos 30 retornos diarios hasta *t* inclusive,
  anualizada con √365. Solo usa el pasado: ``target_weight`` recibe únicamente los cierres
  hasta *t*.
- **Peso:** ``w = señal · min(1, sigma*/sigma_hat)``. En T1, ``w ≥ 0`` (largo o efectivo);
  |w| ≤ 1 siempre.
- **Banda de no-trade:** solo se ajusta si ``|w - w_actual| > 0,10``.
- **Ejecución:** al `open` de la vela que abre en *t* + 1 h, o la siguiente disponible. Es la
  latencia de una hora del pre-registro, que el backtest del carry no aplica (KE-016).
- **T2 (perpetuo):** admite cortos; el largo paga y el corto cobra ``tasa · nocional`` en cada
  liquidación con la posición abierta antes de ella, valorada al `close` del perpetuo.
- **Desarrollo:** no decide ni cobra eventos ``≥ HOLDOUT_START`` (corrección de KE-014).

**Este módulo no ejecuta evaluaciones.** Cada ejecución sobre datos reales es un ensayo y suma a N:
se hace con ``run_and_register``, que deja la fila en el registro compartido (PQ-112).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np
import polars as pl

from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.backtest import CostModel, SymbolResult, portfolio_returns
from prometheus_platform.research.carry_evaluation import ExperimentRegistry, TrialRecord
from prometheus_platform.research.validation import performance

DAYS_PER_YEAR = 365
VOL_WINDOW = 30  # retornos diarios; fijo, no es un parámetro (§4)
NO_TRADE_BAND = 0.10  # fija, no es un parámetro (§4)
EXECUTION_DELAY = timedelta(hours=1)
EVALUATION_START = datetime(2020, 5, 1, tzinfo=HOLDOUT_START.tzinfo)  # §4, tras el calentamiento
L_GRID = (20, 60, 120)
SIGMA_GRID = (0.20, 0.40)
FAMILY = "tendencia"


class Hypothesis(StrEnum):
    T1 = "T1"  # spot, solo largo o efectivo
    T2 = "T2"  # perpetuo, largo o corto, con funding


@dataclass(frozen=True)
class TrendConfig:
    lookback: int
    sigma_target: float
    hypothesis: Hypothesis = Hypothesis.T1
    vol_targeting: bool = True  # False: benchmark B3 (misma señal, sin escalar)
    buy_and_hold: bool = False  # True: benchmark B1

    def __post_init__(self) -> None:
        if self.lookback < 1:
            raise ValueError(f"L debe ser ≥ 1: {self.lookback}")
        if not 0 < self.sigma_target <= 2:
            raise ValueError(f"sigma* fuera de rango: {self.sigma_target}")
        if self.buy_and_hold and self.hypothesis is not Hypothesis.T1:
            raise ValueError("B1 es comprar y mantener spot (T1)")

    @property
    def name(self) -> str:
        if self.buy_and_hold:
            return "B1-comprar-y-mantener"
        base = f"{self.hypothesis}-L{self.lookback}"
        return (
            f"{base}-sin-vol"
            if not self.vol_targeting
            else f"{base}-vol{round(self.sigma_target * 100)}"
        )

    @property
    def warmup_days(self) -> int:
        return max(self.lookback, VOL_WINDOW + 1)


def target_weight(closes: Sequence[float], config: TrendConfig) -> float | None:
    """Peso objetivo en *t* con los cierres diarios **hasta t inclusive**.

    Devuelve ``None`` si todavía falta historia para la señal o la volatilidad.
    """
    if config.buy_and_hold:
        return 1.0
    if len(closes) <= config.warmup_days - 1 or len(closes) < config.lookback + 1:
        return None
    now, past = closes[-1], closes[-1 - config.lookback]
    momentum = now / past - 1
    signal = 1.0 if momentum > 0 else -1.0 if momentum < 0 else 0.0
    if config.hypothesis is Hypothesis.T1:
        signal = max(signal, 0.0)
    if not config.vol_targeting:
        return signal
    window = np.asarray(closes[-(VOL_WINDOW + 1) :], dtype=float)
    returns = window[1:] / window[:-1] - 1
    sigma = float(np.std(returns, ddof=1)) * math.sqrt(DAYS_PER_YEAR)
    scale = 1.0 if sigma <= 0 else min(1.0, config.sigma_target / sigma)
    return max(-1.0, min(1.0, signal * scale))


@dataclass
class TrendResult(SymbolResult):
    traded_notional: float = 0.0  # para la rotación anual (§8)
    weights: list[tuple[datetime, float]] = field(default_factory=list)  # decisiones aplicadas


@dataclass
class _Book:
    """Estado de un símbolo. ``q`` en unidades (negativas = corto, solo T2)."""

    perp: bool
    fee: float
    result: TrendResult
    cash: float
    q: float = 0.0
    mark: float = math.nan
    pending: tuple[float, datetime] | None = None  # (nocional objetivo, ejecutable desde)

    @property
    def equity(self) -> float:
        # El perpetuo lleva su P&L al efectivo en cada marca; el spot vale q · precio.
        return self.cash if self.perp or not self.q else self.cash + self.q * self.mark

    def execute(self, at: datetime, price: float) -> None:
        """Lleva la posición al nocional pendiente, al precio de apertura de esta vela."""
        if self.pending is None:
            return
        if self.perp and self.q and not math.isnan(self.mark):
            self.cash += self.q * (price - self.mark)  # P&L hasta el precio de ejecución
        new_q = self.pending[0] / price
        traded = (new_q - self.q) * price
        if not self.perp:
            self.cash -= traded
        self.cash -= abs(traded) * self.fee
        self.result.costs += abs(traded) * self.fee
        self.result.traded_notional += abs(traded)
        self.result.trades.append((at, "ajuste"))
        self.q, self.mark, self.pending = new_q, price, None

    def mark_to(self, price: float) -> None:
        if self.q and not math.isnan(self.mark):
            pnl = self.q * (price - self.mark)
            self.result.price_pnl += pnl
            if self.perp:
                self.cash += pnl
        self.mark = price

    def settle(self, rate: float, price: float) -> None:
        """Funding de T2: el largo paga con tasa positiva y el corto cobra."""
        paid = self.q * price * rate
        self.cash -= paid
        self.result.funding_pnl -= paid

    def decide(self, at: datetime, closes: Sequence[float], config: TrendConfig) -> None:
        equity = self.equity
        if equity <= 0 or math.isnan(self.mark):
            return
        if config.buy_and_hold:
            # B1: compra todo en la primera decisión y mantiene, sin reequilibrar.
            if not self.q and self.pending is None and not self.result.weights:
                self.pending = (equity, at + EXECUTION_DELAY)
                self.result.weights.append((at, 1.0))
            return
        weight = target_weight(closes, config)
        if weight is not None and abs(weight - self.q * self.mark / equity) > NO_TRADE_BAND:
            self.pending = (weight * equity, at + EXECUTION_DELAY)
            self.result.weights.append((at, weight))


def simulate_trend(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del ensayo
    symbol: str,
    hourly: pl.DataFrame,
    settlements: pl.DataFrame | None,
    *,
    config: TrendConfig,
    costs: CostModel,
    capital: float,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
) -> TrendResult:
    """Simula un símbolo con su parte del capital. ``hourly`` viene de ``panel.hourly_prices``."""
    perp = config.hypothesis is Hypothesis.T2
    open_col, close_col = ("perp_open", "perp_close") if perp else ("spot_open", "spot_close")
    rates: dict[datetime, float] = {}
    if perp and settlements is not None:
        rates = dict(settlements.select("funding_time", "funding_rate").iter_rows())
    result = TrendResult(symbol=symbol, daily_equity=pl.DataFrame())
    book = _Book(perp, costs.perp if perp else costs.spot, result, cash=capital)
    closes: list[float] = []
    days: list[tuple[datetime, float]] = []

    bars = hourly.filter(pl.col("open_time") < end)
    for o, px_open, px_close, spot_close in bars.select(
        "open_time",
        pl.col(open_col).alias("px_open"),
        pl.col(close_col).alias("px_close"),
        pl.col("spot_close").alias("signal_close"),  # la señal usa siempre el spot (§4)
    ).iter_rows():
        if book.pending is not None and o >= book.pending[1] and px_open is not None:
            book.execute(o, px_open)
        if px_close is not None:
            book.mark_to(px_close)
        close_time = o + timedelta(hours=1)
        rate = rates.get(close_time)
        if rate is not None and book.q and close_time < HOLDOUT_START and px_close is not None:
            book.settle(rate, px_close)
        if close_time.hour != 0 or spot_close is None:
            continue
        closes.append(spot_close)
        result.hours_total += 24
        if close_time < start:
            continue
        days.append((close_time, book.equity))
        result.hours_invested += 24 if book.q else 0
        if close_time < HOLDOUT_START:  # se valora el cierre del desarrollo, sin decidir (KE-014)
            book.decide(close_time, closes, config)

    result.daily_equity = pl.DataFrame(
        {"date": [d for d, _ in days], "equity": [e for _, e in days]},
        schema={"date": pl.Datetime("ms", "UTC"), "equity": pl.Float64},
    )
    return result


@dataclass(frozen=True)
class SymbolMarket:
    symbol: str
    hourly: pl.DataFrame
    settlements: pl.DataFrame | None = None


def run_config(
    data: Sequence[SymbolMarket], config: TrendConfig, costs: CostModel
) -> tuple[pl.DataFrame, list[TrendResult]]:
    """Cartera a partes iguales entre símbolos (§4). Devuelve los retornos diarios sobre C."""
    share = 1.0 / len(data)
    results = [
        simulate_trend(d.symbol, d.hourly, d.settlements, config=config, costs=costs, capital=share)
        for d in data
    ]
    return portfolio_returns(list(results), share), results


def run_and_register(
    data: Sequence[SymbolMarket],
    config: TrendConfig,
    costs: CostModel,
    registry: ExperimentRegistry,
    *,
    tags: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Ejecuta una configuración **y la registra** (suma a N, pre-registro §5)."""
    frame, results = run_config(data, config, costs)
    returns = frame["ret"].to_numpy()
    perf = performance(returns)
    years = max(len(returns) / DAYS_PER_YEAR, 1e-9)
    registry.log_trial(
        TrialRecord(
            hypothesis=str(config.hypothesis),
            name=config.name,
            params={
                "L": str(config.lookback),
                "sigma_target": str(config.sigma_target),
                "vol_targeting": str(config.vol_targeting),
            },
            metrics={
                "sharpe": perf.sharpe,
                "sharpe_daily": perf.sharpe_daily,
                "cagr": perf.cagr,
                "max_drawdown": perf.max_drawdown,
                "turnover_anual": sum(r.traded_notional for r in results) / years,
            },
            tags={"family": FAMILY, "period": "desarrollo", **(tags or {})},
        )
    )
    return frame
