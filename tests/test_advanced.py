"""The second layer of analysis on made-up markets where the true betas, alphas and groups are known."""

import numpy as np
import pandas as pd
import pytest

from psxsec import advanced, analysis, config, metrics, portfolios

MARKET = analysis.MARKET


@pytest.fixture(autouse=True)
def quick_bootstrap(monkeypatch):
    monkeypatch.setattr(config, "BOOTSTRAP_DRAWS", 300)


def made_up(n=1300, seed=0, alpha_first=0.0008):
    """Six sectors with known betas to a market factor; the first has a real alpha. Returns the indexes, the rest-of-market series, cash."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2021-10-28", periods=n)
    market = pd.Series(rng.normal(0.0004, 0.010, n), index=index)
    betas = [0.5, 1.0, 1.5, 0.8, 1.2, 0.9]
    sectors = [f"S{i}" for i in range(6)]
    data = {s: b * market + rng.normal(0, 0.004, n) + (alpha_first if i == 0 else 0.0) for i, (s, b) in enumerate(zip(sectors, betas, strict=True))}
    idx = pd.DataFrame(data)
    idx[MARKET] = market
    rest = pd.DataFrame({s: market + rng.normal(0, 0.001, n) for s in sectors}, index=index)
    safe = pd.Series(0.0001, index=index)
    return idx, rest, safe, sectors, betas, index[0] - pd.Timedelta(days=1)


def test_the_rest_of_the_market_leaves_the_sector_out():
    rng = np.random.default_rng(1)
    index = pd.bdate_range("2024-01-01", periods=60)
    returns = pd.DataFrame(rng.normal(0, 0.01, (60, 4)), index=index, columns=["a1", "a2", "b1", "b2"])
    rest = advanced.market_excluding(returns, {"A": ["a1", "a2"], "B": ["b1", "b2"]}, ["A", "B"])
    assert rest["A"].to_numpy() == pytest.approx(analysis.equal_weight_return(returns[["b1", "b2"]], "M").to_numpy())
    assert rest["B"].to_numpy() == pytest.approx(analysis.equal_weight_return(returns[["a1", "a2"]], "M").to_numpy())


def test_beta_alpha_and_the_multiple_testing_correction_on_a_known_market():
    idx, rest, safe, sectors, betas, base = made_up()
    years = len(idx) / 245.4
    table, summary = advanced.risk_and_alpha(idx, safe, rest, sectors, base, years)
    assert table["beta"].to_numpy() == pytest.approx(betas, abs=0.12)
    assert table.loc["S0", "alpha"] == pytest.approx(0.0008 * 245.4, abs=0.07)                                  # a daily 0.08% is about 20% a year
    assert table.loc["S0", "alpha_p_adjusted"] < 0.05 and (table.drop(index="S0")["alpha_p_adjusted"] > 0.05).sum() >= 4
    assert (table["alpha_p_adjusted"] >= table["alpha_p"] - 1e-9).all()                                          # the correction can only make it harder
    assert table["market_model_r2"].between(0, 1).all() and summary["trials"] == 6 and summary["alpha_adjusted_significant"] >= 1
    assert (table["cvar_95"] <= table["var_95"]).all() and (table["sortino"] > table["alpha"] * 0 - 5).all()
    assert table.loc["S2", "up_capture"] > table.loc["S0", "up_capture"]                                        # the higher-beta sector captures more of the rises
    assert 0 <= table["dsr"].max() <= 1 and summary["expected_best_sharpe"] > 0


def test_macro_inputs_keep_only_full_months_and_measure_the_changes():
    index = pd.bdate_range("2024-01-24", "2024-06-05")                    # January and June are part months
    rng = np.random.default_rng(2)
    idx = pd.DataFrame(rng.normal(0, 0.01, (len(index), 2)), index=index, columns=["A", "B"])
    rest = idx.copy()
    safe = pd.Series(0.0002, index=index)
    policy = pd.DataFrame({"effective_date": pd.to_datetime(["2023-01-01", "2024-03-12"]), "policy_rate_pct": [20.0, 18.0]})
    fx = pd.Series(np.linspace(280, 290, len(index)), index=index)
    frame = advanced.macro_inputs(idx, safe, rest, ["A", "B"], policy, fx)
    assert list(frame.index) == ["2024-02", "2024-03", "2024-04", "2024-05"]
    assert frame["d_policy_rate_pp"].tolist() == [0.0, -2.0, 0.0, 0.0]
    february_end = fx.loc[:"2024-02-29"].iloc[-1]
    january_end = fx.loc[:"2024-01-31"].iloc[-1]
    assert frame.loc["2024-02", "d_rupees_pct"] == pytest.approx((february_end / january_end - 1) * 100)
    assert frame.loc["2024-02", "ret__A"] == pytest.approx((1 + idx.loc["2024-02", "A"]).prod() - 1)
    assert {"ret__A", "ret__B", "rest__A", "rest__B", "safe"} <= set(frame.columns)


def test_macro_betas_recover_known_sensitivities():
    rng = np.random.default_rng(3)
    months = 240                                                           # a long made-up history so the estimates are tight
    market = rng.normal(0.01, 0.05, months)
    d_rate = np.where(rng.random(months) < 0.4, rng.choice([-1.0, -0.5, 0.5, 1.0, 2.0], months), 0.0)
    d_fx = rng.normal(0.8, 2.0, months)
    safe = np.full(months, 0.01)
    frame = pd.DataFrame({"safe": safe, "d_policy_rate_pp": d_rate, "d_rupees_pct": d_fx, "rest__A": market + safe})
    frame["ret__A"] = safe + 0.9 * market + (1.5 * d_rate - 0.4 * d_fx + rng.normal(0, 1.0, months)) / 100
    betas = advanced.macro_betas(frame)
    row = betas.loc["A"]
    assert row["macro_market_beta"] == pytest.approx(0.9, abs=0.1) and row["rate_beta"] == pytest.approx(1.5, abs=0.3)
    assert row["fx_beta"] == pytest.approx(-0.4, abs=0.15) and row["rate_p"] < 0.01 and row["fx_p"] < 0.01
    assert 0 <= row["rate_q"] <= 1


def synthetic_strategies(n=1100, seed=4):
    """Eight sectors with steady, different drifts (so the past is informative) and a market that is their average.

    In twelve such markets (seeds 0 to 11) the past winners beat the past losers in eleven and the information coefficient was
    positive in all twelve; this seed is a typical one.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2021-10-28", periods=n)
    sectors = [f"S{i}" for i in range(8)]
    idx = pd.DataFrame(rng.normal(np.linspace(-0.0003, 0.0012, 8), 0.01, (n, 8)), index=index, columns=sectors)
    idx[MARKET] = analysis.equal_weight_return(idx[sectors], "M")
    return idx, pd.Series(0.0002, index=index), sectors, index[0] - pd.Timedelta(days=1)


