"""The second layer of analysis, built on the sector indexes of `analysis`:

* the market model: how much of a sector's return is just the market, and whether any alpha survives having looked at 22 sectors;
* more measures of risk (downside risk, tail losses, capture ratios, how long a fall lasts) and of how much to believe a Sharpe ratio;
* a test of whether the ranking could have been used, with every rule seeing only the past;
* what moves the sectors: the market, interest rates and the rupee, and how the sectors group together.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, metrics, portfolios, stats
from .analysis import MARKET, equal_weight_return, weekly


def monthly(returns):
    """Compound daily returns into calendar months."""
    return (1 + returns).groupby(returns.index.to_period("M")).prod() - 1


def market_excluding(returns: pd.DataFrame, members: dict[str, list[str]], sectors: list[str]) -> pd.DataFrame:
    """For each sector, the return of the rest of the market: an equal-weighted portfolio, rebalanced monthly, of every qualifying
    company that is not in that sector. A sector is a part of the whole market, so comparing it with the whole would partly
    compare it with itself."""
    return pd.DataFrame({s: equal_weight_return(returns[[c for c in returns.columns if c not in set(members[s])]], "M") for s in sectors})


# ---------------------------------------------------------------------------
# Risk and the market model
# ---------------------------------------------------------------------------
def risk_and_alpha(idx: pd.DataFrame, safe: pd.Series, rest: pd.DataFrame, sectors: list[str], base_date: pd.Timestamp, years: float) -> tuple[pd.DataFrame, dict]:
    """More measures of risk, and each sector's alpha and beta against the rest of the market."""
    ppy = metrics.periods_per_year(len(idx), years)
    excess = idx[sectors].sub(safe, axis=0)
    start = pd.Series([100.0], index=[base_date])
    monthly_sector, monthly_rest = monthly(idx[sectors]), monthly(rest)

    week_sector, week_safe = weekly(idx[sectors], safe)
    week_rest, _ = weekly(rest, safe)
    y = week_sector.sub(week_safe, axis=0).to_numpy()
    x = week_rest.sub(week_safe, axis=0).to_numpy()
    weeks_per_year = len(week_safe) / years
    check = stats.alpha_reality_check(y[1:], x[1:], x[:-1], config.BOOTSTRAP_DRAWS, config.BOOTSTRAP_BLOCK_WEEKS, config.SEED)

    daily_sharpe = excess.mean() / excess.std(ddof=1)
    rows = {}
    for k, sector in enumerate(sectors):
        returns, ex = idx[sector], excess[sector]
        var, shortfall = metrics.tail_risk(returns)
        skew, kurt = metrics.moments(ex)
        up, down = metrics.capture_ratios(monthly_sector[sector], monthly_rest[sector])
        fit = stats.market_model(y[:, k], x[:, k], config.HAC_LAGS_WEEKLY)
        level = pd.concat([start, metrics.cumulative(returns)])
        rows[sector] = {
            "sortino": metrics.sortino(ex, ppy), "var_95": var, "cvar_95": shortfall, "skew": skew, "excess_kurtosis": kurt - 3,
            "longest_fall_months": metrics.longest_drawdown_days(level) / (ppy / 12), "up_capture": up, "down_capture": down,
            "beta": fit["beta"], "beta_se": fit["beta_se"], "alpha": fit["alpha"] * weeks_per_year, "alpha_se": fit["alpha_se"] * weeks_per_year,
            "alpha_t": fit["alpha_t"], "market_model_r2": fit["r2"], "alpha_p_adjusted": check["p_adjusted"][k],
            "psr_zero": stats.probabilistic_sharpe(daily_sharpe[sector], len(ex), skew, kurt, 0.0),
            "dsr": stats.deflated_sharpe(daily_sharpe[sector], len(ex), skew, kurt, daily_sharpe.to_numpy())}
    table = pd.DataFrame.from_dict(rows, orient="index")
    table["alpha_p"] = stats.normal_p(table["alpha_t"])
    table["alpha_q"] = stats.benjamini_hochberg(table["alpha_p"])
    summary = {"expected_best_sharpe": stats.expected_max_sharpe(daily_sharpe.to_numpy()) * np.sqrt(ppy), "trials": len(sectors),
               "weeks": len(week_safe), "weeks_per_year": weeks_per_year,
               "alpha_raw_positive": int(((table["alpha_p"] < 0.05) & (table["alpha"] > 0)).sum()),
               "alpha_raw_negative": int(((table["alpha_p"] < 0.05) & (table["alpha"] < 0)).sum()),
               "alpha_adjusted_significant": int((table["alpha_p_adjusted"] < 0.05).sum()),
               "alpha_fdr_significant": int((table["alpha_q"] < 0.05).sum()),
               "null_largest_t_95": float(np.quantile(check["largest_t"], 0.95))}
    return table, summary


