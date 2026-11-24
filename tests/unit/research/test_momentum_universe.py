"""Universo del momentum transversal (PQ-114, pre-registro §3)."""

from __future__ import annotations

import pytest

from prometheus_platform.research.momentum_universe import (
    SMALLEST,
    UNIVERSE_SIZE,
    candidates,
    is_candidate,
    select_universe,
)


@pytest.mark.parametrize(
    ("symbol", "ok"),
    [
        ("BTCUSDT", True),
        ("1000SHIBUSDT", True),
        ("USDCUSDT", False),  # stablecoin
        ("BUSDUSDT", False),
        ("BTCUPUSDT", False),  # token apalancado
        ("ETHDOWNUSDT", False),
        ("BTCUSDT_210326", False),  # trimestral, no perpetuo
        ("BTCBUSD", False),  # no cotiza en USDT
        ("USDT", False),
    ],
)
def test_candidatos_sin_stablecoins_ni_apalancados(symbol: str, ok: bool) -> None:
    assert is_candidate(symbol) is ok


def test_candidatos_ordenados_y_sin_duplicados() -> None:
    assert candidates(["ETHUSDT", "BTCUSDT", "BTCUSDT", "USDCUSDT"]) == ["BTCUSDT", "ETHUSDT"]


def _volumes(n: int) -> dict[str, float]:
    return {f"S{i:02d}USDT": float(1000 - i) for i in range(n)}


def test_elige_los_15_de_mayor_volumen_y_marca_los_5_menores() -> None:
    volumes = _volumes(20) | {"USDCUSDT": 10**9, "BTCUPUSDT": 10**9, "CEROUSDT": 0.0}
    universe = select_universe(volumes)
    assert universe.symbols == tuple(f"S{i:02d}USDT" for i in range(UNIVERSE_SIZE))
    assert universe.smallest == tuple(f"S{i:02d}USDT" for i in range(10, 15))
    assert len(universe.smallest) == SMALLEST
    # Las exclusiones no entran ni aunque tengan más volumen; un volumen 0 tampoco cuenta.
    assert "USDCUSDT" not in universe.volumes
    assert "CEROUSDT" not in universe.volumes
    assert universe.candidates == 20


def test_empates_por_simbolo_y_falla_si_faltan_candidatos() -> None:
    tie = {"BBBUSDT": 5000.0, "AAAUSDT": 5000.0} | _volumes(13)
    universe = select_universe(tie)
    assert universe.symbols[:2] == ("AAAUSDT", "BBBUSDT")
    with pytest.raises(ValueError, match="se necesitan 15"):
        select_universe(_volumes(14))
