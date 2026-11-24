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
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from prometheus_platform.data_platform.polymarket import resolution_asof
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
MAX_PAID = 0.999  # enmienda 1: el coste por acción nunca llega a 1
FULL_PAYOUT = 0.999  # un pago completo (los del AMM traen decimales casi 1)
MIDNIGHT_TOLERANCE = timedelta(minutes=1)  # los puntos diarios llegan a las 00:00:0x (PQ-92)
OTHER_STRATEGIES = ("carry_H2", "tendencia_T1")


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
    "finance": 0.04,
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
    markets: pl.DataFrame,
    category: Category,
    min_volume: float = MIN_VOLUME,
    cutoff: datetime = EVALUATION.cutoff,
) -> pl.DataFrame:
    """Reglas 1 a 4 de §3, con la enmienda 1.

    - Binarios con dos tokens y un pago publicado de dos valores sin nulos (dato válido).
    - Volumen ≥ ``min_volume``.
    - ``["0", "0"]`` se excluye **solo si esa resolución ya se conocía en el corte** (enmienda 1):
      si llegó después, en el corte el mercado seguía sin resolver y se valora al corte.
    - Un mercado sin ``closedTime`` se queda: se valora al corte.
    """
    return markets.filter(
        _eligible(min_volume, cutoff) & (pl.col("is_sports") == (category is Category.P2))
    )


def _valid_payout() -> pl.Expr:
    return (pl.col("payouts").list.len() == BINARY) & (
        pl.col("payouts").list.eval(pl.element().is_null()).list.any().not_()
    )


def _undefined_known(cutoff: datetime) -> pl.Expr:
    return (
        pl.col("excluded_reason").eq(UNDEFINED_PAYOUT).fill_null(False)
        & pl.col("resolution_known_at").is_not_null()
        & (pl.col("resolution_known_at") <= cutoff)
    )


def _eligible(min_volume: float, cutoff: datetime) -> pl.Expr:
    return (
        (pl.col("outcomes").list.len() == BINARY)
        & (pl.col("token_ids").list.len() == BINARY)
        & _valid_payout()
        & (pl.col("volume_usd").fill_null(0.0) >= min_volume)
        & _undefined_known(cutoff).not_()
    )


def exclusions(
    markets: pl.DataFrame, category: Category, cutoff: datetime = EVALUATION.cutoff
) -> dict[str, int]:
    """Cuántos mercados de la categoría quedan fuera y por qué (§3.4: se cuentan e informan)."""
    pool = markets.filter(pl.col("is_sports") == (category is Category.P2))
    binary = (pl.col("outcomes").list.len() == BINARY) & (pl.col("token_ids").list.len() == BINARY)
    return {
        "no_binarios": pool.filter(binary.not_()).height,
        "pago_no_valido": pool.filter(binary & _valid_payout().not_()).height,
        "volumen_menor_1000": pool.filter(
            binary & _valid_payout() & (pl.col("volume_usd").fill_null(0.0) < MIN_VOLUME)
        ).height,
        "pago_sin_definir_conocido_al_corte": pool.filter(
            binary
            & _valid_payout()
            & (pl.col("volume_usd").fill_null(0.0) >= MIN_VOLUME)
            & _undefined_known(cutoff)
        ).height,
    }


@dataclass
class Snapshots:
    """Instantáneas diarias del primer token conocidas en el corte, preparadas una sola vez.

    Solo puntos con precio válido (los rellenos ya son nulos en silver), con ``knowledge_time`` ≤
    el corte y a menos de ``MIDNIGHT_TOLERANCE`` de las 00:00 UTC (la instantánea diaria, §4).
    """

    times: dict[str, list[datetime]]
    prices: dict[str, list[float]]
    last_price: dict[str, float]
    off_midnight: int


