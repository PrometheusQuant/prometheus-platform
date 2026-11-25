"""Fear & Greed en el lakehouse (PQ-128): una copia por descarga y silver point-in-time."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from prometheus_platform.data_platform import sentiment as se


def body(values: dict[date, int]) -> str:
    rows = [
        {
            "value": str(v),
            "value_classification": "Extreme Fear" if v <= 25 else "Fear",
            "timestamp": str(int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())),
        }
        for d, v in values.items()
    ]
    return json.dumps({"data": rows})


def test_each_download_is_kept_and_the_first_value_wins(tmp_path: Path) -> None:
    bronze, silver = tmp_path / "bronze", tmp_path / "silver"
    first = {date(2024, 1, 1): 20, date(2024, 1, 2): 30, date(2024, 1, 5): 40}
    se.write_bronze(bronze, body(first), "u", datetime(2024, 1, 6, tzinfo=UTC))
    revised = {**first, date(2024, 1, 2): 31}
    se.write_bronze(bronze, body(revised), "u", datetime(2024, 1, 7, tzinfo=UTC))

    quality = se.build_silver(bronze, silver)

    assert quality.downloads == 2
    assert quality.revised == [("2024-01-02", 30, 31)]
    assert quality.gaps == [("2024-01-02", 2)]
    table = se.read_silver(silver)
    assert table["value"].to_list() == [20, 30, 40]  # la primera vez que se vio
    assert table["knowledge_time"][0] == datetime(2024, 1, 1, 1, tzinfo=UTC)


def test_values_out_of_range_are_rejected(tmp_path: Path) -> None:
    se.write_bronze(tmp_path / "b", body({date(2024, 1, 1): 101}), "u", datetime.now(UTC))
    with pytest.raises(se.SentimentValidationError):
        se.build_silver(tmp_path / "b", tmp_path / "s")
    with pytest.raises(se.SentimentValidationError, match="No hay descargas"):
        se.build_silver(tmp_path / "vacio", tmp_path / "s")


def test_bronze_needs_an_aware_fetch_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        se.write_bronze(tmp_path, "{}", "u", datetime(2024, 1, 1))  # noqa: DTZ001
