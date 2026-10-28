"""The portfolio tools on small cases with known answers, including a check that the out-of-sample test cannot look ahead."""

import numpy as np
import pandas as pd
import pytest

from psxsec import analysis, portfolios


def days(n, start="2022-01-03"):
    return pd.bdate_range(start, periods=n)


# ---- weights --------------------------------------------------------------------------------------------------------------
def test_shrunk_covariance_keeps_total_variance_and_shrinks_less_with_more_data():
    rng = np.random.default_rng(1)
    mixing = rng.normal(size=(6, 6))
    small = rng.normal(size=(60, 6)) @ mixing
    large = rng.normal(size=(4000, 6)) @ mixing
    cov_small, shrink_small = portfolios.shrunk_covariance(small)
    cov_large, shrink_large = portfolios.shrunk_covariance(large)
    assert 0 <= shrink_large < shrink_small <= 1
    assert np.trace(cov_small) == pytest.approx(np.trace(np.cov(small.T, bias=True)))
    assert np.linalg.eigvalsh(cov_small).min() > 0                                       # a usable (positive definite) matrix
    assert np.linalg.cond(cov_small) < np.linalg.cond(np.cov(small.T, bias=True))        # and better conditioned than the raw one


def test_project_simplex_gives_valid_weights_and_leaves_valid_weights_alone():
    w = portfolios.project_simplex(np.array([0.7, -0.4, 1.3, 0.2]))
    assert w.sum() == pytest.approx(1.0) and (w >= 0).all()
    already = np.array([0.2, 0.3, 0.5])
    assert portfolios.project_simplex(already) == pytest.approx(already)


def test_min_variance_matches_the_two_asset_formula_and_respects_the_no_short_rule():
    sigma1, sigma2, rho = 0.2, 0.1, 0.3
    cov = np.array([[sigma1 ** 2, rho * sigma1 * sigma2], [rho * sigma1 * sigma2, sigma2 ** 2]])
    expected_first = (sigma2 ** 2 - rho * sigma1 * sigma2) / (sigma1 ** 2 + sigma2 ** 2 - 2 * rho * sigma1 * sigma2)
    w = portfolios.min_variance(cov)
    assert w[0] == pytest.approx(expected_first, abs=1e-5) and w.sum() == pytest.approx(1.0)
    # With a correlation of 0.8 the unconstrained answer would short the riskier asset (weight -1/3); with no shorting it gets none.
    sigma1, sigma2, rho = 0.2, 0.1, 0.8
    corner = portfolios.min_variance(np.array([[sigma1 ** 2, rho * sigma1 * sigma2], [rho * sigma1 * sigma2, sigma2 ** 2]]))
    assert corner == pytest.approx([0.0, 1.0], abs=1e-6)


def test_min_variance_beats_random_weights():
    rng = np.random.default_rng(3)
    returns = rng.normal(size=(500, 8)) @ rng.normal(size=(8, 8))
    cov = portfolios.shrunk_covariance(returns)[0]
    best = portfolios.min_variance(cov)
    variance = lambda w: w @ cov @ w  # noqa: E731
    others = [rng.dirichlet(np.ones(8)) for _ in range(500)] + [np.full(8, 1 / 8)]
    assert variance(best) <= min(variance(w) for w in others) + 1e-12


def test_inverse_volatility_gives_the_calmer_asset_more_weight():
    cov = np.diag([0.04, 0.01, 0.0025])
    w = portfolios.inverse_volatility(cov)
    assert w == pytest.approx(np.array([1 / 0.2, 1 / 0.1, 1 / 0.05]) / (1 / 0.2 + 1 / 0.1 + 1 / 0.05)) and w.sum() == pytest.approx(1.0)


# ---- holding a portfolio -----------------------------------------------------------------------------------------------------
def test_a_rebalanced_portfolio_drifts_within_the_month_and_is_reset_at_the_next():
    index = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
    returns = pd.DataFrame({"A": [0.01, 0.01, 0.01, 0.01], "B": [0.0, 0.0, 0.0, 0.0]}, index=index)
    portfolio = portfolios.rebalanced_portfolio(returns, pd.Series({"A": 0.5, "B": 0.5}))
    assert portfolio.iloc[0] == pytest.approx(0.005)                       # day one: half of 1%
    assert portfolio.iloc[1] == pytest.approx(1.01005 / 1.005 - 1)         # A has grown, so it is more than half by day two
    assert portfolio.iloc[2] == pytest.approx(0.005)                       # a new month: back to half and half