def test_the_out_of_sample_test_reports_every_strategy_and_cannot_beat_itself():
    idx, safe, sectors, base = synthetic_strategies()
    result = advanced.out_of_sample(idx, safe, sectors, base, ppy=245.4)
    table = result["table"]
    assert list(table.index) == ["equal_weight", "winners", "losers", "min_variance", "inverse_volatility", "market"]
    assert np.isnan(table.loc["equal_weight", "vs_equal_p"]) and table.loc["equal_weight", "sharpe_vs_equal"] == 0
    assert table.loc["winners", "sharpe"] > table.loc["losers", "sharpe"]                       # the drifts persist in this made-up market
    assert (table["vs_equal_p_adjusted"].dropna() >= table["vs_equal_p"].dropna()).all()
    assert len(result["sensitivity"]) == 6 and result["sensitivity"]["difference"].notna().all()
    assert result["months"] == len(set(result["returns"].index.to_period("M"))) and result["ic_summary"]["months"] == len(result["ic"])
    assert table.loc["min_variance", "volatility"] < table.loc["equal_weight", "volatility"] * 1.05


def grouped_market(n=2500, seed=4):
    """Eight sectors: one market factor, plus a shared factor within each of two groups of four."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2021-10-28", periods=n)
    market, group = rng.normal(0, 0.01, n), rng.normal(0, 0.01, (n, 2))
    sectors = [f"G{g}_{i}" for g in range(2) for i in range(4)]
    idx = pd.DataFrame({s: market + group[:, int(s[1])] * 0.9 + rng.normal(0, 0.004, n) for s in sectors}, index=index)
    rest = pd.DataFrame({s: market + rng.normal(0, 0.0005, n) for s in sectors}, index=index)
    return idx, pd.Series(0.0, index=index), rest, sectors


def test_structure_finds_the_market_and_then_the_groups_that_remain():
    idx, safe, rest, sectors = grouped_market()
    result = advanced.structure(idx, safe, rest, sectors)
    assert result["share"][0] > 0.4 and result["effective_bets"] < 4
    corr = result["residual_correlations"]
    within = np.mean([corr.loc[a, b] for a in sectors for b in sectors if a != b and a[:2] == b[:2]])
    across = np.mean([corr.loc[a, b] for a in sectors for b in sectors if a[:2] != b[:2]])
    assert within > 0.3 and across < 0.1
    assert all(pair["first"][:2] == pair["second"][:2] for pair in result["strongest_pairs"])
    assert all(len({name[:2] for name in group}) == 1 for group in result["groups"])          # no group mixes the two true groups
    assert sorted(name for group in result["groups"] for name in group) == sorted(sectors) and set(result["order"]) == set(sectors)


def test_presets_are_valid_portfolios_and_the_minimum_variance_one_has_less_variance():
    idx, safe, sectors, _ = synthetic_strategies(seed=7)
    table = advanced.presets(idx, safe, sectors)
    assert list(table.index) == ["equal_weight", "best_sharpe", "min_variance", "inverse_volatility"]
    assert table.sum(axis=1).to_numpy() == pytest.approx(1.0) and (table >= -1e-12).all().all()
    assert (table.loc["best_sharpe"] > 0).sum() == config.TOP_SECTORS
    daily = {name: portfolios.rebalanced_portfolio(idx[sectors], table.loc[name]) for name in table.index}
    assert daily["min_variance"].std() < daily["equal_weight"].std()
    ratio = (idx[sectors].sub(safe, axis=0)).mean() / idx[sectors].std()
    assert set(table.loc["best_sharpe"][table.loc["best_sharpe"] > 0].index) == set(ratio.nlargest(config.TOP_SECTORS).index)
    assert metrics.annualised_return(daily["equal_weight"], 4.0) > -1
