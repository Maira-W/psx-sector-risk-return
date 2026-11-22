"""The tables Power BI imports, all derived from data/processed so the report, the dashboard and the documents agree."""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config, metrics, portfolios
from ..analysis import MARKET

CASH = "Safe return (policy rate)"           # the column of daily cash returns in sector_daily_returns.csv
CASH_LABEL = "Cash at the policy rate"
CLASSES = ("Significant after the correction", "Significant on its own only", "Not significant")      # in the order the legend shows them
PRESET_LABELS = {"equal_weight": "Equal weight", "best_sharpe": f"Best {config.TOP_SECTORS} by Sharpe", "min_variance": "Minimum variance",
                 "inverse_volatility": "Inverse volatility"}
MIN_WEIGHT = 0.0005          # a preset's holding below this is not listed (the weights of a preset add up to one)

TABLE_NOTES = {
    "sectors": "One row per ranked sector: return, risk, the chance of each rank, alpha and beta, rate and rupee effects, group. The main table.",
    "market": "One row of single numbers about the whole market, cash and the tests (read by cards).",
    "market_years": "The whole market's return in each of the five twelve-month periods.",
    "levels_top": "Weekly growth of 100 rupees for the best three sectors, the whole market and cash.",
    "levels": "Weekly growth of 100 rupees and fall from the last peak for every sector, the market and cash.",
    "year_returns": "Each sector's return in each of the five twelve-month periods. Filtered by the sector slicer.",
    "rank_choices": "Each sector's Sharpe ratio and position under the main analysis and the 12 other ways of doing it.",
    "robustness_summary": "The 12 other ways of doing the analysis, with how closely each agrees with the main ranking.",
    "strategies": "The five rules and the whole market in the out-of-sample test, with their Sharpe ratios and p-values.",
    "strategy_levels": "Weekly growth of 100 rupees for each rule in the out-of-sample test.",
    "info_coeff": "Each month, the rank correlation between past Sharpe ratios and the next month's returns.",
    "sensitivity": "The best-sectors rule again with other look-backs and numbers of sectors.",
    "presets": "The weights of the four preset portfolios (holdings below 0.05% are left out).",
    "preset_stats": "Return, volatility, worst fall and Sharpe ratio of the four preset portfolios. Filters the weights.",
    "preset_levels": "Weekly growth of 100 rupees for the four portfolios and the whole market.",
    "components": "Share of the variation in sector returns carried by each principal component.",
    "groups": "The groups of sectors that move together once the market is taken out.",
    "notes": "The text on the About page.",
}