# ---------------------------------------------------------------------------
# Interest rates and the rupee
# ---------------------------------------------------------------------------
def macro_inputs(idx: pd.DataFrame, safe: pd.Series, rest: pd.DataFrame, sectors: list[str], policy: pd.DataFrame, fx: pd.Series) -> pd.DataFrame:
    """One row per full calendar month: each sector's return and the rest of the market's, the return on cash, the change in the
    policy rate (percentage points) and the change in rupees per dollar (percent; positive means a weaker rupee)."""
    months = idx.index.to_period("M")
    full = sorted(set(months))[1:-1]                      # the first and last months of the window are only part months
    ends = portfolios.month_ends(idx.index)
    end_periods = ends.to_period("M")
    rate = pd.Series(metrics.rate_in_force(ends, policy), index=end_periods)
    rupees = pd.Series(fx.loc[ends].to_numpy(), index=end_periods)
    frame = pd.concat([monthly(idx[sectors]).loc[full].add_prefix("ret__"), monthly(rest).loc[full].add_prefix("rest__")], axis=1)
    frame["safe"] = ((1 + safe).groupby(months).prod() - 1).loc[full]
    frame["d_policy_rate_pp"] = rate.diff().loc[full]
    frame["d_rupees_pct"] = rupees.pct_change().loc[full] * 100
    frame.index = frame.index.astype(str)
    frame.index.name = "month"
    return frame


def macro_betas(frame: pd.DataFrame) -> pd.DataFrame:
    """Each sector's monthly excess return regressed on the rest of the market's, the change in the policy rate and the change
    in the rupee. Returns (in percent) per one percentage point more on the policy rate and per one percent weaker rupee."""
    sectors = [c[len("ret__"):] for c in frame.columns if c.startswith("ret__")]
    rows = {}
    for sector in sectors:
        y = 100 * (frame[f"ret__{sector}"] - frame["safe"]).to_numpy()
        design = np.column_stack([np.ones(len(frame)), 100 * (frame[f"rest__{sector}"] - frame["safe"]), frame["d_policy_rate_pp"], frame["d_rupees_pct"]])
        fit = stats.ols(y, design, config.HAC_LAGS_MONTHLY)
        rows[sector] = {"macro_market_beta": fit.coef[1], "rate_beta": fit.coef[2], "rate_se": fit.se[2], "rate_t": fit.t[2],
                        "fx_beta": fit.coef[3], "fx_se": fit.se[3], "fx_t": fit.t[3], "macro_r2": fit.r2}
    out = pd.DataFrame.from_dict(rows, orient="index")
    for name in ("rate", "fx"):
        out[f"{name}_p"] = stats.normal_p(out[f"{name}_t"])
        out[f"{name}_q"] = stats.benjamini_hochberg(out[f"{name}_p"])
    return out


# ---------------------------------------------------------------------------
# Could the ranking have been used?
# ---------------------------------------------------------------------------
def _performance(returns: pd.Series, safe: pd.Series, ppy: float, start_date: pd.Timestamp) -> dict:
    years = len(returns) / ppy
    level = pd.concat([pd.Series([100.0], index=[start_date]), metrics.cumulative(returns)])
    return {"cagr": metrics.annualised_return(returns, years), "volatility": metrics.volatility(returns, ppy),
            "sharpe": metrics.sharpe(returns - safe, ppy), "max_drawdown": metrics.max_drawdown(level)["max_drawdown"]}


