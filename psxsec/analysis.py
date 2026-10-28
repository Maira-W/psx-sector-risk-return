"""Sector indexes, their risk and return, how sure we can be of the ranking, and how it changes under other choices.

A sector index is the equal-weighted average of its companies' daily total returns (price change plus dividends). Risk and
return are measured over the five-year window; the safe return is cash earning the State Bank's policy rate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config, metrics

MARKET = "Whole market"


@dataclass
class Data:
    total: pd.DataFrame     # daily total return of every qualifying company
    price: pd.DataFrame     # daily price-only return of the same companies
    wide: pd.DataFrame      # total returns of the qualifying companies plus those that traded on fewer days
    stocks: pd.DataFrame    # one row per operating company: sector, KSE-100 membership, how often it traded, status
    safe: pd.Series         # what cash at the policy rate earned over each return period
    base_date: pd.Timestamp
    years: float
    flagged: list = field(default_factory=list)   # companies whose prices needed a correction (build.corrections)

    @property
    def ppy(self) -> float:
        return metrics.periods_per_year(len(self.total), self.years)


def load() -> Data:
    stocks = pd.read_csv(config.PROCESSED / "stock_status.csv", dtype={"sector_code": str})
    read = {"index_col": 0, "parse_dates": True}
    total = pd.read_csv(config.INTERIM / "returns_total.csv.gz", **read)
    price = pd.read_csv(config.INTERIM / "returns_price.csv.gz", **read)
    wide = pd.read_csv(config.INTERIM / "returns_total_wide.csv.gz", **read)
    window = json.loads((config.INTERIM / "data_quality.json").read_text(encoding="utf-8"))["window"]
    base = pd.Timestamp(window["base_date"])
    policy = pd.read_csv(config.POLICY_RATE_FILE, parse_dates=["effective_date"])
    flagged = sorted(pd.read_csv(config.PROCESSED / "price_corrections.csv")["symbol"].unique())
    return Data(total, price, wide, stocks, metrics.safe_return(total.index, base, policy), base, window["years"], flagged)


# ---------------------------------------------------------------------------
# Building the indexes
# ---------------------------------------------------------------------------
def sector_members(stocks: pd.DataFrame, available, min_n: int) -> dict[str, list[str]]:
    """Sector name -> its companies that are in `available`, for sectors with at least `min_n` of them."""
    pool = stocks[stocks["symbol"].isin(list(available)) & ~stocks["sector_code"].isin(config.UNRANKED)]
    members = {sector: group["symbol"].tolist() for sector, group in pool.groupby("sector", sort=True)}
    return {sector: symbols for sector, symbols in members.items() if len(symbols) >= min_n}


def equal_weight_return(returns: pd.DataFrame, rebalance: str = "M") -> pd.Series:
    """Return of an equal-weighted portfolio of the columns of `returns`.

    rebalance="M": equal weights on the first day of every month, then left to drift (buy and hold) until the next month.
    rebalance="D": equal weights again every period, which is the plain average of the returns. Rebalancing every day
    flatters shares that trade rarely (their price bounces between the bid and the ask), so the monthly version is the default.
    """
    if rebalance == "D":
        return returns.mean(axis=1)
    month = pd.Series(returns.index.to_period(rebalance), index=returns.index)
    value = (1 + returns).groupby(month.to_numpy()).cumprod().mean(axis=1)       # growth since the start of the month, averaged
    previous = value.shift(1).where(month == month.shift(1), 1.0)                # a new month starts again from 1
    return value / previous - 1


def index_returns(returns: pd.DataFrame, members: dict[str, list[str]], market: list[str] | None = None, rebalance: str = "M") -> pd.DataFrame:
    """Equal-weighted return of each sector, and of the whole market if `market` is given."""
    out = {sector: equal_weight_return(returns[symbols], rebalance) for sector, symbols in members.items()}
    if market is not None:
        out[MARKET] = equal_weight_return(returns[market], rebalance)
    return pd.DataFrame(out)


def measure(idx: pd.DataFrame, safe: pd.Series, base_date: pd.Timestamp, years: float) -> pd.DataFrame:
    """Return, risk and the Sharpe ratio of every column of daily index returns."""
    ppy = metrics.periods_per_year(len(idx), years)
    excess = idx.sub(safe, axis=0)
    start = pd.Series([100.0], index=[base_date])
    rows = {}
    for name in idx:
        returns = idx[name]
        drawdown = metrics.max_drawdown(pd.concat([start, metrics.cumulative(returns)]))
        cagr = metrics.annualised_return(returns, years)
        rows[name] = {"total_return": metrics.total_return(returns), "cagr": cagr, "volatility": metrics.volatility(returns, ppy),
                      "sharpe": metrics.sharpe(excess[name], ppy), "max_drawdown": drawdown["max_drawdown"],
                      "peak_date": drawdown["peak_date"], "trough_date": drawdown["trough_date"],
                      "recovery_date": drawdown["recovery_date"], "drawdown_now": drawdown["drawdown_now"],
                      "calmar": metrics.calmar(cagr, drawdown["max_drawdown"])}
    return pd.DataFrame.from_dict(rows, orient="index")


def year_edges(dates: pd.DatetimeIndex, base_date: pd.Timestamp, n: int = config.WINDOW_YEARS) -> list[pd.Timestamp]:
    """The last market day of each of the n twelve-month periods that make up the window, starting from the base date."""
    edges = [base_date]
    for k in range(1, n):
        edges.append(dates[dates <= base_date + pd.DateOffset(years=k)].max())
    edges.append(dates[-1])
    return edges


def yearly_returns(idx: pd.DataFrame, edges: list[pd.Timestamp]) -> pd.DataFrame:
    out = {}
    for k in range(len(edges) - 1):
        part = idx[(idx.index > edges[k]) & (idx.index <= edges[k + 1])]
        out[f"year{k + 1}"] = (1 + part).prod() - 1
    return pd.DataFrame(out)


def stock_table(d: Data) -> pd.DataFrame:
    """Return and risk of every qualifying company."""
    idx = d.total
    stats = measure(idx, d.safe, d.base_date, d.years)
    price_cagr = (1 + d.price).prod() ** (1 / d.years) - 1
    table = d.stocks.set_index("symbol").loc[idx.columns, ["company", "sector", "in_kse100", "traded_share"]].join(stats)
    table["price_cagr"] = price_cagr
    table["dividend_points"] = table["cagr"] - table["price_cagr"]
    return table.reset_index()


# ---------------------------------------------------------------------------
# How sure can we be?
# ---------------------------------------------------------------------------
def bootstrap_summary(excess: pd.DataFrame, ranked: list[str], ppy: float) -> dict:
    """Resample the days and re-rank the sectors many times; report intervals and how often each sector comes first."""
    columns = [*ranked, MARKET]
    draws = metrics.bootstrap_sharpe(excess[columns], ppy, config.BOOTSTRAP_DRAWS, config.BOOTSTRAP_BLOCK, config.SEED)
    sector_draws, market_draws = draws[:, :-1], draws[:, -1]
    ranks = metrics.ranks(sector_draws)
    k = len(ranked)
    distribution = np.stack([(ranks == r).mean(axis=0) for r in range(1, k + 1)], axis=1)     # sector x rank
    return {"sharpe_lo": np.percentile(sector_draws, 2.5, axis=0), "sharpe_hi": np.percentile(sector_draws, 97.5, axis=0),
            "rank_median": np.median(ranks, axis=0), "rank_lo": np.percentile(ranks, 2.5, axis=0),
            "rank_hi": np.percentile(ranks, 97.5, axis=0), "p_top1": (ranks == 1).mean(axis=0),
            "p_top3": (ranks <= 3).mean(axis=0), "p_beats_market": (sector_draws > market_draws[:, None]).mean(axis=0),
            "market_lo": float(np.percentile(market_draws, 2.5)), "market_hi": float(np.percentile(market_draws, 97.5)),
            "distribution": distribution}


# ---------------------------------------------------------------------------
# Other choices
# ---------------------------------------------------------------------------
def sharpe_by_sector(returns: pd.DataFrame, members: dict[str, list[str]], safe: pd.Series, ppy: float, rebalance: str = "M") -> pd.Series:
    idx = index_returns(returns, members, rebalance=rebalance)
    return metrics.sharpe(idx.sub(safe, axis=0), ppy)


def weekly(returns: pd.DataFrame, safe: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Compound daily returns into Friday-to-Friday weeks (a week that is cut short by a holiday still counts as one)."""
    week = returns.index.to_period("W-FRI")
    return (1 + returns).groupby(week).prod() - 1, (1 + safe).groupby(week).prod() - 1


