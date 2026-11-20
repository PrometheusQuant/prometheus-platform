"""Motor de tendencia (PQ-67): reglas del pre-registro de la Estrategia 2, con datos sintéticos.

Ninguna prueba toca datos reales: cada ejecución real sería un ensayo y sumaría a N.

El mercado sintético separa lo que el motor no debe confundir: el spot y el perpetuo difieren, el
`open` de cada vela no es el `close` anterior y puede haber velas que faltan. Cada prueba falla si
el motor rompe la regla que comprueba (revisión adversarial del 2026-11-13: los mutantes que la
primera versión dejaba pasar).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.research.carry_evaluation import TrialRecord
from prometheus_platform.research.trend import (
    EXECUTION_DELAY,
    NO_TRADE_BAND,
    Hypothesis,
    Period,
    SymbolMarket,
    TrendConfig,
    TrendResult,
    _Book,
    run_and_register,
    simulate_trend,
    target_weight,
)

T0 = datetime(2023, 1, 1, tzinfo=UTC)
FREE = CostModel(spot_fee=0.0, perp_fee=0.0, slippage=0.0)
COSTS = CostModel()  # VIP0 + 2 pb (escenario principal, §6)
L5 = TrendConfig(lookback=5, sigma_target=0.40)
T2_L5 = TrendConfig(lookback=5, sigma_target=0.40, hypothesis=Hypothesis.T2)
START = T0 + timedelta(days=40)  # tras el calentamiento de la volatilidad (31 cierres)


def wave(i: int) -> float:
    """Sube 60 días y baja otros 60, con ruido determinista de unas horas."""
    day = i / 24
    trend = 100 * (1.004 ** min(day, 60)) * (0.996 ** max(day - 60, 0))
    return float(trend * (1 + 0.01 * math.sin(i / 7)))


def build(  # noqa: PLR0913 - mercado sintético configurable
    days: int = 120,
    price: Callable[[int], float] = wave,
    *,
    perp: Callable[[int], float] | None = None,
    gap: float = 0.002,
    rate: float = 0.0001,
    start: datetime = T0,
    missing: frozenset[int] = frozenset(),
    missing_perp: frozenset[int] = frozenset(),
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Velas de 1 h (open ≠ close anterior) y liquidaciones cada 8 h con tasa constante."""
    perp_price = perp or (lambda i: price(i) * 1.001)
    rows = []
    for i in range(days * 24):
        if i in missing:
            continue
        no_perp = i in missing_perp
        rows.append(
            {
                "open_time": start + timedelta(hours=i),
                "spot_open": price(i) * (1 + gap),
                "spot_close": price(i + 1),
                "perp_open": None if no_perp else perp_price(i) * (1 + gap),
                "perp_close": None if no_perp else perp_price(i + 1),
            }
        )
    hourly = pl.DataFrame(rows, schema_overrides={"open_time": pl.Datetime("ms", "UTC")})
    times = [start + timedelta(hours=8 * k) for k in range(1, days * 3 + 1)]
    settlements = pl.DataFrame(
        {"funding_time": times, "funding_rate": [rate] * len(times)},
        schema_overrides={"funding_time": pl.Datetime("ms", "UTC")},
    )
    return hourly, settlements


def sim(
    config: TrendConfig = L5, costs: CostModel = FREE, **market: object
) -> tuple[TrendResult, pl.DataFrame]:
    hourly, settlements = build(**market)  # type: ignore[arg-type]
    origin = market.get("start", T0)
    assert isinstance(origin, datetime)
    start = origin + (START - T0)
    result = simulate_trend(
        "BTC", hourly, settlements, config=config, costs=costs, capital=1.0, start=start
    )
    return result, hourly


def at_open(hourly: pl.DataFrame, when: datetime, column: str = "spot_open") -> float:
    return float(hourly.filter(pl.col("open_time") == when)[column][0])


# --- sin anticipación -------------------------------------------------------------------------


@pytest.mark.parametrize("cut_day", [45, 60, 75, 90])
def test_weight_at_t_ignores_every_price_from_t_onwards(cut_day: int) -> None:
    """FR-002: alterar las velas que abren en t o después no cambia la decisión de t."""
    cut = T0 + timedelta(days=cut_day)
    base, _ = sim()

    def crash(i: int) -> float:
        # price(i) es el precio en T0 + i h: el cierre de t se conoce en t; solo cambia lo posterior
        return wave(i) * (0.3 if T0 + timedelta(hours=i) > cut else 1.0)

    altered, _ = sim(price=crash)

    assert [w for w in base.weights if w[0] <= cut] == [w for w in altered.weights if w[0] <= cut]
    assert any(w[0] <= cut for w in base.weights)