NOTES = [
    ("Companies", "Every company in the KSE All Share Index on 28 October 2026 that trades regularly: a price on nearly every market day "
                  "and trading on at least 90% of them. Investment funds, ETFs and property trusts are left out. Only companies "
                  "listed today are included, so returns are flattered a little."),
    ("Prices and dividends", "Yahoo Finance (not an official source). Wrong prices and one-day jumps beyond the exchange's daily limit are "
                             "corrected by fixed rules and every correction is listed in data/processed/price_corrections.csv. "
                             "The daily return is (close + dividend) / previous close - 1."),
    ("Sector indexes", "Equal amounts of each qualifying company in the sector, put back to equal at the start of every month, with "
                       "dividends included. Sectors with fewer than four qualifying companies are not ranked."),
    ("Return and risk", "Compound annual return, volatility (standard deviation of daily returns scaled to a year), worst fall from a peak, "
                        "and the Sharpe ratio: average daily return above cash divided by its standard deviation, scaled to a year."),
    ("Safe return", "Cash at the State Bank of Pakistan's policy rate, accrued daily. The table of changes, with a source for every row, "
                    "is in data/reference/policy_rate.csv."),
    ("How sure", "The days are resampled 2,000 times in blocks of about 10 (a stationary block bootstrap) and the sectors re-ranked each time. "
                 "The analysis is also repeated in 12 other ways (who is included, how the index is built, which dates)."),
    ("Alpha and beta", "Weekly returns above cash of each sector against the rest of the market (every company outside that sector), with "
                       "last week's market return included (Dimson). Beta is the sum of the two slopes; alpha is the intercept, annualised. "
                       "Standard errors allow for related weeks (Newey and West)."),
    ("Correction for many tests", "The best of 22 sectors looks good by chance, so each p-value is also corrected: the weeks are resampled, "
                                  "the largest t-statistic over all sectors is recorded each time and a sector counts only if it beats that "
                                  "(Romano and Wolf). 'q' is the looser false-discovery-rate version. The deflated Sharpe ratio asks whether "
                                  "the best of 22 could reach its level by luck."),
    ("Interest rates and the rupee", "For each of 59 full months, a sector's return above cash is explained by the rest of the market's, the "
                                     "change in the policy rate and the change in rupees per dollar. Effects are in percent of return."),
    ("Groups", "Principal components of the sectors' correlations show how many independent bets there are. Groups come from clustering the "
               "correlations that remain once the rest of the market is taken out of each sector; they describe these five years."),
    ("Out-of-sample test", "On the last day of each month a rule sees only the previous 12 months and chooses weights for the next month. "
                           "Each rule's Sharpe ratio is compared with equal weights by resampling the days; the p-value is multiplied by the "
                           "five comparisons made (Bonferroni)."),
    ("Preset portfolios", "Weights worked out with hindsight from the whole five years and held with monthly rebalancing. They show what "
                          "diversification does; they are not a test and not a forecast. No trading costs are included."),
    ("Limits", "Five years is one history. Past performance does not predict future returns. This is analysis, not investment advice."),
]


@dataclass
class Results:
    summary: dict
    ranked: pd.DataFrame
    market: pd.Series
    daily: pd.DataFrame
    robust_sharpe: pd.DataFrame
    robust_summary: pd.DataFrame
    structure: pd.DataFrame
    walk: pd.DataFrame
    walk_summary: pd.DataFrame
    ic: pd.DataFrame
    sensitivity: pd.DataFrame
    presets: pd.DataFrame


def load() -> Results:
    p = config.PROCESSED
    table = pd.read_csv(p / "sector_summary.csv", dtype={"sector_code": str})
    return Results(
        summary=json.loads((p / "summary.json").read_text(encoding="utf-8")),
        ranked=table[table["ranked"]].sort_values("sharpe", ascending=False).reset_index(drop=True),
        market=table[table["sector"] == MARKET].iloc[0],
        daily=pd.read_csv(p / "sector_daily_returns.csv", index_col=0, parse_dates=True),
        robust_sharpe=pd.read_csv(p / "robustness_sharpe.csv", index_col=0),
        robust_summary=pd.read_csv(p / "robustness_summary.csv"),
        structure=pd.read_csv(p / "sector_structure.csv"),
        walk=pd.read_csv(p / "walk_forward_daily_returns.csv", index_col=0, parse_dates=True),
        walk_summary=pd.read_csv(p / "walk_forward_summary.csv", index_col="strategy"),
        ic=pd.read_csv(p / "walk_forward_ic.csv", parse_dates=["decision_date"]),
        sensitivity=pd.read_csv(p / "walk_forward_sensitivity.csv"),
        presets=pd.read_csv(p / "portfolio_presets.csv", index_col="portfolio"),
    )


def _month(iso: str) -> str:
    return f"{pd.Timestamp(iso):%b %Y}"


def _class(p_alone: float, p_corrected: float) -> str:
    return CLASSES[0] if p_corrected < 0.05 else CLASSES[1] if p_alone < 0.05 else CLASSES[2]


def _int(series: pd.Series) -> pd.Series:
    return series.round().astype("int64")


def _weekly(levels: pd.DataFrame) -> pd.DataFrame:
    return levels.resample("W-FRI").last()