def test_equal_weights_rebalanced_monthly_agree_with_the_sector_index_function():
    rng = np.random.default_rng(5)
    returns = pd.DataFrame(rng.normal(0, 0.01, (200, 4)), index=days(200), columns=list("ABCD"))
    ours = portfolios.rebalanced_portfolio(returns, pd.Series(0.25, index=returns.columns))
    assert ours.to_numpy() == pytest.approx(analysis.equal_weight_return(returns, "M").to_numpy())


def test_a_portfolio_can_follow_different_targets_in_different_months():
    index = days(50, "2024-01-01")
    returns = pd.DataFrame({"A": 0.01, "B": 0.0}, index=index)
    months = sorted(set(index.to_period("M")))
    targets = pd.DataFrame({"A": [1.0, 0.0], "B": [0.0, 1.0]}, index=pd.PeriodIndex(months[:2], freq="M"))
    portfolio = portfolios.rebalanced_portfolio(returns, targets)
    in_month = portfolio.index.to_period("M")
    assert portfolio[in_month == months[0]].round(10).eq(0.01).all()          # all in A in the first month
    assert portfolio[in_month == months[1]].eq(0.0).all()                     # all in B in the second
    assert set(in_month) == set(months[:2])                                   # and the third month, which has no target, is left out


def test_turnover_is_zero_when_nothing_has_to_change_and_positive_when_the_target_moves():
    index = days(80, "2024-01-01")
    returns = pd.DataFrame({"A": 0.0, "B": 0.0}, index=index)
    months = pd.PeriodIndex(sorted(set(index.to_period("M")))[:3], freq="M")
    still = pd.DataFrame({"A": 0.5, "B": 0.5}, index=months)
    assert portfolios.average_turnover(returns, still) == pytest.approx(0.0)
    switching = pd.DataFrame({"A": [1.0, 0.0, 1.0], "B": [0.0, 1.0, 0.0]}, index=months)
    assert portfolios.average_turnover(returns, switching) == pytest.approx(1.0)


def test_month_ends_are_the_last_market_days():
    index = pd.DatetimeIndex(["2024-01-29", "2024-01-31", "2024-02-01", "2024-02-28", "2024-02-29", "2024-03-01"])
    assert list(portfolios.month_ends(index)) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29"), pd.Timestamp("2024-03-01")]


# ---- testing a rule out of sample -------------------------------------------------------------------------------------------
def persistent_market(n=700, seed=0):
    """Eight sectors; each has its own steady drift, so a sector that did well tends to keep doing well."""
    rng = np.random.default_rng(seed)
    drift = np.linspace(-0.0004, 0.0012, 8)
    index = days(n)
    returns = pd.DataFrame(rng.normal(drift, 0.01, (n, 8)), index=index, columns=[f"S{i}" for i in range(8)])
    safe = pd.Series(0.0002, index=index)
    return returns, safe, index[0] - pd.Timedelta(days=1)


RULES = {"equal": portfolios.equal_weight_rule, "winners": portfolios.top_sharpe_rule(2), "losers": portfolios.top_sharpe_rule(2, worst=True),
         "min_variance": portfolios.min_variance_rule, "inverse_volatility": portfolios.inverse_volatility_rule}


def test_walk_forward_starts_after_a_full_look_back_window_and_holds_valid_weights():
    returns, safe, first = persistent_market()
    result = portfolios.walk_forward(returns, safe, RULES, lookback_months=12, first_date=first)
    equal = result["weights"]["equal"]
    assert equal.index[0] >= (returns.index[0] + pd.DateOffset(months=12)).to_period("M")
    for name, frame in result["weights"].items():
        assert (frame.sum(axis=1).round(9) == 1.0).all() and (frame >= -1e-12).all().all(), name
    assert result["returns"].index[0].to_period("M") == equal.index[0]
    assert len(result["ic"]) == len(equal) and result["ic"].between(-1, 1).all()


