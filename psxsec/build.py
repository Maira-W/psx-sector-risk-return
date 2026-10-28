"""Turn the raw files into clean, checked tables (data/interim) and decide which companies qualify.

The checks stop the build on a real problem (duplicate rows, a price of zero or less, a window end that is not a market day).
Bad prices that Yahoo Finance is known to contain are cleaned by stated rules, and every correction is listed in data/processed.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config


def load_prices() -> pd.DataFrame:
    path = config.RAW / config.PRICES_FILE
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `python -m psxsec ingest` to download the prices")
    return pd.read_csv(path, parse_dates=["date"])


def load_universe() -> pd.DataFrame:
    return pd.read_csv(config.UNIVERSE_FILE, dtype={"sector_code": str})


def check_prices(prices: pd.DataFrame) -> dict:
    """Stop on a real problem in the raw prices; return a few counts for the quality report."""
    needed = {"symbol", "date", "close", "adj_close", "volume", "dividend", "split"}
    if not needed <= set(prices.columns):
        raise ValueError(f"the prices file lacks columns {sorted(needed - set(prices.columns))}")
    if prices.duplicated(["symbol", "date"]).any():
        raise ValueError("duplicate symbol and date rows in the prices")
    if (prices["close"] <= 0).any():
        raise ValueError("a price of zero or less in the prices")
    if (prices["volume"] < 0).any():
        raise ValueError("negative volume in the prices")
    # Yahoo's dividend-adjusted close is not used for returns (see returns()); where it is invalid that is reported, not fatal
    return {"rows": len(prices), "symbols": int(prices["symbol"].nunique()),
            "first_date": str(prices["date"].min().date()), "last_date": str(prices["date"].max().date()),
            "invalid_adjusted_close": sorted(prices.loc[prices["adj_close"] <= 0, "symbol"].unique())}


def market_days(prices: pd.DataFrame) -> pd.DatetimeIndex:
    """Dates on which the exchange was open: at least MIN_TRADING_COMPANIES companies traded.

    Yahoo lists PSX holidays as rows with no volume and the previous price carried forward; those dates are dropped here.
    """
    traded = prices.loc[prices["volume"] > 0].groupby("date")["symbol"].nunique()
    days = traded.index[traded >= config.MIN_TRADING_COMPANIES]
    return pd.DatetimeIndex(days[days <= pd.Timestamp(config.WINDOW_END)])


def window(days: pd.DatetimeIndex) -> tuple[pd.Timestamp, pd.DatetimeIndex]:
    """The base date (the close that the first return is measured from) and the dates of the returns."""
    end = pd.Timestamp(config.WINDOW_END)
    if end not in days:
        raise ValueError(f"{config.WINDOW_END} is not a market day in the downloaded prices (last market day: {days.max().date()})")
    target = end - pd.DateOffset(years=config.WINDOW_YEARS)
    base = days[days <= target].max()
    return base, days[(days > base) & (days <= end)]


def matrices(prices: pd.DataFrame, base: pd.Timestamp, dates: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """One table per field, a row for the base date and every return date, a column for every symbol."""
    index = pd.DatetimeIndex([base, *dates])
    out = {}
    for field in ("close", "adj_close", "volume"):
        out[field] = prices.pivot(index="date", columns="symbol", values=field).reindex(index)
    out["volume"] = out["volume"].fillna(0)
    # A dividend dated on a day that is not a market day is credited to the next market day.
    paid = prices.loc[prices["dividend"] > 0, ["symbol", "date", "dividend"]]
    position = index.searchsorted(paid["date"])
    paid = paid[position < len(index)].assign(date=index[position[position < len(index)]])
    out["dividend"] = paid.pivot_table(index="date", columns="symbol", values="dividend", aggfunc="sum").reindex(index).fillna(0)
    out["dividend"] = out["dividend"].reindex(columns=out["close"].columns, fill_value=0.0)
    return out


def diagnostics(m: dict[str, pd.DataFrame], universe: pd.DataFrame) -> pd.DataFrame:
    """For every company: how much of the window it has a price for, how often it traded, and whether it qualifies."""
    close, volume = m["close"], m["volume"]
    present = close.notna()
    rows = []
    for symbol in universe["symbol"]:
        if symbol not in close.columns:
            rows.append({"symbol": symbol, "history_share": 0.0, "traded_share": 0.0, "status": "no prices on Yahoo Finance"})
            continue
        history = float(present[symbol].mean())
        traded = float((volume[symbol].iloc[1:] > 0).mean())
        if not present[symbol].iloc[0]:
            status = "listed after the start of the window"
        elif history < config.MIN_HISTORY_SHARE or not present[symbol].iloc[-5:].any():
            status = "prices missing on too many days"
        elif traded < config.MIN_TRADED_SHARE:
            status = "traded on too few days"
        else:
            status = "qualifies"
        rows.append({"symbol": symbol, "history_share": history, "traded_share": traded, "status": status})
    return universe.merge(pd.DataFrame(rows), on="symbol", how="left")


# ---------------------------------------------------------------------------
# Cleaning the prices and computing returns
# ---------------------------------------------------------------------------
def remove_spikes(close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replace a bad price that lasts one to SPIKE_DAYS days by the price before it.

    A bad price is one that is at least SPIKE_RATIO times (or at most 1 / SPIKE_RATIO of) the price before it on every day of
    the run, after which the price is back within SPIKE_BACK of where it was. A share does not go up tenfold for a day and
    come back, so this is a data error. Returns the cleaned prices and a table of what was replaced.
    """
    cleaned = close.copy()
    spike, back = np.log(config.SPIKE_RATIO), np.log(config.SPIKE_BACK)
    found = []
    for symbol in cleaned.columns:
        p = cleaned[symbol].to_numpy(dtype=float).copy()
        t = 1
        while t < len(p):
            reference = p[t - 1]
            if np.isfinite(reference) and np.isfinite(p[t]) and abs(np.log(p[t] / reference)) > spike:
                for days in range(1, config.SPIKE_DAYS + 1):
                    end = t + days
                    if end >= len(p):
                        break
                    if (np.abs(np.log(p[t:end] / reference)) > spike).all() and abs(np.log(p[end] / reference)) <= back:
                        found.append((symbol, cleaned.index[t], days, p[t] / reference - 1))
                        p[t:end] = reference
                        t = end
                        break
            t += 1
        cleaned[symbol] = p
    return cleaned, pd.DataFrame(found, columns=["symbol", "date", "days", "price_return"])


