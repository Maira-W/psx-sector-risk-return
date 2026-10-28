"""The build and analysis steps on small made-up markets where the right answer is known."""

import numpy as np
import pandas as pd
import pytest

from psxsec import analysis, build, config, ingest, metrics


# ---- a made-up market -----------------------------------------------------------------------------------------------
def made_up_market(n=520, seed=0):
    """Ten companies in two sectors, two in a sector too small to rank, two in the catch-all group."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-04", periods=n)
    layout = {"0804": ("Cement", ["C1", "C2", "C3", "C4", "C5"], 0.0010), "0807": ("Commercial banks", ["B1", "B2", "B3", "B4", "B5"], 0.0002),
              "0832": ("Tobacco", ["T1", "T2"], 0.0004), "0818": ("Miscellaneous", ["M1", "M2"], 0.0003)}
    rows, columns, drift = [], [], {}
    for code, (sector, symbols, mu) in layout.items():
        for symbol in symbols:
            rows.append({"symbol": symbol, "company": symbol + " Ltd", "sector_code": code, "sector": sector, "in_kse100": symbol in ("C1", "C2", "C3", "B1", "B2", "B3"),
                         "history_share": 1.0, "traded_share": 0.99, "status": "qualifies"})
            columns.append(symbol)
            drift[symbol] = mu
    returns = pd.DataFrame({s: rng.normal(drift[s], 0.012, n) for s in columns}, index=dates)
    stocks = pd.DataFrame(rows)
    base = dates[0] - pd.offsets.BDay(1)
    policy = pd.DataFrame({"effective_date": [base - pd.Timedelta(days=30)], "policy_rate_pct": [12.0]})
    years = (dates[-1] - base).days / 365.25
    safe = metrics.safe_return(dates, base, policy)
    return analysis.Data(returns, returns * 0.9, returns, stocks, safe, base, years)


def test_sector_members_keeps_sectors_with_enough_companies_and_drops_the_catch_all():
    d = made_up_market()
    assert set(analysis.sector_members(d.stocks, d.total.columns, 4)) == {"Cement", "Commercial banks"}
    assert set(analysis.sector_members(d.stocks, d.total.columns, 1)) == {"Cement", "Commercial banks", "Tobacco"}   # never Miscellaneous
    assert analysis.sector_members(d.stocks, ["C1", "C2"], 1) == {"Cement": ["C1", "C2"]}


def test_a_sector_index_rebalanced_every_day_is_the_plain_average_and_the_market_uses_every_company():
    d = made_up_market()
    members = analysis.sector_members(d.stocks, d.total.columns, 4)
    idx = analysis.index_returns(d.total, members, list(d.total.columns), rebalance="D")
    assert idx["Cement"].iloc[10] == pytest.approx(d.total.loc[d.total.index[10], ["C1", "C2", "C3", "C4", "C5"]].mean())
    assert idx[analysis.MARKET].iloc[10] == pytest.approx(d.total.iloc[10].mean())


def test_a_monthly_rebalanced_index_starts_each_month_equal_weighted_and_then_drifts():
    d = made_up_market()
    members = analysis.sector_members(d.stocks, d.total.columns, 4)
    idx = analysis.index_returns(d.total, members, rebalance="M")
    cement = d.total[members["Cement"]]
    month = cement.index.to_period("M")
    for day in cement.index.to_series().groupby(month).first():                 # on the first day of a month the weights are equal
        assert idx.loc[day, "Cement"] == pytest.approx(cement.loc[day].mean())
    one_month = cement[month == month[40]]                                       # over a month it grows like buy and hold
    assert (1 + idx.loc[one_month.index, "Cement"]).prod() == pytest.approx((1 + one_month).prod().mean())
    assert not idx["Cement"].equals(analysis.index_returns(d.total, members, rebalance="D")["Cement"])     # and differs from daily


def test_measure_agrees_with_the_metric_functions():
    d = made_up_market()
    idx = analysis.index_returns(d.total, analysis.sector_members(d.stocks, d.total.columns, 4))
    table = analysis.measure(idx, d.safe, d.base_date, d.years)
    r = idx["Cement"]
    assert table.loc["Cement", "total_return"] == pytest.approx((1 + r).prod() - 1)
    assert table.loc["Cement", "cagr"] == pytest.approx(metrics.annualised_return(r, d.years))
    assert table.loc["Cement", "sharpe"] == pytest.approx(metrics.sharpe(r - d.safe, d.ppy))
    assert -1 < table.loc["Cement", "max_drawdown"] <= 0
    assert table.loc["Cement", "peak_date"] <= table.loc["Cement", "trough_date"]


def test_the_five_yearly_returns_compound_to_the_total():
    d = made_up_market(n=1300)
    idx = analysis.index_returns(d.total, analysis.sector_members(d.stocks, d.total.columns, 4))
    edges = analysis.year_edges(d.total.index, d.base_date)
    assert len(edges) == 6 and edges[0] == d.base_date and edges[-1] == d.total.index[-1]
    assert all(a < b for a, b in zip(edges, edges[1:], strict=False))
    yearly = analysis.yearly_returns(idx, edges)
    assert (1 + yearly).prod(axis=1).to_numpy() == pytest.approx((1 + idx).prod().to_numpy())


def test_weekly_returns_compound_to_the_same_total():
    d = made_up_market()
    weekly, weekly_safe = analysis.weekly(d.total, d.safe)
    assert ((1 + weekly).prod() - (1 + d.total).prod()).abs().max() < 1e-9
    assert (1 + weekly_safe).prod() == pytest.approx((1 + d.safe).prod())


def test_bootstrap_ranks_are_consistent_and_find_a_clearly_better_sector():
    d = made_up_market(n=900, seed=3)
    members = analysis.sector_members(d.stocks, d.total.columns, 4)
    idx = analysis.index_returns(d.total, members, list(d.total.columns))
    excess = idx.sub(d.safe, axis=0)
    out = analysis.bootstrap_summary(excess, list(members), d.ppy)
    dist = out["distribution"]
    assert dist.shape == (2, 2)
    assert dist.sum(axis=1) == pytest.approx([1, 1]) and dist.sum(axis=0) == pytest.approx([1, 1])   # each draw gives out each rank once
    assert (out["p_top3"] >= out["p_top1"]).all() and (out["sharpe_lo"] < out["sharpe_hi"]).all()
    cement = list(members).index("Cement")
    assert out["p_top1"][cement] > 0.8 and out["p_beats_market"][cement] > 0.5


def test_dropping_a_sectors_best_company_lowers_its_sharpe_when_one_company_is_a_star():
    d = made_up_market(n=700, seed=4)
    d.total["C3"] = d.total["C3"] + 0.004          # a runaway winner inside Cement
    members = analysis.sector_members(d.stocks, d.total.columns, 4)
    table = analysis.scenarios(d, members)
    assert table["Main result"]["Cement"] > table["Without each sector's best company"]["Cement"]
    assert set(table) >= {"Main result", "KSE-100 companies only", "Rebalanced every day", "Weekly returns", "Typical company (median)", "First half of the window",
                          "Second half of the window", "Start 3 months later", "End 3 months earlier"}


def test_robustness_summary_reports_a_perfect_match_for_identical_rankings():
    same = pd.Series({"a": 1.0, "b": 0.5, "c": 0.2, "d": -0.1})
    sharpes, summary = analysis.robustness({"Main result": same, "Copy": same * 2, "Reversed": -same, "First half of the window": same})
    row = summary.set_index("choice")
    assert row.loc["Copy", "rank_correlation"] == pytest.approx(1.0) and bool(row.loc["Copy", "same_top_sector"])
    assert row.loc["Reversed", "rank_correlation"] == pytest.approx(-1.0) and not bool(row.loc["Reversed", "same_top_sector"])
    assert sharpes.shape == (4, 4)
    assert row["kind"].to_dict() == {"Copy": "method", "Reversed": "method", "First half of the window": "period"}
    method = analysis.robustness_totals(summary, "method")
    assert method["n"] == 2 and method["n_tested"] == 2 and method["min_rank_correlation"] == pytest.approx(-1.0)
    assert method["n_top_sector_stays_first"] == 1 and method["n_top_sector_stays_top3"] == 1
    assert analysis.robustness_totals(summary, "period")["median_rank_correlation"] == pytest.approx(1.0)


def test_when_a_choice_drops_the_main_top_sector_it_is_not_counted_as_staying_on_top():
    full = pd.Series({"a": 1.0, "b": 0.5, "c": 0.2, "d": -0.1})
    without_a = pd.Series({"b": 0.9, "c": 0.4, "d": 0.1})                     # sector a has too few companies under this choice
    _, summary = analysis.robustness({"Main result": full, "Without a": without_a})
    row = summary.iloc[0]
    assert not row["top_tested"] and not row["same_top_sector"] and not row["main_top_sector_still_top3"]
    assert row["sectors_compared"] == 3 and row["rank_correlation"] == pytest.approx(1.0)
    totals = analysis.robustness_totals(summary, "method")
    assert totals["n"] == 1 and totals["n_tested"] == 0 and totals["n_top_sector_stays_top3"] == 0


# ---- the build step -------------------------------------------------------------------------------------------------
def made_up_prices():
    dates = pd.bdate_range("2021-06-01", "2026-10-30")
    holiday = pd.Timestamp("2023-03-15")
    ends = (dates >= "2021-10-20") & (dates <= "2021-10-29") | (dates >= "2026-10-20")      # both ends of the window are busy days
    rows = []
    for symbol, traded in [("AAA", 0.99), ("BBB", 0.99), ("CCC", 0.5)]:
        rng = np.random.default_rng(len(symbol) + ord(symbol[0]))
        price = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(dates)))
        volume = np.where(rng.random(len(dates)) < traded, 1000, 0)
        volume[ends] = 1000
        volume[dates == holiday] = 0
        rows.append(pd.DataFrame({"symbol": symbol, "date": dates, "close": price, "adj_close": price, "volume": volume,
                                  "dividend": 0.0, "split": 0.0}))
    return pd.concat(rows, ignore_index=True), holiday


def test_market_days_drop_holidays_and_the_window_starts_five_years_back(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRADING_COMPANIES", 2)
    monkeypatch.setattr(config, "WINDOW_END", pd.Timestamp("2026-10-27").date())
    prices, holiday = made_up_prices()
    days = build.market_days(prices)
    assert holiday not in days and days.max() == pd.Timestamp("2026-10-27")
    base, dates = build.window(days)
    assert base == pd.Timestamp("2021-10-27") and dates[0] == pd.Timestamp("2021-10-28")
    assert dates[-1] == pd.Timestamp("2026-10-27") and base not in dates


def test_a_dividend_dated_on_a_holiday_is_credited_to_the_next_market_day(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRADING_COMPANIES", 2)
    monkeypatch.setattr(config, "WINDOW_END", pd.Timestamp("2026-10-27").date())
    prices, holiday = made_up_prices()
    days = build.market_days(prices)
    base, dates = build.window(days)
    ordinary = days[days > pd.Timestamp("2024-05-01")][0]
    prices.loc[(prices["symbol"] == "AAA") & (prices["date"] == holiday), "dividend"] = 2.0
    prices.loc[(prices["symbol"] == "BBB") & (prices["date"] == ordinary), "dividend"] = 1.0
    prices.loc[(prices["symbol"] == "CCC") & (prices["date"] == pd.Timestamp("2021-09-01")), "dividend"] = 5.0     # before the window
    m = build.matrices(prices, base, dates)
    assert holiday not in m["dividend"].index
    assert m["dividend"].loc[days[days > holiday][0], "AAA"] == 2.0 and m["dividend"].loc[ordinary, "BBB"] == 1.0
    assert m["dividend"].iloc[1:].sum().sum() == 3.0                      # the one before the window is not counted
    assert list(m["dividend"].columns) == list(m["close"].columns)


def test_window_end_must_be_a_market_day(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRADING_COMPANIES", 2)
    monkeypatch.setattr(config, "WINDOW_END", pd.Timestamp("2026-10-25").date())     # a Sunday
    prices, _ = made_up_prices()
    with pytest.raises(ValueError, match="not a market day"):
        build.window(build.market_days(prices))


def test_diagnostics_separate_liquid_from_thinly_traded_companies(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRADING_COMPANIES", 2)
    monkeypatch.setattr(config, "WINDOW_END", pd.Timestamp("2026-10-27").date())
    prices, _ = made_up_prices()
    days = build.market_days(prices)
    base, dates = build.window(days)
    m = build.matrices(prices, base, dates)
    universe = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC", "ZZZ"], "company": list("abcd"), "sector_code": ["0804"] * 4,
                             "sector": ["Cement"] * 4, "in_kse100": [True, False, False, False]})
    status = build.diagnostics(m, universe).set_index("symbol")["status"]
    assert status["AAA"] == "qualifies" and status["BBB"] == "qualifies"
    assert status["CCC"] == "traded on too few days" and status["ZZZ"] == "no prices on Yahoo Finance"


def test_checks_stop_on_bad_prices():
    prices, _ = made_up_prices()
    assert build.check_prices(prices)["symbols"] == 3
    with pytest.raises(ValueError, match="duplicate"):
        build.check_prices(pd.concat([prices, prices.iloc[:1]]))
    bad = prices.copy()
    bad.loc[5, "close"] = 0
    with pytest.raises(ValueError, match="zero or less"):
        build.check_prices(bad)
    broken = prices.copy()                       # Yahoo's dividend-adjusted close can go wrong; that is reported, not fatal
    broken.loc[broken["symbol"] == "CCC", "adj_close"] = -1.0
    assert build.check_prices(broken)["invalid_adjusted_close"] == ["CCC"]


def made_up_dividend_case():
    dates = pd.bdate_range("2024-01-01", periods=6)
    close = pd.DataFrame({"X": [100, 100, 80, 80, 80, 80.0], "Y": [10.0] * 6}, index=dates)       # X falls 20% on day 3
    dividend = pd.DataFrame({"X": [0, 0, 0, 2.0, 0, 0], "Y": [0.0] * 6}, index=dates)               # and pays 2 on day 4
    factor = 1 - 2.0 / 80                                                                           # Yahoo scales earlier prices by this
    adj = pd.DataFrame({"X": [100 * factor, 100 * factor, 80 * factor, 80, 80, 80.0], "Y": [-1.0] * 6}, index=dates)   # Y: a broken series
    return {"close": close, "adj_close": adj, "volume": close * 0 + 1, "dividend": dividend}, dates


def test_total_return_is_price_plus_dividend_over_yesterdays_price():
    m, dates = made_up_dividend_case()
    total, price, jumps = build.returns(m["close"], m["dividend"])
    assert total.loc[dates[3], "X"] == pytest.approx((80 + 2) / 80 - 1) and price.loc[dates[3], "X"] == 0
    assert (total["Y"] == 0).all() and not jumps["Y"].any()


def test_a_move_beyond_the_daily_limit_is_a_jump_and_its_price_return_is_set_to_zero():
    m, dates = made_up_dividend_case()
    total, price, jumps = build.returns(m["close"], m["dividend"])      # X falls from 100 to 80 on day 3: more than 15% and Rs 1.05
    assert bool(jumps.loc[dates[2], "X"]) and jumps["X"].sum() == 1
    assert price.loc[dates[2], "X"] == 0 and total.loc[dates[2], "X"] == 0


def test_a_share_that_falls_by_its_dividend_has_not_made_a_jump():
    dates = pd.bdate_range("2024-01-01", periods=4)
    close = pd.DataFrame({"X": [29.0, 15.0, 15.2, 15.1]}, index=dates)                  # the price halves on day 2 ...
    dividend = pd.DataFrame({"X": [0.0, 15.0, 0.0, 0.0]}, index=dates)                  # ... because Rs 15 was paid out that day
    assert not build.jump_days(close, dividend)["X"].any()
    assert build.jump_days(close)["X"].iloc[0]                                          # without the dividend it would look like a jump
    total, price, _ = build.returns(close, dividend)
    assert total.loc[dates[1], "X"] == pytest.approx((15 + 15) / 29 - 1) and price.loc[dates[1], "X"] == pytest.approx(15 / 29 - 1)


def test_a_cheap_share_may_move_a_large_percentage_but_a_mirror_image_pair_is_caught_together():
    dates = pd.bdate_range("2024-01-01", periods=6)
    cheap = [0.80, 0.64, 0.79, 0.59, 0.70, 0.70]                  # 20% moves, but each is less than Re 1: allowed on a cheap share
    pair = [50.0, 58.5, 50.0, 50.0, 50.0, 50.0]                    # +17% and then -14.5%: the same move up and back
    near = [50.0, 56.0, 56.0, 56.0, 56.0, 56.0]                    # +12%: inside the limit
    scale_error = [1.23, 0.123, 1.26, 1.23, 1.22, 1.23]            # a share at Rs 1.2 that shows a tenth of its price for a day (a Rs 1.1 move)
    jumps = build.jump_days(pd.DataFrame({"cheap": cheap, "pair": pair, "near": near, "scale": scale_error}, index=dates))
    assert not jumps["cheap"].any() and not jumps["near"].any()
    assert list(jumps["pair"][:2]) == [True, True] and jumps["pair"].sum() == 2
    assert list(jumps["scale"][:2]) == [True, True]                  # more than Re 1, so it is caught even though it is a small sum


def test_a_bad_price_that_lasts_up_to_three_days_and_comes_back_is_replaced():
    dates = pd.bdate_range("2024-01-01", periods=9)
    one_day = [10.0, 10.2, 1.0, 10.1, 10.3, 10.3, 10.3, 10.3, 10.3]                  # a ten-fold error for a day
    two_days = [93.0, 93.5, 467.0, 467.0, 98.0, 99.0, 99.0, 99.0, 99.0]             # five times too high for two days
    shift = [285.0, 284.0, 1412.0, 1412.0, 1415.0, 1420.0, 1420.0, 1420.0, 1420.0]   # a permanent change of level: not a spike
    four_days = [10.0, 10.0, 30.0, 30.0, 30.0, 30.0, 10.0, 10.0, 10.0]              # lasts too long to be treated as an error
    frame = pd.DataFrame({"one": one_day, "two": two_days, "shift": shift, "four": four_days}, index=dates)
    cleaned, found = build.remove_spikes(frame)
    assert list(cleaned["one"][:5]) == [10.0, 10.2, 10.2, 10.1, 10.3]
    assert list(cleaned["two"][:5]) == [93.0, 93.5, 93.5, 93.5, 98.0]
    assert (cleaned["shift"] == frame["shift"]).all() and (cleaned["four"] == frame["four"]).all()
    assert found[["symbol", "days"]].values.tolist() == [["one", 1], ["two", 2]]
    jumps = build.jump_days(cleaned)
    assert bool(jumps.loc[dates[2], "shift"]) and jumps["shift"].sum() == 1              # the level change is a jump instead


def test_corrections_are_listed_for_review():
    m, dates = made_up_dividend_case()
    cleaned, spikes = build.remove_spikes(m["close"])
    _, _, jumps = build.returns(cleaned, m["dividend"])
    fixed = build.corrections(spikes, cleaned, m["dividend"], jumps, ["X", "Y"], pd.Series({"X": "X Ltd", "Y": "Y Ltd"}))
    assert len(fixed) == 1 and fixed.iloc[0]["date"] == dates[2].date() and fixed.iloc[0]["symbol"] == "X"
    assert fixed.iloc[0]["price_move_pct"] == pytest.approx(-20.0) and "daily limit" in fixed.iloc[0]["treatment"]


def test_the_cross_check_against_yahoos_adjusted_close_skips_an_invalid_series():
    m, _ = made_up_dividend_case()
    raw_total = build.holding_period_return(m["close"], m["dividend"])
    check = build.cross_check(m, raw_total, ["X", "Y"])
    assert check["companies_compared"] == 1 and check["excluded"] == ["Y"] and check["dividend_events"] == 1
    assert check["days_agreeing_pct"] == 100.0 and check["gap_over_5_points"] == 0


def test_rupee_rates_use_the_last_rate_on_or_before_each_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW", tmp_path)
    assert build.fx_rates(pd.Timestamp("2021-10-27"), pd.Timestamp("2026-10-27")) is None        # no file yet
    (tmp_path / "yahoo").mkdir()
    fx = pd.DataFrame({"rupees_per_dollar": [170.0, 172.0, 280.0]}, index=pd.to_datetime(["2021-10-26", "2021-10-28", "2026-10-26"]))
    fx.rename_axis("date").to_csv(tmp_path / config.FX_FILE)
    rates = build.fx_rates(pd.Timestamp("2021-10-27"), pd.Timestamp("2026-10-27"))
    assert rates["base"] == 170.0 and rates["end"] == 280.0 and rates["rupee_change"] == pytest.approx(280 / 170 - 1)


# ---- the download ---------------------------------------------------------------------------------------------------
def _one_row(symbol):
    return pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "close": [1.0], "adj_close": [1.0], "volume": [10], "dividend": [0.0],
                         "split": [0.0], "symbol": [symbol]})


def test_an_empty_answer_is_retried_and_only_believed_after_every_round(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW", tmp_path)
    monkeypatch.setattr(ingest.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(ingest, "MAX_EMPTY_SHARE", 0.5)
    calls = {"A": 0, "B": 0, "C": 0}

    def fake(symbol):
        calls[symbol] += 1
        if symbol == "A" or (symbol == "B" and calls["B"] >= 2):       # B times out the first time, which looks like "no data"
            return _one_row(symbol)
        return None

    monkeypatch.setattr(ingest, "_single", fake)
    prices, missing = ingest.fetch_prices(["A", "B", "C"])
    assert sorted(prices["symbol"]) == ["A", "B"] and missing == ["C"]
    assert calls == {"A": 1, "B": 2, "C": ingest.ROUNDS}
    prices_again, missing_again = ingest.fetch_prices(["A", "B", "C"])           # a second run uses the saved answers
    assert calls == {"A": 1, "B": 2, "C": ingest.ROUNDS} and missing_again == ["C"] and len(prices_again) == 2


def test_a_download_that_gets_nothing_back_is_an_error_not_an_empty_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW", tmp_path)
    monkeypatch.setattr(ingest.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(ingest, "_single", lambda symbol: None)
    with pytest.raises(RuntimeError, match="outage"):
        ingest.fetch_prices(["A", "B", "C"])


# ---- the listing ----------------------------------------------------------------------------------------------------
PAGE = """<table><thead><tr><th>SYMBOL</th><th>SECTOR</th></tr></thead><tbody>
<tr><td data-order="OGDC"><a data-title="Oil &amp; Gas Development Company"><strong>OGDC</strong></a></td><td>0820</td><td>ALLSHR,KSE100,KSE100PR</td>{cells}</tr>
<tr><td data-order="OGDCR"><a data-title="OGDC (Right)"><strong>OGDCR</strong></a></td><td></td><td></td>{cells}</tr>
<tr><td data-order="ABC"><a data-title="ABC Mills"><strong>ABC</strong></a></td><td>0830</td><td>ALLSHR,KMIALLSHR</td>{cells}</tr>
</tbody></table>""".format(cells="<td>1</td>" * 8)


def test_the_screener_page_is_read_into_the_all_share_universe():
    listings = ingest.parse_screener(PAGE)
    assert listings["symbol"].tolist() == ["OGDC", "OGDCR", "ABC"]
    universe = ingest.universe_from_listings(listings)
    assert universe["symbol"].tolist() == ["ABC", "OGDC"]                       # the right (a rights issue) is not in the All Share
    assert universe.set_index("symbol").loc["OGDC", "in_kse100"] and not universe.set_index("symbol").loc["ABC", "in_kse100"]
    assert universe.set_index("symbol").loc["OGDC", "sector"] == "Oil and gas exploration"
    with pytest.raises(ValueError, match="expected 11"):
        ingest.parse_screener(PAGE.replace("<td>1</td>", "", 1))
