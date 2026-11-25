"""Motor de backtest del momentum transversal en perpetuos (PQ-114, Estrategia 3).

Implementa las reglas del [pre-registro](docs/estrategias/03-momentum-transversal/pre-registro.md),
§3 a §6, con las convenciones de la tendencia (`research/trend.py`):

- **Cierre diario:** el `close` del perpetuo de la última vela de 1 h del día con precio. Un día sin
  velas repite el cierre anterior, así *L* cuenta **días de calendario**.
- **Rebalanceo semanal:** cada lunes a las 00:00 UTC. Entran al ranking los símbolos con una vela en
  el día que acaba de cerrar («tienen precio ese día») y con *L* días de historia.
- **Señal:** ``ret_L = cierre_t / cierre_{t-L} - 1``. El ranking va de mayor a menor; los empates se
  ordenan por símbolo, alfabéticamente.
- **Carteras:** con *n* símbolos elegibles, cada tercio tiene ``floor(n / 3)`` símbolos. X1: el
  tercio superior largo y el inferior corto, 0,5 del capital por lado a partes iguales. X2: el
  tercio superior largo con 1x. B1: todo el universo elegible largo a partes iguales, con 1x.
- **Ejecución:** al `open` de la vela que abre en *t* + 1 h, o la siguiente con precio, símbolo por
  símbolo. Cada decisión sustituye a las órdenes pendientes de la anterior. El nocional objetivo es
  ``peso · capital`` al ejecutar, descontando la comisión para que el bruto no pase de 1x.
- **Costes:** comisión taker del perpetuo más el slippage del símbolo, por lado (§6).
- **Funding:** en cada liquidación con la posición abierta antes de ella, el largo paga y el corto
  cobra ``tasa · nocional``, al `close` de la vela que cierra en la liquidación.
- **Deslistados (§3.4):** un símbolo que **ya no vuelve a tener velas** se cierra a su último
  precio un día después de la última, pagando costes. Nunca se sustituye por otro. Un hueco
  temporal de los datos (p. ej. tres días sin velas en Data Vision en 2022) **no** es un
  deslistado: la posición se mantiene y se valora cuando vuelven las velas. El símbolo sí queda
  fuera del ranking del lunes si no tuvo precio el día anterior.
- **Fronteras:** como en la tendencia (KE-014). El desarrollo termina en ``HOLDOUT_START`` y a esa
  hora solo se valora.

**Este módulo no ejecuta evaluaciones.** Cada ejecución sobre datos reales es un ensayo y suma a N:
se hace con ``run_and_register``. B1 y la sensibilidad maker se calculan con ``run_config`` y no se
registran.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np
import polars as pl

from prometheus_platform.domain.protocol import HOLDOUT_END, HOLDOUT_START
from prometheus_platform.research.carry_evaluation import ExperimentRegistry, TrialRecord
from prometheus_platform.research.validation import performance

DAYS_PER_YEAR = 365
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
EXECUTION_DELAY = HOUR
STALE_AFTER = DAY  # §3.4: un día después de su última vela, el símbolo se da por deslistado
EVALUATION_START = datetime(2021, 2, 1, tzinfo=HOLDOUT_START.tzinfo)  # §7
L_GRID = (7, 14, 28)  # §5
FAMILY = "tendencia"  # §5: el mismo factor que el TSMOM
MONDAY = 0


class Hypothesis(StrEnum):
    X1 = "X1"  # largo/corto
    X2 = "X2"  # solo largo


class Period(StrEnum):
    DESARROLLO = "desarrollo"
    HOLDOUT = "holdout"


@dataclass(frozen=True)
class MomentumCosts:
    """Costes por lado (§6): comisión del perpetuo más el slippage de cada símbolo."""

    perp_fee: float = 0.0005
    slippage: float = 0.0005
    slippage_by_symbol: Mapping[str, float] = field(default_factory=dict)

    def rate(self, symbol: str) -> float:
        return self.perp_fee + self.slippage_by_symbol.get(symbol, self.slippage)


def main_costs(low_volume: Sequence[str]) -> MomentumCosts:
    """Escenario principal: 5 pb de slippage, 10 pb en los 5 de menor volumen de dic-2020."""
    return MomentumCosts(slippage_by_symbol=dict.fromkeys(low_volume, 0.0010))


MAKER_COSTS = MomentumCosts(perp_fee=0.0002, slippage=0.0)  # solo sensibilidad


@dataclass(frozen=True)
class MomentumConfig:
    lookback: int
    hypothesis: Hypothesis = Hypothesis.X1
    equal_weight: bool = False  # True: benchmark B1 (todo el universo largo a partes iguales)

    def __post_init__(self) -> None:
        if self.lookback < 1:
            raise ValueError(f"L debe ser ≥ 1: {self.lookback}")

    @property
    def name(self) -> str:
        return "B1-universo" if self.equal_weight else f"{self.hypothesis}-L{self.lookback}"

    @property
    def is_benchmark(self) -> bool:
        return self.equal_weight


def target_weights(
    closes: Mapping[str, Sequence[float]], eligible: Sequence[str], config: MomentumConfig
) -> dict[str, float]:
    """Pesos objetivo del lunes. ``closes`` tiene, por símbolo, los cierres diarios hasta *t*.

    Solo usa el pasado: cada lista termina en el cierre del día que acaba de terminar.
    """
    lookback = config.lookback
    ready = [s for s in eligible if len(closes[s]) > lookback and closes[s][-lookback - 1] > 0]
    if config.equal_weight:
        return {s: 1.0 / len(ready) for s in sorted(ready)} if ready else {}
    signal = {s: closes[s][-1] / closes[s][-lookback - 1] - 1 for s in ready}
    ranked = sorted(ready, key=lambda s: (-signal[s], s))  # empates: por símbolo (§4)
    third = len(ranked) // 3
    if third == 0:
        return {}
    top, bottom = ranked[:third], ranked[-third:]
    if config.hypothesis is Hypothesis.X2:
        return {s: 1.0 / third for s in top}
    weights = {s: 0.5 / third for s in top}
    weights.update({s: -0.5 / third for s in bottom})
    return weights


@dataclass
class MomentumResult:
    daily_equity: pl.DataFrame
    price_pnl: float = 0.0
    funding_pnl: float = 0.0
    costs: float = 0.0
    traded_notional: float = 0.0
    rebalances: int = 0
    delisted: list[tuple[str, datetime]] = field(default_factory=list)


@dataclass
class _Book:
    """La cartera entera: un solo efectivo y una posición en unidades por símbolo."""

    costs: MomentumCosts
    result: MomentumResult
    cash: float
    q: dict[str, float] = field(default_factory=dict)
    mark: dict[str, float] = field(default_factory=dict)
    last_available: dict[str, datetime] = field(default_factory=dict)  # última vela de la serie
    pending: dict[str, float] = field(default_factory=dict)  # peso objetivo por símbolo
    pending_from: datetime | None = None

    @property
    def equity(self) -> float:
        # Perpetuos: el P&L de precio pasa al efectivo en cada marca.
        return self.cash

    def mark_to(self, symbol: str, price: float) -> None:
        qty = self.q.get(symbol, 0.0)
        previous = self.mark.get(symbol)
        if qty and previous is not None:
            pnl = qty * (price - previous)
            self.cash += pnl
            self.result.price_pnl += pnl
        self.mark[symbol] = price

    def trade(self, symbol: str, new_q: float, price: float) -> None:
        traded = abs(new_q - self.q.get(symbol, 0.0)) * price
        fee = traded * self.costs.rate(symbol)
        self.cash -= fee
        self.result.costs += fee
        self.result.traded_notional += traded
        self.q[symbol] = new_q

    def execute(self, symbol: str, price: float) -> None:
        """Lleva el símbolo a su peso pendiente, al precio de apertura de esta vela."""
        self.mark_to(symbol, price)
        weight = self.pending.pop(symbol)
        rate = self.costs.rate(symbol)
        new_q = weight * self.equity / (1 + rate) / price
        self.trade(symbol, new_q, price)

    def settle(self, symbol: str, rate: float, price: float) -> None:
        paid = self.q.get(symbol, 0.0) * price * rate
        self.cash -= paid
        self.result.funding_pnl -= paid

    def close_delisted(self, at: datetime) -> None:
        """§3.4: cierra al último precio las posiciones de símbolos que ya no vuelven a cotizar."""
        for symbol, qty in list(self.q.items()):
            last = self.last_available.get(symbol)
            if qty and last is not None and at - last > STALE_AFTER:
                self.trade(symbol, 0.0, self.mark[symbol])
                self.pending.pop(symbol, None)
                self.result.delisted.append((symbol, at))


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


@dataclass(frozen=True)
class SymbolMarket:
    """Velas de 1 h del perpetuo (``open_time``, ``open``, ``close``) y liquidaciones."""

    symbol: str
    hourly: pl.DataFrame
    settlements: pl.DataFrame


def _panel(data: Sequence[SymbolMarket], end: datetime) -> pl.DataFrame:
    """Una fila por (hora, símbolo) con vela, ordenada por hora. Sin imputar huecos."""
    frames = [
        d.hourly.filter(pl.col("open_time") < end)
        .select("open_time", "open", "close")
        .with_columns(pl.lit(d.symbol).alias("symbol"))
        for d in data
    ]
    return pl.concat(frames).sort("open_time", "symbol")


def _delisted(panel: pl.DataFrame, end: datetime) -> dict[str, datetime]:
    """Última vela de las series que terminan antes del final del periodo: dejaron de cotizar.

    Un deslistado se anuncia antes de ocurrir, así que saber que no vuelve no es mirar el futuro.
    """
    last_seen = panel.group_by("symbol").agg(pl.col("open_time").max())
    return {
        symbol: last for symbol, last in last_seen.iter_rows() if last + HOUR < end - STALE_AFTER
    }


def simulate(  # noqa: PLR0913 - keyword-only; el bucle horario sigue las reglas en orden
    data: Sequence[SymbolMarket],
    *,
    config: MomentumConfig,
    costs: MomentumCosts,
    capital: float = 1.0,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
    period: Period = Period.DESARROLLO,
) -> MomentumResult:
    _validate_period(start, end, period)
    rates = {
        d.symbol: dict(d.settlements.select("funding_time", "funding_rate").iter_rows())
        for d in data
    }
    symbols = [d.symbol for d in data]
    result = MomentumResult(daily_equity=pl.DataFrame())
    book = _Book(costs, result, cash=capital)
    closes: dict[str, list[float]] = {s: [] for s in symbols}
    day_close: dict[str, float] = {}  # último cierre visto, para repetirlo en un día sin velas
    traded_today: set[str] = set()  # símbolos con al menos una vela en el día en curso
    days: list[tuple[datetime, float]] = []

    panel = _panel(data, end)
    book.last_available = _delisted(panel, end)
    hours = panel.partition_by("open_time", maintain_order=True, as_dict=True)
    current = min(o for (o,) in hours) if hours else end
    last = max(o for (o,) in hours) if hours else end
    while current <= last:
        rows = hours.get((current,))
        bars = (
            {}
            if rows is None
            else {s: (o, c) for s, o, c in rows.select("symbol", "open", "close").iter_rows()}
        )
        close_time = current + HOUR
        for symbol, (px_open, px_close) in bars.items():
            if (
                symbol in book.pending
                and book.pending_from is not None
                and current >= book.pending_from
                and px_open is not None
            ):
                book.execute(symbol, px_open)
            if px_close is not None:
                book.mark_to(symbol, px_close)
                day_close[symbol] = px_close
                traded_today.add(symbol)
        if close_time < end:
            # Se liquida aunque falte la vela: a su close o, si no hay, a la última marca.
            for symbol, qty in book.q.items():
                rate = rates[symbol].get(close_time)
                if rate is not None and qty:
                    book.settle(symbol, rate, book.mark[symbol])
        current = close_time
        if close_time.hour != 0:
            continue
        eligible = sorted(traded_today)
        for symbol in symbols:
            if symbol in day_close:
                closes[symbol].append(day_close[symbol])  # un día sin velas repite el anterior
        traded_today = set()
        book.close_delisted(close_time)
        if close_time < start:
            continue
        days.append((close_time, book.equity))
        if close_time >= end or close_time.weekday() != MONDAY:
            continue  # en end solo se valora (KE-014)
        weights = target_weights(closes, eligible, config)
        book.pending = {s: weights.get(s, 0.0) for s in symbols if weights.get(s) or book.q.get(s)}
        book.pending_from = close_time + EXECUTION_DELAY
        result.rebalances += 1

    result.daily_equity = pl.DataFrame(
        {"date": [d for d, _ in days], "equity": [e for _, e in days]},
        schema={"date": pl.Datetime("ms", "UTC"), "equity": pl.Float64},
    )
    return result


def daily_returns(result: MomentumResult) -> pl.DataFrame:
    equity = result.daily_equity
    return equity.select(
        "date", (pl.col("equity") / pl.col("equity").shift(1) - 1).alias("ret")
    ).drop_nulls()


def run_config(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del ensayo
    data: Sequence[SymbolMarket],
    config: MomentumConfig,
    costs: MomentumCosts,
    *,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
    period: Period = Period.DESARROLLO,
) -> tuple[pl.DataFrame, MomentumResult]:
    result = simulate(data, config=config, costs=costs, start=start, end=end, period=period)
    return daily_returns(result), result


def run_and_register(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del ensayo
    data: Sequence[SymbolMarket],
    config: MomentumConfig,
    costs: MomentumCosts,
    registry: ExperimentRegistry,
    *,
    costs_label: str,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
    period: Period = Period.DESARROLLO,
) -> pl.DataFrame:
    """Ejecuta una configuración **y la registra** (suma a N, pre-registro §5)."""
    if config.is_benchmark:
        raise ValueError(f"{config.name} es un benchmark: se calcula con run_config")
    familia = getattr(registry, "familia", FAMILY)
    if familia != FAMILY:
        raise ValueError(f"El registro es de la familia {familia!r}, no de {FAMILY!r}")
    frame, result = run_config(data, config, costs, start=start, end=end, period=period)
    returns = frame["ret"].to_numpy()
    perf = performance(returns)
    years = max(len(returns) / DAYS_PER_YEAR, 1e-9)
    registry.log_trial(
        TrialRecord(
            hypothesis=str(config.hypothesis),
            name=config.name,
            params={"L": str(config.lookback), "universo": str(len(data))},
            metrics={
                "sharpe": perf.sharpe,
                "sharpe_daily": perf.sharpe_daily,
                "cagr": perf.cagr,
                "max_drawdown": perf.max_drawdown,
                "calmar": perf.calmar,
                "t_stat": perf.t_stat,
                "peor_dia": float(returns.min()),
                "vol_realizada": float(np.std(returns, ddof=1)) * math.sqrt(DAYS_PER_YEAR),
                # Capital inicial C = 1: el nocional negociado ya es una fracción de C.
                "rotacion_anual": result.traded_notional / years,
                "pnl_funding": result.funding_pnl,
                "pnl_precio": result.price_pnl,
                "costes": result.costs,
                "rebalanceos": float(result.rebalances),
                "deslistados": float(len(result.delisted)),
            },
            tags={"period": str(period), "costs": costs_label},
        )
    )
    return frame