def prepare(prices: pl.DataFrame, tokens: Sequence[str], cutoff: datetime) -> Snapshots:
    first = prices.filter(
        pl.col("token_id").is_in(list(tokens))
        & (pl.col("outcome_index") == 0)
        & pl.col("price").is_not_null()
        & (pl.col("knowledge_time") <= cutoff)
    ).select("token_id", "knowledge_time", "price")
    seconds = (
        pl.col("knowledge_time").dt.hour().cast(pl.Int32) * 3600
        + pl.col("knowledge_time").dt.minute().cast(pl.Int32) * 60
        + pl.col("knowledge_time").dt.second().cast(pl.Int32)
    )
    near = seconds <= MIDNIGHT_TOLERANCE.total_seconds()
    off = first.filter(near.not_()).height
    first = first.filter(near).sort("token_id", "knowledge_time")
    grouped = first.group_by("token_id", maintain_order=True).agg("knowledge_time", "price")
    times = dict(
        zip(grouped["token_id"].to_list(), grouped["knowledge_time"].to_list(), strict=True)
    )
    values = dict(zip(grouped["token_id"].to_list(), grouped["price"].to_list(), strict=True))
    return Snapshots(times, values, {t: v[-1] for t, v in values.items() if v}, off)


def _entry(  # noqa: PLR0913 - el mercado y la banda
    times: Sequence[datetime],
    prices: Sequence[float],
    band: Band | None,
    *,
    created: datetime | None,
    closed: datetime | None,
    period: Period,
) -> tuple[datetime, int, float] | None:
    """Primera instantánea en la banda (``band=None``: la primera instantánea, B1).

    La instantánea tiene que ser posterior a la creación y anterior al cierre (§4).
    """
    for at, price in zip(times, prices, strict=True):
        if created is not None and at < created:
            continue
        if closed is not None and at >= closed:
            return None  # el mercado ya estaba cerrado: no hay instantánea
        favorite, fav_price = (0, price) if price >= FAVORITE_MIN else (1, 1.0 - price)
        if band is None or band.contains(fav_price):
            if at < period.entry_start or at > period.entry_end:
                return None  # la primera entrada cae fuera del periodo: no pertenece a él
            return at, favorite, fav_price
    return None


def build_bets(  # noqa: PLR0913 - keyword-only salvo los datos, la banda y el periodo
    pool: pl.DataFrame,
    snapshots: Snapshots,
    band: Band | None,
    period: Period = EVALUATION,
    *,
    spread_in: float = SPREAD_IN,
    spread_out: float = SPREAD_OUT,
    with_fees: bool = True,
) -> list[Bet]:
    """Apuestas de un universo y una banda, sin usar nada posterior a ``period.cutoff``.

    ``pool`` es un universo (``universe``) y ``snapshots`` sale de ``prepare`` con el mismo corte.
    La comisión usa el precio de ejecución (instantánea + diferencial), con tope de 0,999 para
    que el coste por acción nunca llegue a 1 (enmienda 1).
    """
    bets = []
    for m in resolution_asof(pool, period.cutoff).iter_rows(named=True):
        token0 = m["token_ids"][0]
        times = snapshots.times.get(token0)
        if not times:
            continue
        entry = _entry(
            times,
            snapshots.prices[token0],
            band,
            created=m["created_at"],
            closed=m["closed_time"],
            period=period,
        )
        if entry is None:
            continue
        at, favorite, fav_price = entry
        paid = min(fav_price + spread_in, MAX_PAID)
        fee = fee_rate(m["fee_type"], m["tags"]) * paid * (1 - paid) if with_fees else 0.0
        if m["resolved_asof"]:
            payout, realized, resolved = (
                float(m["payouts"][favorite]),
                m["resolution_known_at"],
                True,
            )
        else:
            p0 = snapshots.last_price[token0]
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
    hit_rate: float  # resueltas con pago completo (≥ 0,999)
    partial_payouts: int  # resueltas con pago parcial (ni 0 ni 1)
    mean_price: float  # calibración, sobre las resueltas: precio medio del favorito
    mean_payout: float  # calibración, sobre las mismas: pago medio


