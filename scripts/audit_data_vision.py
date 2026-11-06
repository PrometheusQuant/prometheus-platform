"""Auditoría de las fuentes de Binance Data Vision (spike PQ-19).

Qué hace: lista los archivos publicados en el bucket público de Data Vision para un universo de
símbolos, descarga cada archivo en memoria, verifica su checksum SHA-256 y mide calidad: filas,
cabecera, unidad de los timestamps, duplicados, huecos y rango de fechas. No escribe datos en
disco: solo imprime un resumen JSON (y lo guarda en ``--out`` si se indica).

Cómo se ejecuta::

    uv run python scripts/audit_data_vision.py --out /tmp/auditoria.json
    uv run python scripts/audit_data_vision.py --symbols BTCUSDT --datasets um-funding

Solo usa la librería estándar. Es idempotente y no modifica nada.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import itertools
import json
import re
import sys
import time
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from xml.etree import ElementTree as ET

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DOWNLOAD = "https://data.binance.vision"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
UNIVERSE = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
HOUR_MS = 3_600_000
PERIOD = re.compile(r"-(\d{4})-(\d{2})(?:-(\d{2}))?\.zip$")


@dataclass(frozen=True)
class Dataset:
    name: str
    prefix: str  # admite {symbol}
    step_ms: int | None  # paso esperado entre filas; None si es irregular
    sample_only: bool = False  # True: archivos diarios, se audita el día 1 de cada mes


DATASETS = {
    d.name: d
    for d in (
        Dataset("spot-klines-1h", "data/spot/monthly/klines/{symbol}/1h/", HOUR_MS),
        Dataset("spot-klines-1d", "data/spot/monthly/klines/{symbol}/1d/", 24 * HOUR_MS),
        Dataset("um-klines-1h", "data/futures/um/monthly/klines/{symbol}/1h/", HOUR_MS),
        Dataset("um-klines-1d", "data/futures/um/monthly/klines/{symbol}/1d/", 24 * HOUR_MS),
        Dataset("um-funding", "data/futures/um/monthly/fundingRate/{symbol}/", None),
        Dataset(
            "um-premium-1h", "data/futures/um/monthly/premiumIndexKlines/{symbol}/1h/", HOUR_MS
        ),
        Dataset(
            "um-metrics-5m",
            "data/futures/um/daily/metrics/{symbol}/",
            5 * 60_000,
            sample_only=True,
        ),
    )
}


@dataclass
class FileReport:
    key: str
    size: int
    checksum_ok: bool | None = None
    rows: int = 0
    header: bool = False
    ts_digits: list[int] = field(default_factory=list)
    first_ts: int | None = None
    last_ts: int | None = None
    duplicates: int = 0
    error: str | None = None


@dataclass
class DatasetReport:
    dataset: str
    symbol: str
    files: int = 0
    bytes: int = 0
    first_file: str | None = None
    last_file: str | None = None
    missing_periods: list[str] = field(default_factory=list)
    audited_files: int = 0
    checksum_failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rows: int = 0
    files_with_header: int = 0
    ts_digit_counts: dict[str, int] = field(default_factory=dict)
    first_ts: str | None = None
    last_ts: str | None = None
    duplicates: int = 0
    files_with_duplicates: int = 0
    last_file_with_duplicates: str | None = None
    gaps: int = 0
    largest_gap_hours: float = 0.0
    step_counts_hours: dict[str, int] = field(default_factory=dict)


def fetch(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - URL fija https
                return bytes(response.read())
        except (URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("inalcanzable")


def list_keys(prefix: str) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    marker = ""
    while True:
        url = f"{BUCKET}?prefix={quote(prefix)}&marker={quote(marker)}"
        root = ET.fromstring(fetch(url))  # noqa: S314 - XML de un bucket público conocido
        for item in root.findall("s3:Contents", S3_NS):
            key = item.findtext("s3:Key", "", S3_NS)
            keys.append((key, int(item.findtext("s3:Size", "0", S3_NS))))
        if root.findtext("s3:IsTruncated", "false", S3_NS) != "true" or not keys:
            return keys
        marker = keys[-1][0]


def to_ms(raw: int) -> int:
    """Normaliza a milisegundos: Data Vision pasó a microsegundos en spot desde 2025."""
    return raw // 1000 if raw >= 10**15 else raw


def parse_timestamp(cell: str) -> tuple[int, int] | None:
    """Devuelve (milisegundos, nº de dígitos) o None si la celda es una cabecera.

    Los klines y el funding usan epoch numérico; ``metrics`` usa texto ``YYYY-MM-DD HH:MM:SS``
    (se informa como 0 dígitos).
    """
    if cell.isdigit():
        return to_ms(int(cell)), len(cell)
    try:
        moment = datetime.strptime(cell, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return int(moment.timestamp() * 1000), 0


def missing_periods(keys: list[str]) -> list[str]:
    """Meses (o días, en datasets diarios) sin archivo entre el primero y el último."""
    periods = []
    for key in keys:
        if match := PERIOD.search(key):
            year, month, day = match.groups()
            periods.append((int(year), int(month), int(day) if day else None))
    if len(periods) < 2:
        return []
    present = set(periods)
    (y, m, d), last = periods[0], periods[-1]
    missing = []
    while (y, m, d) != last:
        if (y, m, d) not in present:
            missing.append(f"{y:04d}-{m:02d}" + (f"-{d:02d}" if d else ""))
        if d is None or d == calendar.monthrange(y, m)[1]:
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            d = None if d is None else 1
        else:
            d += 1
    return missing


def audit_file(key: str, size: int) -> tuple[FileReport, list[int]]:
    report = FileReport(key=key, size=size)
    timestamps: list[int] = []
    try:
        payload = fetch(f"{DOWNLOAD}/{key}")
        expected = fetch(f"{DOWNLOAD}/{key}.CHECKSUM").decode().split()[0]
        report.checksum_ok = hashlib.sha256(payload).hexdigest() == expected
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            [member] = archive.namelist()
            text = archive.read(member).decode()
        digits: Counter[int] = Counter()
        for row in csv.reader(io.StringIO(text)):
            if not row:
                continue
            parsed = parse_timestamp(row[0])
            if parsed is None:
                report.header = True
                continue
            report.rows += 1
            digits[parsed[1]] += 1
            timestamps.append(parsed[0])
        report.ts_digits = sorted(digits)
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
    if timestamps:
        report.first_ts, report.last_ts = min(timestamps), max(timestamps)
        report.duplicates = len(timestamps) - len(set(timestamps))
    return report, timestamps


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def audit(dataset: Dataset, symbol: str, pool: ThreadPoolExecutor) -> DatasetReport:
    listing = [
        (k, s) for k, s in list_keys(dataset.prefix.format(symbol=symbol)) if k.endswith(".zip")
    ]
    report = DatasetReport(dataset=dataset.name, symbol=symbol, files=len(listing))
    if not listing:
        return report
    report.bytes = sum(s for _, s in listing)
    report.first_file, report.last_file = listing[0][0], listing[-1][0]
    report.missing_periods = missing_periods([k for k, _ in listing])
    targets = listing
    if dataset.sample_only:
        # Un día por mes (el día 1) más el último archivo publicado.
        targets = [item for item in listing if item[0].endswith("-01.zip")] + [listing[-1]]
    results = list(pool.map(lambda item: audit_file(*item), targets))

    all_ts: list[int] = []
    gaps: list[int] = []
    digit_counts: Counter[str] = Counter()
    for file_report, timestamps in results:
        if dataset.sample_only and dataset.step_ms:
            # Muestra no contigua: los huecos solo se miden dentro de cada archivo.
            day = sorted(set(timestamps))
            gaps += [b - a for a, b in itertools.pairwise(day) if b - a > dataset.step_ms]
        report.audited_files += 1
        report.rows += file_report.rows
        report.files_with_header += file_report.header
        digit_counts.update(str(d) for d in file_report.ts_digits)
        if file_report.duplicates:
            report.files_with_duplicates += 1
            report.last_file_with_duplicates = file_report.key
        if file_report.checksum_ok is False:
            report.checksum_failures.append(file_report.key)
        if file_report.error:
            report.errors.append(f"{file_report.key}: {file_report.error}")
        all_ts.extend(timestamps)
    report.ts_digit_counts = dict(digit_counts)
    if not all_ts:
        return report

    ordered = sorted(all_ts)
    report.first_ts, report.last_ts = iso(ordered[0]), iso(ordered[-1])
    unique = sorted(set(ordered))
    report.duplicates = len(ordered) - len(unique)
    if dataset.sample_only:
        report.gaps = len(gaps)
        report.largest_gap_hours = max(gaps, default=0) / HOUR_MS
        return report
    steps = [b - a for a, b in itertools.pairwise(unique)]
    if dataset.step_ms is None:
        # Irregular (funding): se informa la distribución de intervalos redondeada a horas.
        report.step_counts_hours = {
            str(h): n for h, n in Counter(round(s / HOUR_MS) for s in steps).most_common(6)
        }
    else:
        gaps = [s for s in steps if s > dataset.step_ms]
        report.gaps = len(gaps)
        report.largest_gap_hours = max(gaps, default=0) / HOUR_MS
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--symbols", nargs="+", default=list(UNIVERSE))
    parser.add_argument("--datasets", nargs="+", default=list(DATASETS), choices=list(DATASETS))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", help="Ruta donde guardar el JSON (opcional)")
    args = parser.parse_args(argv)

    reports: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name in args.datasets:
            for symbol in args.symbols:
                started = time.monotonic()
                report = audit(DATASETS[name], symbol, pool)
                print(
                    f"{name:<15} {symbol:<8} archivos={report.files:<5} filas={report.rows:<8}"
                    f" checksum_fallidos={len(report.checksum_failures)}"
                    f" ({time.monotonic() - started:.0f}s)",
                    file=sys.stderr,
                )
                reports.append(asdict(report))

    output = json.dumps(
        {"generated_at": datetime.now(UTC).isoformat(), "reports": reports}, indent=2
    )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
