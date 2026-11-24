"""Evaluación de la estrategia de Polymarket: sesgo favorito-longshot (PQ-93).

Ejecuta exactamente lo pre-registrado en ``docs/estrategias/04-polymarket/pre-registro.md``:

1. **Universo** (§3): mercados binarios, con libro, volumen ≥ 1.000 USD y pago definido; fuera
   de deportes (P1) o de deportes (P2).
2. **Entrada** (§4): instantánea diaria (el punto diario del CLOB, ``knowledge_time``) mientras el
   mercado está abierto; el favorito es el resultado con precio ≥ 0,5 (el segundo vale 1 - *p*);
   se entra en la **primera** instantánea con el favorito dentro de la banda, una vez por mercado.
3. **Costes** (§6): +0,01 al entrar y comisión taker ``tasa x p x (1 - p)`` por acción con la
   tasa de la categoría (0,07 si es desconocida). 1 USD por apuesta.
4. **Pago** (§4): el ``outcomePrices`` publicado del favorito, en ``closedTime``. Una apuesta que
   no se resolvió antes del corte del periodo (§7) se valora al último precio válido menos 0,01.
5. **Ensayos** (§5): 3 bandas x 2 categorías = 6, familia ``polymarket``. Cada uno se registra
   **antes** de evaluarse.
6. **Gates** (§8) sobre la banda [0,80; 0,95) de P1: DSR, PBO (CSCV de 16 bloques entre las 3
   bandas), t agrupado por evento, retorno por apuesta y por dólar-año frente a B1 y B2, y G5
   (retorno ponderado por evento > 0).

**Point-in-time.** Las entradas solo usan precios con ``knowledge_time`` ≤ la instantánea; el pago
solo se usa si ``resolution_known_at`` ≤ el corte (``resolution_asof``); la valoración al corte
usa ``prices_asof``. Nada posterior al corte de evaluación entra en el cálculo: el holdout queda
intacto.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from prometheus_platform.data_platform.polymarket import prices_asof, resolution_asof
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.carry_evaluation import (
    DSR_GATE,
    PBO_GATE,
    STABLECOIN_HURDLE,
    T_GATE,
    ExperimentRegistry,
    Gate,
    TrialRecord,
)
from prometheus_platform.research.validation import (
    DAYS_PER_YEAR,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe_daily,
)

FAMILY = "polymarket"
MIN_VOLUME = 1000.0  # §3.2
SENSITIVITY_VOLUME = 10_000.0  # §3, solo se informa
SPREAD_IN = 0.01  # §6
SPREAD_OUT = 0.01  # §6, solo al valorar en el corte
UNKNOWN_FEE = 0.07  # §6
CSCV_BLOCKS = 16  # §8
PRINCIPAL_BAND = "B80"
BINARY = 2
FAVORITE_MIN = 0.5
UNDEFINED_PAYOUT = "pago sin definir (todos 0)"  # excluded_reason del silver (PQ-92)


class Category(StrEnum):
    P1 = "fuera-de-deportes"
    P2 = "deportes"


@dataclass(frozen=True)
class Band:
    name: str
    low: float
    high: float  # abierto: [low, high)

    def contains(self, price: float) -> bool:
        return self.low <= price < self.high


BANDS = (Band("B70", 0.70, 0.85), Band("B80", 0.80, 0.95), Band("B90", 0.90, 0.98))  # §5


@dataclass(frozen=True)
class Period:
    name: str
    entry_start: datetime
    entry_end: datetime  # incluido
    cutoff: datetime  # valoración de lo no resuelto


EVALUATION = Period(
    "evaluacion",
    datetime(2023, 1, 1, tzinfo=UTC),
    datetime(2025, 6, 30, 23, 59, 59, tzinfo=UTC),
    datetime(2025, 6, 30, 23, 59, 59, tzinfo=UTC),
)  # §7
HOLDOUT = Period(
    "holdout",
    datetime(2025, 7, 1, tzinfo=UTC),
    datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
    datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC),
)  # §7: no se usa en esta evaluación

# §6: tasas de compliance/polymarket.md §2. Las claves son prefijos de ``feeType`` y etiquetas.
FEE_RATES: Mapping[str, float] = {
    "politics": 0.04,
    "elections": 0.04,
    "finance": 0.04,
    "economy": 0.04,
    "business": 0.04,
    "tech": 0.04,
    "sports": 0.05,
    "crypto": 0.07,
    "geopolitics": 0.0,
}


def fee_rate(fee_type: str | None, tags: Sequence[str]) -> float:
    """Tasa taker de la categoría (§6).

    Primero ``feeType`` (``politics_fees`` → ``politics``). Si no está, las etiquetas; si varias
    coinciden se toma la **más alta** (pesimista). Sin coincidencias: 0,07.
    """
    if fee_type:
        key = fee_type.lower().removesuffix("_fees")
        if key in FEE_RATES:
            return FEE_RATES[key]
    matches = [FEE_RATES[t.lower()] for t in tags if t.lower() in FEE_RATES]
    return max(matches) if matches else UNKNOWN_FEE


# --- Apuestas ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bet:
    market_id: str
    event_id: str
    entry_time: datetime
    favorite: int  # índice del resultado comprado
    price: float  # precio del favorito en la instantánea
    cost_per_share: float  # precio pagado + comisión
    payout: float  # por acción
    realized_at: datetime
    resolved: bool  # False: valorada al corte

    @property
    def shares(self) -> float:
        return 1.0 / self.cost_per_share

    @property
    def pnl(self) -> float:
        """PnL de 1 USD apostado."""
        return self.shares * self.payout - 1.0

    @property
    def years_held(self) -> float:
        days = max((self.realized_at - self.entry_time).total_seconds() / 86_400, 1.0)
        return days / DAYS_PER_YEAR


def universe(
    markets: pl.DataFrame, category: Category, min_volume: float = MIN_VOLUME
) -> pl.DataFrame:
    """Reglas 1 a 4 de §3.

    Solo se excluye el pago sin definir (``["0", "0"]``, regla 4). Un mercado sin ``closedTime``
    se queda: su resolución no es conocible y la apuesta se valora al corte (§4).
    """
    sports = category is Category.P2
    return markets.filter(
        (pl.col("outcomes").list.len() == BINARY)
        & (pl.col("token_ids").list.len() == BINARY)
        & (pl.col("volume_usd") >= min_volume)
        & pl.col("excluded_reason").ne(UNDEFINED_PAYOUT).fill_null(True)
        & (pl.col("is_sports") == sports)
    )


def _entry(
    snapshots: pl.DataFrame, band: Band | None, closed: datetime | None, period: Period
) -> tuple[datetime, int, float] | None:
    """Primera instantánea en la banda (``band=None``: la primera instantánea, B1).

    ``snapshots`` son los puntos válidos del primer token, ordenados por ``knowledge_time``.
    """
    for at, price in snapshots.select("knowledge_time", "price").iter_rows():
        if closed is not None and at >= closed:
            return None  # el mercado ya estaba cerrado: no hay instantánea
        favorite, fav_price = (0, price) if price >= FAVORITE_MIN else (1, 1.0 - price)
        if band is None or band.contains(fav_price):
            if at < period.entry_start or at > period.entry_end:
                return None  # la primera entrada cae fuera del periodo: no pertenece a él
            return at, favorite, fav_price
    return None


def build_bets(  # noqa: PLR0913 - keyword-only salvo los datos, la banda y el periodo
    markets: pl.DataFrame,
    prices: pl.DataFrame,
    band: Band | None,
    period: Period = EVALUATION,
    *,
    spread_in: float = SPREAD_IN,
    spread_out: float = SPREAD_OUT,
    with_fees: bool = True,
) -> list[Bet]:
    """Apuestas de un universo y una banda, sin usar nada posterior a ``period.cutoff``."""
    known = prices.filter(pl.col("knowledge_time") <= period.cutoff)
    first_token = known.filter((pl.col("outcome_index") == 0) & pl.col("price").is_not_null()).sort(
        "token_id", "knowledge_time"
    )
    by_token = {key[0]: frame for key, frame in first_token.group_by("token_id")}
    asof = resolution_asof(markets, period.cutoff)
    last = prices_asof(first_token, period.cutoff)
    last_price = dict(zip(last["token_id"].to_list(), last["price"].to_list(), strict=True))

    bets = []
    for m in asof.iter_rows(named=True):
        token0 = m["token_ids"][0]
        snapshots = by_token.get(token0)
        if snapshots is None:
            continue
        entry = _entry(snapshots, band, m["closed_time"], period)
        if entry is None:
            continue
        at, favorite, fav_price = entry
        paid = min(fav_price + spread_in, 0.999)
        fee = fee_rate(m["fee_type"], m["tags"]) * paid * (1 - paid) if with_fees else 0.0
        if m["resolved_asof"] and m["payouts"] is not None:
            payout, realized, resolved = (
                float(m["payouts"][favorite]),
                m["resolution_known_at"],
                True,
            )
        else:
            p0 = last_price.get(token0, fav_price if favorite == 0 else 1 - fav_price)
            mark = p0 if favorite == 0 else 1.0 - p0
            payout, realized, resolved = max(mark - spread_out, 0.0), period.cutoff, False
        bets.append(
            Bet(
                market_id=m["market_id"],
                event_id=m["event_id"] or m["market_id"],
                entry_time=at,
                favorite=favorite,
                price=fav_price,
                cost_per_share=paid + fee,
                payout=payout,
                realized_at=realized,
                resolved=resolved,
            )
        )
    return bets


# --- Métricas ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BetStats:
    n_bets: int
    n_events: int
    n_unresolved: int
    mean_return: float  # por apuesta, ponderación igual por mercado
    t_cluster: float  # t del retorno medio, error agrupado por evento
    event_weighted_return: float  # un voto por evento padre
    dollar_year_return: float  # PnL / suma de dólares x años
    hit_rate: float
    mean_price: float  # calibración: precio medio del favorito
    mean_payout: float  # calibración: pago medio


def bet_stats(bets: Sequence[Bet]) -> BetStats:
    if not bets:
        nan = math.nan
        return BetStats(0, 0, 0, nan, nan, nan, nan, nan, nan, nan)
    r = np.array([b.pnl for b in bets])
    events = np.array([b.event_id for b in bets])
    mean = float(r.mean())
    resolved = [b.payout for b in bets if b.resolved]
    groups = {e: r[events == e] for e in np.unique(events)}
    n, g = len(r), len(groups)
    # Error estándar de la media agrupado por evento (sándwich de clústeres, corrección G/(G-1)).
    meat = sum(float(np.sum(v - mean)) ** 2 for v in groups.values())
    se = math.sqrt(meat) / n * math.sqrt(g / (g - 1)) if g > 1 else math.nan
    return BetStats(
        n_bets=n,
        n_events=g,
        n_unresolved=sum(not b.resolved for b in bets),
        mean_return=mean,
        t_cluster=mean / se if se and se > 0 else math.nan,
        event_weighted_return=float(np.mean([v.mean() for v in groups.values()])),
        dollar_year_return=float(r.sum() / sum(b.years_held for b in bets)),
        hit_rate=float(np.mean([p >= FAVORITE_MIN for p in resolved])) if resolved else math.nan,
        mean_price=float(np.mean([b.price for b in bets])),
        mean_payout=float(np.mean(resolved)) if resolved else math.nan,
    )


def daily_pnl(bets: Sequence[Bet], period: Period = EVALUATION) -> pl.DataFrame:
    """PnL diario (USD con 1 USD por apuesta), en el día de la resolución o del corte (§8).

    Incluye todos los días del periodo, también los que no tienen ninguna resolución.
    """
    days = pl.date_range(period.entry_start.date(), period.cutoff.date(), "1d", eager=True)
    if not bets:
        return pl.DataFrame({"date": days, "pnl": [0.0] * len(days)})
    realized = (
        pl.DataFrame({"date": [b.realized_at.date() for b in bets], "pnl": [b.pnl for b in bets]})
        .group_by("date")
        .agg(pl.col("pnl").sum())
    )
    return (
        pl.DataFrame({"date": days})
        .join(realized, on="date", how="left")
        .with_columns(pl.col("pnl").fill_null(0.0))
        .sort("date")
    )


def series_stats(pnl: np.ndarray) -> dict[str, float]:
    std = float(np.std(pnl, ddof=1)) if pnl.size > 1 else 0.0
    sharpe_d = sharpe_daily(pnl)
    centered = pnl - pnl.mean()
    m2 = float(np.mean(centered**2))
    skew = float(np.mean(centered**3) / m2**1.5) if m2 > 0 else 0.0
    kurt = float(np.mean(centered**4) / m2**2) if m2 > 0 else 3.0
    return {
        "sharpe_daily": sharpe_d,
        "sharpe": sharpe_d * math.sqrt(DAYS_PER_YEAR),
        "skew": skew,
        "kurtosis": kurt,
        "std_daily": std,
        "pnl_total": float(pnl.sum()),
        "peor_dia": float(pnl.min()) if pnl.size else 0.0,
    }


# --- Evaluación -------------------------------------------------------------------------------


@dataclass
class ConfigResult:
    name: str
    category: Category
    band: Band
    bets: list[Bet]
    stats: BetStats
    daily: pl.DataFrame
    series: dict[str, float]


@dataclass
class PolymarketEvaluation:
    category: Category
    configs: dict[str, ConfigResult]
    benchmark_b1: BetStats
    pbo: float
    dsr: float
    n_trials: int
    var_sharpe: float
    gates: list[Gate] = field(default_factory=list)
    sensitivity: dict[str, dict[str, float]] = field(default_factory=dict)
    correlations: dict[str, float | None] = field(default_factory=dict)

    @property
    def principal(self) -> ConfigResult:
        return self.configs[config_name(self.category, PRINCIPAL_BAND)]

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)


def config_name(category: Category, band: str) -> str:
    return f"{'P1' if category is Category.P1 else 'P2'}-{band}"


def run_and_register(  # noqa: PLR0913 - cada argumento es una dimensión del ensayo
    markets: pl.DataFrame,
    prices: pl.DataFrame,
    category: Category,
    band: Band,
    registry: ExperimentRegistry,
    *,
    period: Period = EVALUATION,
) -> ConfigResult:
    """Una configuración de §5, **registrada** (suma a N) antes de que nadie la mire."""
    familia = getattr(registry, "familia", FAMILY)
    if familia != FAMILY:
        raise ValueError(f"El registro es de la familia {familia!r}, no de {FAMILY!r}")
    if period is not EVALUATION:
        raise ValueError("Esta evaluación solo usa el periodo de evaluación; el holdout es aparte")
    bets = build_bets(universe(markets, category), prices, band, period)
    stats = bet_stats(bets)
    daily = daily_pnl(bets, period)
    series = series_stats(daily["pnl"].to_numpy())
    name = config_name(category, band.name)
    registry.log_trial(
        TrialRecord(
            hypothesis="P1" if category is Category.P1 else "P2",
            name=name,
            params={"banda": f"[{band.low}; {band.high})", "categoria": str(category)},
            metrics={
                **series,
                "apuestas": float(stats.n_bets),
                "eventos": float(stats.n_events),
                "sin_resolver": float(stats.n_unresolved),
                "retorno_por_apuesta": stats.mean_return,
                "t_agrupado": stats.t_cluster,
                "retorno_por_evento": stats.event_weighted_return,
                "retorno_dolar_ano": stats.dollar_year_return,
            },
            tags={"period": period.name, "costs": "principal"},
        )
    )
    return ConfigResult(name, category, band, bets, stats, daily, series)


def evaluate(
    markets: pl.DataFrame,
    prices: pl.DataFrame,
    registry: ExperimentRegistry,
    other_strategies: Mapping[str, pl.DataFrame] | None = None,
) -> dict[Category, PolymarketEvaluation]:
    """Registra las 6 configuraciones y evalúa P1 y P2 con el N resultante."""
    results = {
        c: {band.name: run_and_register(markets, prices, c, band, registry) for band in BANDS}
        for c in Category
    }
    trials = [t for t in registry.trials() if "sharpe_daily" in t.metrics]
    n_trials = max(len(registry.trials()), len(BANDS) * len(Category))
    sharpes = np.array([t.metrics["sharpe_daily"] for t in trials])
    var_sharpe = float(np.var(sharpes, ddof=1)) if sharpes.size > 1 else 0.0
    return {
        c: _evaluate(
            c,
            results[c],
            markets,
            prices,
            n_trials=n_trials,
            var_sharpe=var_sharpe,
            other_strategies=other_strategies or {},
        )
        for c in Category
    }


def _evaluate(  # noqa: PLR0913 - keyword-only salvo los datos de la hipótesis
    category: Category,
    by_band: dict[str, ConfigResult],
    markets: pl.DataFrame,
    prices: pl.DataFrame,
    *,
    n_trials: int,
    var_sharpe: float,
    other_strategies: Mapping[str, pl.DataFrame],
) -> PolymarketEvaluation:
    configs = {r.name: r for r in by_band.values()}
    principal = by_band[PRINCIPAL_BAND]
    matrix = np.column_stack([by_band[b.name].daily["pnl"].to_numpy() for b in BANDS])
    pbo = probability_of_backtest_overfitting(matrix, n_blocks=CSCV_BLOCKS)
    s = principal.series
    dsr = deflated_sharpe_ratio(
        s["sharpe_daily"],
        n_obs=principal.daily.height,
        skew=s["skew"],
        kurtosis=s["kurtosis"],
        n_trials=n_trials,
        var_sharpe=var_sharpe,
    )
    pool = universe(markets, category)
    b1 = bet_stats(build_bets(pool, prices, None))
    st = principal.stats
    gates = [
        Gate("G1", f"Deflated Sharpe > {DSR_GATE}", dsr, dsr > DSR_GATE),
        Gate("G2", f"PBO < {PBO_GATE}", pbo, pbo < PBO_GATE),
        Gate("G3", f"t agrupado por evento > {T_GATE}", st.t_cluster, st.t_cluster > T_GATE),
        Gate(
            "G4",
            "retorno por apuesta > 0, > B1, y por dólar-año > 4 %",
            st.mean_return,
            st.mean_return > 0
            and st.mean_return > b1.mean_return
            and st.dollar_year_return > STABLECOIN_HURDLE,
        ),
        Gate(
            "G5",
            "retorno ponderado por evento > 0",
            st.event_weighted_return,
            st.event_weighted_return > 0,
        ),
    ]
    band = principal.band
    sensitivity = {
        "sin_diferencial": _summary(build_bets(pool, prices, band, spread_in=0.0, spread_out=0.0)),
        "diferencial_0.02": _summary(build_bets(pool, prices, band, spread_in=0.02)),
        "sin_comision": _summary(build_bets(pool, prices, band, with_fees=False)),
        "volumen_10000": _summary(
            build_bets(universe(markets, category, SENSITIVITY_VOLUME), prices, band)
        ),
    }
    return PolymarketEvaluation(
        category=category,
        configs=configs,
        benchmark_b1=b1,
        pbo=pbo,
        dsr=dsr,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
        gates=gates,
        sensitivity=sensitivity,
        correlations={
            name: correlation(principal.daily, other) for name, other in other_strategies.items()
        },
    )


def _summary(bets: Sequence[Bet]) -> dict[str, float]:
    st = bet_stats(bets)
    return {
        "apuestas": float(st.n_bets),
        "retorno_por_apuesta": st.mean_return,
        "retorno_por_evento": st.event_weighted_return,
        "retorno_dolar_ano": st.dollar_year_return,
        "t_agrupado": st.t_cluster,
    }


def correlation(pnl: pl.DataFrame, other: pl.DataFrame, min_days: int = 60) -> float | None:
    """Correlación diaria en los días comunes; ``other`` tiene ``date`` y ``ret``."""
    joined = pnl.join(
        other.with_columns(pl.col("date").cast(pl.Date)), on="date", how="inner"
    ).drop_nulls()
    if joined.height < min_days:
        return None
    a, b = joined["pnl"].to_numpy(), joined["ret"].to_numpy()
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def entry_dates(bets: Sequence[Bet]) -> tuple[date | None, date | None]:
    if not bets:
        return None, None
    days = [b.entry_time.date() for b in bets]
    return min(days), max(days)


# --- Entrada y salida -------------------------------------------------------------------------


def load_silver(silver_root: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Mercados y precios diarios del silver de PQ-92."""
    base = silver_root / "polymarket"
    markets, prices = base / "markets.parquet", base / "prices_1440.parquet"
    for path in (markets, prices):
        if not path.exists():
            raise FileNotFoundError(
                f"Falta {path}: ejecuta la ingesta de PQ-92 (pq polymarket ...)"
            )
    return pl.read_parquet(markets), pl.read_parquet(prices)


