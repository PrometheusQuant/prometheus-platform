"""Ping a la verificación externa de disponibilidad (PQ-97): Healthchecks.io u otro similar."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from prometheus_platform.adapters.uptime_ping import UptimePinger
from prometheus_platform.ops.settings import Settings

URL = "https://hc-ping.com/" + "0000-prueba"


def pinger(handler: httpx.MockTransport, fallback: io.StringIO) -> UptimePinger:
    return UptimePinger(httpx.Client(transport=handler), SecretStr(URL), fallback=fallback)


def test_a_healthy_check_pings_the_url_and_a_failing_one_its_fail_endpoint() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="OK")

    ping = pinger(httpx.MockTransport(handler), io.StringIO())
    assert ping.ping(healthy=True)
    assert ping.ping(healthy=False)
    assert seen == [URL, URL + "/fail"]


def test_failures_never_raise_nor_print_the_url() -> None:
    fallback = io.StringIO()

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"sin red hacia {request.url}")

    assert not pinger(httpx.MockTransport(down), fallback).ping(healthy=True)
    rejected = httpx.MockTransport(lambda r: httpx.Response(404, text="not found"))
    assert not pinger(rejected, fallback).ping(healthy=True)

    out = fallback.getvalue()
    assert "ConnectError" in out
    assert "HTTP 404" in out
    assert URL not in out  # la URL es un secreto: con ella cualquiera fingiría que la VM vive


def test_the_url_must_be_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PQ_HEALTHCHECK_URL", "http://hc-ping.com/x")
    with pytest.raises(ValidationError, match="https"):
        Settings()
    monkeypatch.setenv("PQ_HEALTHCHECK_URL", URL)
    assert Settings().healthcheck_url is not None


def test_the_watchdog_pings_after_each_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prometheus_platform.adapters import uptime_ping  # noqa: PLC0415
    from prometheus_platform.api.cli import main  # noqa: PLC0415

    pings: list[bool] = []

    def record(self: object, *, healthy: bool) -> bool:
        pings.append(healthy)
        return True

    monkeypatch.setattr(uptime_ping.UptimePinger, "ping", record)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    assert main(["paper", "watchdog", "--once"]) == 1
    assert pings == []  # sin URL configurada no hay ping

    monkeypatch.setenv("PQ_HEALTHCHECK_URL", URL)
    assert main(["paper", "watchdog", "--once"]) == 1  # sin heartbeat: no está sano
    assert pings == [False]
