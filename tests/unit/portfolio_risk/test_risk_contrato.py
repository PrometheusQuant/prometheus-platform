"""Decisiones y bordes exactos del gestor de riesgo: lo que dejaban pasar los mutantes (PQ-99).

Las pruebas de test_risk_and_kill_switch.py comprobaban la regla que salta. Aquí se fija además:

- si la orden se aprueba;
- si la violación activa el kill-switch;
- qué pasa justo en cada límite.
"""

from decimal import Decimal

import pytest

from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.portfolio_risk.risk import (
    Leg,
    PortfolioSnapshot,
    Position,
    ProposedOrder,
    RiskLimits,
    RiskManager,
)

D = Decimal
SPOT = InstrumentId("SOLUSDT", Venue.BINANCE)
PERP = InstrumentId("SOLUSDT-PERP", Venue.BINANCE)
OTRO = InstrumentId("ETHUSDT", Venue.BINANCE)
RISK = RiskManager(
    RiskLimits(
        max_notional_symbol=D(500),
        max_notional_total=D(1000),
        max_leverage=D(1),
        hard_leverage=D("1.5"),
        max_daily_loss=D("0.02"),
        max_hedge_imbalance=D("0.15"),
        imbalance_grace_seconds=300,
    )
)


def libro(qty: str = "2", equity: str = "1000", sod: str = "1000") -> PortfolioSnapshot:
    return PortfolioSnapshot(
        equity=D(equity),
        start_of_day_equity=D(sod),
        positions=(
            Position(SPOT, "SOLUSDT", Leg.SPOT, D(qty), D(100)),
            Position(PERP, "SOLUSDT", Leg.PERP, -D(qty), D(100)),
        ),
    )


def compra(qty: str, instrument: InstrumentId = SPOT, symbol: str = "SOLUSDT") -> ProposedOrder:
    return ProposedOrder("carry-h2", instrument, symbol, Leg.SPOT, Side.BUY, D(qty), D(100))


# --- Pre-trade ---------------------------------------------------------------------------------


def test_con_el_kill_switch_activo_no_se_aprueba_nada_que_aumente_exposicion() -> None:
    decision = RISK.pre_trade(compra("1"), libro(), kill_switch_active=True)
    assert (decision.approved, decision.rule) == (False, "kill_switch")


@pytest.mark.parametrize("equity", ["0", "-5"])
def test_equity_no_positiva_rechaza_la_orden(equity: str) -> None:
    decision = RISK.pre_trade(compra("1"), libro(equity=equity), kill_switch_active=False)
    assert (decision.approved, decision.rule) == (False, "equity")


def test_una_equity_pequena_pero_positiva_no_es_motivo_de_rechazo_por_equity() -> None:
    # 0,5 USD de equity: rechaza el apalancamiento, no la regla de equity no positiva.
    decision = RISK.pre_trade(compra("1"), libro(qty="0", equity="0.5"), kill_switch_active=False)
    assert (decision.approved, decision.rule) == (False, "apalancamiento")


def test_un_instrumento_registrado_con_otro_simbolo_se_rechaza() -> None:
    decision = RISK.pre_trade(compra("1", symbol="ETHUSDT"), libro(), kill_switch_active=False)
    assert (decision.approved, decision.rule) == (False, "simbolo_inconsistente")


def test_un_instrumento_que_no_esta_en_la_cartera_usa_el_precio_de_la_orden() -> None:
    # Sin posición previa: 4 x 100 = 400 ≤ 500 por símbolo; 400 + 400 de SOL = 800 ≤ 1000 total.
    decision = RISK.pre_trade(
        compra("4", instrument=OTRO, symbol="ETHUSDT"), libro(), kill_switch_active=False
    )
    assert decision.approved
    decision = RISK.pre_trade(
        compra("6", instrument=OTRO, symbol="ETHUSDT"), libro(), kill_switch_active=False
    )
    assert (decision.approved, decision.rule) == (False, "nocional_simbolo")


# --- Monitor -----------------------------------------------------------------------------------


@pytest.mark.parametrize("equity", ["0", "-1"])
def test_equity_no_positiva_dispara_el_kill_switch(equity: str) -> None:
    [breach] = RISK.monitor(libro(equity=equity))
    assert (breach.rule, breach.trips_kill_switch) == ("equity", True)


def test_una_cuenta_pequena_y_sana_no_tiene_violaciones() -> None:
    assert RISK.monitor(libro(qty="0", equity="0.5", sod="0.5")) == []


@pytest.mark.parametrize("sod", ["0", "-3"])
def test_sin_equity_de_inicio_del_dia_valida_se_dispara(sod: str) -> None:
    [breach] = RISK.monitor(libro(sod=sod))
    assert (breach.rule, breach.trips_kill_switch) == ("equity_inicio_dia", True)


def test_perder_exactamente_el_limite_diario_no_dispara_y_un_poco_mas_si() -> None:
    assert RISK.monitor(libro(equity="980", sod="1000")) == []  # -2,00 %: el límite es estricto
    [breach] = RISK.monitor(libro(equity="979.99", sod="1000"))
    assert (breach.rule, breach.trips_kill_switch) == ("perdida_diaria", True)


def test_apalancamiento_justo_en_cada_limite() -> None:
    # Nocional bruto = 2 x qty x 100; equity 500.
    assert RISK.monitor(libro(qty="2.5", equity="500", sod="500")) == []  # 1,0x exacto
    [suave] = RISK.monitor(libro(qty="3.75", equity="500", sod="500"))  # 1,5x exacto
    assert (suave.rule, suave.trips_kill_switch) == ("apalancamiento", False)
    [duro] = RISK.monitor(libro(qty="3.76", equity="500", sod="500"))
    assert (duro.rule, duro.trips_kill_switch) == ("apalancamiento_duro", True)