def _as_date(column: pl.Series) -> pl.Series:
    """Fechas guardadas como texto ISO o como fecha-hora: siempre ``Date``."""
    if column.dtype == pl.String:
        column = column.str.to_datetime(time_zone="UTC")
    return column.dt.date() if column.dtype != pl.Date else column


def load_other_strategies(research_dir: Path) -> dict[str, pl.DataFrame]:
    """Retornos diarios de la configuración elegida del carry H2 y de la tendencia T1.

    Solo el desarrollo: la última fila de esas series puede ser ya una valoración del holdout
    (2024-07-01, KE-014), así que se corta antes de ``HOLDOUT_START``.
    """
    out: dict[str, pl.DataFrame] = {}
    for label, sub in (("carry_H2", "carry/H2"), ("tendencia_T1", "trend/T1")):
        summary_path = research_dir / sub / "summary.json"
        daily_path = research_dir / sub / "daily_returns.parquet"
        if not (summary_path.exists() and daily_path.exists()):
            continue
        selected = json.loads(summary_path.read_text())["selected"]
        frame = pl.read_parquet(daily_path)
        if selected not in frame.columns:
            continue
        out[label] = (
            pl.DataFrame({"date": _as_date(frame["date"]), "ret": frame[selected]})
            .filter(pl.col("date") < HOLDOUT_START.date())
            .drop_nulls()
        )
    return out