def scenarios(d: Data, members: dict[str, list[str]]) -> dict[str, pd.Series]:
    """Sharpe ratio of each sector under other reasonable choices, keyed by a description of the choice."""
    out = {}
    available = list(d.total.columns)
    ppy = d.ppy
    out["Main result"] = sharpe_by_sector(d.total, members, d.safe, ppy)

    kse = d.stocks[d.stocks["in_kse100"]]["symbol"]
    out["KSE-100 companies only"] = sharpe_by_sector(
        d.total, sector_members(d.stocks[d.stocks["symbol"].isin(kse)], available, config.MIN_KSE100_SECTOR_STOCKS), d.safe, ppy)

    for share in config.TRADED_SHARE_CHECKS:
        stocks = d.stocks[d.stocks["traded_share"] >= share]
        pool = d.wide if share < config.MIN_TRADED_SHARE else d.total
        out[f"Must trade on {share:.0%} of days"] = sharpe_by_sector(
            pool, sector_members(stocks, pool.columns, config.MIN_SECTOR_STOCKS), d.safe, ppy)

    if d.flagged:
        kept = [s for s in available if s not in set(d.flagged)]
        out["Without companies with price corrections"] = sharpe_by_sector(
            d.total[kept], sector_members(d.stocks, kept, config.MIN_SECTOR_STOCKS), d.safe, ppy)

    out["Rebalanced every day"] = sharpe_by_sector(d.total, members, d.safe, ppy, rebalance="D")

    weekly_returns, weekly_safe = weekly(d.total, d.safe)
    out["Weekly returns"] = sharpe_by_sector(weekly_returns, members, weekly_safe, len(weekly_returns) / d.years, rebalance="D")

    stock_total = (1 + d.total).prod() - 1
    trimmed = {sector: [s for s in symbols if s != stock_total[symbols].idxmax()] for sector, symbols in members.items()}
    out["Without each sector's best company"] = sharpe_by_sector(d.total, trimmed, d.safe, ppy)

    per_stock = metrics.sharpe(d.total.sub(d.safe, axis=0), ppy)
    out["Typical company (median)"] = pd.Series({sector: per_stock[symbols].median() for sector, symbols in members.items()})

    middle = d.total.index[d.total.index <= d.base_date + pd.DateOffset(months=30)].max()
    for label, keep in [("First half of the window", d.total.index <= middle), ("Second half of the window", d.total.index > middle),
                        ("Start 3 months later", d.total.index > d.base_date + pd.DateOffset(months=3)),
                        ("End 3 months earlier", d.total.index <= d.total.index[-1] - pd.DateOffset(months=3))]:
        out[label] = sharpe_by_sector(d.total[keep], members, d.safe[keep], ppy)
    return out


