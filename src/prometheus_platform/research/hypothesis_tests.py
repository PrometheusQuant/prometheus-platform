"""Validación estadística del impacto de la optimización (PQ-48, Proyecto Integrador 7.4).

Implementa el plan fijado **antes** de calcular en
``docs/investigacion/2026-11-06-validacion-estadistica.md``:

- **HE1:** la política optimizada rinde más que B1 (t pareada con HAC, Wilcoxon, bootstrap).
- **HE2:** rinde más que el hurdle de la stablecoin (t con HAC, bootstrap).
- **HE3:** las 10 políticas no son equivalentes (ANOVA de referencia, Friedman y post-hoc con Holm).

Las series diarias tienen colas pesadas y autocorrelación: por eso los errores estándar son de
Newey-West y el bootstrap es de bloques circulares. Solo usa el periodo de desarrollo.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy import stats

from prometheus_platform.research.backtest import CarryConfig
from prometheus_platform.research.carry_evaluation import (
    HYPOTHESES,
    STABLECOIN_HURDLE,
    load_symbol,
    run_config,
)
from prometheus_platform.research.validation import performance

FloatArray = NDArray[np.float64]
ALPHA = 0.05
BOOTSTRAP_REPLICAS = 10_000
BLOCK_DAYS = 21  # duración de los regímenes del cap. 6
SEED = 2026
LJUNG_BOX_LAGS = 10
DAYS_PER_YEAR = 365
BENCHMARK = "B1-siempre-activo"


@dataclass(frozen=True)
class MeanTest:
    """Prueba unilateral (H1: media > ``mu0``) con HAC y bootstrap, más sus diagnósticos."""

    hypothesis: str
    n: int
    mean_daily: float
    mean_annualized: float
    mu0_daily: float
    t_hac: float
    p_hac: float
    hac_lag: int
    ci95_annualized: tuple[float, float]
    wilcoxon_p: float | None
    cohens_d: float
    reject_h0: bool


@dataclass(frozen=True)
class Diagnostics:
    jarque_bera_p: float
    ljung_box_q: float
    ljung_box_p: float
    skew: float
    excess_kurtosis: float


@dataclass(frozen=True)
class GroupTest:
    anova_f: float
    anova_p: float
    eta_squared: float
    levene_p: float
    friedman_chi2: float
    friedman_p: float
    kendall_w: float
    reject_h0: bool
    posthoc_vs_benchmark: dict[str, dict[str, float | bool]]


def newey_west_lag(n: int) -> int:
    """Regla habitual de Newey-West (1994): ⌊4 (T/100)^(2/9)⌋."""
    return math.floor(4 * math.pow(n / 100, 2 / 9))


def newey_west_se(x: FloatArray, lag: int | None = None) -> float:
    """Error estándar de la media robusto a heterocedasticidad y autocorrelación (Bartlett)."""
    n = x.size
    lag = newey_west_lag(n) if lag is None else lag
    e = x - x.mean()
    long_run = float(e @ e) / n
    for j in range(1, lag + 1):
        weight = 1 - j / (lag + 1)
        long_run += 2 * weight * float(e[j:] @ e[:-j]) / n
    return math.sqrt(max(long_run, 0.0) / n)


def block_bootstrap_means(
    x: FloatArray, replicas: int = BOOTSTRAP_REPLICAS, block: int = BLOCK_DAYS, seed: int = SEED
) -> FloatArray:
    """Medias de remuestras por bloques circulares: conserva la dependencia de corto plazo."""
    rng = np.random.default_rng(seed)
    n = x.size
    blocks = math.ceil(n / block)
    starts = rng.integers(0, n, size=(replicas, blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    samples = x[idx.reshape(replicas, -1)[:, :n]]
    means: FloatArray = samples.mean(axis=1)
    return means


def ljung_box(x: FloatArray, lags: int = LJUNG_BOX_LAGS) -> tuple[float, float]:
    n = x.size
    e = x - x.mean()
    denom = float(e @ e)
    if denom == 0:
        return 0.0, 1.0
    acf = np.array([float(e[k:] @ e[:-k]) / denom for k in range(1, lags + 1)])
    q = n * (n + 2) * float(np.sum(acf**2 / (n - np.arange(1, lags + 1))))
    return q, float(stats.chi2.sf(q, lags))


def diagnostics(x: FloatArray) -> Diagnostics:
    q, p = ljung_box(x)
    return Diagnostics(
        jarque_bera_p=float(stats.jarque_bera(x).pvalue),
        ljung_box_q=q,
        ljung_box_p=p,
        skew=float(stats.skew(x)),
        excess_kurtosis=float(stats.kurtosis(x)),
    )


def mean_greater_test(
    hypothesis: str, x: FloatArray, mu0: float = 0.0, *, wilcoxon: bool = True
) -> MeanTest:
    """H0: E[x] ≤ mu0 frente a H1: E[x] > mu0. Rechaza solo si HAC y bootstrap coinciden."""
    n = x.size
    se = newey_west_se(x)
    mean = float(x.mean())
    t_hac = (mean - mu0) / se if se > 0 else 0.0
    p_hac = float(stats.t.sf(t_hac, df=n - 1))
    boot = block_bootstrap_means(x)
    low, high = np.quantile(boot, [ALPHA / 2, 1 - ALPHA / 2])
    ci = ((float(low) - mu0) * DAYS_PER_YEAR, (float(high) - mu0) * DAYS_PER_YEAR)
    w_p = None
    if wilcoxon and np.any(x != mu0):
        w_p = float(stats.wilcoxon(x - mu0, alternative="greater").pvalue)
    sd = float(x.std(ddof=1))
    return MeanTest(
        hypothesis=hypothesis,
        n=n,
        mean_daily=mean,
        mean_annualized=mean * DAYS_PER_YEAR,
        mu0_daily=mu0,
        t_hac=t_hac,
        p_hac=p_hac,
        hac_lag=newey_west_lag(n),
        ci95_annualized=ci,
        wilcoxon_p=w_p,
        cohens_d=(mean - mu0) / sd if sd > 0 else 0.0,
        reject_h0=p_hac < ALPHA and ci[0] > 0,
    )


def holm(p_values: Mapping[str, float]) -> dict[str, float]:
    """Valores p ajustados por Holm-Bonferroni (controla el error de familia)."""
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted


def group_test(returns: Mapping[str, FloatArray], benchmark: str) -> GroupTest:
    """HE3: ANOVA (referencia), Friedman (decide) y Wilcoxon de cada política contra B1 (Holm)."""
    names = list(returns)
    groups = [returns[n] for n in names]
    anova = stats.f_oneway(*groups)
    pooled = np.concatenate(groups)
    ss_total = float(((pooled - pooled.mean()) ** 2).sum())
    ss_between = float(sum(g.size * (g.mean() - pooled.mean()) ** 2 for g in groups))
    friedman = stats.friedmanchisquare(*groups)
    n_blocks, k = groups[0].size, len(groups)
    raw = {
        n: float(stats.wilcoxon(returns[n] - returns[benchmark]).pvalue)
        for n in names
        if n != benchmark
    }
    adjusted = holm(raw)
    posthoc: dict[str, dict[str, float | bool]] = {
        n: {
            "p": raw[n],
            "p_holm": adjusted[n],
            "diferencia_anualizada": float((returns[n] - returns[benchmark]).mean())
            * DAYS_PER_YEAR,
            "significativa": adjusted[n] < ALPHA,
        }
        for n in raw
    }
    return GroupTest(
        anova_f=float(anova.statistic),
        anova_p=float(anova.pvalue),
        eta_squared=ss_between / ss_total if ss_total > 0 else 0.0,
        levene_p=float(stats.levene(*groups, center="median").pvalue),
        friedman_chi2=float(friedman.statistic),
        friedman_p=float(friedman.pvalue),
        kendall_w=float(friedman.statistic) / (n_blocks * (k - 1)),
        reject_h0=float(friedman.pvalue) < ALPHA,
        posthoc_vs_benchmark=posthoc,
    )


@dataclass(frozen=True)
class ValidationResult:
    hypothesis: str
    selected: str
    benchmark: str
    days: int
    period: tuple[str, str]
    he1: MeanTest
    he2: MeanTest
    he3: GroupTest
    diagnostics: dict[str, Diagnostics]
    # KE-014: el último día incluye la liquidación del 2024-07-01 00:00 (holdout). Se repiten las
    # decisiones sin ese día para mostrar que no cambian.
    sin_dia_frontera: dict[str, bool | float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_policies(  # noqa: PLR0913 - keyword-only: cada argumento es parte del plan fijado
    returns: Mapping[str, FloatArray],
    *,
    hypothesis: str,
    selected: str,
    benchmark: str,
    hurdle_annual: float,
    period: tuple[str, str],
) -> ValidationResult:
    lengths = {r.size for r in returns.values()}
    if len(lengths) != 1:
        raise ValueError(f"Las series deben estar alineadas por día; largos: {sorted(lengths)}")
    sel, bench = returns[selected], returns[benchmark]
    hurdle_daily = hurdle_annual / DAYS_PER_YEAR
    return ValidationResult(
        hypothesis=hypothesis,
        selected=selected,
        benchmark=benchmark,
        days=sel.size,
        period=period,
        he1=mean_greater_test("HE1: optimizada > B1", sel - bench),
        he2=mean_greater_test("HE2: optimizada > hurdle", sel, hurdle_daily),
        he3=group_test(returns, benchmark),
        diagnostics={n: diagnostics(r) for n, r in returns.items()},
    )


def verdict(reject: bool, kind: Literal["media", "grupo"]) -> str:
    if kind == "grupo":
        return "se rechaza H0: las políticas difieren" if reject else "no se rechaza H0"
    return "se rechaza H0" if reject else "no se rechaza H0"


# --- Datos de la evaluación del carry ----------------------------------------------------------

SHARPE_TOLERANCE = 1e-6


def load_policy_returns(data_dir: Path, hypothesis: str) -> tuple[dict[str, FloatArray], list[str]]:
    """Retornos diarios del grid (artefacto de la evaluación) y de B1, recalculado igual que allí.

    B1 no se guardó como serie en la evaluación: se recalcula con ``run_config`` sobre el periodo
    de desarrollo. No es un ensayo nuevo (N no cambia), y se verifica que su Sharpe coincida con el
    del ``summary.json``; si no coincide, los datos o el código cambiaron y no se sigue.
    """
    folder = data_dir / "research" / "carry" / hypothesis
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    wide = pl.read_parquet(folder / "daily_returns.parquet")
    if wide.schema["date"] == pl.String:
        wide = wide.with_columns(pl.col("date").str.to_datetime(time_zone="UTC", time_unit="ms"))

    data = [load_symbol(data_dir / "silver", s) for s in HYPOTHESES[hypothesis]]
    bench_frame, _ = run_config(data, CarryConfig(9, 0.0, always_on=True))
    aligned = wide.join(
        bench_frame.select("date", pl.col("ret").alias(BENCHMARK)), on="date", how="left"
    ).with_columns(pl.col(BENCHMARK).fill_null(0.0))
    expected = float(summary["benchmark_B1"]["sharpe"])
    got = performance(aligned[BENCHMARK].to_numpy()).sharpe
    if abs(got - expected) > SHARPE_TOLERANCE:
        raise ValueError(f"B1 recalculado (Sharpe {got:.6f}) ≠ evaluación ({expected:.6f})")
    returns = {c: aligned[c].to_numpy().astype(np.float64) for c in aligned.columns if c != "date"}
    return returns, [str(d) for d in aligned["date"].to_list()]


def run_validation(data_dir: Path, hypothesis: str = "H2") -> ValidationResult:
    summary = json.loads(
        (data_dir / "research" / "carry" / hypothesis / "summary.json").read_text(encoding="utf-8")
    )
    returns, dates = load_policy_returns(data_dir, hypothesis)

    def run(series: Mapping[str, FloatArray], period: tuple[str, str]) -> ValidationResult:
        return validate_policies(
            series,
            hypothesis=hypothesis,
            selected=str(summary["selected"]),
            benchmark=BENCHMARK,
            hurdle_annual=STABLECOIN_HURDLE,
            period=period,
        )

    result = run(returns, (dates[0], dates[-1]))
    trimmed = run({k: v[:-1] for k, v in returns.items()}, (dates[0], dates[-2]))
    return replace(
        result,
        sin_dia_frontera={
            "he1_p_hac": trimmed.he1.p_hac,
            "he1_rechaza": trimmed.he1.reject_h0,
            "he2_p_hac": trimmed.he2.p_hac,
            "he2_rechaza": trimmed.he2.reject_h0,
            "he3_friedman_p": trimmed.he3.friedman_p,
            "he3_rechaza": trimmed.he3.reject_h0,
        },
    )


def write_validation(result: ValidationResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
