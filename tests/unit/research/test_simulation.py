import numpy as np
import pytest

from prometheus_platform.research.simulation import (
    BASE_RATE,
    CarryRules,
    Regime,
    apply_exchange_failure,
    classify,
    fit_markov,
    fit_regimes,
    fit_weekly_model,
    optimal_allocation,
    regime_spells,
    run_carry,
    run_simulation_study,
    simulate_rates,
    simulate_rates_semimarkov,
    sojourn_tests,
)


def markov_sequence(n: int, transition: np.ndarray, seed: int = 0) -> np.ndarray:
    """Tasas sintéticas: régimen por una Markov conocida y un valor típico por régimen."""
    rng = np.random.default_rng(seed)
    regime, out = 1, np.empty(n)
    for t in range(n):
        if regime == Regime.NEGATIVE:
            out[t] = -rng.lognormal(-3, 0.5)
        elif regime == Regime.BASE:
            out[t] = BASE_RATE if rng.random() < 0.5 else rng.uniform(0.01, 0.19)
        else:
            out[t] = 0.2 + rng.exponential(0.1)
        regime = rng.choice(3, p=transition[regime])
    return out


TRUE_P = np.array([[0.8, 0.2, 0.0], [0.1, 0.8, 0.1], [0.0, 0.3, 0.7]])


def test_classify_regimes() -> None:
    assert classify(np.array([-0.01, 0.0, 0.1095, 0.199, 0.2, 3.0])).tolist() == [0, 1, 1, 1, 2, 2]


def test_markov_recovers_the_true_transition_matrix() -> None:
    chain = fit_markov([markov_sequence(20_000, TRUE_P)])
    assert chain.transition == pytest.approx(TRUE_P, abs=0.02)
    assert chain.stationary.sum() == pytest.approx(1.0)
    assert chain.stationary @ chain.transition == pytest.approx(chain.stationary, abs=1e-9)
    assert chain.chi2_p_value < 0.001  # la memoria importa
    assert chain.expected_duration[0] == pytest.approx(1 / 0.2, rel=0.1)


def test_transitions_are_never_counted_across_symbols() -> None:
    a, b = np.full(10, -0.5), np.full(10, 0.5)
    chain = fit_markov([a, b])
    assert chain.counts[Regime.NEGATIVE, Regime.HIGH] == 0
    assert chain.counts.sum() == 18


def test_fits_detect_point_masses_and_pick_the_true_family() -> None:
    models = fit_regimes(markov_sequence(20_000, TRUE_P, seed=1))
    assert models[Regime.BASE].point_mass[BASE_RATE] == pytest.approx(0.5, abs=0.03)
    assert models[Regime.HIGH].best.distribution in {"expon", "gamma", "genpareto"}
    assert models[Regime.NEGATIVE].best.distribution in {"lognorm", "weibull_min"}
    rng = np.random.default_rng(0)
    draws = models[Regime.BASE].sample(rng, 5000)
    assert np.isclose(draws, BASE_RATE).mean() == pytest.approx(0.5, abs=0.03)
    assert ((draws >= 0) & (draws < 0.2)).all()
    assert models[Regime.HIGH].sample(rng, 500, parametric=False).min() >= 0.2


def test_geometric_sojourns_pass_and_long_spells_fail() -> None:
    seq = markov_sequence(30_000, TRUE_P, seed=2)
    chain = fit_markov([seq])
    assert all(t.p_value > 0.001 for t in sojourn_tests(chain, regime_spells([seq])))
    blocky = np.repeat(markov_sequence(3_000, TRUE_P, seed=3), 8)  # rachas 8 veces más largas
    chain_b = fit_markov([blocky])
    assert any(t.p_value < 0.001 for t in sojourn_tests(chain_b, regime_spells([blocky])))


def test_simulators_produce_paths_of_the_requested_shape() -> None:
    seq = markov_sequence(5_000, TRUE_P, seed=4)
    chain, rng = fit_markov([seq]), np.random.default_rng(0)
    assert simulate_rates(chain, fit_regimes(seq), n_paths=7, n_steps=50, rng=rng).shape == (7, 50)
    assert simulate_rates_semimarkov(
        chain, regime_spells([seq]), n_paths=7, n_steps=50, rng=rng
    ).shape == (7, 50)
    weekly = fit_weekly_model([seq], block=21)
    assert weekly.simulate(n_paths=7, n_steps=50, rng=rng).shape == (7, 50)


def test_run_carry_collects_funding_and_pays_costs() -> None:
    rules = CarryRules(k=3, theta=0.2, round_trip_cost=0.01, notional_fraction=0.5)
    high = np.full((1, 1000), 0.30)
    result = run_carry(high, rules, warmup=3)
    # Entra en la liquidación 3, paga medio coste de ida y vuelta y capitaliza el funding.
    growth = (1 + 0.5 * 0.30 / 1095) ** (1000 - 3 - 1)
    assert result.annual_returns[0] == pytest.approx((1 - 0.5 * 0.01 / 2) * growth - 1, rel=1e-3)
    assert result.cycles[0] == 1
    flat = run_carry(np.full((1, 100), BASE_RATE), rules, warmup=3)
    assert flat.annual_returns[0] == 0.0
    assert flat.invested_fraction[0] == 0.0


def test_exchange_failure_and_frontier() -> None:
    rng = np.random.default_rng(0)
    returns = np.full(100_000, 0.05)
    failed = apply_exchange_failure(returns, 0.10, 1.0, rng)
    assert (failed == -1.0).mean() == pytest.approx(0.10, abs=0.005)
    frontier = optimal_allocation(failed, hurdle=0.04, cvar_limit=0.05, steps=5)
    assert frontier[0]["w_carry"] == 0.0
    assert frontier[0]["retorno_esperado"] == pytest.approx(0.04)
    assert frontier[0]["cumple"]
    assert not frontier[-1]["cumple"]


def test_full_study_validates_against_history() -> None:
    seqs = [markov_sequence(3_000, TRUE_P, seed=s) for s in (5, 6)]
    study = run_simulation_study(seqs, n_paths=200, exchange_failure=(0.02,))
    assert [v.model[:2] for v in study.validation] == ["v1", "v2", "v3"]
    assert study.historical.model == "historia real"
    assert set(study.scenarios) == {"sin quiebra del exchange", "quiebra con p = 2% anual"}
    assert 0.0 <= study.break_even_failure < 1.0
    assert len(study.frontier) == 21
