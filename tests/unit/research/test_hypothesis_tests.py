import json
import math
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from prometheus_platform.api import cli
from prometheus_platform.research import hypothesis_tests as ht
from prometheus_platform.research.validation import performance

RNG = np.random.default_rng(7)


def ar1(n: int, phi: float, scale: float = 1.0) -> np.ndarray:
    noise = RNG.normal(0, scale, n)
    out = np.empty(n)
    out[0] = noise[0]
    for i in range(1, n):
        out[i] = phi * out[i - 1] + noise[i]
    return out


def test_newey_west_matches_the_classic_error_without_lags_and_grows_with_autocorrelation() -> None:
    x = RNG.normal(0, 1, 2_000)
    classic = x.std(ddof=0) / math.sqrt(x.size)
    assert ht.newey_west_se(x, lag=0) == pytest.approx(classic)
    persistent = ar1(2_000, 0.8)
    assert ht.newey_west_se(persistent) > 2 * ht.newey_west_se(persistent, lag=0)
    assert ht.newey_west_lag(1_642) == 7


def test_block_bootstrap_is_reproducible_and_centered() -> None:
    x = RNG.normal(0.5, 1, 500)
    first, second = (
        ht.block_bootstrap_means(x, replicas=2_000),
        ht.block_bootstrap_means(x, replicas=2_000),
    )
    np.testing.assert_array_equal(first, second)  # semilla fija
    assert first.mean() == pytest.approx(x.mean(), abs=0.02)


def test_ljung_box_separates_white_noise_from_autocorrelation() -> None:
    _, p_noise = ht.ljung_box(RNG.normal(0, 1, 1_000))
    _, p_ar = ht.ljung_box(ar1(1_000, 0.5))
    assert p_noise > ht.ALPHA
    assert p_ar < 1e-6
    assert ht.ljung_box(np.zeros(50)) == (0.0, 1.0)


def test_mean_test_rejects_a_clear_edge_and_not_noise() -> None:
    edge = ht.mean_greater_test("edge", RNG.normal(0.002, 0.01, 1_500))
    assert edge.reject_h0
    assert edge.ci95_annualized[0] > 0
    noise = ht.mean_greater_test("ruido", RNG.normal(0.0, 0.01, 1_500))
    assert not noise.reject_h0
    hurdle = ht.mean_greater_test("hurdle", RNG.normal(0.002, 0.01, 1_500), mu0=0.002)
    assert not hurdle.reject_h0  # rendir lo mismo que el hurdle no es superarlo


def test_mean_test_needs_both_hac_and_bootstrap() -> None:
    # Pocas observaciones muy autocorrelacionadas: la t clásica engañaría; HAC y bootstrap no.
    x = 0.001 + ar1(200, 0.95, 0.002)
    result = ht.mean_greater_test("persistente", x)
    assert result.reject_h0 == (result.p_hac < ht.ALPHA and result.ci95_annualized[0] > 0)


def test_holm_adjustment() -> None:
    adjusted = ht.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_group_test_detects_a_different_policy_and_flags_it_in_the_post_hoc() -> None:
    rng = np.random.default_rng(11)
    base = rng.normal(0, 0.01, 800)
    half = rng.normal(0, 0.001, 400)
    symmetric = np.concatenate([half, -half])  # mediana exactamente 0: «igual» no difiere de B1
    rng.shuffle(symmetric)
    returns = {
        "B1": base,
        "igual": base + symmetric,
        "mejor": base + 0.003 + rng.normal(0, 0.001, 800),
    }
    result = ht.group_test(returns, "B1")
    assert result.reject_h0
    assert result.posthoc_vs_benchmark["mejor"]["significativa"]
    assert not result.posthoc_vs_benchmark["igual"]["significativa"]
    assert 0 <= result.kendall_w <= 1


def test_validate_policies_requires_aligned_series() -> None:
    with pytest.raises(ValueError, match="alineadas"):
        ht.validate_policies(
            {"a": np.zeros(10), "B1": np.zeros(9)},
            hypothesis="H2",
            selected="a",
            benchmark="B1",
            hurdle_annual=0.04,
            period=("x", "y"),
        )


@pytest.fixture
def evaluation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, np.ndarray]:
    """Artefactos de una evaluación y un B1 recalculado falso (no hace falta silver)."""
    n = 400
    dates = pl.datetime_range(
        pl.datetime(2020, 1, 3, time_zone="UTC"),
        pl.datetime(2020, 1, 3, time_zone="UTC") + pl.duration(days=n - 1),
        "1d",
        eager=True,
    ).dt.cast_time_unit("ms")
    bench = RNG.normal(0.0001, 0.005, n)
    folder = tmp_path / "research" / "carry" / "H2"
    folder.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": dates.dt.to_string("%Y-%m-%d %H:%M:%S%:z"),
            "k9-theta20": bench + 0.0004 + RNG.normal(0, 0.001, n),
            "k3-theta10": bench + RNG.normal(0, 0.001, n),
        }
    ).write_parquet(folder / "daily_returns.parquet")
    summary = {"selected": "k9-theta20", "benchmark_B1": {"sharpe": performance(bench).sharpe}}
    (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    monkeypatch.setattr(ht, "load_symbol", lambda *_: object())
    frame = pl.DataFrame({"date": dates, "ret": bench})
    monkeypatch.setattr(ht, "run_config", lambda *_args, **_kw: (frame, []))
    return tmp_path, bench


def test_run_validation_end_to_end_with_boundary_sensitivity(
    evaluation: tuple[Path, np.ndarray],
) -> None:
    data_dir, _ = evaluation
    result = ht.run_validation(data_dir)
    assert result.days == 400
    assert result.selected == "k9-theta20"
    assert set(result.diagnostics) == {"k9-theta20", "k3-theta10", ht.BENCHMARK}
    assert result.sin_dia_frontera is not None
    assert result.sin_dia_frontera["he1_rechaza"] == result.he1.reject_h0
    path = ht.write_validation(result, data_dir / "research" / "stats")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["he1"]["hypothesis"].startswith("HE1")


def test_recomputed_benchmark_must_match_the_evaluation(
    evaluation: tuple[Path, np.ndarray],
) -> None:
    data_dir, _ = evaluation
    summary_path = data_dir / "research" / "carry" / "H2" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["benchmark_B1"]["sharpe"] += 0.1
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="B1 recalculado"):
        ht.load_policy_returns(data_dir, "H2")


def test_cli_prints_the_verdicts(
    evaluation: tuple[Path, np.ndarray],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir, _ = evaluation
    monkeypatch.setenv("PQ_DATA_DIR", str(data_dir))
    assert cli.main(["research", "stats"]) == 0
    out = capsys.readouterr().out
    assert "HE1: optimizada > B1" in out
    assert "HE3: Friedman" in out
    assert (data_dir / "research" / "stats" / "summary.json").is_file()
