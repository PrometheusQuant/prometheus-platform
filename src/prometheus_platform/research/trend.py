"""Motor de backtest de tendencia con volatility targeting (PQ-67, Estrategia 2).

Implementa las reglas del [pre-registro](docs/estrategias/02-tendencia/pre-registro.md), §3-§8,
con las convenciones del carry (`research/backtest.py`):

- **Decisión diaria a las 00:00 UTC** con el cierre del día: el `close` de la última vela de 1 h
  del día que tenga precio. Un día sin ninguna vela repite el cierre anterior, así *L* y la ventana
  de volatilidad cuentan **días de calendario**.
- **Señal:** ``signo(cierre_t / cierre_{t-L} - 1)``, siempre con el spot.
- **Volatilidad:** desviación muestral de los últimos 30 retornos diarios hasta *t* inclusive,
  anualizada con √365. Solo usa el pasado: ``target_weight`` recibe únicamente los cierres
  hasta *t*.
- **Peso:** ``w = señal · min(1, sigma*/sigma_hat)``. En T1, ``w ≥ 0`` (largo o efectivo);
  |w| ≤ 1 siempre, también después de comisiones.
- **Banda de no-trade:** solo se ajusta si ``|w - w_actual| > 0,10``. Cada decisión cancela la
  orden anterior que no llegó a ejecutarse.
- **Ejecución:** al `open` de la vela que abre en *t* + 1 h, o la siguiente con precio. Es la
  latencia de una hora del pre-registro, que el backtest del carry no aplica (KE-016).
- **T2 (perpetuo):** admite cortos; el largo paga y el corto cobra ``tasa · nocional`` en cada
  liquidación con la posición abierta antes de ella, al `close` del perpetuo de esa vela (o a la
  última marca si falta).
- **Fronteras:** cada periodo cuenta sus eventos en ``[start, end)``. El desarrollo termina en
  ``HOLDOUT_START`` y no decide ni cobra nada a esa hora (KE-014); la última valoración usa el
  cierre del 30-06, que es del desarrollo. Un periodo ``holdout`` solo puede empezar en
  ``HOLDOUT_START``. Así nadie lee el holdout por error.

**Este módulo no ejecuta evaluaciones.** Cada ejecución sobre datos reales es un ensayo y suma a N:
se hace con ``run_and_register``, que deja la fila en el registro compartido (PQ-112). Los
benchmarks B1 y B3 se calculan con ``run_config`` y no se registran, como en el carry.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np
import polars as pl

from prometheus_platform.domain.protocol import HOLDOUT_END, HOLDOUT_START
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
HOUR = timedelta(hours=1)


class Hypothesis(StrEnum):
    T1 = "T1"  # spot, solo largo o efectivo
    T2 = "T2"  # perpetuo, largo o corto, con funding


class Period(StrEnum):
    DESARROLLO = "desarrollo"
    HOLDOUT = "holdout"


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
        if not self.vol_targeting:
            return f"{base}-sin-vol"
        return f"{base}-vol{round(self.sigma_target * 100)}"

    @property
    def is_benchmark(self) -> bool:
        return self.buy_and_hold or not self.vol_targeting

    @property
    def warmup_days(self) -> int:
        """Cierres necesarios antes de la primera decisión."""
        return max(self.lookback, VOL_WINDOW) + 1


def target_weight(closes: Sequence[float], config: TrendConfig) -> float | None:
    """Peso objetivo en *t* con los cierres diarios **hasta t inclusive**.

    Devuelve ``None`` si todavía falta historia para la señal o la volatilidad.
    """
    if config.buy_and_hold:
        return 1.0
    if len(closes) < config.warmup_days:
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
    # Decisiones aplicadas: (instante, peso objetivo, peso actual en ese momento).
    weights: list[tuple[datetime, float, float]] = field(default_factory=list)
    fills: list[tuple[datetime, float]] = field(default_factory=list)  # (vela, precio)


@dataclass
class _Book:
    """Estado de un símbolo. ``q`` en unidades (negativas = corto, solo T2)."""

    perp: bool
    fee: float
    result: TrendResult
    cash: float
    q: float = 0.0
    mark: float = math.nan
    pending: tuple[float, datetime] | None = None  # (peso objetivo, ejecutable desde)

    @property
    def equity(self) -> float:
        # El perpetuo lleva su P&L al efectivo en cada marca; el spot vale q · precio.
        return self.cash if self.perp or not self.q else self.cash + self.q * self.mark

    def mark_to(self, price: float) -> None:
        """Realiza el movimiento de precio desde la marca anterior (en el P&L de precio)."""
        if self.q and not math.isnan(self.mark):
            pnl = self.q * (price - self.mark)
            self.result.price_pnl += pnl
            if self.perp:
                self.cash += pnl
        self.mark = price

    def execute(self, at: datetime, price: float) -> None:
        """Lleva la posición al peso pendiente, al precio de apertura de esta vela."""
        if self.pending is None:
            return
        self.mark_to(price)  # el salto hasta el precio de ejecución es P&L de precio
        weight = self.pending[0]
        # |w| ≤ 1 incluso pagando la comisión: el nocional se reduce en el coste de operar.
        new_q = weight * self.equity / (1 + self.fee) / price
        traded = (new_q - self.q) * price
        if not self.perp:
            self.cash -= traded
        self.cash -= abs(traded) * self.fee
        self.result.costs += abs(traded) * self.fee
        self.result.traded_notional += abs(traded)
        self.result.trades.append((at, "ajuste"))
        self.result.fills.append((at, price))
        self.q, self.pending = new_q, None

    def settle(self, rate: float, price: float) -> None:
        """Funding de T2: el largo paga con tasa positiva y el corto cobra."""
        paid = self.q * price * rate
        self.cash -= paid
        self.result.funding_pnl -= paid

    def decide(self, at: datetime, closes: Sequence[float], config: TrendConfig) -> None:
        self.pending = None  # una decisión nueva sustituye a la orden que no llegó a ejecutarse
        equity = self.equity
        if equity <= 0 or math.isnan(self.mark):
            return
        current = self.q * self.mark / equity
        if config.buy_and_hold:
            # B1: compra todo en la primera decisión y mantiene, sin reequilibrar.
            if not self.q and not self.result.weights:
                self.pending = (1.0, at + EXECUTION_DELAY)
                self.result.weights.append((at, 1.0, current))
            return
        weight = target_weight(closes, config)
        if weight is not None and abs(weight - current) > NO_TRADE_BAND:
            self.pending = (weight, at + EXECUTION_DELAY)
            self.result.weights.append((at, weight, current))


def _validate_period(start: datetime, end: datetime, period: Period) -> None:
    if start >= end:
        raise ValueError(f"start ({start}) debe ser anterior a end ({end})")
    if period is Period.DESARROLLO and end > HOLDOUT_START:
        raise ValueError(
            f"El desarrollo termina en HOLDOUT_START ({HOLDOUT_START:%Y-%m-%d}): "
            "evaluar más allá es leer el holdout"
        )
    if period is Period.HOLDOUT and (
        start < HOLDOUT_START or end > HOLDOUT_END + timedelta(seconds=1)
    ):
        raise ValueError("El holdout va de HOLDOUT_START a HOLDOUT_END")


def _require_warmup(
    symbol: str, closes: Sequence[float], config: TrendConfig, at: datetime
) -> None:
    """Todas las configuraciones se evalúan sobre los mismos días (§4): sin historia, se falla."""
    if not config.buy_and_hold and target_weight(closes, config) is None:
        raise ValueError(
            f"{symbol}: calentamiento insuficiente para {config.name} en {at}:"
            f" {len(closes)} cierres de {config.warmup_days}"
        )


def _hourly_grid(hourly: pl.DataFrame, end: datetime) -> pl.DataFrame:
    """Rejilla horaria completa hasta ``end``: una vela que falta queda como fila con nulos."""
    bars = hourly.filter(pl.col("open_time") < end).sort("open_time")
    if bars.is_empty():
        raise ValueError("No hay velas antes de end")
    first = bars["open_time"][0]
    last = bars["open_time"][-1]
    grid = pl.DataFrame(
        {"open_time": pl.datetime_range(first, last, interval="1h", eager=True)}
    ).with_columns(pl.col("open_time").cast(bars.schema["open_time"]))
    return grid.join(bars, on="open_time", how="left")


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
    period: Period = Period.DESARROLLO,
) -> TrendResult:
    """Simula un símbolo con su parte del capital. ``hourly`` viene de ``panel.hourly_prices``."""
    _validate_period(start, end, period)
    perp = config.hypothesis is Hypothesis.T2
    if perp and settlements is None:
        raise ValueError("T2 necesita las liquidaciones de funding")
    open_col, close_col = ("perp_open", "perp_close") if perp else ("spot_open", "spot_close")
    rates: dict[datetime, float] = {}
    if perp and settlements is not None:
        rates = dict(settlements.select("funding_time", "funding_rate").iter_rows())
    result = TrendResult(symbol=symbol, daily_equity=pl.DataFrame())
    book = _Book(perp, costs.perp if perp else costs.spot, result, cash=capital)
    closes: list[float] = []
    day_close: float | None = None  # último cierre spot visto en el día en curso
    days: list[tuple[datetime, float]] = []
    checked_warmup = False

    rows = _hourly_grid(hourly, end).select(
        "open_time",
        pl.col(open_col).alias("px_open"),
        pl.col(close_col).alias("px_close"),
        pl.col("spot_close").alias("signal_close"),  # la señal usa siempre el spot (§4)
    )
    for o, px_open, px_close, signal_close in rows.iter_rows():
        if book.pending is not None and o >= book.pending[1] and px_open is not None:
            book.execute(o, px_open)
        if px_close is not None:
            book.mark_to(px_close)
        if signal_close is not None:
            day_close = signal_close
        close_time = o + HOUR
        rate = rates.get(close_time)
        if rate is not None and book.q and close_time < end and not math.isnan(book.mark):
            book.settle(rate, px_close if px_close is not None else book.mark)
        if close_time.hour != 0:
            continue
        if day_close is not None:
            closes.append(day_close)  # un día sin velas repite el cierre anterior
        if close_time < start or not closes:
            continue
        if not checked_warmup:
            _require_warmup(symbol, closes, config, close_time)
            checked_warmup = True
        days.append((close_time, book.equity))
        result.hours_total += 24
        result.hours_invested += 24 if book.q else 0
        if close_time < end:  # en end solo se valora (KE-014)
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


def run_config(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del ensayo
    data: Sequence[SymbolMarket],
    config: TrendConfig,
    costs: CostModel,
    *,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
    period: Period = Period.DESARROLLO,
) -> tuple[pl.DataFrame, list[TrendResult]]:
    """Cartera a partes iguales entre símbolos (§4). Devuelve los retornos diarios sobre C."""
    share = 1.0 / len(data)
    results = [
        simulate_trend(
            d.symbol,
            d.hourly,
            d.settlements,
            config=config,
            costs=costs,
            capital=share,
            start=start,
            end=end,
            period=period,
        )
        for d in data
    ]
    return portfolio_returns(list(results), share), results


def run_and_register(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del ensayo
    data: Sequence[SymbolMarket],
    config: TrendConfig,
    costs: CostModel,
    registry: ExperimentRegistry,
    *,
    costs_label: str,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
    period: Period = Period.DESARROLLO,
) -> pl.DataFrame:
    """Ejecuta una configuración **y la registra** (suma a N, pre-registro §5).

    Los benchmarks no se registran: no son ensayos y su Sharpe no debe entrar en V[SR].
    """
    if config.is_benchmark:
        raise ValueError(f"{config.name} es un benchmark: se calcula con run_config")
    familia = getattr(registry, "familia", FAMILY)
    if familia != FAMILY:
        raise ValueError(f"El registro es de la familia {familia!r}, no de {FAMILY!r}")
    frame, results = run_config(data, config, costs, start=start, end=end, period=period)
    returns = frame["ret"].to_numpy()
    perf = performance(returns)
    years = max(len(returns) / DAYS_PER_YEAR, 1e-9)
    invested = sum(r.hours_invested for r in results) / max(sum(r.hours_total for r in results), 1)
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
                "calmar": perf.calmar,
                "t_stat": perf.t_stat,
                "peor_dia": float(returns.min()),
                "vol_realizada": float(np.std(returns, ddof=1)) * math.sqrt(DAYS_PER_YEAR),
                "tiempo_invertido": invested,
                # Capital total C = 1: el nocional negociado ya es una fracción de C.
                "rotacion_anual": sum(r.traded_notional for r in results) / years,
                "pnl_funding": sum(r.funding_pnl for r in results),
                "pnl_precio": sum(r.price_pnl for r in results),
                "costes": sum(r.costs for r in results),
            },
            tags={"period": str(period), "costs": costs_label},
        )
    )
    return frame
