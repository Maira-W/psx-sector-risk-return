"""The extra measures and the statistics, each on a case with a known answer or on simulated data where the truth is known."""

from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from psxsec import metrics, stats


# ---- more measures ---------------------------------------------------------------------------------------------------
def test_sortino_counts_only_the_shortfalls_as_risk():
    excess = [0.02, -0.01, 0.01, -0.03]            # mean -0.0025; shortfalls squared average (0.0001 + 0.0009) / 4 = 0.00025
    assert metrics.sortino(excess, ppy=4) == pytest.approx(-0.0025 / np.sqrt(0.00025) * 2)


def test_moments_of_a_skewed_sample():
    skew, kurt = metrics.moments([0, 0, 0, 4])          # centred values -1, -1, -1, 3: variance 3, third moment 6, fourth moment 21
    assert skew == pytest.approx(6 / 3 ** 1.5) and kurt == pytest.approx(21 / 9)
    symmetric = metrics.moments([-1, 1, -1, 1])
    assert symmetric[0] == pytest.approx(0.0) and symmetric[1] == pytest.approx(1.0)


def test_value_at_risk_and_expected_shortfall():
    var, es = metrics.tail_risk(np.arange(-10, 10), level=0.90)
    assert var == pytest.approx(-8.1) and es == pytest.approx(-9.5)


def test_capture_ratios():
    benchmark = pd.Series([0.02, -0.01, 0.04, -0.02])
    sector = pd.Series([0.03, -0.005, 0.05, -0.01])
    up, down = metrics.capture_ratios(sector, benchmark)
    assert up == pytest.approx(0.04 / 0.03) and down == pytest.approx(0.0075 / 0.015)


def test_longest_drawdown_counts_the_longest_run_below_a_peak():
    level = pd.Series([100, 99, 98, 101, 100, 99, 98, 97, 102.0])
    assert metrics.longest_drawdown_days(level) == 4


# ---- regression --------------------------------------------------------------------------------------------------------
def test_ols_recovers_the_coefficients_and_robust_errors_are_wider_when_errors_are_autocorrelated():
    rng = np.random.default_rng(1)
    n = 3000

    def persistent(coefficient):
        series = np.empty(n)
        series[0] = rng.normal()
        for t in range(1, n):
            series[t] = coefficient * series[t - 1] + rng.normal()
        return series

    regressor, noise = persistent(0.7), persistent(0.7)       # both persistent, so the errors really are autocorrelated
    design = np.column_stack([np.ones(n), regressor])
    y = 1.0 + 2.0 * regressor + noise
    plain, robust = stats.ols(y, design, lags=0), stats.ols(y, design, lags=20)
    assert plain.coef == pytest.approx([1.0, 2.0], abs=0.15) and robust.coef == pytest.approx(plain.coef)
    assert robust.se[1] > 1.3 * plain.se[1]          # allowing for the autocorrelation makes the slope less certain, as it should
    assert 0.5 < plain.r2 < 1.0 and plain.n == n


def test_robust_errors_agree_with_the_textbook_ones_when_errors_are_independent():
    rng = np.random.default_rng(2)
    n = 4000
    x = rng.normal(size=n)
    y = 0.5 + 1.5 * x + rng.normal(size=n)
    design = np.column_stack([np.ones(n), x])
    fit = stats.ols(y, design, lags=5)
    classical = np.sqrt(np.sum((y - design @ fit.coef) ** 2) / (n - 2) * np.diag(np.linalg.inv(design.T @ design)))
    assert fit.se == pytest.approx(classical, rel=0.12)
    assert fit.t[1] == pytest.approx(1.5 / classical[1], rel=0.12)


def test_market_model_adds_the_two_slopes_and_finds_zero_alpha_when_there_is_none():
    rng = np.random.default_rng(3)
    n = 2500
    market = rng.normal(0, 0.02, n)
    lagged = np.concatenate([[0.0], market[:-1]])
    sector = 0.5 * market + 0.3 * lagged + rng.normal(0, 0.01, n)       # reacts partly one period late
    fit = stats.market_model(sector, market, lags=4)
    assert fit["beta"] == pytest.approx(0.8, abs=0.06) and abs(fit["alpha_t"]) < 3
    assert fit["beta_se"] > 0 and 0.5 < fit["r2"] < 1 and fit["n"] == n - 1