def summary(evaluation: PolymarketEvaluation) -> dict[str, Any]:
    first, last = entry_dates(evaluation.principal.bets)
    return {
        "categoria": str(evaluation.category),
        "periodo": {
            "entradas": [str(EVALUATION.entry_start.date()), str(EVALUATION.entry_end.date())],
            "corte": EVALUATION.cutoff.isoformat(),
            "primera_entrada": str(first),
            "ultima_entrada": str(last),
        },
        "configuraciones": {
            name: {"banda": [r.band.low, r.band.high], **asdict(r.stats), **r.series}
            for name, r in evaluation.configs.items()
        },
        "principal": evaluation.principal.name,
        "benchmark_B1": asdict(evaluation.benchmark_b1),
        "pbo": evaluation.pbo,
        "dsr": evaluation.dsr,
        "n_trials": evaluation.n_trials,
        "var_sharpe_daily": evaluation.var_sharpe,
        "gates": [asdict(g) for g in evaluation.gates],
        "passed": evaluation.passed,
        "sensibilidad": evaluation.sensitivity,
        "correlaciones": evaluation.correlations,
    }


def write_outputs(evaluation: PolymarketEvaluation, out_dir: Path) -> Path:
    """``summary.json``, el PnL diario de las 3 bandas y las apuestas de la principal."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.json"
    path.write_text(json.dumps(summary(evaluation), indent=2, ensure_ascii=False, default=str))
    daily = pl.DataFrame({"date": evaluation.principal.daily["date"]}).with_columns(
        [r.daily["pnl"].alias(name) for name, r in evaluation.configs.items()]
    )
    daily.write_parquet(out_dir / "daily_pnl.parquet")
    pl.DataFrame([asdict(b) | {"pnl": b.pnl} for b in evaluation.principal.bets]).write_parquet(
        out_dir / "bets.parquet"
    )
    return path