def out_of_sample(idx: pd.DataFrame, safe: pd.Series, sectors: list[str], base_date: pd.Timestamp, ppy: float) -> dict:
    """Test rules for weighting the sectors, each seeing only the past, against holding them all equally and against the market."""
    returns = idx[sectors]
    rules = {"equal_weight": portfolios.equal_weight_rule, "winners": portfolios.top_sharpe_rule(config.TOP_SECTORS),
             "losers": portfolios.top_sharpe_rule(config.TOP_SECTORS, worst=True), "min_variance": portfolios.min_variance_rule,
             "inverse_volatility": portfolios.inverse_volatility_rule}
    result = portfolios.walk_forward(returns, safe, rules, config.LOOKBACK_MONTHS, base_date)
    strategies = result["returns"].copy()
    strategies["market"] = idx[MARKET].loc[strategies.index]
    safe_test = safe.loc[strategies.index]
    start_date = returns.index[returns.index < strategies.index[0]].max()
    draws = metrics.bootstrap_sharpe(strategies.sub(safe_test, axis=0), ppy, config.BOOTSTRAP_DRAWS, config.BOOTSTRAP_BLOCK, config.SEED)
    reference = list(strategies.columns).index("equal_weight")
    rows = {}
    for k, name in enumerate(strategies.columns):
        row = _performance(strategies[name], safe_test, ppy, start_date)
        row["turnover"] = portfolios.average_turnover(returns, result["weights"][name]) if name in result["weights"] else float("nan")
        difference = draws[:, k] - draws[:, reference]
        compared = k != reference
        row.update({"sharpe_vs_equal": row["sharpe"] - metrics.sharpe(strategies["equal_weight"] - safe_test, ppy),
                    "vs_equal_lo": float(np.percentile(difference, 2.5)) if compared else float("nan"),
                    "vs_equal_hi": float(np.percentile(difference, 97.5)) if compared else float("nan"),
                    "vs_equal_p": float(min(1.0, 2 * min((difference <= 0).mean(), (difference >= 0).mean()))) if compared else float("nan")})
        rows[name] = row
    table = pd.DataFrame.from_dict(rows, orient="index")
    table["vs_equal_p_adjusted"] = (table["vs_equal_p"] * table["vs_equal_p"].notna().sum()).clip(upper=1.0)       # Bonferroni: five comparisons were made
    table.index.name = "strategy"

    sensitivity = []
    for lookback in (*config.LOOKBACK_CHECKS[:1], config.LOOKBACK_MONTHS, *config.LOOKBACK_CHECKS[1:]):
        for top in (config.TOP_SECTORS, *config.TOP_CHECKS):
            other = portfolios.walk_forward(returns, safe, {"equal_weight": portfolios.equal_weight_rule, "winners": portfolios.top_sharpe_rule(top)},
                                            lookback, base_date)
            test = other["returns"]
            excess = test.sub(safe.loc[test.index], axis=0)
            diff = metrics.bootstrap_sharpe(excess, ppy, config.BOOTSTRAP_DRAWS, config.BOOTSTRAP_BLOCK, config.SEED)
            spread = diff[:, 1] - diff[:, 0]
            sensitivity.append({"lookback_months": lookback, "top_sectors": top, "months": len(set(test.index.to_period("M"))),
                                "sharpe_winners": metrics.sharpe(excess["winners"], ppy), "sharpe_equal_weight": metrics.sharpe(excess["equal_weight"], ppy),
                                "difference": metrics.sharpe(excess["winners"], ppy) - metrics.sharpe(excess["equal_weight"], ppy),
                                "p": float(min(1.0, 2 * min((spread <= 0).mean(), (spread >= 0).mean()))),
                                "mean_information_coefficient": portfolios.summarise_ic(other["ic"])["mean"]})
    return {"returns": strategies, "table": table, "ic": result["ic"], "ic_summary": portfolios.summarise_ic(result["ic"]),
            "sensitivity": pd.DataFrame(sensitivity), "weights": result["weights"], "first_month": str(strategies.index[0].to_period("M")),
            "months": len(set(strategies.index.to_period("M")))}


