import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from prometheus_platform.ops.settings import Environment, Settings, load_settings

KEY = "real-api-key-123"
SECRET = "real-api-secret-456"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Aísla los tests del .env y de las variables PQ_* de quien los ejecute.
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)


def test_defaults_are_a_safe_dev_environment() -> None:
    settings = load_settings()
    assert settings.environment is Environment.DEV
    assert settings.binance_testnet is True
    assert settings.data_dir == Path("data")


def test_reads_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PQ_ENVIRONMENT", "paper")
    monkeypatch.setenv("PQ_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PQ_DATA_DIR", "/srv/lakehouse")
    settings = load_settings()
    assert settings.environment is Environment.PAPER
    assert settings.log_level == "DEBUG"
    assert settings.data_dir == Path("/srv/lakehouse")


def test_reads_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PQ_ENVIRONMENT=paper\nPQ_TELEGRAM_CHAT_ID=42\n")
    settings = load_settings()
    assert settings.environment is Environment.PAPER
    assert settings.telegram_chat_id == "42"


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({}, "PQ_BINANCE_API_KEY, PQ_BINANCE_API_SECRET"),
        ({"PQ_BINANCE_API_KEY": KEY}, "PQ_BINANCE_API_SECRET"),
        ({"PQ_BINANCE_API_KEY": "  ", "PQ_BINANCE_API_SECRET": SECRET}, "PQ_BINANCE_API_KEY"),
    ],
)
def test_live_without_api_keys_fails_with_clear_error(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], missing: str
) -> None:
    monkeypatch.setenv("PQ_ENVIRONMENT", "live")
    monkeypatch.setenv("PQ_BINANCE_TESTNET", "false")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=f"El entorno live requiere {missing}"):
        load_settings()


def test_live_cannot_point_to_testnet() -> None:
    with pytest.raises(ValidationError, match="no puede usar la testnet"):
        Settings(
            environment=Environment.LIVE,
            binance_api_key=KEY,
            binance_api_secret=SECRET,
            binance_testnet=True,
        )


def test_live_with_keys_and_mainnet_is_valid() -> None:
    settings = Settings(
        environment=Environment.LIVE,
        binance_api_key=KEY,
        binance_api_secret=SECRET,
        binance_testnet=False,
    )
    assert settings.binance_api_secret is not None
    assert settings.binance_api_secret.get_secret_value() == SECRET


def test_paper_never_trades_on_mainnet() -> None:
    with pytest.raises(ValidationError, match="solo opera en testnet"):
        Settings(environment=Environment.PAPER, binance_testnet=False)


def test_secrets_never_appear_in_repr_or_dumps() -> None:
    settings = Settings(
        binance_api_key=KEY,
        binance_api_secret=SECRET,
        telegram_bot_token="bot-token-789",
    )
    for rendered in (repr(settings), str(settings), settings.model_dump_json()):
        assert KEY not in rendered
        assert SECRET not in rendered
        assert "bot-token-789" not in rendered


def test_settings_are_immutable() -> None:
    settings = load_settings()
    with pytest.raises(ValidationError):
        settings.environment = Environment.LIVE  # type: ignore[misc]