def _growth(returns: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    """Growth of 100 from `start`, as the daily series with the start day first."""
    head = pd.DataFrame([[100.0] * returns.shape[1]], index=[start], columns=returns.columns)
    return pd.concat([head, 100 * (1 + returns).cumprod()])


def _long(frame: pd.DataFrame, series_name: str, value: str, order: dict[str, int]) -> pd.DataFrame:
    out = frame.rename_axis("date").reset_index().melt(id_vars="date", var_name=series_name, value_name=value)
    out["series_order"] = out[series_name].map(order).astype("int64")
    return out.sort_values(["series_order", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# the tables
# ---------------------------------------------------------------------------
def sectors(r: Results) -> pd.DataFrame:
    t = r.ranked.merge(r.structure[["sector", "component_1", "component_2"]], on="sector", how="left")
    return pd.DataFrame({
        "sector": t["sector"], "short_name": t["sector"].map(lambda s: config.SHORT_NAMES.get(s, s)),
        "n_companies": t["n_companies"], "n_in_kse100": t["n_in_kse100"], "rank_sharpe": _int(t["rank_sharpe"]),
        "cagr": t["cagr"], "volatility": t["volatility"], "max_drawdown": t["max_drawdown"], "sharpe": t["sharpe"],
        "sharpe_lo": t["sharpe_lo"], "sharpe_hi": t["sharpe_hi"], "rank_median": t["rank_median"],
        "rank_lo": _int(t["rank_lo"]), "rank_hi": _int(t["rank_hi"]), "p_top1": t["p_top1"], "p_top3": t["p_top3"],
        "p_beats_market": t["p_beats_market"], "dividend_points": t["dividend_points"], "usd_cagr": t["usd_cagr"],
        "correlation_with_market": t["correlation_with_market"], "typical_company_sharpe": t["typical_company_sharpe"],
        "best_company": t["best_company"],
        "sortino": t["sortino"], "var_95": t["var_95"], "cvar_95": t["cvar_95"], "skew": t["skew"], "excess_kurtosis": t["excess_kurtosis"],
        "longest_fall_months": t["longest_fall_months"], "up_capture": t["up_capture"], "down_capture": t["down_capture"],
        "beta": t["beta"], "beta_se": t["beta_se"], "alpha": t["alpha"], "alpha_se": t["alpha_se"], "alpha_t": t["alpha_t"],
        "alpha_p": t["alpha_p"], "alpha_p_adjusted": t["alpha_p_adjusted"], "alpha_q": t["alpha_q"], "dsr": t["dsr"],
        "market_model_r2": t["market_model_r2"], "alpha_class": [_class(a, b) for a, b in zip(t["alpha_p"], t["alpha_p_adjusted"], strict=True)],
        "alpha_class_order": [CLASSES.index(_class(a, b)) for a, b in zip(t["alpha_p"], t["alpha_p_adjusted"], strict=True)],
        "rate_beta": t["rate_beta"], "rate_se": t["rate_se"], "rate_p": t["rate_p"], "rate_q": t["rate_q"],
        "rate_class": [_class(a, b) for a, b in zip(t["rate_p"], t["rate_q"], strict=True)],
        "fx_beta": t["fx_beta"], "fx_se": t["fx_se"], "fx_p": t["fx_p"], "fx_q": t["fx_q"],
        "fx_class": [_class(a, b) for a, b in zip(t["fx_p"], t["fx_q"], strict=True)], "macro_r2": t["macro_r2"],
        "group_letter": t["group"].map(lambda g: config.GROUP_LETTERS[int(g)]), "component_1": t["component_1"], "component_2": t["component_2"],
    })


def market(r: Results) -> pd.DataFrame:
    s, m, top = r.summary, r.market, r.summary["top_sharpe"][0]
    a, mac, st, wf = s["alpha"], s["macro"], s["structure"], s["walk_forward"]
    shares = r.robust_sharpe
    half = metrics.spearman(shares["First half of the window"], shares["Second half of the window"])
    robust = s["robustness"]
    return pd.DataFrame([{
        "market_cagr": m["cagr"], "market_volatility": m["volatility"], "market_max_drawdown": m["max_drawdown"], "market_sharpe": m["sharpe"],
        "market_usd_cagr": m["usd_cagr"], "market_total_return": m["total_return"], "cash_cagr": s["safe"]["cagr"],
        "policy_rate_start": s["safe"]["policy_rate_start"], "policy_rate_peak": s["safe"]["policy_rate_peak"],
        "policy_rate_end": s["safe"]["policy_rate_end"], "years": s["window"]["years"], "market_days": s["window"]["market_days"],
        "n_companies": s["n_companies"], "n_sectors_ranked": s["n_sectors_ranked"],
        "top_sector": top["sector"], "top_sharpe": top["sharpe"], "top_p1": top["p_top1"],
        "method_rank_correlation_median": robust["method"]["median_rank_correlation"],
        "method_rank_correlation_min": robust["method"]["min_rank_correlation"],
        "period_rank_correlation_min": robust["period"]["min_rank_correlation"], "half_correlation": half,
        "alpha_raw_positive": a["alpha_raw_positive"], "alpha_raw_negative": a["alpha_raw_negative"],
        "alpha_adjusted_significant": a["alpha_adjusted_significant"], "alpha_fdr_significant": a["alpha_fdr_significant"],
        "best_alpha_sector": a["best_sector"], "best_alpha": a["best_alpha"], "best_alpha_p": a["best_alpha_p"],
        "best_alpha_p_adjusted": a["best_alpha_p_adjusted"], "best_dsr": a["best_dsr"], "expected_best_sharpe": a["expected_best_sharpe"],
        "null_largest_t_95": a["null_largest_t_95"],
        "pc1_share": st["pc1_share"], "effective_bets": st["effective_bets"], "mean_correlation": st["mean_correlation"],
        "residual_mean_correlation": st["residual_mean_correlation"], "n_rate_fdr": len(mac["rate_fdr"]), "n_fx_fdr": len(mac["fx_fdr"]),
        "macro_months": mac["months"], "policy_changes": mac["policy_changes"],
        "wf_months": wf["months"], "wf_lookback": wf["lookback_months"], "wf_top": wf["top_sectors"], "ic_mean": wf["ic"]["mean"],
        "ic_t": wf["ic"]["t"], "ic_share_positive": wf["ic"]["share_positive"],
    }])


def market_years(r: Results) -> pd.DataFrame:
    edges = r.summary["window"]["year_edges"]
    return pd.DataFrame({"period_index": range(1, 6), "period": [f"{_month(edges[k - 1])} to {_month(edges[k])}" for k in range(1, 6)],
                         "period_return": [r.market[f"year{k}"] for k in range(1, 6)]})


def year_returns(r: Results) -> pd.DataFrame:
    years = market_years(r)
    rows = []
    for t in r.ranked.itertuples():
        for k in range(1, 6):
            rows.append((t.sector, k, years.loc[k - 1, "period"], getattr(t, f"year{k}")))
    return pd.DataFrame(rows, columns=["sector", "period_index", "period", "period_return"])


def _levels(r: Results) -> tuple[pd.DataFrame, pd.DataFrame]:
    names = list(r.ranked["sector"]) + [MARKET]
    returns = r.daily[names].copy()
    returns[CASH_LABEL] = r.daily[CASH]
    levels = _growth(returns, pd.Timestamp(r.summary["window"]["base_date"]))
    drawdown = levels / levels.cummax() - 1
    return _weekly(levels), drawdown.resample("W-FRI").min() * 100


def levels(r: Results) -> pd.DataFrame:
    weekly, falls = _levels(r)
    order = {name: i for i, name in enumerate(weekly.columns, 1)}
    out = _long(weekly.round(1), "series", "level", order)
    drawdown = _long(falls.round(1), "series", "drawdown_pct", order)
    return out.merge(drawdown[["date", "series", "drawdown_pct"]], on=["date", "series"]).drop(columns="series_order")


def levels_top(r: Results) -> pd.DataFrame:
    weekly, _ = _levels(r)
    keep = [MARKET, *r.ranked["sector"].head(3), CASH_LABEL]
    return _long(weekly[keep].round(1), "series", "level", {name: i for i, name in enumerate(keep, 1)})


# Shorter names for the places where a chart has little room (an axis label or a legend entry).
CHOICE_SHORT = {
    "Main result": "Main result", "KSE-100 companies only": "KSE-100 only", "Must trade on 80% of days": "Trades 80% of days",
    "Must trade on 95% of days": "Trades 95% of days", "Without companies with price corrections": "No price corrections",
    "Rebalanced every day": "Daily rebalancing", "Weekly returns": "Weekly returns", "Without each sector's best company": "No best company",
    "Typical company (median)": "Median company", "First half of the window": "First half", "Second half of the window": "Second half",
    "Start 3 months later": "Starts 3 months later", "End 3 months earlier": "Ends 3 months earlier",
}
STRATEGY_SHORT = {
    "Equal weight, all sectors": "Equal weight", "Best sectors of the past year": "Best sectors", "Worst sectors of the past year": "Worst sectors",
    "Minimum variance": "Min. variance", "Inverse volatility": "Inverse vol.", "Whole market": "Whole market",
}


def rank_choices(r: Results) -> pd.DataFrame:
    sharpes = r.robust_sharpe.loc[r.ranked["sector"]]
    ranks = sharpes.rank(ascending=False, method="min")                 # 1 is best; blank where a sector is not in that analysis
    kinds = {"Main result": "Main result"}
    kinds.update({c: ("Method" if k == "method" else "Dates") for c, k in zip(r.robust_summary["choice"], r.robust_summary["kind"], strict=True)})
    rows = [(sector, choice, CHOICE_SHORT[choice], order, kinds[choice], sharpes.loc[sector, choice], ranks.loc[sector, choice])
            for sector in sharpes.index for order, choice in enumerate(sharpes.columns, 1)]
    return pd.DataFrame(rows, columns=["sector", "choice", "choice_short", "choice_order", "kind", "sharpe", "position"])


def robustness_summary(r: Results) -> pd.DataFrame:
    t = r.robust_summary
    outcome = np.where(~t["top_tested"], "not in this analysis", np.where(t["same_top_sector"], "still first",
                       np.where(t["main_top_sector_still_top3"], "still in the top 3", "falls out of the top 3")))
    return pd.DataFrame({"choice": t["choice"], "choice_order": range(2, len(t) + 2), "kind": t["kind"].map({"method": "Method", "period": "Dates"}),
                         "sectors_compared": t["sectors_compared"], "rank_correlation": t["rank_correlation"],
                         "top3_in_common": t["top3_in_common"], "main_top_sector": outcome})


def strategies(r: Results) -> pd.DataFrame:
    keys = list(config.STRATEGIES)
    t = r.walk_summary.loc[keys].copy()
    t.insert(0, "strategy_key", keys)
    t.insert(1, "strategy", [config.STRATEGIES[k] for k in keys])
    t.insert(2, "strategy_order", range(1, len(keys) + 1))
    return t.reset_index(drop=True)[["strategy_key", "strategy", "strategy_order", "cagr", "volatility", "max_drawdown", "sharpe", "sharpe_vs_equal",
                                     "vs_equal_lo", "vs_equal_hi", "vs_equal_p", "vs_equal_p_adjusted", "turnover"]]


def strategy_levels(r: Results) -> pd.DataFrame:
    start = r.daily.index[r.daily.index < r.walk.index[0]].max()
    weekly = _weekly(_growth(r.walk[list(config.STRATEGIES)], start)).round(1)
    out = _long(weekly.rename(columns=config.STRATEGIES), "strategy", "level", {name: i for i, name in enumerate(config.STRATEGIES.values(), 1)})
    out = out.rename(columns={"series_order": "strategy_order"})
    out["strategy_short"] = out["strategy"].map(STRATEGY_SHORT)
    return out[["date", "strategy", "strategy_short", "strategy_order", "level"]]


def info_coeff(r: Results) -> pd.DataFrame:
    t = r.ic.copy()
    t["direction"] = np.where(t["information_coefficient"] > 0, "Pointed the right way", "Pointed the wrong way")
    return t


def sensitivity(r: Results) -> pd.DataFrame:
    t = r.sensitivity.copy()
    t.insert(2, "setting", [f"{a} months, {b} sectors" for a, b in zip(t["lookback_months"], t["top_sectors"], strict=True)])
    t.insert(3, "setting_order", range(1, len(t) + 1))
    return t.rename(columns={"sharpe_winners": "sharpe_rule"})


def _preset_returns(r: Results) -> dict[str, pd.Series]:
    sectors_ = list(r.ranked["sector"])
    returns = r.daily[sectors_]
    return {key: portfolios.rebalanced_portfolio(returns, r.presets.loc[key, sectors_]) for key in PRESET_LABELS}


def presets(r: Results) -> pd.DataFrame:
    rows = []
    for order, (key, label) in enumerate(PRESET_LABELS.items(), 1):
        weights = r.presets.loc[key]
        for sector in r.ranked["sector"]:
            if weights[sector] > MIN_WEIGHT:
                rows.append((label, order, sector, config.SHORT_NAMES.get(sector, sector), weights[sector]))
    return pd.DataFrame(rows, columns=["preset", "preset_order", "sector", "short_name", "weight"])


def preset_stats(r: Results) -> pd.DataFrame:
    years = r.summary["window"]["years"]
    ppy = len(r.daily) / years
    safe = r.daily[CASH]
    rows = []
    for order, (key, series) in enumerate(_preset_returns(r).items(), 1):
        level = pd.concat([pd.Series([100.0], index=[r.daily.index[0] - pd.Timedelta(days=1)]), metrics.cumulative(series)])
        rows.append((PRESET_LABELS[key], order, float(metrics.annualised_return(series, years)), float(metrics.volatility(series, ppy)),
                     float(metrics.max_drawdown(level)["max_drawdown"]), float(metrics.sharpe(series - safe, ppy)),
                     int((r.presets.loc[key, list(r.ranked["sector"])] > MIN_WEIGHT).sum())))
    return pd.DataFrame(rows, columns=["preset", "preset_order", "cagr", "volatility", "max_drawdown", "sharpe", "sectors_held"])


def preset_levels(r: Results) -> pd.DataFrame:
    frame = pd.DataFrame({PRESET_LABELS[k]: v for k, v in _preset_returns(r).items()})
    frame[MARKET] = r.daily[MARKET]
    weekly = _weekly(_growth(frame, pd.Timestamp(r.summary["window"]["base_date"]))).round(1)
    return _long(weekly, "series", "level", {name: i for i, name in enumerate(weekly.columns, 1)})


def components(r: Results) -> pd.DataFrame:
    shares = r.summary["structure"]["shares"]
    return pd.DataFrame({"component_number": range(1, len(shares) + 1), "component": [str(i) for i in range(1, len(shares) + 1)], "share": shares})


def groups(r: Results) -> pd.DataFrame:
    g = r.summary["structure"]["groups"]
    return pd.DataFrame({"group_letter": [config.GROUP_LETTERS[i] for i in range(len(g))], "n_sectors": [len(x) for x in g],
                         "sectors": [", ".join(x) for x in g]})


def notes() -> pd.DataFrame:
    return pd.DataFrame(NOTES, columns=["topic", "note"])


def make_tables(r: Results | None = None) -> dict[str, pd.DataFrame]:
    """Table name -> data, in the order they appear in the model. Floats are rounded to six decimals (the weights to nine, so that
    a portfolio's holdings still add up to one)."""
    r = r or load()
    tables = {
        "sectors": sectors(r), "market": market(r), "market_years": market_years(r), "levels_top": levels_top(r), "levels": levels(r),
        "year_returns": year_returns(r), "rank_choices": rank_choices(r), "robustness_summary": robustness_summary(r),
        "strategies": strategies(r), "strategy_levels": strategy_levels(r), "info_coeff": info_coeff(r), "sensitivity": sensitivity(r),
        "presets": presets(r), "preset_stats": preset_stats(r), "preset_levels": preset_levels(r), "components": components(r),
        "groups": groups(r), "notes": notes(),
    }
    return {name: frame.round(9 if name == "presets" else 6) for name, frame in tables.items()}
