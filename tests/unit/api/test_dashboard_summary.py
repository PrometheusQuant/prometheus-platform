"""Frases de contexto del dashboard (PQ-127): cifras con comparación y solo las excepciones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from prometheus_platform.api.dashboard import summary
from prometheus_platform.api.paper.report import PaperView
from prometheus_platform.domain.events import FundingSettled, PortfolioValued
from prometheus_platform.domain.model import InstrumentId, Venue

NOW = datetime(2026, 11, 24, 18, tzinfo=UTC)


def settled(symbol: str, s_k: str, action: str = "mantener") -> FundingSettled:
    return FundingSettled(
        occurred_at=NOW,
        symbol=symbol,
        funding_time=NOW,
        rate=Decimal("0.0001"),
        interval_hours=8,
        amount=Decimal(0),
        action=action,
        s_k=s_k,
        target_open=False,
        was_open=False,
        rebalance=False,
    )


def valued(at: datetime, equity: str) -> PortfolioValued:
    return PortfolioValued(
        occurred_at=at, equity=Decimal(equity), cash=Decimal(equity), gross_notional=Decimal(0)
    )


def test_the_threshold_comes_from_the_selected_configuration() -> None:
    assert summary.entry_threshold("k9-theta20") == 0.20
    assert summary.entry_threshold("k3-theta10") == 0.10
    assert summary.entry_threshold(None) == summary.DEFAULT_THETA


def test_the_headline_explains_why_the_paper_is_in_cash() -> None:
    view = PaperView(
        valuations=[valued(NOW - timedelta(days=11), "1000"), valued(NOW, "1000")],
        settlements=[settled("SOLUSDT", "0.006"), settled("XRPUSDT", "0.025"), settled("BNB", "")],
    )
    headline = summary.paper_headline(view, 0.20, NOW)
    assert headline is not None
    assert headline.days == 11
    assert headline.sentence.startswith("El paper está en efectivo: en sus 11 días")
    assert "umbral de entrada del 20 % anual" in headline.sentence
    assert "La señal más alta fue 2,5 % en XRPUSDT." in headline.sentence
    assert headline.change == "igual que al empezar"
    assert headline.capital == "1.000,00 USD"


def test_the_headline_compares_the_capital_with_the_start() -> None:
    perp = InstrumentId("SOLUSDT-PERP", Venue.BINANCE)
    view = PaperView(
        valuations=[valued(NOW - timedelta(days=2), "1000"), valued(NOW, "1012.5")],
        positions={perp: Decimal(-2)},
    )
    headline = summary.paper_headline(view, 0.20, NOW)
    assert headline is not None
    assert headline.sentence.startswith("El paper tiene una posición abierta")
    assert headline.change == "+12,50 USD desde el inicio (+1,25 %)"
    assert summary.paper_headline(PaperView(), 0.20, NOW) is None


def test_settlements_show_the_exception_not_every_row() -> None:
    quiet = [settled("SOLUSDT", "0.006"), settled("XRPUSDT", "0.036"), settled("BNBUSDT", "")]
    assert summary.settlements_summary(quiet, 0.20) == (
        "Ninguna de las 3 liquidaciones superó el 20 %; la más alta fue 3,6 % en XRPUSDT. "
        "Decisión en todas: «mantener»."
    )
    busy = [*quiet, settled("SOLUSDT", "0.31", action="entrada")]
    assert summary.settlements_summary(busy, 0.20) == (
        "1 de 4 liquidaciones superaron el 20 %; la más alta fue 31,0 % en SOLUSDT."
    )
    assert summary.settlements_summary([], 0.20) == "Aún no hay liquidaciones."


def test_freshness_warns_after_two_settlements() -> None:
    assert not summary.freshness(NOW - timedelta(hours=7), NOW).stale
    old = summary.freshness(NOW - timedelta(days=4), NOW)
    assert old.stale
    assert old.text == "hace 4 días"
    assert summary.freshness(NOW - timedelta(hours=17), NOW).text == "hace 17 h"
    assert summary.freshness(NOW - timedelta(minutes=5), NOW).text == "hace menos de una hora"


@dataclass(frozen=True)
class Row:
    symbol: str
    probability_high: float


def test_the_nowcast_summary_names_the_closest_coin() -> None:
    rows = [Row("SOLUSDT", 0.12), Row("XRPUSDT", 0.31), Row("BNBUSDT", 0.05)]
    assert summary.nowcast_summary(rows) == (
        "Ninguna de las 3 monedas tiene funding alto probable. La más cercana es XRPUSDT, con "
        "31,0 %."
    )
    assert summary.nowcast_summary([Row("SOLUSDT", 0.7), Row("XRPUSDT", 0.2)]).startswith(
        "Funding alto probable en SOLUSDT."
    )


def test_the_histogram_leaves_the_exchange_failures_out() -> None:
    capital = np.array([0.0, 0.0, 990.0, 1000.0, 1010.0, 1100.0])
    frame = summary.histogram_frame(capital, bins=4)
    assert frame["trayectorias"].sum() == 4  # las 2 quiebras van como cifra aparte
    assert frame["desde"][0] == 990.0
    assert frame["hasta"][-1] == 1100.0
    assert summary.histogram_frame(np.zeros(3)).is_empty()
