"""Ida y vuelta real en Binance Demo (PQ-52): dinero ficticio, solo con claves y opt-in.

Corre solo con ``PQ_DEMO_INTEGRATION=1`` y las claves Demo en el ``.env``:

    PQ_DEMO_INTEGRATION=1 uv run pytest -m demo --no-cov

Compra y vende 0,1 SOL en spot, y abre y cierra un corto de 0,1 SOL en USDⓈ-M. Cada orden de
mercado se ejecuta de verdad (unos 7 USDT ficticios y sus comisiones). La CI no tiene claves y la
salta.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.domain.model import Side
from prometheus_platform.ops.settings import Settings
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

# Se leen al importar: el conftest raíz borra las variables PQ_* antes de cada test (KE-013).
_OPT_IN = os.environ.get("PQ_DEMO_INTEGRATION") == "1"
_SETTINGS = Settings() if _OPT_IN else None
_KEYS = (_SETTINGS.binance_api_key, _SETTINGS.binance_api_secret) if _SETTINGS else (None, None)

pytestmark = [
    pytest.mark.demo,
    pytest.mark.skipif(
        not (_OPT_IN and all(_KEYS)), reason="sin PQ_DEMO_INTEGRATION=1 o sin claves Demo"
    ),
]


def test_round_trip_in_spot_and_usdm() -> None:
    from prometheus_platform.adapters.ccxt_execution import CcxtExecution  # noqa: PLC0415

    key, secret = _KEYS
    assert key is not None
    assert secret is not None
    now = datetime.now(UTC)
    gateway = CcxtExecution.binance_demo(
        key.get_secret_value(), secret.get_secret_value(), FixedClock(now)
    )
    assert gateway.balance("USDT", perp=False) > 10
    assert gateway.balance("USDT", perp=True) > 10
    stamp = f"{now:%Y%m%dT%H%M%S}"
    for instrument, first, second in (
        (spot_instrument("SOLUSDT"), Side.BUY, Side.SELL),
        (perp_instrument("SOLUSDT"), Side.SELL, Side.BUY),
    ):
        prefix = f"pq52-{stamp}-{instrument.symbol}"
        opened = gateway.market_order(f"{prefix}-a", instrument, first, Decimal("0.1"))
        assert opened.price > 0
        assert opened.fee >= 0
        assert opened.quantity > 0
        closed = gateway.market_order(f"{prefix}-b", instrument, second, opened.quantity)
        assert closed.quantity > 0
    assert perp_instrument("SOLUSDT") not in gateway.positions([perp_instrument("SOLUSDT")])
    gateway.funding_income(perp_instrument("SOLUSDT"), now - timedelta(days=1))