def test_target_weight_follows_the_formula() -> None:
    # Ruido aleatorio (no alternado): con 29 retornos la volatilidad ya sería distinta.
    rng = np.random.default_rng(1)
    closes = list(100 * np.cumprod(1 + rng.normal(0.01, 0.03, 200)))
    w = target_weight(closes, TrendConfig(20, 0.20))
    window = np.asarray(closes[-31:])
    sigma = float(np.std(window[1:] / window[:-1] - 1, ddof=1)) * math.sqrt(365)

    assert closes[-1] > closes[-21]  # señal +1: la prueba no compara 0 con 0
    assert w is not None
    assert 0 < w < 1  # el escalado por volatilidad actúa
    assert w == pytest.approx(min(1.0, 0.20 / sigma))
    assert target_weight(closes[:30], TrendConfig(20, 0.20)) is None  # faltan 31 cierres


def test_signal_always_uses_the_spot_even_in_t2() -> None:
    """El perpetuo baja y el spot sube: la señal de T2 es la del spot (§4)."""
    result, _ = sim(
        T2_L5,
        price=lambda i: 100 * 1.004 ** (i / 24) * (1 + 0.01 * math.sin(i / 7)),
        perp=lambda i: 100 * 0.995 ** (i / 24),
    )
    assert result.weights
    assert all(target > 0 for _, target, _ in result.weights)


# --- ejecución --------------------------------------------------------------------------------


def test_fills_happen_at_the_open_of_the_bar_one_hour_after_the_decision() -> None:
    """FR-003: se ejecuta al open de la vela que abre en t + 1 h (no al close; no KE-016)."""
    result, hourly = sim()
    decided = {at for at, _, _ in result.weights}

    assert result.fills
    for when, price in result.fills:
        assert when.hour == 1
        assert when - EXECUTION_DELAY in decided
        assert price == at_open(hourly, when)  # el open lleva un salto respecto al close previo


def test_a_missing_execution_bar_fills_at_the_next_available_one() -> None:
    first, _ = sim()
    decision = first.weights[0][0]
    hour = int((decision + EXECUTION_DELAY - T0) / timedelta(hours=1))
    result, hourly = sim(missing=frozenset({hour}))

    when, price = result.fills[0]
    assert when == decision + 2 * EXECUTION_DELAY
    assert price == at_open(hourly, when)


def test_each_decision_replaces_an_order_that_could_not_be_filled() -> None:
    """Sin perpetuo durante dos días, la orden vieja no se ejecuta con el capital de entonces."""
    first, _ = sim(T2_L5)
    decision = first.weights[0][0]
    start_hour = int((decision - T0) / timedelta(hours=1))
    gap = frozenset(range(start_hour, start_hour + 48))
    result, _ = sim(T2_L5, missing_perp=gap)

    decisions = [at for at, _, _ in result.weights]
    for when, _ in result.fills:
        latest = max(at for at in decisions if at < when)
        later = [at for at in decisions if latest < at < when]
        assert not later  # la orden ejecutada es la de la decisión más reciente


def test_a_stale_order_is_cancelled_when_the_new_decision_is_inside_the_band() -> None:
    """Orden de comprar sin ejecutar (faltaron aperturas) y hoy la señal dice «fuera»: se anula."""
    book = _Book(
        perp=False,
        fee=0.0,
        result=TrendResult(symbol="BTC", daily_equity=pl.DataFrame()),
        cash=1.0,
        mark=100.0,
        pending=(1.0, T0 + timedelta(hours=1)),
    )
    falling = [100.0 * 0.99**k for k in range(40)]  # momentum negativo: T1 → w = 0 = peso actual

    book.decide(T0 + timedelta(days=1), falling, L5)

    assert book.pending is None  # sin cancelarla, se compraría con la decisión de ayer


def test_no_trade_band_compares_with_the_current_weight() -> None:
    result, _ = sim()
    assert result.weights
    assert all(abs(target - current) > NO_TRADE_BAND for _, target, current in result.weights)


# --- contabilidad -----------------------------------------------------------------------------


@pytest.mark.parametrize("config", [L5, T2_L5], ids=["T1", "T2"])
def test_pnl_decomposition_adds_up(config: TrendConfig) -> None:
    """Capital final - inicial = precio + funding - costes, con saltos y velas faltantes."""
    result, _ = sim(config, COSTS, missing=frozenset(range(1500, 1510)))
    final = result.daily_equity["equity"][-1]
    assert final - 1.0 == pytest.approx(
        result.price_pnl + result.funding_pnl - result.costs, abs=1e-12
    )


