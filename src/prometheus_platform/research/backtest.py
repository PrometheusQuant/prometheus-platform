"""Backtest del carry de funding con entrada por umbral (pre-registro + enmienda 1, PQ-23).

Reglas, citando las secciones del pre-registro (``docs/estrategias/01-carry/pre-registro.md``):

- Señal en cada liquidación t: ``S_k(t)``, media de las últimas k tasas anualizadas (§4).
- Entrada si no hay posición y ``S_k ≥ θ``; salida si ``S_k < θ/2`` o la última tasa es
  negativa (§4).
- Ejecución al ``open`` de la vela que abre en t + 1 h, por pata; si falta, la siguiente (enm. 1.1).
- Funding: en cada liquidación s con la posición ya abierta, ``tasa * q_perp * close_perp(s)``
  (enm. 1.2). Long spot / short perp con el mismo nocional, 1x (§4).
- Apalancamiento 1x: si una pata se desvía más de un 10 % de capital/2, ambas se redimensionan
  a capital/2 (§4, enm. 1.4 y enmienda 2).
- Valoración diaria a las 00:00 UTC con los ``close`` (enm. 1.3).

El bucle es secuencial porque la histéresis tiene estado; recorre ~60 000 velas por símbolo en
milisegundos. El resultado guarda la descomposición del P&L (funding, precio y costes), como en
He, Manela, Ross y von Wachter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import polars as pl

REBALANCE_DRIFT = 0.10


@dataclass(frozen=True)
class CostModel:
    """Costes por lado y pata, en fracción del nocional (pre-registro §6)."""

    spot_fee: float = 0.0010
    perp_fee: float = 0.0005
    slippage: float = 0.0002

    @property
    def spot(self) -> float:
        return self.spot_fee + self.slippage

    @property
    def perp(self) -> float:
        return self.perp_fee + self.slippage


MAIN_COSTS = CostModel()
ALT_COSTS = CostModel(slippage=0.0005)  # SOL, BNB, XRP: 5 pb de slippage
MAKER_COSTS = CostModel(spot_fee=0.00075, perp_fee=0.0002, slippage=0.0)  # solo sensibilidad


@dataclass(frozen=True)
class CarryConfig:
    k: int
    theta: float
    always_on: bool = False  # benchmark B1

    @property
    def name(self) -> str:
        return (
            "B1-siempre-activo" if self.always_on else f"k{self.k}-theta{round(self.theta * 100)}"
        )


@dataclass
class SymbolResult:
    symbol: str
    daily_equity: pl.DataFrame  # columnas: date, equity
    funding_pnl: float = 0.0
    price_pnl: float = 0.0
    costs: float = 0.0
    cycles: int = 0
    hours_invested: int = 0
    hours_total: int = 0
    trades: list[tuple[datetime, str]] = field(default_factory=list)


class _CarryBook:
    """Estado de un símbolo: efectivo, cantidades, órdenes pendientes y contabilidad del P&L.

    Todas las órdenes llevan una pata a un *nocional objetivo*: capital/2 al entrar y al
    rebalancear (apalancamiento 1x, §4 y enmienda 2) y 0 al salir.
    """

    def __init__(self, symbol: str, capital: float, config: CarryConfig, costs: CostModel) -> None:
        self.config, self.costs = config, costs
        self.cash = capital
        self.q_spot = self.q_perp = 0.0
        self.spot_mark = self.perp_mark = math.nan
        self.pending_spot = self.pending_perp = False
        self.target_notional = 0.0
        self.is_open = False
        self.result = SymbolResult(symbol=symbol, daily_equity=pl.DataFrame())

    @property
    def equity(self) -> float:
        return self.cash + (self.q_spot * self.spot_mark if self.q_spot else 0.0)

    def _charge(self, notional: float, rate: float) -> None:
        fee = abs(notional) * rate
        self.cash -= fee
        self.result.costs += fee

    def execute_spot(self, price: float) -> None:
        """Enm. 1.1: la pata spot se ejecuta al open en cuanto hay vela."""
        self.mark_spot(price)
        target = self.target_notional / price
        traded = (target - self.q_spot) * price
        self.cash -= traded
        self._charge(traded, self.costs.spot)
        self.q_spot = target
        self.pending_spot = False

    def execute_perp(self, price: float) -> None:
        self.mark_perp(price)
        target = self.target_notional / price
        self._charge((target - self.q_perp) * price, self.costs.perp)
        self.q_perp = target
        self.pending_perp = False

    def mark_perp(self, price: float) -> None:
        """El short gana cuando el perp baja: el P&L se realiza en efectivo en cada marca."""
        if self.q_perp and not math.isnan(self.perp_mark):
            pnl = self.q_perp * (self.perp_mark - price)
            self.cash += pnl
            self.result.price_pnl += pnl
        self.perp_mark = price

    def mark_spot(self, price: float) -> None:
        if self.q_spot and not math.isnan(self.spot_mark):
            self.result.price_pnl += self.q_spot * (price - self.spot_mark)
        self.spot_mark = price

    def _order(self, notional: float, label: str, at: datetime) -> None:
        self.target_notional = notional
        self.pending_spot = self.pending_perp = True
        self.result.trades.append((at, label))

    def settle_and_decide(self, at: datetime, rate: float, s_k: float | None) -> None:
        """Liquidación de funding (enm. 1.2) y decisión con la regla de histéresis (§4)."""
        if self.is_open and self.q_perp and not math.isnan(self.perp_mark):
            received = self.q_perp * self.perp_mark * rate
            self.cash += received
            self.result.funding_pnl += received
        if s_k is None:  # ventana inicial de la señal
            return
        config = self.config
        if not self.is_open and (config.always_on or s_k >= config.theta):
            self.is_open = True
            self.result.cycles += 1
            self._order(self.equity / 2, "entrada", at)
        elif self.is_open and not config.always_on and (s_k < config.theta / 2 or rate < 0):
            self.is_open = False
            self._order(0.0, "salida", at)
        elif self.is_open and self.q_perp and self.q_spot:
            # Enmienda 2: cada pata vale capital/2 (1x); se rebalancea si una se desvía > 10 %.
            target = self.equity / 2
            spot_value = self.q_spot * self.spot_mark
            perp_value = self.q_perp * self.perp_mark
            drift = max(abs(spot_value - target), abs(perp_value - target)) / target
            if drift > REBALANCE_DRIFT:
                self._order(target, "rebalanceo", at)


def simulate_symbol(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del ensayo
    symbol: str,
    hourly: pl.DataFrame,
    settlements: pl.DataFrame,
    *,
    config: CarryConfig,
    costs: CostModel,
    capital: float,
    end: datetime | None = None,
) -> SymbolResult:
    """Simula un símbolo con su parte del capital. ``hourly`` viene de ``hourly_prices``."""
    bars = hourly if end is None else hourly.filter(pl.col("open_time") < end)
    signal = f"s_{config.k}"
    by_time = {
        t: (rate, s_k)
        for t, rate, s_k in settlements.select("funding_time", "funding_rate", signal).iter_rows()
    }
    book = _CarryBook(symbol, capital, config, costs)
    days: list[tuple[datetime, float]] = []

    for o, s_open, s_close, p_open, p_close in bars.select(
        "open_time", "spot_open", "spot_close", "perp_open", "perp_close"
    ).iter_rows():
        if book.pending_spot and s_open is not None:
            book.execute_spot(s_open)
        if book.pending_perp and p_open is not None:
            book.execute_perp(p_open)
        if p_close is not None:
            book.mark_perp(p_close)
        if s_close is not None:
            book.mark_spot(s_close)

        close_time = o + timedelta(hours=1)
        book.result.hours_total += 1
        book.result.hours_invested += int(book.is_open)
        if close_time in by_time:
            book.settle_and_decide(close_time, *by_time[close_time])
        if close_time.hour == 0:  # enm. 1.3: valoración a las 00:00 UTC, tras la liquidación
            days.append((close_time, book.equity))

    book.result.daily_equity = pl.DataFrame(
        {"date": [d for d, _ in days], "equity": [e for _, e in days]},
        schema={"date": pl.Datetime("ms", "UTC"), "equity": pl.Float64},
    )
    return book.result


def portfolio_returns(results: list[SymbolResult], capital_per_symbol: float) -> pl.DataFrame:
    """Suma el capital de los símbolos por día y devuelve los retornos diarios del total.

    Un símbolo que aún no empezó aporta su parte en efectivo (enm. 1.5).
    """
    frames = [
        r.daily_equity.rename({"equity": r.symbol})
        for r in results
        if not r.daily_equity.is_empty()
    ]
    if not frames:
        return pl.DataFrame(
            schema={"date": pl.Datetime("ms", "UTC"), "equity": pl.Float64, "ret": pl.Float64}
        )
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.join(frame, on="date", how="full", coalesce=True)
    merged = merged.sort("date")
    symbols = [r.symbol for r in results if not r.daily_equity.is_empty()]
    missing = len(results) - len(symbols)
    merged = merged.with_columns(
        [pl.col(s).forward_fill().fill_null(capital_per_symbol) for s in symbols]
    ).with_columns((pl.sum_horizontal(symbols) + missing * capital_per_symbol).alias("equity"))
    return (
        merged.select("date", "equity")
        .with_columns((pl.col("equity") / pl.col("equity").shift(1) - 1).alias("ret"))
        .drop_nulls("ret")
    )
