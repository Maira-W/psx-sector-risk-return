"""The committed data and results: consistent with each other, with the rules, and with what can be recomputed from them."""

import numpy as np
import pandas as pd
import pytest

from psxsec import advanced, analysis, config, metrics, stats


def test_the_universe_matches_the_manifest_and_the_sector_list(universe, manifest):
    entry = manifest[config.SCREENER_FILE]
    assert len(universe) == entry["in_all_share"] and int(universe["in_kse100"].sum()) == entry["in_kse100"] == 100
    assert universe["symbol"].is_unique
    assert set(universe["sector_code"]) <= set(config.SECTORS)
    assert (universe["sector"] == universe["sector_code"].map(config.SECTORS)).all()
    assert entry["listings"] > entry["in_all_share"]          # rights issues and bonds are listed too, and are not in the index


def test_the_policy_rate_table_is_in_order_and_each_row_has_a_source(summary):
    policy = pd.read_csv(config.POLICY_RATE_FILE, parse_dates=["effective_date"])
    assert policy["effective_date"].is_monotonic_increasing and policy["effective_date"].is_unique
    assert policy["policy_rate_pct"].diff().iloc[1:].ne(0).all()                      # every row is a change
    assert policy["source"].str.startswith("https://").all()
    assert policy["effective_date"].iloc[0] <= pd.Timestamp(summary["window"]["base_date"])    # the table covers the whole window
    assert policy["policy_rate_pct"].max() == 22.0 and policy.loc[policy["policy_rate_pct"].idxmax(), "effective_date"].year == 2023


def test_status_follows_the_rules(status, universe):
    assert set(status["status"]) <= {"qualifies", "traded on too few days", "prices missing on too many days",
                                     "listed after the start of the window", "no prices on Yahoo Finance"}
    qualifying = status[status["status"] == "qualifies"]
    assert (qualifying["history_share"] >= config.MIN_HISTORY_SHARE).all() and (qualifying["traded_share"] >= config.MIN_TRADED_SHARE).all()
    thin = status[status["status"] == "traded on too few days"]
    assert (thin["traded_share"] < config.MIN_TRADED_SHARE).all()
    assert not status["sector_code"].isin(config.NOT_OPERATING).any()                 # funds, ETFs and REITs never get this far
    assert set(status["symbol"]) <= set(universe["symbol"])


def test_the_funnel_only_narrows(summary):
    funnel = pd.read_csv(config.PROCESSED / "universe_funnel.csv")
    assert funnel["companies"].is_monotonic_decreasing
    assert funnel["companies"].iloc[-1] == summary["n_companies"]


def test_daily_sector_returns_are_complete_and_plausible(daily, summary, sectors):
    assert daily.index.is_monotonic_increasing and daily.index.is_unique
    assert len(daily) == summary["window"]["market_days"]
    assert not daily.isna().any().any()
    assert (daily["Safe return (policy rate)"] > 0).all()
    ranked = [s for s in sectors["sector"][sectors["ranked"] | (sectors["sector"] == analysis.MARKET)]]
    assert daily[ranked].abs().max().max() < 0.25      # an average of four or more companies does not move 25% in a day
    assert daily.drop(columns="Safe return (policy rate)").abs().max().max() < 1.0


def test_every_headline_measure_can_be_recomputed_from_the_daily_returns(sectors, daily, summary):
    base = pd.Timestamp(summary["window"]["base_date"])
    years = summary["window"]["years"]
    ppy = len(daily) / years
    safe = daily["Safe return (policy rate)"]
    for r in sectors.itertuples():
        returns = daily[r.sector]
        level = pd.concat([pd.Series([100.0], index=[base]), metrics.cumulative(returns)])
        assert metrics.annualised_return(returns, years) == pytest.approx(r.cagr, abs=1e-5), r.sector
        assert metrics.volatility(returns, ppy) == pytest.approx(r.volatility, abs=1e-5), r.sector
        assert metrics.max_drawdown(level)["max_drawdown"] == pytest.approx(r.max_drawdown, abs=1e-5), r.sector
        assert metrics.sharpe(returns - safe, ppy) == pytest.approx(r.sharpe, abs=1e-4), r.sector
        assert metrics.total_return(returns) == pytest.approx(r.total_return, abs=1e-4), r.sector


def test_the_five_yearly_returns_compound_to_the_total(sectors):
    compounded = (1 + sectors[[f"year{k}" for k in range(1, 6)]]).prod(axis=1)
    assert compounded.to_numpy() == pytest.approx((1 + sectors["total_return"]).to_numpy(), rel=1e-4)