def test_batch_alpha_agrees_with_one_regression_at_a_time():
    rng = np.random.default_rng(4)
    n, columns = 300, 5
    x0 = rng.normal(size=(n, columns))
    x1 = np.vstack([np.zeros((1, columns)), x0[:-1]])
    y = 0.1 + 0.6 * x0 + 0.2 * x1 + rng.normal(size=(n, columns))
    alpha, se, beta = stats.batch_alpha(y, x0, x1)
    for s in range(columns):
        design = np.column_stack([np.ones(n), x0[:, s], x1[:, s]])
        coef = np.linalg.lstsq(design, y[:, s], rcond=None)[0]
        resid = y[:, s] - design @ coef
        expected_se = np.sqrt(resid @ resid / (n - 3) * np.linalg.inv(design.T @ design)[0, 0])
        assert alpha[s] == pytest.approx(coef[0]) and se[s] == pytest.approx(expected_se) and beta[s] == pytest.approx(coef[1] + coef[2])


def test_the_p_value_helpers():
    assert stats.normal_p(1.96)[0] == pytest.approx(0.05, abs=0.001) and stats.normal_p(0.0)[0] == pytest.approx(1.0)
    adjusted = stats.benjamini_hochberg([0.01, 0.04, 0.03, 0.005])
    assert adjusted == pytest.approx([0.02, 0.04, 0.04, 0.02])
    assert (stats.benjamini_hochberg([0.9, 0.95]) <= 1).all()


# ---- looking at many sectors at once -----------------------------------------------------------------------------------
def weekly_panel(seed, columns=12, n=260, planted=None):
    rng = np.random.default_rng(seed)
    x0 = rng.normal(0, 0.02, (n, columns))
    x1 = np.vstack([np.zeros((1, columns)), x0[:-1]])
    y = 0.8 * x0 + rng.normal(0, 0.015, (n, columns))
    if planted is not None:
        y[:, 0] += planted
    return y, x0, x1


def test_reality_check_flags_a_planted_alpha_but_not_noise():
    y, x0, x1 = weekly_panel(seed=7, planted=0.01)                       # a 1% a week alpha in the first column only
    result = stats.alpha_reality_check(y, x0, x1, draws=400, seed=1)
    assert result["p_adjusted"][0] < 0.05
    assert (result["p_adjusted"][1:] > 0.05).all()
    # With no alpha anywhere, the best of twelve should be called significant in about 1 panel in 20 (a calibration run of 200
    # panels of 22 sectors gave 2.5%, against 70% without the correction), so very few of eight noise panels should be flagged.
    flagged = sum(stats.alpha_reality_check(*weekly_panel(seed=seed), draws=300, seed=seed)["p_adjusted"].min() < 0.05 for seed in range(21, 29))
    assert flagged <= 2


def test_the_adjusted_p_value_is_larger_than_the_naive_one_for_the_best_of_many():
    y, x0, x1 = weekly_panel(seed=5, columns=30)
    result = stats.alpha_reality_check(y, x0, x1, draws=400, seed=2)
    best = int(np.argmax(np.abs(result["t"])))
    naive = stats.normal_p(result["t"][best])[0]
    assert result["p_adjusted"][best] > naive


# ---- the Sharpe ratio's own uncertainty -------------------------------------------------------------------------------
def test_probabilistic_sharpe_matches_the_textbook_formula_for_normal_returns():
    value = stats.probabilistic_sharpe(0.1, n=101, skew=0.0, kurtosis=3.0, benchmark=0.0)
    assert value == pytest.approx(NormalDist().cdf(0.1 * 10 / np.sqrt(1 + 0.1 ** 2 / 2)))
    assert stats.probabilistic_sharpe(0.1, 101, 0.0, 3.0, benchmark=0.1) == pytest.approx(0.5)
    assert stats.probabilistic_sharpe(0.1, 400, 0.0, 3.0) > value                  # more data, more certainty


def test_expected_max_sharpe_matches_a_simulation_of_strategies_with_no_skill():
    rng = np.random.default_rng(9)
    simulated_max, predicted = [], []
    for _ in range(400):
        returns = rng.normal(0, 0.01, (500, 22))
        sharpes = returns.mean(axis=0) / returns.std(axis=0, ddof=1)
        simulated_max.append(sharpes.max())
        predicted.append(stats.expected_max_sharpe(sharpes))
    assert np.mean(predicted) == pytest.approx(np.mean(simulated_max), rel=0.10)


def test_the_deflated_sharpe_is_stricter_than_the_probabilistic_one_and_falls_with_a_wider_field():
    narrow = np.linspace(-0.02, 0.05, 22)
    wide = np.linspace(-0.06, 0.09, 22)
    plain = stats.probabilistic_sharpe(0.08, 1200, 0.0, 3.0)
    deflated_narrow = stats.deflated_sharpe(0.08, 1200, 0.0, 3.0, narrow)
    deflated_wide = stats.deflated_sharpe(0.08, 1200, 0.0, 3.0, wide)
    assert deflated_wide < deflated_narrow < plain
    assert 0 < deflated_wide < 1
