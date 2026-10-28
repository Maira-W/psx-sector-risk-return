"""The measures of return and risk, each on a case small enough to work out by hand."""

import numpy as np
import pandas as pd
import pytest

from psxsec import metrics


def days(n, start="2024-01-02"):
    return pd.bdate_range(start, periods=n)


def test_total_and_annual_return():
    r = pd.Series([0.10, -0.10])
    assert metrics.total_return(r) == pytest.approx(1.1 * 0.9 - 1)
    two_years = pd.Series([0.10, 0.10])       # 10% in each of two years is 21% in all, which is 10% a year
    assert metrics.annualised_return(two_years, years=2) == pytest.approx(0.10)
    assert metrics.annualised_return(pd.Series([0.21]), years=2) == pytest.approx(0.10)
    assert metrics.annualised_return(pd.Series([0.21]), years=1) == pytest.approx(0.21)


def test_cumulative_starts_from_the_base():
    level = metrics.cumulative(pd.Series([0.5, -0.5]), base=100)
    assert list(level) == [150.0, 75.0]


def test_volatility_is_the_sample_standard_deviation_scaled_to_a_year():
    r = pd.Series([0.01, -0.01, 0.01, -0.01])
    assert metrics.volatility(r, ppy=4) == pytest.approx(r.std(ddof=1) * 2)
    assert metrics.volatility(r, ppy=4) == pytest.approx(0.0230940, abs=1e-6)


def test_sharpe_on_a_case_with_a_known_answer():
    excess = pd.Series([0.02, 0.00, 0.02, 0.00])       # mean 0.01, sample standard deviation 0.011547
    assert metrics.sharpe(excess, ppy=4) == pytest.approx(0.01 / 0.0115470054 * 2, abs=1e-6)
    assert metrics.sharpe(excess * 3, ppy=4) == pytest.approx(metrics.sharpe(excess, ppy=4))       # scale does not matter


def test_max_drawdown_finds_the_worst_peak_to_low_fall_and_whether_it_recovered():
    level = pd.Series([100, 120, 90, 100, 130, 65.0], index=days(6))
    d = metrics.max_drawdown(level)
    assert d["max_drawdown"] == pytest.approx(-0.5)
    assert d["peak_date"] == level.index[4] and d["trough_date"] == level.index[5]
    assert d["recovery_date"] is None and d["drawdown_now"] == pytest.approx(-0.5)

    recovered = pd.Series([100, 120, 90, 125.0], index=days(4))
    d = metrics.max_drawdown(recovered)
    assert d["max_drawdown"] == pytest.approx(-0.25)
    assert d["peak_date"] == recovered.index[1] and d["trough_date"] == recovered.index[2] and d["recovery_date"] == recovered.index[3]
    assert d["drawdown_now"] == 0.0


def test_a_rising_series_has_no_drawdown():
    level = pd.Series([100, 101, 102.0], index=days(3))
    assert metrics.max_drawdown(level)["max_drawdown"] == 0.0
    assert np.isnan(metrics.calmar(0.1, 0.0))
    assert metrics.calmar(0.2, -0.4) == pytest.approx(0.5)


def test_drawdown_series_matches_the_worst_point():
    level = pd.Series([100, 120, 90, 100.0], index=days(4))
    assert metrics.drawdown_series(level).min() == pytest.approx(-0.25)


# ---- the safe return ----------------------------------------------------------------------------------------------
POLICY = pd.DataFrame({"effective_date": pd.to_datetime(["2023-12-01", "2024-01-04"]), "policy_rate_pct": [10.0, 20.0]})


def test_rate_in_force_is_the_latest_change_on_or_before_the_date():
    dates = pd.DatetimeIndex(["2023-12-01", "2024-01-03", "2024-01-04", "2024-02-01"])
    assert list(metrics.rate_in_force(dates, POLICY)) == [10.0, 10.0, 20.0, 20.0]
    with pytest.raises(ValueError):
        metrics.rate_in_force(pd.DatetimeIndex(["2023-11-30"]), POLICY)


def test_safe_return_accrues_by_calendar_day_at_the_rate_in_force_on_the_previous_day():
    base = pd.Timestamp("2024-01-03")                      # a Wednesday
    dates = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-08"])    # Thu, Fri, then Monday (3 days)
    safe = metrics.safe_return(dates, base, POLICY)
    assert safe.iloc[0] == pytest.approx(0.10 / 365)       # the rate on Wednesday is still 10%
    assert safe.iloc[1] == pytest.approx(0.20 / 365)       # the change on Thursday applies from then on
    assert safe.iloc[2] == pytest.approx(0.20 * 3 / 365)   # across the weekend


# ---- the bootstrap ------------------------------------------------------------------------------------------------
def test_bootstrap_indices_are_valid_reproducible_and_in_runs():
    rng = np.random.default_rng(1)
    index = metrics.stationary_bootstrap_indices(500, 400, 10, rng)
    assert index.shape == (400, 500) and index.min() >= 0 and index.max() < 500
    again = metrics.stationary_bootstrap_indices(500, 400, 10, np.random.default_rng(1))
    assert (index == again).all()
    carry_on = ((index[:, 1:] - index[:, :-1]) % 500 == 1).mean()
    assert carry_on == pytest.approx(0.9, abs=0.02)        # a jump happens about once in 10 days


def test_bootstrap_sharpe_is_centred_on_the_sample_value_for_independent_days():
    rng = np.random.default_rng(5)
    excess = pd.DataFrame({"a": rng.normal(0.0008, 0.01, 1000), "b": rng.normal(0.0002, 0.02, 1000)})
    ppy = 250
    draws = metrics.bootstrap_sharpe(excess, ppy, draws=600, mean_block=5, seed=3)
    assert draws.shape == (600, 2)
    sample = metrics.sharpe(excess, ppy)
    assert draws.mean(axis=0) == pytest.approx(sample.to_numpy(), abs=0.15)
    assert (draws.std(axis=0) > 0.1).all()                 # and there is real spread to report
    assert (metrics.bootstrap_sharpe(excess, ppy, 50, 5, seed=3) == metrics.bootstrap_sharpe(excess, ppy, 50, 5, seed=3)).all()


def test_ranks_give_one_to_the_largest():
    values = np.array([[0.5, 1.5, 1.0], [2.0, 2.0, 1.0]])
    assert metrics.ranks(values).tolist() == [[3, 1, 2], [1, 2, 3]]


def test_spearman():
    a = pd.Series({"x": 1.0, "y": 2.0, "z": 3.0, "w": 4.0})
    assert metrics.spearman(a, a * 10) == pytest.approx(1.0)
    assert metrics.spearman(a, -a) == pytest.approx(-1.0)
    assert np.isnan(metrics.spearman(a.iloc[:2], a.iloc[:2]))
