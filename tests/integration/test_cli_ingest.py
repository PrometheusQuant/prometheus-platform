import os
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest
import structlog

from prometheus_platform.adapters.binance_data_vision import archive_path
from prometheus_platform.api import cli
from prometheus_platform.domain.datasets import ArchiveRef, DatasetKind, Market

ZipFactory = Callable[[str, str], tuple[bytes, str]]
BASE = "https://data.binance.vision"
FUNDING_CSV = "calc_time,funding_interval_hours,last_funding_rate\n{ts},8,0.00010000\n"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    yield
    structlog.reset_defaults()


def serve(monkeypatch: pytest.MonkeyPatch, routes: dict[str, bytes]) -> list[str]:
    """Sustituye la red por un servidor simulado y devuelve las URLs pedidas."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        body = routes.get(str(request.url))
        return httpx.Response(200, content=body) if body is not None else httpx.Response(404)

    monkeypatch.setattr(
        cli, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return requested


def publish(routes: dict[str, bytes], ref: ArchiveRef, payload: bytes, sha: str) -> None:
    routes[f"{BASE}/{archive_path(ref)}"] = payload
    routes[f"{BASE}/{archive_path(ref)}.CHECKSUM"] = f"{sha}  file.zip".encode()


def funding_ref(month: int) -> ArchiveRef:
    return ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", date(2024, month, 1))


def test_ingest_funding_end_to_end_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_zip: ZipFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    routes: dict[str, bytes] = {}
    for month, ts in ((1, 1704067200000), (2, 1706745600000)):
        publish(routes, funding_ref(month), *make_zip("f.csv", FUNDING_CSV.format(ts=ts)))
    requested = serve(monkeypatch, routes)

    args = ["ingest", "funding", "--symbol", "btcusdt", "--start", "2024-01", "--end", "2024-03"]
    assert cli.main(args) == 0
    assert "escritos=2 ya_ingeridos=0 no_publicados=1 rechazados=0" in capsys.readouterr().out
    files = sorted((tmp_path / "lake" / "bronze").rglob("*.parquet"))
    assert [f.name for f in files] == ["BTCUSDT-fundingRate-2024-01.parquet",
                                       "BTCUSDT-fundingRate-2024-02.parquet"]  # fmt: skip
    assert pq.read_table(files[0]).column("calc_time").to_pylist() == ["1704067200000"]

    downloads_before = sum(not url.endswith(".CHECKSUM") for url in requested)
    assert cli.main(args) == 0
    assert "escritos=0 ya_ingeridos=2" in capsys.readouterr().out
    assert sum(not url.endswith(".CHECKSUM") for url in requested) == downloads_before


def test_corrupt_archive_makes_the_command_fail_and_is_logged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_zip: ZipFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ref = ArchiveRef(Market.SPOT, DatasetKind.KLINES, "ETHUSDT", date(2024, 1, 1), "1d")
    payload, _ = make_zip("k.csv", "1704067200000,1,2,0.5,1.5,10,1704153599999,15,3,5,7,0\n")
    routes: dict[str, bytes] = {}
    publish(routes, ref, payload, "0" * 64)
    serve(monkeypatch, routes)

    code = cli.main(["ingest", "klines", "--market", "spot", "--symbol", "ETHUSDT",
                     "--interval", "1d", "--start", "2024-01", "--end", "2024-01"])  # fmt: skip
    assert code == 1
    assert "rechazados=1" in capsys.readouterr().out
    assert "checksum" in (tmp_path / "lake" / "bronze" / "_rejections.jsonl").read_text()
    assert not list((tmp_path / "lake").rglob("*.parquet"))


def test_end_defaults_to_last_complete_month() -> None:
    assert cli.last_complete_month(date(2026, 10, 23)) == date(2026, 9, 1)
    assert cli.last_complete_month(date(2027, 1, 5)) == date(2026, 12, 1)


def test_rejects_malformed_month(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["ingest", "funding", "--symbol", "BTCUSDT", "--start", "2024/01"])
    assert "AAAA-MM" in capsys.readouterr().err


def test_default_http_client_follows_redirects() -> None:
    with cli.http_client() as client:
        assert client.follow_redirects
