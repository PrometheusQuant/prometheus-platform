"""Ida y vuelta real en Bybit testnet (PQ-100): dinero ficticio, solo con claves y opt-in.

Corre solo con ``PQ_TESTNET_INTEGRATION=1`` y las claves de testnet en el ``.env``:

    PQ_TESTNET_INTEGRATION=1 uv run pytest -m testnet --no-cov

Abre y cierra un corto de 0,1 SOL en el perpetuo lineal y comprueba que no queda posición. La CI no
tiene claves y la salta.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.ops.settings import Settings

# Se leen al importar: el conftest raíz borra las variables PQ_* antes de cada test (KE-013).
_OPT_IN = os.environ.get("PQ_TESTNET_INTEGRATION") == "1"
_SETTINGS = Settings() if _OPT_IN else None
_KEYS = (_SETTINGS.bybit_api_key, _SETTINGS.bybit_api_secret) if _SETTINGS else (None, None)

pytestmark = [
    pytest.mark.testnet,
    pytest.mark.skipif(
        not (_OPT_IN and all(_KEYS)), reason="sin PQ_TESTNET_INTEGRATION=1 o sin claves de Bybit"
    ),
]


def test_round_trip_in_the_linear_perp() -> None:
    from prometheus_platform.adapters.ccxt_execution import CcxtExecution  # noqa: PLC0415

    key, secret = _KEYS
    assert key is not None
    assert secret is not None
    now = datetime.now(UTC)
    gateway = CcxtExecution.bybit_testnet(
        key.get_secret_value(), secret.get_secret_value(), FixedClock(now)
    )
    perp = InstrumentId("SOLUSDT-PERP", Venue.BYBIT)
    assert gateway.balance("USDT", perp=True) > 10
    prefix = f"pq100-{now:%Y%m%dT%H%M%S}"
    opened = gateway.market_order(f"{prefix}-a", perp, Side.SELL, Decimal("0.1"))
    assert opened.price > 0
    assert opened.fee >= 0
    closed = gateway.market_order(f"{prefix}-b", perp, Side.BUY, opened.quantity)
    assert closed.quantity == opened.quantity
    assert perp not in gateway.positions([perp])
    gateway.funding_income(perp, now - timedelta(days=1))