def bet_stats(bets: Sequence[Bet]) -> BetStats:
    if not bets:
        nan = math.nan
        return BetStats(0, 0, 0, nan, nan, nan, nan, nan, 0, nan, nan)
    r = np.array([b.pnl for b in bets])
    _, group = np.unique(np.array([b.event_id for b in bets]), return_inverse=True)
    n, g = len(r), int(group.max()) + 1
    mean = float(r.mean())
    sums = np.bincount(group, weights=r - mean)
    sizes = np.bincount(group)
    # Error estándar de la media agrupado por evento (sándwich de clústeres, CR1: G/(G-1)).
    se = math.sqrt(float(np.sum(sums**2))) / n * math.sqrt(g / (g - 1)) if g > 1 else math.nan
    event_means = np.bincount(group, weights=r) / sizes
    resolved = [b for b in bets if b.resolved]
    full = [b.payout >= FULL_PAYOUT for b in resolved]
    partial = sum(1 for b in resolved if 1 - FULL_PAYOUT < b.payout < FULL_PAYOUT)
    return BetStats(
        n_bets=n,
        n_events=g,
        n_unresolved=n - len(resolved),
        mean_return=mean,
        t_cluster=mean / se if se and se > 0 else math.nan,
        event_weighted_return=float(event_means.mean()),
        dollar_year_return=float(r.sum() / sum(b.years_held for b in bets)),
        hit_rate=float(np.mean(full)) if resolved else math.nan,
        partial_payouts=partial,
        mean_price=float(np.mean([b.price for b in resolved])) if resolved else math.nan,
        mean_payout=float(np.mean([b.payout for b in resolved])) if resolved else math.nan,
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


def _longest_losing_streak(pnl: np.ndarray) -> int:
    longest = current = 0
    for value in pnl:
        current = current + 1 if value < 0 else (current if value == 0 else 0)
        longest = max(longest, current)
    return longest


def series_stats(pnl: np.ndarray) -> dict[str, float]:
    """Estadísticos de la serie diaria. La curtosis es la **bruta** (la que espera el DSR)."""
    std = float(np.std(pnl, ddof=1)) if pnl.size > 1 else 0.0
    sharpe_d = sharpe_daily(pnl)
    centered = pnl - pnl.mean()
    m2 = float(np.mean(centered**2))
    skew = float(np.mean(centered**3) / m2**1.5) if m2 > 0 else 0.0
    kurt = float(np.mean(centered**4) / m2**2) if m2 > 0 else 3.0
    cumulative = np.cumsum(pnl)
    drawdown = (
        float(np.max(np.maximum.accumulate(np.concatenate([[0.0], cumulative]))[1:] - cumulative))
        if pnl.size
        else 0.0
    )
    return {
        "sharpe_daily": sharpe_d,
        "sharpe": sharpe_d * math.sqrt(DAYS_PER_YEAR),
        "skew": skew,
        "kurtosis": kurt,
        "std_daily": std,
        "pnl_total": float(pnl.sum()),
        "peor_dia": float(pnl.min()) if pnl.size else 0.0,
        "max_caida_usd": drawdown,
        "peor_racha_dias": float(_longest_losing_streak(pnl)),
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
    correlations: dict[str, dict[str, Any]] = field(default_factory=dict)
    excluded: dict[str, int] = field(default_factory=dict)
    off_midnight: int = 0

    @property
    def principal(self) -> ConfigResult:
        return self.configs[config_name(self.category, PRINCIPAL_BAND)]

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)


def config_name(category: Category, band: str) -> str:
    return f"{'P1' if category is Category.P1 else 'P2'}-{band}"


def run_config(
    pool: pl.DataFrame, snapshots: Snapshots, category: Category, band: Band
) -> ConfigResult:
    """Una configuración de §5, **sin registrar**: ``evaluate`` registra las 6 juntas."""
    bets = build_bets(pool, snapshots, band, EVALUATION)
    daily = daily_pnl(bets, EVALUATION)
    return ConfigResult(
        config_name(category, band.name),
        category,
        band,
        bets,
        bet_stats(bets),
        daily,
        series_stats(daily["pnl"].to_numpy()),
    )


def _register(result: ConfigResult, registry: ExperimentRegistry) -> None:
    st = result.stats
    metrics = {
        **result.series,
        "apuestas": float(st.n_bets),
        "eventos": float(st.n_events),
        "sin_resolver": float(st.n_unresolved),
        "retorno_por_apuesta": st.mean_return,
        "t_agrupado": st.t_cluster,
        "retorno_por_evento": st.event_weighted_return,
        "retorno_dolar_ano": st.dollar_year_return,
    }
    registry.log_trial(
        TrialRecord(
            hypothesis="P1" if result.category is Category.P1 else "P2",
            name=result.name,
            params={
                "banda": f"[{result.band.low}; {result.band.high})",
                "categoria": str(result.category),
            },
            metrics={
                k: v for k, v in metrics.items() if math.isfinite(v)
            },  # el .jsonl no admite NaN
            tags={"period": EVALUATION.name, "costs": "principal"},
        )
    )


def evaluate(
    markets: pl.DataFrame,
    prices: pl.DataFrame,
    registry: ExperimentRegistry,
    other_strategies: Mapping[str, pl.DataFrame] | None = None,
) -> dict[Category, PolymarketEvaluation]:
    """Las 6 configuraciones de §5 y la evaluación de P1 y P2.

    Orden pensado para no dejar nunca filas a medias en el registro: primero se calculan las 6
    configuraciones (sin mirarlas); si algo falla, no se ha registrado nada. Después se registran
    las 6 juntas (suman a N) y solo entonces se calculan los gates con el N resultante.
    """
    familia = getattr(registry, "familia", FAMILY)
    if familia != FAMILY:
        raise ValueError(f"El registro es de la familia {familia!r}, no de {FAMILY!r}")
    candidates = markets.filter(_eligible(MIN_VOLUME, EVALUATION.cutoff))
    snapshots = prepare(
        prices, [t[0] for t in candidates["token_ids"].to_list()], EVALUATION.cutoff
    )
    pools = {c: universe(markets, c) for c in Category}
    results = {
        c: {band.name: run_config(pools[c], snapshots, c, band) for band in BANDS} for c in Category
    }
    for c in Category:
        for result in results[c].values():
            _register(result, registry)
    trials = [t for t in registry.trials() if "sharpe_daily" in t.metrics]
    n_trials = max(len(registry.trials()), len(BANDS) * len(Category))
    sharpes = np.array([t.metrics["sharpe_daily"] for t in trials])
    var_sharpe = float(np.var(sharpes, ddof=1)) if sharpes.size > 1 else 0.0
    return {
        c: _evaluate(
            c,
            results[c],
            markets,
            pools[c],
            snapshots,
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
    pool: pl.DataFrame,
    snapshots: Snapshots,
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
    b1 = bet_stats(build_bets(pool, snapshots, None))
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
        "entrada_0": _summary(build_bets(pool, snapshots, band, spread_in=0.0)),
        "entrada_0.02": _summary(build_bets(pool, snapshots, band, spread_in=0.02)),
        "salida_0": _summary(build_bets(pool, snapshots, band, spread_out=0.0)),
        "sin_comision": _summary(build_bets(pool, snapshots, band, with_fees=False)),
        "volumen_10000": _summary(
            build_bets(universe(markets, category, SENSITIVITY_VOLUME), snapshots, band)
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
            name: correlation_report(principal.daily, other_strategies.get(name))
            for name in OTHER_STRATEGIES
        },
        excluded=exclusions(markets, category),
        off_midnight=snapshots.off_midnight,
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


def correlation_report(pnl: pl.DataFrame, other: pl.DataFrame | None) -> dict[str, Any]:
    """La correlación con su ventana; si falta la serie, lo dice en vez de omitirla."""
    if other is None:
        return {"correlacion": None, "motivo": "serie no disponible en data/research"}
    common = pnl.join(other.with_columns(pl.col("date").cast(pl.Date)), on="date", how="inner")
    return {
        "correlacion": correlation(pnl, other),
        "dias_comunes": common.height,
        "desde": str(common["date"].min()) if common.height else None,
        "hasta": str(common["date"].max()) if common.height else None,
    }


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
    for label, sub in zip(OTHER_STRATEGIES, ("carry/H2", "trend/T1"), strict=True):
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
        "excluidos_3_4": evaluation.excluded,
        "puntos_fuera_de_medianoche": evaluation.off_midnight,
        "nota_pbo": "con 3 bandas, el PBO esperado sin habilidad es ~2/3 (el rango mediano cuenta"
        " como sobreajuste): G2 es exigente",
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