def test_ranked_sectors_follow_the_rules_and_the_bootstrap_is_coherent(sectors, summary):
    ranked = sectors[sectors["ranked"]]
    assert len(ranked) == summary["n_sectors_ranked"] and (ranked["n_companies"] >= config.MIN_SECTOR_STOCKS).all()
    assert not ranked["sector_code"].isin(config.UNRANKED).any() and not sectors["sector_code"].isin(config.NOT_OPERATING).any()
    assert sorted(ranked["rank_sharpe"].astype(int)) == list(range(1, len(ranked) + 1))
    assert ranked["p_top1"].sum() == pytest.approx(1.0, abs=1e-6) and ranked["p_top3"].sum() == pytest.approx(3.0, abs=1e-6)
    assert (ranked["sharpe_lo"] < ranked["sharpe_hi"]).all() and (ranked["p_top3"] >= ranked["p_top1"]).all()
    assert (ranked["rank_lo"] <= ranked["rank_median"]).all() and (ranked["rank_median"] <= ranked["rank_hi"]).all()
    unranked = sectors[~sectors["ranked"] & (sectors["sector"] != analysis.MARKET)]
    assert (unranked["n_companies"] < config.MIN_SECTOR_STOCKS).all()
    assert sectors["n_companies"].max() == summary["n_companies"] and sectors.loc[sectors["sector"] == analysis.MARKET, "n_companies"].item() == summary["n_companies"]


def test_rank_distribution_gives_each_position_to_exactly_one_sector_per_resample():
    dist = pd.read_csv(config.PROCESSED / "sector_rank_distribution.csv", index_col=0)
    assert dist.sum(axis=1).to_numpy() == pytest.approx(1.0, abs=1e-3) and dist.sum(axis=0).to_numpy() == pytest.approx(1.0, abs=1e-3)


def test_robustness_table_starts_from_the_main_result(sectors):
    sharpes = pd.read_csv(config.PROCESSED / "robustness_sharpe.csv", index_col=0)
    ranked = sectors[sectors["ranked"]].set_index("sector")
    assert sharpes.columns[0] == "Main result"
    assert sharpes["Main result"].dropna().sort_index().to_numpy() == pytest.approx(ranked["sharpe"].sort_index().to_numpy(), abs=1e-3)
    summary_rows = pd.read_csv(config.PROCESSED / "robustness_summary.csv")
    assert len(summary_rows) == len(sharpes.columns) - 1
    assert summary_rows["rank_correlation"].between(-1, 1).all()
    assert set(summary_rows["kind"]) == {"method", "period"}
    assert set(summary_rows.loc[summary_rows["kind"] == "period", "choice"]) == set(analysis.PERIOD_CHOICES)


def test_stock_summary_agrees_with_the_sector_summary(stocks, sectors, status):
    qualifying = status[status["status"] == "qualifies"]
    assert sorted(stocks["symbol"]) == sorted(qualifying["symbol"])
    sizes = stocks.groupby("sector")["symbol"].count()
    for r in sectors[sectors["sector"] != analysis.MARKET].itertuples():
        assert sizes[r.sector] == r.n_companies, r.sector
    assert (stocks["traded_share"] >= config.MIN_TRADED_SHARE).all()


def test_price_corrections_listed_for_review_really_are_beyond_the_rules():
    fixed = pd.read_csv(config.PROCESSED / "price_corrections.csv")
    if len(fixed):
        up, down = (config.JUMP_RATIO - 1) * 100, (1 / config.JUMP_RATIO - 1) * 100
        assert ((fixed["price_move_pct"] >= up - 0.01) | (fixed["price_move_pct"] <= down + 0.01)).all()
        assert not fixed.duplicated(["symbol", "date"]).any()
        assert fixed["treatment"].str.startswith(("bad price", "price return set to zero")).all()


def test_market_model_results_can_be_recomputed_from_the_committed_returns(sectors, daily, summary):
    rest = pd.read_csv(config.PROCESSED / "market_excluding_sector_daily_returns.csv", index_col=0, parse_dates=True)
    safe = daily["Safe return (policy rate)"]
    ranked = sectors[sectors["ranked"]]
    weekly_sector, weekly_safe = analysis.weekly(daily[list(ranked["sector"])], safe)
    weekly_rest, _ = analysis.weekly(rest[list(ranked["sector"])], safe)
    weeks_per_year = len(weekly_safe) / summary["window"]["years"]
    for r in ranked.itertuples():
        fit = stats.market_model(weekly_sector[r.sector] - weekly_safe, weekly_rest[r.sector] - weekly_safe, config.HAC_LAGS_WEEKLY)
        assert fit["beta"] == pytest.approx(r.beta, abs=1e-4) and fit["alpha"] * weeks_per_year == pytest.approx(r.alpha, abs=1e-4), r.sector
        assert fit["alpha_t"] == pytest.approx(r.alpha_t, abs=1e-3), r.sector
    assert (ranked["alpha_p_adjusted"] >= ranked["alpha_p"] - 1e-9).all() and ranked[["alpha_p", "alpha_q", "alpha_p_adjusted", "dsr", "psr_zero"]].apply(
        lambda column: column.between(0, 1).all()).all()
    assert (ranked["cvar_95"] <= ranked["var_95"]).all() and (ranked["var_95"] < 0).all()
    assert summary["alpha"]["alpha_adjusted_significant"] == int((ranked["alpha_p_adjusted"] < 0.05).sum())
    assert summary["alpha"]["trials"] == len(ranked) and summary["alpha"]["expected_best_sharpe"] > 0