def test_the_rules_cannot_look_ahead():
    returns, safe, first = persistent_market(seed=2)
    original = portfolios.walk_forward(returns, safe, RULES, 12, first)
    cut = returns.index[-150]
    changed = returns.copy()
    changed.loc[changed.index > cut] = np.random.default_rng(99).normal(0.005, 0.03, size=changed.loc[changed.index > cut].shape)
    altered = portfolios.walk_forward(changed, safe, RULES, 12, first)
    decided_before = [p for p in original["weights"]["winners"].index if (p - 1).end_time < cut]        # months decided on data up to the cut
    assert len(decided_before) > 10
    for name in RULES:
        assert original["weights"][name].loc[decided_before].to_numpy() == pytest.approx(altered["weights"][name].loc[decided_before].to_numpy())


def test_winners_do_better_than_losers_when_past_performance_persists_and_ic_is_positive():
    returns, safe, first = persistent_market(n=900, seed=4)
    result = portfolios.walk_forward(returns, safe, RULES, 12, first)
    total = (1 + result["returns"]).prod() - 1
    assert total["winners"] > total["equal"] > total["losers"]
    summary = portfolios.summarise_ic(result["ic"])
    assert summary["mean"] > 0.1 and summary["months"] == len(result["ic"]) and 0 <= summary["share_positive"] <= 1


def test_with_no_persistence_the_information_coefficient_is_near_zero():
    rng = np.random.default_rng(8)
    index = days(900)
    returns = pd.DataFrame(rng.normal(0.0003, 0.01, (900, 8)), index=index, columns=[f"S{i}" for i in range(8)])
    result = portfolios.walk_forward(returns, pd.Series(0.0002, index=index), {"equal": portfolios.equal_weight_rule}, 12, index[0] - pd.Timedelta(days=1))
    assert abs(portfolios.summarise_ic(result["ic"])["mean"]) < 0.15


# ---- how sectors group ------------------------------------------------------------------------------------------------------
def factor_data(columns=6, n=1500, loading=0.9, seed=0):
    rng = np.random.default_rng(seed)
    common = rng.normal(size=(n, 1))
    return pd.DataFrame(loading * common + np.sqrt(1 - loading ** 2) * rng.normal(size=(n, columns)), columns=list("ABCDEF")[:columns])


def test_principal_components_find_the_common_factor():
    strong = portfolios.principal_components(factor_data(loading=0.9))
    assert strong["share"][0] > 0.75 and strong["share"].sum() == pytest.approx(1.0) and strong["effective_bets"] < 2
    assert (strong["loadings"][0] > 0).all()
    none = portfolios.principal_components(factor_data(loading=0.0))
    assert none["share"][0] < 0.25 and none["effective_bets"] > 5


def test_clustering_groups_the_assets_that_move_together():
    rng = np.random.default_rng(1)
    first, second = rng.normal(size=(2000, 1)), rng.normal(size=(2000, 1))
    data = pd.DataFrame({"a": first[:, 0] + 0.3 * rng.normal(size=2000), "c": second[:, 0] + 0.3 * rng.normal(size=2000),
                         "b": first[:, 0] + 0.3 * rng.normal(size=2000), "d": second[:, 0] + 0.3 * rng.normal(size=2000)})
    corr = data.corr().to_numpy()
    merges = portfolios.average_linkage(corr)
    assert len(merges) == 3 and merges[0][2] <= merges[1][2] <= merges[2][2]
    order = portfolios.leaf_order(merges, 4)
    assert sorted(order) == [0, 1, 2, 3]
    names = list(data.columns)
    ordered = [names[i] for i in order]
    assert abs(ordered.index("a") - ordered.index("b")) == 1 and abs(ordered.index("c") - ordered.index("d")) == 1
    labels = portfolios.cut_clusters(merges, 4, 2)
    assert labels[names.index("a")] == labels[names.index("b")] != labels[names.index("c")] == labels[names.index("d")]
    assert sorted(set(portfolios.cut_clusters(merges, 4, 4))) == [0, 1, 2, 3] and set(portfolios.cut_clusters(merges, 4, 1)) == {0}