# ---------------------------------------------------------------------------
# How the sectors group, and portfolios to try
# ---------------------------------------------------------------------------
def market_adjusted(idx: pd.DataFrame, safe: pd.Series, rest: pd.DataFrame, sectors: list[str]) -> pd.DataFrame:
    """Each sector's daily excess return with the part that the rest of the market explains (its return today and yesterday) taken out."""
    out = {}
    for sector in sectors:
        y = (idx[sector] - safe).to_numpy()
        x = (rest[sector] - safe).to_numpy()
        design = np.column_stack([np.ones(len(y) - 1), x[1:], x[:-1]])
        coef = np.linalg.lstsq(design, y[1:], rcond=None)[0]
        out[sector] = pd.Series(y[1:] - design @ coef, index=idx.index[1:])
    return pd.DataFrame(out)


def structure(idx: pd.DataFrame, safe: pd.Series, rest: pd.DataFrame, sectors: list[str]) -> dict:
    """How much the sectors share, and what is left once the market is taken out.

    Almost all of what sectors share is the market, so clustering their raw correlations only separates a few odd sectors from
    the rest. Clustering the correlations of what is left over shows which sectors still move together beyond the market.
    """
    excess = idx[sectors].sub(safe, axis=0)
    components = portfolios.principal_components(excess)
    leftover = market_adjusted(idx, safe, rest, sectors)
    left_components = portfolios.principal_components(leftover)
    corr = leftover.corr()
    merges = portfolios.average_linkage(corr.to_numpy())
    order = portfolios.leaf_order(merges, len(sectors))
    labels = portfolios.cut_clusters(merges, len(sectors), config.CLUSTERS)
    upper = np.triu(np.ones(corr.shape, dtype=bool), 1)
    pairs = corr.where(upper).stack().sort_values(ascending=False)
    raw = excess.corr().to_numpy()
    return {"share": components["share"], "effective_bets": components["effective_bets"], "loadings": components["loadings"],
            "mean_correlation": float(raw[np.triu_indices(len(sectors), 1)].mean()),
            "residual_mean_correlation": float(corr.to_numpy()[np.triu_indices(len(sectors), 1)].mean()),
            "residual_effective_bets": left_components["effective_bets"], "residual_correlations": corr.loc[[sectors[i] for i in order], [sectors[i] for i in order]],
            "order": [sectors[i] for i in order], "labels": dict(zip(sectors, labels, strict=True)),
            "groups": [[sectors[i] for i in order if labels[i] == g] for g in sorted(set(labels))],
            "strongest_pairs": [{"first": a, "second": b, "correlation": float(value)} for (a, b), value in pairs.head(5).items()]}


def presets(idx: pd.DataFrame, safe: pd.Series, sectors: list[str]) -> pd.DataFrame:
    """Weights for the portfolio builder, chosen with hindsight from the whole five years: a way to see what diversification does,
    not a test of anything (the out-of-sample test is the test)."""
    returns = idx[sectors]
    excess = returns.sub(safe, axis=0)
    ratio = excess.mean() / excess.std(ddof=1)
    cov = portfolios.shrunk_covariance(returns)[0]
    top = ratio.nlargest(config.TOP_SECTORS).index
    table = pd.DataFrame({"equal_weight": 1 / len(sectors), "best_sharpe": pd.Series(1 / config.TOP_SECTORS, index=top).reindex(sectors, fill_value=0.0),
                          "min_variance": portfolios.min_variance(cov), "inverse_volatility": portfolios.inverse_volatility(cov)}, index=sectors)
    return table.T
