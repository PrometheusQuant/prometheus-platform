"""Capa gold: modelo en estrella para BI (PQ-46, Proyecto Integrador 7.1).

Toma silver y los artefactos de research (archivos JSON y Parquet de ``data/research/``) y produce
dimensiones y hechos con claves de una sola columna, listos para Power BI (PQ-47).

- Cada tabla se **declara** aquí con su grano, su clave, sus fuentes y la descripción de cada
  columna. El esquema producido debe coincidir con el declarado, y el diccionario de datos y la
  página de documentación se generan desde estas mismas declaraciones.
- **El holdout sigue cerrado:** ningún hecho con fecha tiene filas desde ``HOLDOUT_START``.
- No se importa ``research`` (capa superior): sus resultados se leen como archivos. Si falta un
  artefacto, su hecho queda vacío con el esquema declarado y el informe lo dice.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl

from prometheus_platform.data_platform.silver import silver_path
from prometheus_platform.domain.datasets import DatasetKind, Market
from prometheus_platform.domain.protocol import HOLDOUT_START

GOLD_DIR = "gold"
EXPORT_DIR = "export"
DB_FILE = "gold.duckdb"
DICTIONARY_FILE = "DICCIONARIO.md"
KLINE_INTERVAL = "1h"
HOLDOUT_DATE = HOLDOUT_START.date()
# Un día D se devenga hasta la liquidación y la valoración de las 00:00 de D + 1 (enm. 1.3). El
# último día cuyo devengo termina antes del holdout es, por tanto, el 2024-06-29: el 30 de junio
# incluye la liquidación del 2024-07-01 00:00, que es del holdout (pre-registro §7, KE-014).
LAST_DAY = HOLDOUT_DATE - timedelta(days=2)
_MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class GoldValidationError(ValueError):
    """Una tabla gold viola su declaración: la construcción se detiene."""


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    dtype: pl.DataType
    description: str


@dataclass(frozen=True, slots=True)
class ForeignKey:
    column: str
    table: str


@dataclass(frozen=True, slots=True)
class GoldTable:
    name: str
    kind: Literal["dimensión", "hecho"]
    grain: str
    description: str
    sources: tuple[str, ...]
    columns: tuple[Column, ...]
    key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()

    @property
    def schema(self) -> pl.Schema:
        return pl.Schema({c.name: c.dtype for c in self.columns})

    def empty(self) -> pl.DataFrame:
        return pl.DataFrame(schema=self.schema)


STR, FLT, INT, BOOL, DATE = pl.String(), pl.Float64(), pl.Int64(), pl.Boolean(), pl.Date()


def _cols(*spec: tuple[str, pl.DataType, str]) -> tuple[Column, ...]:
    return tuple(Column(n, t, d) for n, t, d in spec)


DIM_FECHA = GoldTable(
    name="dim_fecha",
    kind="dimensión",
    grain="un día calendario UTC",
    description="Calendario continuo que cubre todas las fechas de los hechos.",
    sources=("fechas de los hechos con fecha",),
    columns=_cols(
        ("fecha", DATE, "Día calendario UTC (clave)"),
        ("anio", INT, "Año"),
        ("trimestre", INT, "Trimestre (1-4)"),
        ("mes", INT, "Mes (1-12)"),
        ("nombre_mes", STR, "Nombre del mes en español"),
        ("dia_semana", STR, "Día de la semana en español"),
        ("periodo", STR, "«desarrollo» antes del 2024-07-01; «holdout» desde esa fecha"),
    ),
    key=("fecha",),
)

DIM_SIMBOLO = GoldTable(
    name="dim_simbolo",
    kind="dimensión",
    grain="un símbolo con datos en silver",
    description="Pares negociados y la hipótesis pre-registrada que los usa.",
    sources=("silver/funding/<SYMBOL>.parquet", "research/carry/H*/summary.json (symbols)"),
    columns=_cols(
        ("simbolo", STR, "Par en Binance, p. ej. SOLUSDT (clave)"),
        ("activo_base", STR, "Activo base, p. ej. SOL"),
        ("activo_cotizado", STR, "Activo de cotización, p. ej. USDT"),
        ("hipotesis", STR, "Hipótesis del carry que lo incluye (H1, H2) o nulo"),
    ),
    key=("simbolo",),
)

DIM_CONFIGURACION = GoldTable(
    name="dim_configuracion",
    kind="dimensión",
    grain="una configuración evaluada de una hipótesis",
    description="Grid pre-registrado del carry (k x θ) y el benchmark B1 de cada hipótesis.",
    sources=("research/carry/H*/summary.json", "research/carry/H*/daily_returns.parquet"),
    columns=_cols(
        ("configuracion_id", STR, "Hipótesis/configuración, p. ej. H2/k9-theta20 (clave)"),
        ("hipotesis", STR, "H1 (BTC, ETH) o H2 (SOL, BNB, XRP)"),
        ("configuracion", STR, "Nombre de la configuración, p. ej. k9-theta20 o B1-siempre-activo"),
        ("ventana_k", INT, "Liquidaciones promediadas en la señal (k); nulo en B1"),
        ("umbral_theta", FLT, "Umbral de entrada anualizado (θ); nulo en B1"),
        ("es_seleccionada", BOOL, "La configuración que eligió la CPCV"),
        ("es_benchmark", BOOL, "Benchmark B1: carry siempre activo"),
        ("sharpe_cpcv", FLT, "Sharpe medio de test en la CPCV; nulo en B1"),
    ),
    key=("configuracion_id",),
)

DIM_MODELO = GoldTable(
    name="dim_modelo",
    kind="dimensión",
    grain="un modelo evaluado en el capítulo 5",
    description="Modelos del funding: regresión del nivel/residuo y clasificación del régimen.",
    sources=("research/funding_model/<formulación>/summary.json",),
    columns=_cols(
        ("modelo_id", STR, "Tarea/algoritmo/ajuste, p. ej. clasificacion/random_forest/ajustado"),
        ("tarea", STR, "regresion o clasificacion"),
        ("algoritmo", STR, "Nombre del algoritmo"),
        ("ajustado", BOOL, "Si se ajustaron hiperparámetros con GridSearch"),
        ("formulacion", STR, "residual o level: qué se predice"),
    ),
    key=("modelo_id",),
)

FACT_FUNDING = GoldTable(
    name="fact_funding_diario",
    kind="hecho",
    grain="un símbolo x un día UTC (solo desarrollo)",
    description="Funding cobrado o pagado por las posiciones cortas en el perpetuo, por día.",
    sources=("silver/funding/<SYMBOL>.parquet ← bronze/dataset=fundingRate",),
    columns=_cols(
        ("fecha", DATE, "Día UTC de devengo: la liquidación de las 00:00 es del día anterior"),
        ("simbolo", STR, "Par"),
        ("funding_total", FLT, "Suma de las tasas liquidadas en el día (fracción del nocional)"),
        ("funding_medio", FLT, "Tasa media por liquidación"),
        (
            "funding_anualizado_medio",
            FLT,
            "Tasa anualizada media (según el intervalo de cada fila)",
        ),
        ("liquidaciones", INT, "Número de liquidaciones en el día"),
    ),
    key=("fecha", "simbolo"),
    foreign_keys=(ForeignKey("fecha", "dim_fecha"), ForeignKey("simbolo", "dim_simbolo")),
)

FACT_MERCADO = GoldTable(
    name="fact_mercado_diario",
    kind="hecho",
    grain="un símbolo x un día UTC (solo desarrollo)",
    description="Cierre diario de spot y perpetuo, base y volumen negociado.",
    sources=(
        "silver/klines/market=spot/interval=1h/<SYMBOL>.parquet ← bronze/dataset=klines",
        "silver/klines/market=um/interval=1h/<SYMBOL>.parquet ← bronze/dataset=klines",
    ),
    columns=_cols(
        ("fecha", DATE, "Día UTC (open_time de las velas horarias)"),
        ("simbolo", STR, "Par"),
        ("cierre_spot", FLT, "Último cierre horario del día en spot"),
        ("cierre_perp", FLT, "Último cierre horario del día en el perpetuo USDⓈ-M"),
        ("base", FLT, "(cierre_perp - cierre_spot) / cierre_spot"),
        ("volumen_spot_usd", FLT, "Volumen en USDT negociado en spot en el día"),
        ("volumen_perp_usd", FLT, "Volumen en USDT negociado en el perpetuo en el día"),
        ("horas_spot", INT, "Velas horarias de spot del día (24 si el día está completo)"),
        ("horas_perp", INT, "Velas horarias del perpetuo del día (24 si el día está completo)"),
    ),
    key=("fecha", "simbolo"),
    foreign_keys=(ForeignKey("fecha", "dim_fecha"), ForeignKey("simbolo", "dim_simbolo")),
)

FACT_RETORNO = GoldTable(
    name="fact_retorno_estrategia",
    kind="hecho",
    grain="una configuración x un día UTC (solo desarrollo)",
    description="Retorno diario de cartera de cada configuración del grid, neto de costes.",
    sources=("research/carry/H*/daily_returns.parquet ← silver (funding y klines)",),
    columns=_cols(
        (
            "fecha",
            DATE,
            "Día UTC al que corresponde el retorno (valoración a las 00:00 del siguiente)",
        ),
        ("configuracion_id", STR, "Configuración"),
        ("retorno", FLT, "Retorno diario neto de costes"),
        ("capital", FLT, "Capital acumulado partiendo de 1"),
    ),
    key=("fecha", "configuracion_id"),
    foreign_keys=(
        ForeignKey("fecha", "dim_fecha"),
        ForeignKey("configuracion_id", "dim_configuracion"),
    ),
)

FACT_DESEMPENO = GoldTable(
    name="fact_desempeno",
    kind="hecho",
    grain="una configuración con métricas completas (seleccionada y B1)",
    description="Métricas del periodo de desarrollo de la configuración elegida y del benchmark.",
    sources=("research/carry/H*/summary.json (selected_performance, benchmark_B1)",),
    columns=_cols(
        ("configuracion_id", STR, "Configuración"),
        ("sharpe", FLT, "Sharpe anualizado"),
        ("cagr", FLT, "Crecimiento anual compuesto"),
        ("max_drawdown", FLT, "Máxima caída desde un pico (negativa)"),
        ("calmar", FLT, "CAGR / |máximo drawdown|"),
        ("t_stat", FLT, "Estadístico t del retorno medio"),
        ("dias", INT, "Días evaluados"),
    ),
    key=("configuracion_id",),
    foreign_keys=(ForeignKey("configuracion_id", "dim_configuracion"),),
)

FACT_GATES = GoldTable(
    name="fact_gates",
    kind="hecho",
    grain="un gate x una hipótesis",
    description="Gates anti-sobreajuste del pre-registro (G1-G4) y su resultado.",
    sources=("research/carry/H*/summary.json (gates)",),
    columns=_cols(
        ("gate_id", STR, "Hipótesis/gate, p. ej. H2/G1 (clave)"),
        ("hipotesis", STR, "Hipótesis"),
        ("gate", STR, "G1 a G4"),
        ("criterio", STR, "Criterio pre-registrado"),
        ("valor", FLT, "Valor obtenido"),
        ("pasa", BOOL, "Si cumple el criterio"),
    ),
    key=("gate_id",),
)

FACT_METRICAS_MODELO = GoldTable(
    name="fact_metricas_modelo",
    kind="hecho",
    grain="un modelo",
    description="Métricas de validación walk-forward; las que no aplican a la tarea quedan nulas.",
    sources=("research/funding_model/<formulación>/summary.json",),
    columns=_cols(
        ("modelo_id", STR, "Modelo"),
        ("rmse", FLT, "Raíz del error cuadrático medio (regresión)"),
        ("mae", FLT, "Error absoluto medio (regresión)"),
        ("r2", FLT, "Coeficiente de determinación (regresión)"),
        ("auc", FLT, "Área bajo la curva ROC (clasificación)"),
        ("f1", FLT, "F1 de la clase de funding alto (clasificación)"),
    ),
    key=("modelo_id",),
    foreign_keys=(ForeignKey("modelo_id", "dim_modelo"),),
)

FACT_ESCENARIOS = GoldTable(
    name="fact_escenarios",
    kind="hecho",
    grain="un escenario del Monte Carlo",
    description="Distribución del retorno anual simulado del carry según el riesgo del exchange.",
    sources=("research/simulation/summary.json (escenarios)",),
    columns=_cols(
        ("escenario", STR, "Escenario de quiebra del exchange (clave)"),
        ("media", FLT, "Retorno anual medio"),
        ("mediana", FLT, "Retorno anual mediano"),
        ("p5", FLT, "Percentil 5"),
        ("p95", FLT, "Percentil 95"),
        ("var95", FLT, "VaR al 95 % (pérdida positiva)"),
        ("cvar95", FLT, "CVaR al 95 % (pérdida positiva)"),
        ("prob_bajo_hurdle", FLT, "Probabilidad de rendir menos que la stablecoin al 4 %"),
        ("prob_perdida", FLT, "Probabilidad de perder dinero en el año"),
        ("tiempo_invertido", FLT, "Fracción del tiempo con posición abierta"),
        ("ciclos", FLT, "Ciclos de entrada y salida por año"),
    ),
    key=("escenario",),
)

FACT_FRONTERA = GoldTable(
    name="fact_frontera",
    kind="hecho",
    grain="un peso del carry en la cartera",
    description="Optimización con CVaR: retorno esperado y riesgo según el peso en el carry.",
    sources=("research/simulation/summary.json (frontera)",),
    columns=_cols(
        ("peso_carry", FLT, "Fracción del capital en el carry (el resto, en la stablecoin al 4 %)"),
        ("retorno_esperado", FLT, "Retorno anual esperado de la cartera"),
        ("cvar95", FLT, "CVaR al 95 % de la cartera"),
        ("cumple", BOOL, "Si respeta el límite de CVaR"),
    ),
    key=("peso_carry",),
)

FACT_CALIDAD = GoldTable(
    name="fact_calidad",
    kind="hecho",
    grain="una tabla silver",
    description=(
        "Informe de calidad de cada tabla silver: filas, huecos y outliers. Única excepción al"
        " corte del holdout: describe la disponibilidad de **toda** la historia de silver (hasta"
        " 2026-09-30), sin precios, tasas ni retornos."
    ),
    sources=("silver/_quality/*.json",),
    columns=_cols(
        ("tabla", STR, "Tabla silver, p. ej. funding/SOLUSDT (clave)"),
        ("filas", INT, "Filas"),
        ("duplicados_eliminados", INT, "Duplicados idénticos eliminados"),
        ("huecos", INT, "Huecos detectados (no se imputan)"),
        ("periodos_faltantes", INT, "Periodos que faltan dentro de los huecos"),
        ("hueco_mayor_horas", FLT, "Duración del hueco más largo"),
        ("outliers", INT, "Valores marcados como outlier (no se eliminan)"),
        ("desde", STR, "Primer registro (UTC)"),
        ("hasta", STR, "Último registro (UTC)"),
    ),
    key=("tabla",),
)

TABLES: tuple[GoldTable, ...] = (
    DIM_FECHA,
    DIM_SIMBOLO,
    DIM_CONFIGURACION,
    DIM_MODELO,
    FACT_FUNDING,
    FACT_MERCADO,
    FACT_RETORNO,
    FACT_DESEMPENO,
    FACT_GATES,
    FACT_METRICAS_MODELO,
    FACT_ESCENARIOS,
    FACT_FRONTERA,
    FACT_CALIDAD,
)
DATED_FACTS = tuple(t for t in TABLES if t.kind == "hecho" and "fecha" in t.schema)


@dataclass
class GoldReport:
    rows: dict[str, int] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


# --- Lectura de fuentes ------------------------------------------------------------------------


def _read_json(path: Path, report: GoldReport) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report.missing.append(str(path))
        return None
    return data if isinstance(data, dict) else None


def _hypotheses(data_dir: Path) -> list[str]:
    root = data_dir / "research" / "carry"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def _model_summary(data_dir: Path, report: GoldReport) -> tuple[str, dict[str, Any]] | None:
    """La formulación oficial es ``residual``; si no existe, ``level`` (igual que el dashboard)."""
    root = data_dir / "research" / "funding_model"
    for mode in ("residual", "level"):
        path = root / mode / "summary.json"
        if path.is_file():
            data = _read_json(path, report)
            if data is not None:
                return mode, data
    report.missing.append(str(root / "residual" / "summary.json"))
    return None


def _symbols(data_dir: Path) -> list[str]:
    root = silver_path(data_dir / "silver", DatasetKind.FUNDING_RATE, "_").parent
    return sorted(p.stem for p in root.glob("*.parquet")) if root.is_dir() else []


# --- Constructores -----------------------------------------------------------------------------


def _frame(table: GoldTable, rows: Sequence[Mapping[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(list(rows), schema=table.schema, orient="row") if rows else table.empty()


def build_dim_simbolo(data_dir: Path, report: GoldReport) -> pl.DataFrame:
    owner: dict[str, str] = {}
    for hyp in _hypotheses(data_dir):
        summary = _read_json(data_dir / "research" / "carry" / hyp / "summary.json", report)
        for symbol in (summary or {}).get("symbols", []):
            owner[str(symbol)] = hyp
    rows = []
    for symbol in _symbols(data_dir):
        quote = "USDT" if symbol.endswith("USDT") else ""
        base = symbol.removesuffix(quote) if quote else symbol
        rows.append(
            {
                "simbolo": symbol,
                "activo_base": base,
                "activo_cotizado": quote or None,
                "hipotesis": owner.get(symbol),
            }
        )
    return _frame(DIM_SIMBOLO, rows)


def _parse_config(name: str) -> tuple[int | None, float | None]:
    if not name.startswith("k") or "-theta" not in name:
        return None, None
    k, theta = name[1:].split("-theta", 1)
    return int(k), int(theta) / 100


def build_dim_configuracion(data_dir: Path, report: GoldReport) -> pl.DataFrame:
    rows = []
    for hyp in _hypotheses(data_dir):
        summary = _read_json(data_dir / "research" / "carry" / hyp / "summary.json", report) or {}
        cpcv: Mapping[str, float] = summary.get("cpcv_mean_test_sharpe", {})
        names = list(cpcv)
        returns = data_dir / "research" / "carry" / hyp / "daily_returns.parquet"
        if returns.is_file():
            names += [c for c in pl.read_parquet_schema(returns) if c != "date" and c not in cpcv]
        for name in sorted(names):
            k, theta = _parse_config(name)
            rows.append(
                {
                    "configuracion_id": f"{hyp}/{name}",
                    "hipotesis": hyp,
                    "configuracion": name,
                    "ventana_k": k,
                    "umbral_theta": theta,
                    "es_seleccionada": name == summary.get("selected"),
                    "es_benchmark": False,
                    "sharpe_cpcv": cpcv.get(name),
                }
            )
        if "benchmark_B1" in summary:
            rows.append(
                {
                    "configuracion_id": f"{hyp}/B1-siempre-activo",
                    "hipotesis": hyp,
                    "configuracion": "B1-siempre-activo",
                    "ventana_k": None,
                    "umbral_theta": None,
                    "es_seleccionada": False,
                    "es_benchmark": True,
                    "sharpe_cpcv": None,
                }
            )
    return _frame(DIM_CONFIGURACION, rows)


def _model_id(task: str, entry: Mapping[str, Any]) -> str:
    return f"{task}/{entry['name']}/{'ajustado' if entry.get('tuned') else 'por-defecto'}"


def build_models(data_dir: Path, report: GoldReport) -> tuple[pl.DataFrame, pl.DataFrame]:
    found = _model_summary(data_dir, report)
    if found is None:
        return DIM_MODELO.empty(), FACT_METRICAS_MODELO.empty()
    mode, summary = found
    dims, facts = [], []
    for task, entries in (("regresion", "regression"), ("clasificacion", "classification")):
        for entry in summary.get(entries, []):
            model_id = _model_id(task, entry)
            dims.append(
                {
                    "modelo_id": model_id,
                    "tarea": task,
                    "algoritmo": entry["name"],
                    "ajustado": bool(entry.get("tuned")),
                    "formulacion": mode,
                }
            )
            facts.append({"modelo_id": model_id} | {m: _num(entry.get(m)) for m in _METRICS})
    return _frame(DIM_MODELO, dims), _frame(FACT_METRICAS_MODELO, facts)


_METRICS = ("rmse", "mae", "r2", "auc", "f1")


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return None if math.isnan(value) else float(value)  # NaN → nulo


def build_fact_funding(data_dir: Path) -> pl.DataFrame:
    frames = []
    for symbol in _symbols(data_dir):
        path = silver_path(data_dir / "silver", DatasetKind.FUNDING_RATE, symbol)
        frames.append(
            pl.scan_parquet(path)
            .filter(pl.col("event_time") < HOLDOUT_START)
            # Día de devengo: la liquidación de las 00:00 corresponde al día anterior.
            .group_by((pl.col("event_time") - timedelta(milliseconds=1)).dt.date().alias("fecha"))
            .agg(
                _sum_or_null("funding_rate").alias("funding_total"),
                pl.col("funding_rate").mean().alias("funding_medio"),
                pl.col("funding_rate_annualized").mean().alias("funding_anualizado_medio"),
                pl.len().cast(pl.Int64).alias("liquidaciones"),
            )
            .with_columns(pl.lit(symbol).alias("simbolo"))
            .filter(pl.col("fecha") <= LAST_DAY)
            .collect()
        )
    if not frames:
        return FACT_FUNDING.empty()
    return pl.concat(frames).select(FACT_FUNDING.schema.names()).sort("simbolo", "fecha")


def _sum_or_null(column: str) -> pl.Expr:
    """Suma que deja nulo un grupo sin ningún valor (polars devolvería 0: sería inventar)."""
    return pl.when(pl.col(column).is_not_null().any()).then(pl.col(column).sum())


def _daily_klines(path: Path, prefix: str) -> pl.LazyFrame:
    return (
        pl.scan_parquet(path)
        .filter(pl.col("open_time").dt.date() <= LAST_DAY)
        .sort("open_time")
        .group_by(pl.col("open_time").dt.date().alias("fecha"))
        .agg(
            pl.col("close").last().alias(f"cierre_{prefix}"),
            _sum_or_null("quote_volume").alias(f"volumen_{prefix}_usd"),
            pl.len().cast(pl.Int64).alias(f"horas_{prefix}"),
        )
    )


def build_fact_mercado(data_dir: Path) -> pl.DataFrame:
    frames = []
    silver = data_dir / "silver"
    for symbol in _symbols(data_dir):
        spot = silver_path(silver, DatasetKind.KLINES, symbol, Market.SPOT, KLINE_INTERVAL)
        perp = silver_path(silver, DatasetKind.KLINES, symbol, Market.USDM, KLINE_INTERVAL)
        if not (spot.is_file() and perp.is_file()):
            continue
        frames.append(
            _daily_klines(spot, "spot")
            .join(_daily_klines(perp, "perp"), on="fecha", how="inner")
            .with_columns(
                pl.lit(symbol).alias("simbolo"),
                ((pl.col("cierre_perp") - pl.col("cierre_spot")) / pl.col("cierre_spot")).alias(
                    "base"
                ),
            )
            .collect()
        )
    if not frames:
        return FACT_MERCADO.empty()
    return pl.concat(frames).select(FACT_MERCADO.schema.names()).sort("simbolo", "fecha")


def build_fact_retorno(data_dir: Path) -> pl.DataFrame:
    frames = []
    for hyp in _hypotheses(data_dir):
        path = data_dir / "research" / "carry" / hyp / "daily_returns.parquet"
        if not path.is_file():
            continue
        wide = pl.read_parquet(path)
        if wide.schema["date"] == pl.String:  # los artefactos guardan la fecha ISO como texto
            wide = wide.with_columns(pl.col("date").str.to_datetime(time_zone="UTC"))
        _check_valuation_times(wide["date"], path)
        frames.append(
            wide.unpivot(index="date", variable_name="configuracion", value_name="retorno")
            # Una valoración en el holdout incluye su liquidación de las 00:00: queda fuera.
            .filter(pl.col("date") < HOLDOUT_START)
            .with_columns(
                # Valoración a las 00:00 UTC (enm. 1.3): el retorno es del día anterior.
                (pl.col("date").dt.date() - timedelta(days=1)).alias("fecha"),
                (pl.lit(f"{hyp}/") + pl.col("configuracion")).alias("configuracion_id"),
            )
            .sort("configuracion_id", "fecha")
            .with_columns(
                (1 + pl.col("retorno")).cum_prod().over("configuracion_id").alias("capital")
            )
            .select(FACT_RETORNO.schema.names())
        )
    return pl.concat(frames) if frames else FACT_RETORNO.empty()


def _check_valuation_times(dates: pl.Series, path: Path) -> None:
    """El desplazamiento de un día solo vale para valoraciones a las 00:00 UTC (enm. 1.3)."""
    dtype = dates.dtype
    if not isinstance(dtype, pl.Datetime) or dtype.time_zone != "UTC":
        raise GoldValidationError(f"{path}: 'date' debe ser un instante UTC, no {dtype}")
    if not (dates.dt.hour() == 0).all() or not (dates.dt.minute() == 0).all():
        raise GoldValidationError(f"{path}: hay valoraciones fuera de las 00:00 UTC")


def build_fact_desempeno(data_dir: Path, report: GoldReport) -> pl.DataFrame:
    rows = []
    for hyp in _hypotheses(data_dir):
        summary = _read_json(data_dir / "research" / "carry" / hyp / "summary.json", report) or {}
        pairs = [
            (summary.get("selected"), summary.get("selected_performance")),
            ("B1-siempre-activo", summary.get("benchmark_B1")),
        ]
        for name, perf in pairs:
            if not name or not isinstance(perf, dict):
                continue
            rows.append(
                {
                    "configuracion_id": f"{hyp}/{name}",
                    "sharpe": _num(perf.get("sharpe")),
                    "cagr": _num(perf.get("cagr")),
                    "max_drawdown": _num(perf.get("max_drawdown")),
                    "calmar": _num(perf.get("calmar")),
                    "t_stat": _num(perf.get("t_stat")),
                    "dias": perf.get("days"),
                }
            )
    return _frame(FACT_DESEMPENO, rows)


def build_fact_gates(data_dir: Path, report: GoldReport) -> pl.DataFrame:
    rows = []
    for hyp in _hypotheses(data_dir):
        summary = _read_json(data_dir / "research" / "carry" / hyp / "summary.json", report) or {}
        rows += [
            {
                "gate_id": f"{hyp}/{g['name']}",
                "hipotesis": hyp,
                "gate": g["name"],
                "criterio": g.get("criterion"),
                "valor": _num(g.get("value")),
                "pasa": bool(g.get("passed")),
            }
            for g in summary.get("gates", [])
        ]
    return _frame(FACT_GATES, rows)


def build_simulation(data_dir: Path, report: GoldReport) -> tuple[pl.DataFrame, pl.DataFrame]:
    path = data_dir / "research" / "simulation" / "summary.json"
    summary = _read_json(path, report) if path.is_file() else None
    if summary is None:
        if not path.is_file():
            report.missing.append(str(path))
        return FACT_ESCENARIOS.empty(), FACT_FRONTERA.empty()
    scenarios = [
        {"escenario": name} | {c: _num(values.get(c)) for c in FACT_ESCENARIOS.schema.names()[1:]}
        for name, values in summary.get("escenarios", {}).items()
    ]
    frontier = [
        {
            "peso_carry": _num(p.get("w_carry")),
            "retorno_esperado": _num(p.get("retorno_esperado")),
            "cvar95": _num(p.get("cvar95")),
            "cumple": bool(p.get("cumple")),
        }
        for p in summary.get("frontera", [])
    ]
    return _frame(FACT_ESCENARIOS, scenarios), _frame(FACT_FRONTERA, frontier)


def build_fact_calidad(data_dir: Path, report: GoldReport) -> pl.DataFrame:
    rows = []
    for path in sorted((data_dir / "silver" / "_quality").glob("*.json")):
        q = _read_json(path, report)
        if q is None or "table" not in q:
            continue
        rows.append(
            {
                "tabla": q["table"],
                "filas": q.get("rows"),
                "duplicados_eliminados": q.get("duplicates_removed"),
                "huecos": q.get("gaps"),
                "periodos_faltantes": q.get("missing_periods"),
                "hueco_mayor_horas": _num(q.get("largest_gap_hours")),
                "outliers": q.get("outliers"),
                "desde": q.get("first"),
                "hasta": q.get("last"),
            }
        )
    return _frame(FACT_CALIDAD, rows)


def build_dim_fecha(facts: Sequence[pl.DataFrame]) -> pl.DataFrame:
    dates = [f["fecha"] for f in facts if not f.is_empty()]
    if not dates:
        return DIM_FECHA.empty()
    all_dates = pl.concat(dates)
    start, end = all_dates.min(), all_dates.max()
    if not isinstance(start, date) or not isinstance(end, date):
        return DIM_FECHA.empty()
    calendar = pl.DataFrame({"fecha": pl.date_range(start, end, "1d", eager=True)})
    return calendar.with_columns(
        pl.col("fecha").dt.year().cast(pl.Int64).alias("anio"),
        pl.col("fecha").dt.quarter().cast(pl.Int64).alias("trimestre"),
        pl.col("fecha").dt.month().cast(pl.Int64).alias("mes"),
        pl.col("fecha")
        .dt.month()
        .map_elements(lambda m: _MONTHS[m - 1], pl.String)
        .alias("nombre_mes"),
        pl.col("fecha")
        .dt.weekday()
        .map_elements(lambda d: _WEEKDAYS[d - 1], pl.String)
        .alias("dia_semana"),
        pl.when(pl.col("fecha") < HOLDOUT_DATE)
        .then(pl.lit("desarrollo"))
        .otherwise(pl.lit("holdout"))
        .alias("periodo"),
    ).select(DIM_FECHA.schema.names())


def build_tables(data_dir: Path, report: GoldReport | None = None) -> dict[str, pl.DataFrame]:
    """Construye y valida todas las tablas en memoria, sin escribir nada."""
    report = report if report is not None else GoldReport()
    dim_modelo, fact_modelo = build_models(data_dir, report)
    escenarios, frontera = build_simulation(data_dir, report)
    tables = {
        "dim_simbolo": build_dim_simbolo(data_dir, report),
        "dim_configuracion": build_dim_configuracion(data_dir, report),
        "dim_modelo": dim_modelo,
        "fact_funding_diario": build_fact_funding(data_dir),
        "fact_mercado_diario": build_fact_mercado(data_dir),
        "fact_retorno_estrategia": build_fact_retorno(data_dir),
        "fact_desempeno": build_fact_desempeno(data_dir, report),
        "fact_gates": build_fact_gates(data_dir, report),
        "fact_metricas_modelo": fact_modelo,
        "fact_escenarios": escenarios,
        "fact_frontera": frontera,
        "fact_calidad": build_fact_calidad(data_dir, report),
    }
    tables["dim_fecha"] = build_dim_fecha([tables[t.name] for t in DATED_FACTS])
    tables = {t.name: tables[t.name] for t in TABLES}  # orden declarado
    validate(tables)
    report.rows = {name: frame.height for name, frame in tables.items()}
    return tables


# --- Validación --------------------------------------------------------------------------------


def validate(tables: Mapping[str, pl.DataFrame]) -> None:
    """Esquema declarado, claves únicas y no nulas, integridad referencial y holdout cerrado."""
    for table in TABLES:
        frame = tables[table.name]
        if frame.schema != table.schema:
            raise GoldValidationError(
                f"{table.name}: esquema {dict(frame.schema)} ≠ declarado {dict(table.schema)}"
            )
        keys = frame.select(table.key)
        if keys.null_count().sum_horizontal().item() > 0:
            raise GoldValidationError(f"{table.name}: clave {table.key} con nulos")
        if keys.is_duplicated().any():
            raise GoldValidationError(f"{table.name}: clave {table.key} duplicada")
        for fk in table.foreign_keys:
            parent = tables[fk.table][fk.column]
            orphans = frame.filter(~pl.col(fk.column).is_in(parent.implode()))
            if orphans.height:
                raise GoldValidationError(
                    f"{table.name}.{fk.column}: {orphans.height} filas sin {fk.table}"
                )
        if "fecha" in table.schema and frame.filter(pl.col("fecha") > LAST_DAY).height:
            raise GoldValidationError(
                f"{table.name}: tiene filas posteriores al {LAST_DAY} (devengo en el holdout)"
            )
    _validate_calendar(tables["dim_fecha"])
    retornos = tables["fact_retorno_estrategia"]["retorno"]
    if retornos.null_count() or retornos.is_nan().any():
        raise GoldValidationError("fact_retorno_estrategia: retorno nulo o NaN")


def _validate_calendar(calendar: pl.DataFrame) -> None:
    if calendar.is_empty():
        return
    first, last = calendar["fecha"].min(), calendar["fecha"].max()
    if isinstance(first, date) and isinstance(last, date):
        expected = (last - first).days + 1
        if calendar.height != expected:
            raise GoldValidationError(f"dim_fecha: {calendar.height} días ≠ {expected} (huecos)")


# --- Escritura ---------------------------------------------------------------------------------


def write_gold(tables: Mapping[str, pl.DataFrame], gold_dir: Path) -> None:
    """Parquet (fuente de verdad), DuckDB (SQL) y CSV con diccionario (Power BI)."""
    export = gold_dir / EXPORT_DIR
    export.mkdir(parents=True, exist_ok=True)
    db_path = gold_dir / DB_FILE
    db_path.unlink(missing_ok=True)
    with duckdb.connect(str(db_path)) as db:
        for name, frame in tables.items():
            parquet = gold_dir / f"{name}.parquet"
            frame.write_parquet(parquet)
            frame.write_csv(export / f"{name}.csv")
            db.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet(?)", [str(parquet)])  # noqa: S608 - nombres declarados en código
    (export / DICTIONARY_FILE).write_text(render_dictionary(), encoding="utf-8")


def build_gold(data_dir: Path) -> GoldReport:
    report = GoldReport()
    write_gold(build_tables(data_dir, report), data_dir / GOLD_DIR)
    return report


# --- Documentación generada --------------------------------------------------------------------


def render_dictionary(heading: str = "#") -> str:
    lines = [
        f"{heading} Diccionario de datos de la capa gold",
        "",
        "Generado por `uv run pq gold docs` desde `data_platform/gold.py`. No editar a mano.",
        "",
        "Todos los hechos con fecha terminan el 2024-06-29: es el último día cuyo devengo",
        "(hasta la liquidación y la valoración de las 00:00 del día siguiente) no toca el",
        "holdout, que empieza el 2024-07-01 y sigue cerrado hasta su evaluación única (PQ-50).",
        "Ver KE-014.",
        "",
    ]
    for table in TABLES:
        lines += [
            f"{heading}# `{table.name}` ({table.kind})",
            "",
            table.description,
            "",
            f"- **Grano:** {table.grain}",
            f"- **Clave:** {', '.join(f'`{k}`' for k in table.key)}",
        ]
        if table.foreign_keys:
            refs = ", ".join(f"`{fk.column}` → `{fk.table}`" for fk in table.foreign_keys)
            lines.append(f"- **Claves foráneas:** {refs}")
        lines += [f"- **Origen:** {'; '.join(f'`{s}`' for s in table.sources)}", ""]
        lines += ["| Columna | Tipo | Descripción |", "|---|---|---|"]
        lines += [f"| `{c.name}` | {c.dtype} | {c.description} |" for c in table.columns]
        lines.append("")
    return "\n".join(lines)


_LINEAGE_HEADER = """```mermaid
flowchart LR
    bronze[(bronze<br/>Data Vision)] --> silver[(silver<br/>validado, point-in-time)]
    silver --> research[[research<br/>backtest, modelo, simulación]]
"""


def render_lineage() -> str:
    """Una flecha por cada capa de la que la tabla lee directamente (primer tramo de la ruta)."""
    lines = [_LINEAGE_HEADER.rstrip("\n")]
    for table in TABLES:
        layers = {s.split("/", 1)[0] for s in table.sources}
        if table is DIM_FECHA:
            layers = {"silver", "research"}  # calendario de las fechas de todos los hechos
        lines += [f"    {layer} --> {table.name}" for layer in sorted(layers & _LAYERS)]
    lines.append("```")
    return "\n".join(lines)


