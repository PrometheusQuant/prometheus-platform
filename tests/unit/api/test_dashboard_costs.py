"""Costes reales en la página del paper (PQ-95): tabla en español, frase y gráfico."""

from __future__ import annotations

import json
import re
from typing import Any

from streamlit.testing.v1 import AppTest

from prometheus_platform.api.dashboard import costs

ARTIFACT: dict[str, Any] = {
    "source": "binance-demo/muestreo",
    "legs": [
        {
            "leg": "spot",
            "orders": 6,
            "slippage_bp_median": 1.25,
            "slippage_bp_mean": 1.4,
            "slippage_bp_p90": 2.5,
            "fee_rate_mean": 0.001,
            "assumed_slippage_bp": 2.0,
            "assumed_fee_rate": 0.001,
            "slippage_worse": False,
            "fee_worse": False,
        },
        {
            "leg": "perp",
            "orders": 6,
            "slippage_bp_median": 6.5,
            "slippage_bp_mean": 6.0,
            "slippage_bp_p90": 9.0,
            "fee_rate_mean": 0.0005,
            "assumed_slippage_bp": 5.0,
            "assumed_fee_rate": 0.0005,
            "slippage_worse": True,
            "fee_worse": False,
        },
    ],
    "orders": [
        {"symbol": "BTCUSDT", "leg": "spot", "slippage_bp": 1.25, "assumed_slippage_bp": 2.0},
        {"symbol": "DOGEUSDT", "leg": "perp", "slippage_bp": 6.5, "assumed_slippage_bp": 5.0},
    ],
}


def test_the_table_is_in_spanish_format_and_flags_what_is_worse() -> None:
    table = costs.legs_table([ARTIFACT])
    assert table["pata"].to_list() == ["al contado", "perpetuo"]
    assert table["slippage mediano"].to_list() == ["1,25 pb", "6,50 pb"]
    assert table["comisión media"].to_list() == ["0,100 %", "0,050 %"]
    assert table["¿peor que lo supuesto?"].to_list() == ["no", "slippage"]
    decimal_point = re.compile(r"\d\.\d")
    assert not any(decimal_point.search(v) for col in table.columns for v in table[col])
    assert costs.legs_table([]).is_empty()


def test_the_headline_says_when_an_amendment_is_due() -> None:
    assert "binance-demo/muestreo (perpetuo)" in costs.headline([ARTIFACT])
    assert "enmienda" in costs.headline([ARTIFACT])
    fine = {**ARTIFACT, "legs": [ARTIFACT["legs"][0]]}
    assert "dentro de lo que suponen" in costs.headline([fine])
    assert costs.headline([]) == "Todavía no hay fills medidos."


def test_orders_feed_the_chart() -> None:
    frame = costs.orders_frame([ARTIFACT])
    assert frame["serie"].to_list() == [
        "binance-demo/muestreo · contado · supuesto 2 pb",
        "binance-demo/muestreo · perpetuo · supuesto 5 pb",
    ]
    assert frame["slippage (pb)"].to_list() == [1.25, 6.5]


def _render(artifacts: list[dict[str, Any]]) -> AppTest:
    script = (
        "import json\n"
        "from prometheus_platform.api.dashboard import app\n"
        "from prometheus_platform.api.dashboard.artifacts import Artifacts\n"
        f"app._live_costs(Artifacts(costs=json.loads({json.dumps(artifacts)!r})))\n"
    )
    return AppTest.from_string(script, default_timeout=30).run()


def test_the_section_renders_with_and_without_artifacts() -> None:
    at = _render([ARTIFACT])
    assert not at.exception
    assert len(at.dataframe) == 1
    assert any("enmienda" in m.value for m in at.markdown)
    empty = _render([])
    assert not empty.exception
    assert any("Todavía no hay costes medidos" in c.value for c in empty.caption)
