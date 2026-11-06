from datetime import timedelta

from prometheus_platform.research.backtest import ALT_COSTS, MAIN_COSTS
from prometheus_platform.research.carry_evaluation import (
    SMOKE_TEST_TRIALS,
    SymbolData,
    TrialRecord,
    costs_for,
    evaluate_hypothesis,
)

from .conftest import T0, HourlyFactory


class MemoryRegistry:
    def __init__(self) -> None:
        self.records: list[TrialRecord] = []

    def log_trial(self, trial: TrialRecord) -> None:
        self.records.append(trial)

    def trials(self) -> list[TrialRecord]:
        return list(self.records)


def test_costs_by_symbol() -> None:
    assert costs_for("BTCUSDT") is MAIN_COSTS
    assert costs_for("SOLUSDT") is ALT_COSTS


def test_evaluation_registers_every_trial_and_applies_the_gates(market: HourlyFactory) -> None:
    # Funding que alterna entre régimen alto y bajo cada ~10 días: hay timing que aprovechar.
    days = 220
    hourly, settlements = market(
        hours=24 * days,
        rate=lambda h: 0.0004 if (h // 240) % 2 == 0 else 0.00002,
        price=lambda i: 100.0 * (1 + 0.1 * ((i // 500) % 2)),
    )
    data = [SymbolData("BTCUSDT", hourly, settlements)]
    registry = MemoryRegistry()
    result = evaluate_hypothesis("H1", data, registry)

    assert len(registry.records) == 9  # las 9 configuraciones pre-declaradas, todas registradas
    assert {r.hypothesis for r in registry.records} == {"H1"}
    assert result.n_trials == 18 + SMOKE_TEST_TRIALS
    assert result.selected in result.cpcv_mean_sharpe
    assert result.selected == max(result.cpcv_mean_sharpe, key=result.cpcv_mean_sharpe.__getitem__)
    assert [g.name for g in result.gates] == ["G1", "G2", "G3", "G4"]
    assert 0.0 <= result.pbo <= 1.0
    assert 0.0 <= result.dsr <= 1.0
    assert result.passed == all(g.passed for g in result.gates)
    assert result.decomposition["funding"] > 0
    assert set(result.sensitivity) == {"sharpe_maker", "sharpe_efectivo_4pct"}
    assert len(result.dates) == len(result.returns[result.selected])
    assert result.dates[0] >= str(T0 + timedelta(days=1))[:10]