def test_perp_fee_and_spot_fee_are_charged_on_traded_notional() -> None:
    t1, _ = sim(L5, COSTS)
    t2, _ = sim(T2_L5, COSTS)
    assert t1.costs == pytest.approx(t1.traded_notional * COSTS.spot)
    assert t2.costs == pytest.approx(t2.traded_notional * COSTS.perp)


def test_funding_is_paid_on_the_position_at_each_settlement_close() -> None:
    """Subida estable y vol baja: el largo de T2 queda en w = 1 y paga tasa · q · close."""

    def steady(i: int) -> float:
        return float(100 * 1.003 ** (i / 24))

    result, hourly = sim(T2_L5, price=steady, gap=0.0, rate=0.0002)
    (fill_time, fill_price), *rest = result.fills
    assert not rest  # w = 1 sostenido: un único ajuste
    q = 1.0 / fill_price  # capital 1, sin comisiones
    closes = dict(
        hourly.select(
            (pl.col("open_time") + pl.duration(hours=1)).alias("t"), "perp_close"
        ).iter_rows()
    )
    end = result.daily_equity["date"][-1]
    expected = sum(
        q * closes[t] * 0.0002 for t in closes if t.hour % 8 == 0 and fill_time < t <= end
    )
    assert result.funding_pnl == pytest.approx(-expected, rel=1e-9)


def test_missing_perp_close_at_a_settlement_still_settles_at_the_last_mark() -> None:
    full, _ = sim(T2_L5, price=lambda i: 100 * 1.003 ** (i / 24), gap=0.0)
    holes = frozenset(h for h in range(24 * 60, 24 * 100) if (h + 1) % 8 == 0)
    partial, _ = sim(T2_L5, price=lambda i: 100 * 1.003 ** (i / 24), gap=0.0, missing_perp=holes)
    assert partial.funding_pnl == pytest.approx(full.funding_pnl, rel=0.01)


def test_one_times_leverage_holds_after_fees() -> None:
    b1 = TrendConfig(1, 0.2, buy_and_hold=True)
    result, _ = sim(b1, COSTS, price=lambda i: 100.0, gap=0.0)
    assert len(result.fills) == 1
    # nocional + comisión = capital: |w| ≤ 1 también después de pagar la comisión
    assert result.traded_notional == pytest.approx(1.0 / (1 + COSTS.spot), rel=1e-12)
    assert result.daily_equity["equity"][-1] == pytest.approx(1.0 - result.costs, rel=1e-12)


def test_invested_time_counts_only_evaluated_days() -> None:
    result, _ = sim(TrendConfig(1, 0.2, buy_and_hold=True), price=lambda i: 100.0, gap=0.0)
    days = result.daily_equity.height
    assert result.hours_total == 24 * days  # sin los días de calentamiento
    assert result.hours_invested == 24 * (days - 1)  # la compra se ejecuta tras el primer día


# --- T1, T2, días y fronteras ------------------------------------------------------------------


def test_t1_is_long_or_cash_and_t2_shorts_and_collects_funding() -> None:
    def down(i: int) -> float:
        return float(100 * 0.997 ** (i / 24) * (1 + 0.01 * math.sin(i / 7)))

    t1, _ = sim(L5, price=down, rate=0.0003)
    t2, _ = sim(T2_L5, price=down, rate=0.0003)
    assert all(target >= 0 for _, target, _ in t1.weights)
    assert t1.funding_pnl == 0  # el spot no paga funding
    assert any(target < 0 for _, target, _ in t2.weights)
    assert t2.funding_pnl > 0  # el corto cobra con funding positivo


def test_a_missing_last_bar_of_the_day_does_not_drop_the_day() -> None:
    full, _ = sim()
    last_bar_of_day_70 = 24 * 70 + 23
    holed, _ = sim(missing=frozenset({last_bar_of_day_70}))
    assert holed.daily_equity.height == full.daily_equity.height  # días de calendario


