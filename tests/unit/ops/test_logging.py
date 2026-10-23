import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import structlog
from pydantic import SecretStr

from prometheus_platform.ops.logging import REDACTED, configure_logging, get_logger
from prometheus_platform.ops.settings import Environment, Settings


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def json_lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def configured(environment: Environment, **overrides: object) -> io.StringIO:
    stream = io.StringIO()
    configure_logging(Settings(environment=environment, **overrides), stream=stream)  # type: ignore[arg-type]
    return stream


def test_paper_emits_one_json_object_per_event_with_required_fields() -> None:
    stream = configured(Environment.PAPER)
    get_logger(component="ingest").info("bars_ingested", rows=24)

    [record] = json_lines(stream)
    assert record["event"] == "bars_ingested"
    assert record["level"] == "info"
    assert record["environment"] == "paper"
    assert record["component"] == "ingest"
    assert record["rows"] == 24
    timestamp = datetime.fromisoformat(str(record["timestamp"]))
    assert timestamp.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - timestamp) < timedelta(minutes=1)


def test_dev_emits_human_readable_lines() -> None:
    stream = configured(Environment.DEV)
    get_logger().warning("disk_almost_full", free_gb=1)
    line = stream.getvalue()
    assert "disk_almost_full" in line
    assert "free_gb=1" in line
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)


def test_level_filter_drops_lower_levels() -> None:
    stream = configured(Environment.PAPER, log_level="WARNING")
    log = get_logger()
    log.info("ignored")
    log.error("kept")
    assert [r["event"] for r in json_lines(stream)] == ["kept"]


def test_secrets_are_masked_in_logs() -> None:
    stream = configured(Environment.PAPER)
    get_logger().info(
        "connecting",
        credentials=SecretStr("s3cr3t-value"),
        api_key="plain-key",
        nested={"bot_token": "tok-123", "symbol": "BTCUSDT"},
    )
    output = stream.getvalue()
    for leaked in ("s3cr3t-value", "plain-key", "tok-123"):
        assert leaked not in output
    [record] = json_lines(stream)
    assert record["credentials"] == REDACTED
    assert record["api_key"] == REDACTED
    assert record["nested"] == {"bot_token": REDACTED, "symbol": "BTCUSDT"}


def test_logging_the_settings_object_does_not_leak_secrets() -> None:
    settings = Settings(
        environment=Environment.PAPER,
        binance_api_secret="very-secret",
    )
    stream = io.StringIO()
    configure_logging(settings, stream=stream)
    get_logger().info("started", settings=settings.model_dump())
    assert "very-secret" not in stream.getvalue()


def test_context_variables_are_merged() -> None:
    stream = configured(
        Environment.LIVE, binance_api_key="k", binance_api_secret="s", binance_testnet=False
    )
    structlog.contextvars.bind_contextvars(run_id="abc")
    get_logger().info("tick")
    [record] = json_lines(stream)
    assert record["run_id"] == "abc"
    assert record["environment"] == "live"