_LAYERS = {"silver", "research"}


_DOCS_INTRO = """# Capa gold: modelo en estrella para BI

Capítulo 7.1 del Proyecto Integrador (PQ-46). La capa gold toma silver y los artefactos de research
y los organiza en **dimensiones** y **hechos** con claves de una sola columna, listos para Power BI
(PQ-47). Se reconstruye con un comando:

```bash
uv run pq gold build   # data/gold/*.parquet, gold.duckdb y export/*.csv
uv run pq gold docs    # regenera esta página desde las declaraciones del código
```

## Trazabilidad

Del dato crudo a la tabla de hechos. Bronze guarda el linaje de cada fila (`_source_file`,
`_source_sha256`); silver conserva `source_file`, y cada tabla gold declara sus fuentes.
"""

_DOCS_GUARANTEES = """
Los hechos sin dimensión de fecha (`fact_gates`, `fact_escenarios`, `fact_frontera`,
`fact_calidad`, `fact_desempeno`, `fact_metricas_modelo`) son resultados agregados de una
evaluación, no series temporales.

## Garantías (se verifican en cada construcción)

- El esquema de cada tabla coincide con el declarado.
- Claves sin nulos ni duplicados; toda clave foránea existe en su dimensión.
- Ningún hecho con fecha pasa del 2024-06-29: nada se devenga en el holdout (2024-07-01).
- `dim_fecha` es continua; los retornos no tienen nulos ni NaN.
- Los retornos vienen de valoraciones a las 00:00 UTC (si no, la construcción se detiene).
- Excepción declarada: `fact_calidad` describe la disponibilidad de toda la historia de silver.
- Lo que no existe en las fuentes queda nulo: no se rellena ni se inventa.
"""


def render_star() -> str:
    relations = [
        f"    {fk.table} ||--o{{ {t.name} : {fk.column}" for t in TABLES for fk in t.foreign_keys
    ]
    return "\n".join(["```mermaid", "erDiagram", *relations, "```"])


def render_docs_page() -> str:
    return "\n".join(
        [
            _DOCS_INTRO,
            render_lineage(),
            "",
            "## Modelo en estrella",
            "",
            render_star(),
            "",
            _DOCS_GUARANTEES,
            render_dictionary("##"),
        ]
    )
