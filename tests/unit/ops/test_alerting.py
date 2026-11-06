import io
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import structlog
from pydantic import SecretStr

from prometheus_platform.adapters.in_memory import RecordingNotifier
from prometheus_platform.api import cli
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.ops.alerting import AlertForwarder
from prometheus_platform.ops.logging import REDACTED, configure_logging, get_logger
from prometheus_platform.ops.settings import Environment, Settings

T0 = datetime(2026, 11, 5, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def configured(notifier: object) -> io.StringIO:
    stream = io.StringIO()
    configure_logging(Settings(environment=Environment.PAPER), stream=stream, notifier=notifier)  # type: ignore[arg-type]
    return stream


def test_errors_are_forwarded_and_info_is_not() -> None:
    notifier = RecordingNotifier()
    stream = configured(notifier)
    log = get_logger(component="live")
    log.info("heartbeat")
    log.warning("slow_fill")
    log.error("hedge_leg_missing", symbol="SOLUSDT")
    log.critical("kill_switch_triggered")

    assert [a.title for a in notifier.alerts] == ["hedge_leg_missing", "kill_switch_triggered"]
    first = notifier.alerts[0]
    assert first.severity is AlertSeverity.ERROR
    assert first.environment == "paper"
    assert first.details == {"component": "live", "symbol": "SOLUSDT"}
    assert stream.getvalue().count("\n") == 4  # el log se sigue escribiendo entero


def test_alerts_never_carry_secrets() -> None:
    notifier = RecordingNotifier()
    configured(notifier)
    get_logger().error("auth_failed", api_key="abc123", creds={"secret": "x"}, s=SecretStr("y"))

    rendered = notifier.alerts[0].render()
    assert "abc123" not in rendered
    assert "'x'" not in rendered
    assert "'y'" not in rendered
    assert REDACTED in rendered


def test_a_failing_notifier_does_not_break_logging() -> None:
    class Exploding:
        def notify(self, alert: Alert) -> bool:
            raise RuntimeError("canal caído")

    stream = configured(Exploding())
    get_logger().error("boom")
    assert "boom" in stream.getvalue()


def test_exceptions_are_alerted_as_errors() -> None:
    notifier = RecordingNotifier()
    configured(notifier)
    try:
        raise ValueError("precio negativo")
    except ValueError:
        get_logger().exception("valuation_failed")
    [alert] = notifier.alerts
    assert alert.severity is AlertSeverity.ERROR
    assert "precio negativo" in alert.details["exception"]


def test_cooldown_suppresses_repeats_of_the_same_event() -> None:
    now = [T0]
    notifier = RecordingNotifier(deliver=False)
    forwarder = AlertForwarder(notifier, cooldown=timedelta(minutes=5), clock=lambda: now[0])
    for minute in (0, 1, 4, 6):
        now[0] = T0 + timedelta(minutes=minute)
        forwarder(None, "error", {"event": "feed_stale", "level": "error"})
    forwarder(None, "error", {"event": "otro", "level": "error"})

    assert [a.occurred_at.minute for a in notifier.alerts] == [0, 6, 6]
    assert forwarder.suppressed == 2
    assert forwarder.failed == 3


def test_render_is_plain_text_and_truncates_long_details() -> None:
    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        title="t",
        occurred_at=T0,
        environment="live",
        details={"b": "x" * 1000, "a": "1"},
    )
    lines = alert.render().splitlines()
    assert lines[0] == "[CRITICAL] t"
    assert lines[2] == "a: 1"
    assert len(lines[3]) == len("b: ") + 300


def test_render_shows_local_time_first_and_utc_as_reference() -> None:
    alert = Alert(severity=AlertSeverity.WARNING, title="t", occurred_at=T0, environment="dev")
    assert alert.render().splitlines()[1] == "entorno=dev hora=2026-11-05T12:00:00+00:00"
    local = alert.render(ZoneInfo("America/La_Paz")).splitlines()[1]
    assert local == "entorno=dev hora=2026-11-05 08:00:00 -04 (12:00:00 UTC)"


def test_cli_alert_test_reports_missing_channel_and_delivery(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    assert cli.main(["alert", "test"]) == 1
    assert "sin canal" in capsys.readouterr().out

    recorder = RecordingNotifier()
    monkeypatch.setattr(cli, "notifier_from_settings", lambda _settings: recorder)
    assert cli.main(["alert", "test"]) == 0
    assert recorder.alerts[0].title == "alerta de prueba"
    assert "entregada=sí" in capsys.readouterr().out