def jump_days(close: pd.DataFrame, dividend: pd.DataFrame | None = None) -> pd.DataFrame:
    """True on a day when the one-day change in the value of a share is beyond what the exchange's daily limit allows.

    The value counts a dividend paid that day (a share that falls by its dividend has not lost anything). The change must be at
    least JUMP_RATIO up (or the same move down, so that a mis-dated adjustment and its mirror image are both caught) and larger
    than JUMP_RUPEES, because the limit is a few percent or Re 1, whichever is larger, which lets cheap shares move by a large
    percentage.
    """
    previous = close.shift(1)
    value = close if dividend is None else close + dividend
    ratio = value / previous
    beyond = ((ratio >= config.JUMP_RATIO) | (ratio <= 1 / config.JUMP_RATIO)) & ((value - previous).abs() > config.JUMP_RUPEES)
    return beyond.iloc[1:]


def holding_period_return(close: pd.DataFrame, dividend: pd.DataFrame) -> pd.DataFrame:
    """(price today + dividend paid today) / price yesterday - 1, for every day after the first."""
    return ((close + dividend) / close.shift(1) - 1).iloc[1:]


def returns(close: pd.DataFrame, dividend: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Daily total return, price return and the jump days, from prices that have already been through remove_spikes.

    The total return is the standard holding-period return from Yahoo's split-adjusted close and its dividend column. Yahoo's
    own dividend-adjusted close is not used: it is invalid for at least one company and uses a different convention for very
    large dividends (cross_check compares the two). On a jump day the price return is set to zero and only the dividend counts.
    """
    jumps = jump_days(close, dividend)
    previous = close.shift(1)
    price = (close / previous - 1).iloc[1:].mask(jumps, 0.0)
    total = holding_period_return(close, dividend).mask(jumps, (dividend / previous).iloc[1:])
    return total, price, jumps


def corrections(spikes: pd.DataFrame, close: pd.DataFrame, dividend: pd.DataFrame, jumps: pd.DataFrame, qualifying: list[str],
                names: pd.Series) -> pd.DataFrame:
    """Every correction made to a qualifying company's prices, for review."""
    rows = [{"symbol": r.symbol, "company": names.get(r.symbol, ""), "date": r.date.date(), "treatment": f"bad price for {r.days} day(s) replaced",
             "price_move_pct": r.price_return * 100} for r in spikes[spikes["symbol"].isin(qualifying)].itertuples()]
    move = ((close + dividend) / close.shift(1) - 1).iloc[1:] * 100          # the change in value, counting any dividend paid that day
    for symbol in qualifying:
        rows += [{"symbol": symbol, "company": names.get(symbol, ""), "date": d.date(), "treatment": "price return set to zero (beyond the daily limit)",
                  "price_move_pct": move.loc[d, symbol]} for d in jumps.index[jumps[symbol]]]
    return pd.DataFrame(rows, columns=["symbol", "company", "date", "treatment", "price_move_pct"]).sort_values(["symbol", "date"]).reset_index(drop=True)


def cross_check(m: dict[str, pd.DataFrame], total: pd.DataFrame, qualifying: list[str]) -> dict:
    """Compare total returns computed from close and dividends with those implied by Yahoo's dividend-adjusted close."""
    adjusted = m["adj_close"].ffill()
    valid = [s for s in qualifying if (adjusted[s].dropna() > 0).all()]
    yahoo = adjusted[valid].pct_change().iloc[1:]
    daily_gap = (yahoo - total[valid]).abs()
    five_year_gap = ((1 + yahoo).prod() - (1 + total[valid]).prod()).abs() * 100          # percentage points of total return
    return {"companies_compared": len(valid), "excluded": sorted(set(qualifying) - set(valid)),
            "days_agreeing_pct": float((daily_gap <= 0.005).to_numpy().mean() * 100),       # within half a point of daily return
            "dividend_events": int((m["dividend"].iloc[1:][qualifying] > 0).sum().sum()),
            "gap_median_points": float(five_year_gap.median()), "gap_over_5_points": int((five_year_gap > 5).sum()),
            "gap_max_points": float(five_year_gap.max()), "gap_max_company": str(five_year_gap.idxmax())}


def fx_rates(base: pd.Timestamp, end: pd.Timestamp) -> dict | None:
    """Rupees per US dollar on the base date and the end date (the last rate on or before each), and the change between them."""
    path = config.RAW / config.FX_FILE
    if not path.exists():
        return None
    fx = pd.read_csv(path, index_col=0, parse_dates=True)["rupees_per_dollar"].dropna()
    at_base, at_end = float(fx.loc[:base].iloc[-1]), float(fx.loc[:end].iloc[-1])
    return {"base": at_base, "end": at_end, "rupee_change": at_end / at_base - 1}


def run() -> None:
    config.INTERIM.mkdir(parents=True, exist_ok=True)
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    prices = load_prices()
    universe = load_universe()
    quality = {"raw": check_prices(prices)}

    days = market_days(prices)
    base, dates = window(days)
    years = (dates[-1] - base).days / 365.25
    m = matrices(prices, base, dates)
    quality["window"] = {"base_date": str(base.date()), "first_return": str(dates[0].date()), "end_date": str(dates[-1].date()),
                         "market_days": len(dates), "years": round(years, 3), "market_days_per_year": round(len(dates) / years, 1),
                         "holiday_rows_dropped": int(prices["date"].nunique() - len(prices["date"].drop_duplicates()[lambda s: s.isin(days)]))}

    quality["fx"] = fx_rates(base, dates[-1])
    operating = universe[~universe["sector_code"].isin(config.NOT_OPERATING)]
    diag = diagnostics(m, operating)
    qualifying = diag.loc[diag["status"] == "qualifies", "symbol"].tolist()

    close = m["close"].ffill()
    quality["cross_check"] = cross_check(m, holding_period_return(close, m["dividend"]), qualifying)   # before any cleaning
    cleaned, spikes = remove_spikes(close)
    total, price, jumps = returns(cleaned, m["dividend"])
    names = universe.set_index("symbol")["company"]
    fixed = corrections(spikes, cleaned, m["dividend"], jumps, qualifying, names)
    quality["corrections"] = {"events": len(fixed), "companies": int(fixed["symbol"].nunique()),
                              "bad_prices": int(fixed["treatment"].str.startswith("bad price").sum()),
                              "beyond_limit": int(fixed["treatment"].str.startswith("price return").sum()),
                              "jump_ratio": config.JUMP_RATIO, "jump_rupees": config.JUMP_RUPEES}
    moved = prices[(prices["date"] > base) & (prices["date"] <= dates[-1]) & ~prices["date"].isin(days) & (prices["dividend"] > 0)
                   & prices["symbol"].isin(qualifying)]
    quality["dividends_moved_to_next_market_day"] = len(moved)    # dated on a day that is not a market day

    manifest = json.loads(config.MANIFEST.read_text(encoding="utf-8"))["files"]
    listings = manifest[config.SCREENER_FILE]["listings"]
    funnel = [("Listings on the PSX data portal (shares, rights, bonds and others)", listings),
              ("In the KSE All Share Index", len(universe)),
              ("Operating companies (funds, ETFs and REITs removed)", len(operating)),
              ("Prices found on Yahoo Finance", int((diag["status"] != "no prices on Yahoo Finance").sum())),
              ("A price on nearly every market day of the five years", int(diag["status"].isin(["qualifies", "traded on too few days"]).sum())),
              ("Traded on at least 90% of market days (qualify)", len(qualifying))]
    pd.DataFrame(funnel, columns=["step", "companies"]).to_csv(config.PROCESSED / "universe_funnel.csv", index=False, lineterminator="\n")

    diag.round({"history_share": 4, "traded_share": 4}).to_csv(config.PROCESSED / "stock_status.csv", index=False, lineterminator="\n")
    fixed.round(2).to_csv(config.PROCESSED / "price_corrections.csv", index=False, lineterminator="\n")
    total[qualifying].to_csv(config.INTERIM / "returns_total.csv.gz", compression="gzip", lineterminator="\n")
    price[qualifying].to_csv(config.INTERIM / "returns_price.csv.gz", compression="gzip", lineterminator="\n")
    # companies that fail only the trading rule are kept for the robustness check that loosens it
    near = diag.loc[diag["status"] == "traded on too few days", "symbol"].tolist()
    total[qualifying + near].to_csv(config.INTERIM / "returns_total_wide.csv.gz", compression="gzip", lineterminator="\n")
    (config.INTERIM / "data_quality.json").write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"[build] {len(dates)} market days from {dates[0].date()} to {dates[-1].date()} (base {base.date()}); "
          f"{len(qualifying)} of {len(operating)} operating companies qualify; {len(fixed)} price corrections in "
          f"{quality['corrections']['companies']} of them")