def test_development_never_decides_or_collects_at_the_holdout_boundary() -> None:
    """KE-014: ni decisión ni funding en HOLDOUT_START, aunque el precio se hunda justo ahí."""
    t0 = HOLDOUT_START - timedelta(days=60)

    def up_then_crash(i: int) -> float:
        at = t0 + timedelta(hours=i)
        return float(100 * 1.003 ** (i / 24) * (0.5 if at >= HOLDOUT_START else 1.0))

    hourly, settlements = build(days=60, price=up_then_crash, gap=0.0, rate=0.0002, start=t0)
    result = simulate_trend(
        "BTC",
        hourly,
        settlements,
        config=T2_L5,
        costs=FREE,
        capital=1.0,
        start=t0 + timedelta(days=40),
    )

    assert all(at < HOLDOUT_START for at, _, _ in result.weights)  # la caída no se opera
    assert result.daily_equity["date"][-1] == HOLDOUT_START  # se valora el cierre del 30-06
    (fill_time, fill_price), *rest = result.fills
    assert not rest
    q = 1.0 / fill_price
    closes = dict(
        hourly.select(
            (pl.col("open_time") + pl.duration(hours=1)).alias("t"), "perp_close"
        ).iter_rows()
    )
    paid = sum(
        q * closes[t] * 0.0002 for t in closes if t.hour % 8 == 0 and fill_time < t < HOLDOUT_START
    )
    assert result.funding_pnl == pytest.approx(-paid, rel=1e-12)  # sin la de HOLDOUT_START


def test_periods_cannot_read_the_holdout_by_accident() -> None:
    hourly, settlements = build()
    with pytest.raises(ValueError, match="holdout"):
        simulate_trend(
            "BTC",
            hourly,
            settlements,
            config=L5,
            costs=FREE,
            capital=1.0,
            start=START,
            end=HOLDOUT_START + timedelta(days=1),
        )
    with pytest.raises(ValueError, match="holdout"):
        simulate_trend(
            "BTC",
            hourly,
            settlements,
            config=L5,
            costs=FREE,
            capital=1.0,
            start=START,
            end=START + timedelta(days=30),
            period=Period.HOLDOUT,
        )


def test_missing_inputs_fail_loudly() -> None:
    hourly, _ = build()
    with pytest.raises(ValueError, match="liquidaciones"):
        simulate_trend("BTC", hourly, None, config=T2_L5, costs=FREE, capital=1.0, start=START)
    with pytest.raises(ValueError, match="calentamiento"):
        simulate_trend(
            "BTC", hourly, None, config=TrendConfig(120, 0.4), costs=FREE, capital=1.0, start=START
        )


# --- registro de ensayos ------------------------------------------------------------------------


class Registry:
    def __init__(self, familia: str = "tendencia") -> None:
        self.familia = familia
        self.items: list[TrialRecord] = []

    def log_trial(self, trial: TrialRecord) -> None:
        self.items.append(trial)

    def trials(self) -> list[TrialRecord]:
        return self.items


def markets() -> list[SymbolMarket]:
    hourly, settlements = build()
    return [
        SymbolMarket("BTCUSDT", hourly, settlements),
        SymbolMarket("ETHUSDT", hourly, settlements),
    ]


def test_run_and_register_counts_every_execution_with_its_cost_scenario() -> None:
    registry = Registry()
    frame = run_and_register(markets(), L5, COSTS, registry, costs_label="principal", start=START)

    (trial,) = registry.items
    assert trial.name == "T1-L5-vol40"
    assert trial.tags == {"period": "desarrollo", "costs": "principal"}
    assert {"t_stat", "calmar", "peor_dia", "vol_realizada", "tiempo_invertido"} <= set(
        trial.metrics
    )
    assert 0 < trial.metrics["tiempo_invertido"] <= 1
    assert frame.height > 0


def test_benchmarks_and_other_families_are_not_registered() -> None:
    with pytest.raises(ValueError, match="benchmark"):
        run_and_register(
            markets(),
            TrendConfig(5, 0.4, vol_targeting=False),
            COSTS,
            Registry(),
            costs_label="principal",
            start=START,
        )
    with pytest.raises(ValueError, match="familia"):
        run_and_register(
            markets(), L5, COSTS, Registry("carry"), costs_label="principal", start=START
        )


def test_config_names_and_validation() -> None:
    assert TrendConfig(60, 0.20).name == "T1-L60-vol20"
    assert TrendConfig(60, 0.20, hypothesis=Hypothesis.T2).name == "T2-L60-vol20"
    assert TrendConfig(60, 0.20, vol_targeting=False).name == "T1-L60-sin-vol"
    assert TrendConfig(1, 0.2, buy_and_hold=True).name == "B1-comprar-y-mantener"
    with pytest.raises(ValueError, match="B1"):
        TrendConfig(1, 0.2, hypothesis=Hypothesis.T2, buy_and_hold=True)
    with pytest.raises(ValueError, match="L"):
        TrendConfig(0, 0.2)