PERIOD_CHOICES = ("First half of the window", "Second half of the window", "Start 3 months later", "End 3 months earlier")


def robustness(table: dict[str, pd.Series]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The Sharpe ratios side by side, and for each choice how closely the ranking agrees with the main result.

    A choice is either about method (who is included, how the index is built, how returns are measured) or about the period
    (which dates are used). The two are kept apart because they answer different questions.
    """
    sharpes = pd.DataFrame(table)
    main = sharpes["Main result"].dropna()
    main_top = main.idxmax()
    rows = []
    for name in sharpes.columns[1:]:
        kind = "period" if name in PERIOD_CHOICES else "method"
        common = sharpes[["Main result", name]].dropna()
        if common.empty:
            rows.append({"choice": name, "kind": kind, "sectors_compared": 0, "rank_correlation": float("nan"), "top3_in_common": 0,
                         "top_tested": False, "same_top_sector": False, "main_top_sector_still_top3": False})
            continue
        top_main = set(common["Main result"].nlargest(3).index)
        top_other = set(common[name].nlargest(3).index)
        tested = main_top in common.index          # the main top sector may not be in the analysis at all under this choice
        rows.append({"choice": name, "kind": kind, "sectors_compared": len(common), "rank_correlation": metrics.spearman(main, common[name]),
                     "top3_in_common": len(top_main & top_other), "top_tested": tested,
                     "same_top_sector": bool(tested and common[name].idxmax() == main_top),
                     "main_top_sector_still_top3": bool(tested and main_top in top_other)})
    return sharpes, pd.DataFrame(rows)


def robustness_totals(rows: pd.DataFrame, kind: str) -> dict:
    """Summary of the choices of one kind. The top-sector counts are out of the choices in which the main top sector is present."""
    part = rows[rows["kind"] == kind]
    return {"n": len(part), "median_rank_correlation": float(part["rank_correlation"].median()), "min_rank_correlation": float(part["rank_correlation"].min()),
            "n_tested": int(part["top_tested"].sum()), "n_top_sector_stays_top3": int(part["main_top_sector_still_top3"].sum()),
            "n_top_sector_stays_first": int(part["same_top_sector"].sum())}


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
def _python(value):
    if isinstance(value, dict):
        return {k: _python(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_python(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


def run() -> None:
    d = load()
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    available = list(d.total.columns)
    members_all = sector_members(d.stocks, available, 1)
    members = {s: m for s, m in members_all.items() if len(m) >= config.MIN_SECTOR_STOCKS}
    ranked = list(members)

    idx_total = index_returns(d.total, members_all, available)
    idx_price = index_returns(d.price, members_all, available)
    stats = measure(idx_total, d.safe, d.base_date, d.years)
    price_cagr = (1 + idx_price).prod() ** (1 / d.years) - 1
    edges = year_edges(d.total.index, d.base_date)
    years = yearly_returns(idx_total, edges)
    excess = idx_total.sub(d.safe, axis=0)
    market_ex = excess[MARKET]
    beta = excess.apply(lambda s: s.cov(market_ex) / market_ex.var())
    corr = idx_total.corr()[MARKET]
    buy_hold = {s: ((1 + d.total[m]).cumprod().mean(axis=1).iloc[-1]) ** (1 / d.years) - 1 for s, m in {**members_all, MARKET: available}.items()}

    boot = bootstrap_summary(excess, ranked, d.ppy)
    table = pd.DataFrame(index=idx_total.columns)
    table["sector"] = table.index
    table["sector_code"] = [d.stocks.loc[d.stocks["sector"] == s, "sector_code"].iloc[0] if s != MARKET else "" for s in table.index]
    table["n_companies"] = [len(members_all[s]) if s != MARKET else len(available) for s in table.index]
    table["n_in_kse100"] = [int(d.stocks[d.stocks["symbol"].isin(members_all[s]) & d.stocks["in_kse100"]].shape[0]) if s != MARKET
                            else int(d.stocks[d.stocks["symbol"].isin(available) & d.stocks["in_kse100"]].shape[0]) for s in table.index]
    table["ranked"] = [s in ranked for s in table.index]
    table = table.join(stats).join(years)
    table["price_cagr"] = price_cagr
    table["dividend_points"] = table["cagr"] - table["price_cagr"]
    table["cagr_buy_and_hold"] = pd.Series(buy_hold)
    table["cagr_daily_rebalanced"] = metrics.annualised_return(index_returns(d.total, members_all, available, rebalance="D"), d.years)
    table["beta"] = beta
    table["correlation_with_market"] = corr
    fx = json.loads((config.INTERIM / "data_quality.json").read_text(encoding="utf-8")).get("fx")
    table["usd_cagr"] = ((1 + table["total_return"]) / (1 + fx["rupee_change"])) ** (1 / d.years) - 1 if fx else np.nan
    for column, key in [("sharpe_lo", "sharpe_lo"), ("sharpe_hi", "sharpe_hi"), ("rank_median", "rank_median"), ("rank_lo", "rank_lo"),
                        ("rank_hi", "rank_hi"), ("p_top1", "p_top1"), ("p_top3", "p_top3"), ("p_beats_market", "p_beats_market")]:
        table.loc[ranked, column] = boot[key]
    table.loc[MARKET, ["sharpe_lo", "sharpe_hi"]] = [boot["market_lo"], boot["market_hi"]]
    table["rank_sharpe"] = table.loc[ranked, "sharpe"].rank(ascending=False, method="min")
    table["rank_cagr"] = table.loc[ranked, "cagr"].rank(ascending=False, method="min")
    table["rank_drawdown"] = table.loc[ranked, "max_drawdown"].rank(ascending=False, method="min")   # 1 = shallowest fall

    typical = metrics.sharpe(d.total.sub(d.safe, axis=0), d.ppy)
    best_total = (1 + d.total).prod() - 1
    table["typical_company_sharpe"] = [typical[members_all[s]].median() if s != MARKET else typical.median() for s in table.index]
    table["best_company"] = [best_total[members_all[s]].idxmax() if s != MARKET else best_total.idxmax() for s in table.index]
    table = table.sort_values(["ranked", "sharpe"], ascending=[False, False])

    stocks = stock_table(d)
    sharpes, summary_rows = robustness(scenarios(d, members))

    # ---- write
    for column in ("peak_date", "trough_date", "recovery_date"):
        table[column] = pd.to_datetime(table[column]).dt.strftime("%Y-%m-%d")
    table.reset_index(drop=True).to_csv(config.PROCESSED / "sector_summary.csv", index=False, float_format="%.6g", lineterminator="\n")
    stocks.assign(**{c: pd.to_datetime(stocks[c]).dt.strftime("%Y-%m-%d") for c in ("peak_date", "trough_date", "recovery_date")}).to_csv(
        config.PROCESSED / "stock_summary.csv", index=False, float_format="%.6g", lineterminator="\n")
    daily = idx_total.copy()
    daily["Safe return (policy rate)"] = d.safe
    daily.index.name = "date"
    daily.to_csv(config.PROCESSED / "sector_daily_returns.csv", float_format="%.7f", lineterminator="\n")
    corr_matrix = idx_total[[*ranked, MARKET]].corr()
    corr_matrix.to_csv(config.PROCESSED / "sector_correlations.csv", float_format="%.4f", lineterminator="\n")
    pd.DataFrame(boot["distribution"], index=ranked, columns=[f"rank_{r}" for r in range(1, len(ranked) + 1)]).to_csv(
        config.PROCESSED / "sector_rank_distribution.csv", index_label="sector", float_format="%.4f", lineterminator="\n")
    sharpes.to_csv(config.PROCESSED / "robustness_sharpe.csv", index_label="sector", float_format="%.4f", lineterminator="\n")
    summary_rows.to_csv(config.PROCESSED / "robustness_summary.csv", index=False, float_format="%.4f", lineterminator="\n")

    # ---- the headline numbers the documents quote
    ranked_table = table[table["ranked"]].sort_values("sharpe", ascending=False)
    first = ranked_table.iloc[0]
    policy = pd.read_csv(config.POLICY_RATE_FILE, parse_dates=["effective_date"])
    in_window = policy[policy["effective_date"] <= d.total.index[-1]]          # the changes that had happened by the end of the window
    market = table.loc[MARKET]
    window = json.loads((config.INTERIM / "data_quality.json").read_text(encoding="utf-8"))
    summary = {
        "window": {"base_date": d.base_date, "end_date": d.total.index[-1], "market_days": len(d.total), "years": d.years,
                   "year_edges": edges},
        "n_companies": len(available), "n_sectors_ranked": len(ranked), "min_sector_stocks": config.MIN_SECTOR_STOCKS, "n_sectors_unranked": int((~table["ranked"]).sum()) - 1,
        "unranked_sectors": table.loc[~table["ranked"] & (table.index != MARKET), "sector"].tolist(),
        "safe": {"cagr": float((1 + d.safe).prod() ** (1 / d.years) - 1), "policy_rate_start": float(policy.loc[policy["effective_date"] <= d.base_date, "policy_rate_pct"].iloc[-1]),
                 "policy_rate_end": float(in_window["policy_rate_pct"].iloc[-1]), "policy_rate_peak": float(in_window["policy_rate_pct"].max())},
        "market": {k: market[k] for k in ("total_return", "cagr", "usd_cagr", "volatility", "sharpe", "max_drawdown", "dividend_points", "sharpe_lo", "sharpe_hi")},
        "top_sharpe": [{"sector": r.sector, "sharpe": r.sharpe, "lo": r.sharpe_lo, "hi": r.sharpe_hi, "cagr": r.cagr, "volatility": r.volatility,
                        "max_drawdown": r.max_drawdown, "p_top1": r.p_top1, "p_top3": r.p_top3, "n": r.n_companies}
                       for r in ranked_table.head(5).itertuples()],
        "bottom_sharpe": [{"sector": r.sector, "sharpe": r.sharpe, "lo": r.sharpe_lo, "hi": r.sharpe_hi, "cagr": r.cagr, "volatility": r.volatility,
                           "max_drawdown": r.max_drawdown, "n": r.n_companies} for r in ranked_table.tail(3).itertuples()],
        "best_cagr": ranked_table.sort_values("cagr", ascending=False).iloc[0]["sector"],
        "lowest_vol": ranked_table.sort_values("volatility").iloc[0]["sector"],
        "shallowest_drawdown": ranked_table.sort_values("max_drawdown", ascending=False).iloc[0]["sector"],
        "deepest_drawdown": ranked_table.sort_values("max_drawdown").iloc[0]["sector"],
        "n_clearly_above_market": int((ranked_table["p_beats_market"] >= 0.95).sum()),
        "n_clearly_below_market": int((ranked_table["p_beats_market"] <= 0.05).sum()),
        "n_with_chance_of_first": int((ranked_table["p_top1"] >= 0.10).sum()),
        "max_p_top1": float(ranked_table["p_top1"].max()), "top_sector": first["sector"],
        "robustness": {"n_choices": len(summary_rows), "method": robustness_totals(summary_rows, "method"),
                       "period": robustness_totals(summary_rows, "period")},
        "quality": window,
    }
    (config.PROCESSED / "summary.json").write_text(json.dumps(_python(summary), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"[analyze] {len(ranked)} sectors ranked from {len(available)} companies; top by Sharpe: {first['sector']} "
          f"({first['sharpe']:.2f}, 95% {first['sharpe_lo']:.2f} to {first['sharpe_hi']:.2f}); market Sharpe {market['sharpe']:.2f}")