def test_macro_sensitivities_can_be_recomputed_from_the_monthly_table(sectors, summary):
    frame = pd.read_csv(config.PROCESSED / "macro_monthly.csv", index_col="month")
    betas = advanced.macro_betas(frame)
    ranked = sectors[sectors["ranked"]].set_index("sector")
    assert set(betas.index) == set(ranked.index) and len(frame) == summary["macro"]["months"]
    for column in ("rate_beta", "rate_t", "fx_beta", "fx_t", "macro_market_beta"):
        assert betas[column].reindex(ranked.index).to_numpy() == pytest.approx(ranked[column].to_numpy(), abs=1e-4), column
    assert not frame.isna().any().any() and (frame["d_policy_rate_pp"] != 0).sum() == summary["macro"]["policy_changes"]
    assert set(summary["macro"]["rate_fdr"]) <= set(summary["macro"]["rate_positive"]) | set(summary["macro"]["rate_negative"])


def test_out_of_sample_results_can_be_recomputed_from_the_daily_returns(summary, daily):
    strategies = pd.read_csv(config.PROCESSED / "walk_forward_daily_returns.csv", index_col=0, parse_dates=True)
    table = pd.read_csv(config.PROCESSED / "walk_forward_summary.csv", index_col="strategy")
    safe = daily["Safe return (policy rate)"].loc[strategies.index]
    ppy = len(daily) / summary["window"]["years"]
    assert list(table.index) == list(config.STRATEGIES)
    assert strategies.index[0].to_period("M") == pd.Period(summary["walk_forward"]["first_month"]) and strategies.index[-1] == daily.index[-1]
    assert len(set(strategies.index.to_period("M"))) == summary["walk_forward"]["months"]
    for name, row in table.iterrows():
        returns = strategies[name]
        assert metrics.sharpe(returns - safe, ppy) == pytest.approx(row["sharpe"], abs=1e-4), name
        assert metrics.annualised_return(returns, len(returns) / ppy) == pytest.approx(row["cagr"], abs=1e-4), name
        assert metrics.volatility(returns, ppy) == pytest.approx(row["volatility"], abs=1e-4), name
    assert strategies["market"].to_numpy() == pytest.approx(daily["Whole market"].loc[strategies.index].to_numpy(), abs=1e-6)
    assert table.loc["equal_weight", "sharpe_vs_equal"] == 0 and (table["vs_equal_p_adjusted"].dropna() >= table["vs_equal_p"].dropna() - 1e-9).all()
    sensitivity = pd.read_csv(config.PROCESSED / "walk_forward_sensitivity.csv")
    assert len(sensitivity) == (len(config.LOOKBACK_CHECKS) + 1) * (len(config.TOP_CHECKS) + 1) and sensitivity["p"].between(0, 1).all()
    ic = pd.read_csv(config.PROCESSED / "walk_forward_ic.csv", index_col=0)["information_coefficient"]
    assert len(ic) == summary["walk_forward"]["ic"]["months"] and ic.between(-1, 1).all()


def test_structure_and_presets_are_complete_and_valid(sectors, summary):
    ranked = set(sectors.loc[sectors["ranked"], "sector"])
    structure = pd.read_csv(config.PROCESSED / "sector_structure.csv")
    assert set(structure["sector"]) == ranked and structure["group"].nunique() == config.CLUSTERS
    assert sum(len(g) for g in summary["structure"]["groups"]) == len(ranked)
    assert summary["structure"]["pc1_share"] > summary["structure"]["pc2_share"] > 0 and summary["structure"]["effective_bets"] > 1
    corr = pd.read_csv(config.PROCESSED / "market_adjusted_correlations.csv", index_col=0)
    assert set(corr.index) == ranked and (corr.to_numpy().diagonal().round(6) == 1).all() and (corr.to_numpy() == corr.to_numpy().T).all()
    presets = pd.read_csv(config.PROCESSED / "portfolio_presets.csv", index_col="portfolio")
    assert set(presets.columns) == ranked and presets.sum(axis=1).to_numpy() == pytest.approx(1.0, abs=1e-6) and (presets >= -1e-9).all().all()


def test_manifest_records_the_prices_it_describes(manifest):
    entry = manifest[config.PRICES_FILE]
    assert entry["symbols_with_data"] + len(entry["symbols_without_data"]) == entry["symbols_requested"]
    assert entry["first_date"] < entry["last_date"] and len(entry["sha256"]) == 64
    assert np.isfinite(entry["rows"])
