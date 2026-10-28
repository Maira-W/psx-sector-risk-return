"""Write README.md and the documents in docs/ from templates and the results, so a number in the text cannot drift
from the data. Edit the templates in psxsec/templates/docs, not the output.

A placeholder is {{name}} or {{name:format}} (a Python format such as .1f or ,.0f). A name with no value is an error.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from . import config, metrics
from .analysis import MARKET

TEMPLATE_DIR = config.TEMPLATES / "docs"
OUTPUTS = {"readme.md": config.ROOT / "README.md", "memo.md": config.DOCS / "recommendation_memo.md",
           "methodology.md": config.DOCS / "methodology.md", "data_sources.md": config.DOCS / "data_sources.md"}
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*(?::([^{}]+?))?\s*\}\}")


def render(template: str, values: dict) -> str:
    def fill(m: re.Match) -> str:
        name, fmt = m.group(1), m.group(2)
        if name not in values:
            raise KeyError(f"template uses {name!r}, which has no value")
        return format(values[name], fmt) if fmt else str(values[name])
    return PLACEHOLDER.sub(fill, template)


def _table(headers: list[str], rows: list[list], align: str) -> str:
    rule = ["---:" if a == "r" else "---" for a in align]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(rule) + " |"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def _join(names: list[str]) -> str:
    names = list(names)
    if not names:
        return "none"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _date(iso: str) -> str:
    d = pd.Timestamp(iso)
    return f"{d.day} {d:%B %Y}"


def _month(iso: str) -> str:
    return f"{pd.Timestamp(iso):%b %Y}"


def _p(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def _sp(x: float, digits: int = 1) -> str:
    return f"{x * 100:+.{digits}f}%"


def context() -> dict:
    p = config.PROCESSED
    s = json.loads((p / "summary.json").read_text(encoding="utf-8"))
    t = pd.read_csv(p / "sector_summary.csv", dtype={"sector_code": str})
    ranked = t[t["ranked"]].sort_values("sharpe", ascending=False).reset_index(drop=True)
    unranked = t[~t["ranked"] & (t["sector"] != MARKET)]
    mk = t[t["sector"] == MARKET].iloc[0]
    robust = pd.read_csv(p / "robustness_summary.csv").set_index("choice")
    sharpes = pd.read_csv(p / "robustness_sharpe.csv", index_col=0)
    funnel = pd.read_csv(p / "universe_funnel.csv")
    status = pd.read_csv(p / "stock_status.csv", dtype={"sector_code": str})
    stocks = pd.read_csv(p / "stock_summary.csv")
    corr = pd.read_csv(p / "sector_correlations.csv", index_col=0)
    policy = pd.read_csv(config.POLICY_RATE_FILE)
    manifest = json.loads(config.MANIFEST.read_text(encoding="utf-8"))["files"]
    quality = s["quality"]
    w, safe = s["window"], s["safe"]
    prices = manifest[config.PRICES_FILE]
    top, bottom = s["top_sharpe"], s["bottom_sharpe"]
    t1 = ranked.iloc[0]

    # which sector led each twelve-month period
    edges = w["year_edges"]
    year_rows, leaders = [], []
    for k in range(1, 6):
        col = ranked[f"year{k}"]
        best, worst = ranked.loc[col.idxmax()], ranked.loc[col.idxmin()]
        leaders.append(best["sector"])
        year_rows.append([f"Year {k}", f"{_month(edges[k - 1])} to {_month(edges[k])}", f"{best['sector']} ({_sp(best[f'year{k}'], 0)})",
                          f"{worst['sector']} ({_sp(worst[f'year{k}'], 0)})", _sp(mk[f"year{k}"], 0)])

    sectors_only = [c for c in corr.columns if c != MARKET]
    pair = corr.loc[sectors_only, sectors_only]
    pair_values = pair.where(~(pair.index.to_numpy()[:, None] == pair.columns.to_numpy()[None, :])).stack()
    lowest_pair = pair_values.idxmin()
    lowest_to_market = ranked.sort_values("correlation_with_market").iloc[0]

    half_corr = metrics.spearman(sharpes["First half of the window"], sharpes["Second half of the window"])
    first_half_top = sharpes["First half of the window"].idxmax()
    second_half_top = sharpes["Second half of the window"].idxmax()
    best_cagr = ranked.sort_values("cagr", ascending=False).iloc[0]
    deepest = ranked.sort_values("max_drawdown").iloc[0]
    shallow = ranked.sort_values("max_drawdown", ascending=False).iloc[0]
    lowvol = ranked.sort_values("volatility").iloc[0]
    most_div = ranked.sort_values("dividend_points", ascending=False).iloc[0]
    qualifying = status[status["status"] == "qualifies"]
    kse_missing = status[(status["status"] == "no prices on Yahoo Finance") & status["in_kse100"]]["symbol"].tolist()
    contenders = ranked[ranked["p_top1"] >= 0.10]
    above = ranked[ranked["p_beats_market"] >= 0.95]
    below = ranked[ranked["p_beats_market"] <= 0.05]
    reb = ranked.assign(gap=ranked["cagr_daily_rebalanced"] - ranked["cagr_buy_and_hold"]).sort_values("gap", ascending=False).iloc[0]
    kse = robust.loc["KSE-100 companies only"]
    fixes = quality["corrections"]
    large_bullet = (f"- **Without companies with price corrections** drops the {fixes['companies']} qualifying companies that have at least one correction "
                    "(`data/processed/price_corrections.csv`), in case a correction missed or mishandled an event." if fixes["companies"] else "")
    fx = quality["fx"]
    usd_note = (f"rupees per dollar went from {fx['base']:.1f} to {fx['end']:.1f}, so in dollars the whole market returned {mk['usd_cagr'] * 100:.1f}% a year "
                f"against {mk['cagr'] * 100:.1f}% in rupees")

    if s["max_p_top1"] >= 0.6:
        certainty = (f"{t1['sector']} is a fairly clear leader: it finishes first in {_p(t1['p_top1'], 0)} of the resampled histories.")
        use_it = "Even a clear leader is one history."
    else:
        certainty = (f"The top of the ranking is not secure. {t1['sector']} finishes first in only {_p(t1['p_top1'], 0)} of the resampled histories, "
                     f"and {len(contenders)} sectors have at least a 10% chance of finishing first. Read the top group as a shortlist, not a winner.")
        use_it = "Use it to build a shortlist, not to pick a winner."

    # how the leader's range compares with the next four
    overlapping = [r for r in top[1:5] if r["hi"] >= top[0]["lo"] and r["lo"] <= top[0]["hi"]]
    if len(overlapping) == len(top[1:5]):
        top5_overlap = "the 95% ranges of the next four sectors all overlap it, so the data cannot separate them from it."
    elif overlapping:
        top5_overlap = f"the 95% ranges of {len(overlapping)} of the next {len(top[1:5])} sectors overlap it."
    else:
        top5_overlap = "none of the next four sectors' 95% ranges overlap it, so it stands apart."

    rb_method, rb_period = s["robustness"]["method"], s["robustness"]["period"]
    if rb_method["median_rank_correlation"] >= 0.8 and rb_method["min_rank_correlation"] >= 0.5:
        rob_verdict = "The ranking is fairly stable when the method is changed."
    elif rb_method["median_rank_correlation"] >= 0.5:
        rob_verdict = "The ranking moves a fair amount when the method is changed, though its broad shape survives."
    else:
        rob_verdict = "The ranking is sensitive to the method, so treat it with caution."
    if rb_period["min_rank_correlation"] >= 0.8:
        period_verdict = "The ranking is fairly stable when the dates are changed."
    elif rb_period["min_rank_correlation"] >= 0.5:
        period_verdict = "The ranking moves a fair amount with the dates used."
    else:
        period_verdict = "The ranking depends strongly on which dates are used."

    n_leaders = len(set(leaders))
    rotation_verdict = ("Leadership rotated almost every year." if n_leaders >= 4 else "Leadership rotated." if n_leaders == 3
                        else "Leadership was fairly persistent.")
    persistence = ("a fair guide" if half_corr >= 0.6 else "only a moderate guide" if half_corr >= 0.3 else "only a weak guide")
    typical_div_share = float((ranked["dividend_points"] / ranked["cagr"]).where(ranked["cagr"] > 0).median())
    div_heading = ("Dividends were a large part of the return." if typical_div_share >= 0.33 else "Dividends were a meaningful part of the return."
                   if typical_div_share >= 0.15 else "Dividends were a modest part of the return.")
    return_heading = "Return alone is a poor guide." if best_cagr["rank_sharpe"] > 2 else "Return and return per unit of risk agree at the top."
    falls_heading = "Falls were deep." if (ranked["max_drawdown"] < -0.2).sum() >= len(ranked) / 2 else "Falls varied widely."

    return {
        # window and universe
        "base_date": _date(w["base_date"]), "end_date": _date(w["end_date"]), "base_month": _month(w["base_date"]), "end_month": _month(w["end_date"]),
        "years": w["years"], "market_days": w["market_days"], "per_year": quality["window"]["market_days_per_year"],
        "n_listings": funnel["companies"].iloc[0], "n_all_share": funnel["companies"].iloc[1], "n_operating": funnel["companies"].iloc[2],
        "n_prices": funnel["companies"].iloc[3], "n_history": funnel["companies"].iloc[4], "n_qualify": s["n_companies"],
        "n_kse100": int(manifest[config.SCREENER_FILE]["in_kse100"]), "n_kse100_qualify": int(qualifying["in_kse100"].sum()),
        "n_sectors": s["n_sectors_ranked"], "n_unranked": s["n_sectors_unranked"], "unranked": _join(s["unranked_sectors"]),
        "n_kse100_no_data": len(kse_missing), "kse100_no_data": _join(kse_missing),
        "n_thin": int((status["status"] == "traded on too few days").sum()), "n_noprice": int((status["status"] == "no prices on Yahoo Finance").sum()),
        "min_sector": config.MIN_SECTOR_STOCKS, "min_kse100_sector": config.MIN_KSE100_SECTOR_STOCKS,
        "min_trading_companies": config.MIN_TRADING_COMPANIES, "min_traded": config.MIN_TRADED_SHARE * 100, "min_history": config.MIN_HISTORY_SHARE * 100,
        "retrieved": manifest[config.PRICES_FILE]["retrieved"][:10], "yf_version": prices["source"].split()[-1],
        "screener_retrieved": manifest[config.SCREENER_FILE]["retrieved"][:10],
        "draws": config.BOOTSTRAP_DRAWS, "block": config.BOOTSTRAP_BLOCK, "seed": config.SEED,
        "jump_pct": (config.JUMP_RATIO - 1) * 100, "jump_down_pct": (1 - 1 / config.JUMP_RATIO) * 100, "jump_rupees": config.JUMP_RUPEES,
        "spike_ratio": config.SPIKE_RATIO, "spike_days": config.SPIKE_DAYS, "spike_back_pct": (config.SPIKE_BACK - 1) * 100,
        # the market and cash
        "mkt_cagr": mk["cagr"] * 100, "mkt_vol": mk["volatility"] * 100, "mkt_mdd": mk["max_drawdown"] * 100, "mkt_sharpe": mk["sharpe"],
        "mkt_total": mk["total_return"] * 100, "mkt_div": mk["dividend_points"], "safe_cagr": safe["cagr"] * 100,
        "policy_start": safe["policy_rate_start"], "policy_peak": safe["policy_rate_peak"], "policy_end": safe["policy_rate_end"],
        "mkt_peak": _month(mk["peak_date"]), "mkt_trough": _month(mk["trough_date"]),
        # the leaders
        "top1": t1["sector"], "top1_sharpe": t1["sharpe"], "top1_lo": t1["sharpe_lo"], "top1_hi": t1["sharpe_hi"], "top1_cagr": t1["cagr"] * 100,
        "top1_vol": t1["volatility"] * 100, "top1_mdd": t1["max_drawdown"] * 100, "top1_p1": t1["p_top1"] * 100, "top1_p3": t1["p_top3"] * 100,
        "top1_n": int(t1["n_companies"]),
        "top3_list": _join([f"{r['sector']} ({r['sharpe']:.2f})" for r in top[:3]]), "top3_names": _join([r["sector"] for r in top[:3]]),
        "top5_names": _join([r["sector"] for r in top[:5]]),
        "bottom_list": _join([f"{r['sector']} ({r['sharpe']:.2f})" for r in bottom]), "bottom1": bottom[-1]["sector"], "bottom1_sharpe": bottom[-1]["sharpe"],
        "bottom1_cagr": bottom[-1]["cagr"] * 100, "bottom1_mdd": bottom[-1]["max_drawdown"] * 100,
        "certainty": certainty, "use_it": use_it, "top5_overlap": top5_overlap, "rob_verdict": rob_verdict, "rotation_verdict": rotation_verdict,
        "persistence": persistence, "div_heading": div_heading, "div_typical_share": typical_div_share * 100, "return_heading": return_heading,
        "falls_heading": falls_heading, "max_p1": s["max_p_top1"] * 100, "n_contenders": len(contenders),
        "contenders": _join(contenders["sector"].tolist()),
        "n_above": len(above), "above": _join(above["sector"].tolist()), "n_below": len(below), "below": _join(below["sector"].tolist()),
        "n_unclear": len(ranked) - len(above) - len(below),
        # return, risk, dividends
        "best_cagr_sector": best_cagr["sector"], "best_cagr": best_cagr["cagr"] * 100, "best_cagr_vol": best_cagr["volatility"] * 100,
        "best_cagr_mdd": best_cagr["max_drawdown"] * 100, "best_cagr_fall": -best_cagr["max_drawdown"] * 100, "best_cagr_rank": int(best_cagr["rank_sharpe"]), "best_cagr_sharpe": best_cagr["sharpe"],
        "deepest_sector": deepest["sector"], "deepest": deepest["max_drawdown"] * 100, "deepest_rank": int(deepest["rank_sharpe"]),
        "shallow_sector": shallow["sector"], "shallow": shallow["max_drawdown"] * 100,
        "lowvol_sector": lowvol["sector"], "lowvol": lowvol["volatility"] * 100,
        "n_deeper_than_20": int((ranked["max_drawdown"] < -0.20).sum()), "n_sectors_ranked": len(ranked),
        "div_median": ranked["dividend_points"].median() * 100, "div_max": most_div["dividend_points"] * 100, "div_max_sector": most_div["sector"],
        "div_market_share": mk["dividend_points"] / mk["cagr"] * 100 if mk["cagr"] > 0 else 0.0,
        "n_still_down": int(ranked["recovery_date"].isna().sum()),
        # diversification
        "corr_mean": pair_values.mean(), "corr_low": pair_values.min(), "corr_low_a": lowest_pair[0], "corr_low_b": lowest_pair[1],
        "corr_to_market_low_sector": lowest_to_market["sector"], "corr_to_market_low": lowest_to_market["correlation_with_market"],
        "corr_to_market_median": ranked["correlation_with_market"].median(),
        # time
        "reb_sector": reb["sector"], "reb_daily": reb["cagr_daily_rebalanced"] * 100, "reb_monthly": reb["cagr"] * 100, "reb_never": reb["cagr_buy_and_hold"] * 100,
        "large_bullet": large_bullet, "usd_note": usd_note, "fx_base": fx["base"], "fx_end": fx["end"], "usd_mkt_cagr": mk["usd_cagr"] * 100,
        "n_leaders": n_leaders, "leaders": _join(sorted(set(leaders))), "half_corr": half_corr, "first_half_top": first_half_top,
        "second_half_top": second_half_top,
        # robustness
        "rob_n": rb_method["n"], "rob_median": rb_method["median_rank_correlation"], "rob_min": rb_method["min_rank_correlation"],
        "rob_top3": rb_method["n_top_sector_stays_top3"], "rob_first": rb_method["n_top_sector_stays_first"], "rob_tested": rb_method["n_tested"],
        "per_n": rb_period["n"], "per_median": rb_period["median_rank_correlation"], "per_min": rb_period["min_rank_correlation"],
        "per_top3": rb_period["n_top_sector_stays_top3"], "per_tested": rb_period["n_tested"], "period_verdict": period_verdict, "rob_total": s["robustness"]["n_choices"],
        "kse_corr": kse["rank_correlation"], "kse_sectors": int(kse["sectors_compared"]), "kse_top_phrase": ("The main top sector is not among the sectors compared." if not bool(kse["top_tested"]) else "The top sector is the same as in the main result."
                           if bool(kse["same_top_sector"]) else "The top sector is different from the main result."),
        # data quality
        "fix_n": fixes["events"], "fix_companies": fixes["companies"], "fix_bad": fixes["bad_prices"], "fix_jump": fixes["beyond_limit"],
        "fix_share": fixes["companies"] / s["n_companies"] * 100,
        "div_events": quality["cross_check"]["dividend_events"], "cc_companies": quality["cross_check"]["companies_compared"],
        "cc_days": quality["cross_check"]["days_agreeing_pct"], "cc_median": quality["cross_check"]["gap_median_points"],
        "cc_over5": quality["cross_check"]["gap_over_5_points"], "cc_max": quality["cross_check"]["gap_max_points"],
        "cc_max_company": quality["cross_check"]["gap_max_company"], "invalid_adj": _join(quality["raw"]["invalid_adjusted_close"]),
        "moved_div": quality["dividends_moved_to_next_market_day"], "no_price": _join(prices["symbols_without_data"][:12]),
        "n_no_price_requested": len(prices["symbols_without_data"]), "n_requested": prices["symbols_requested"], "n_rows": prices["rows"],
        "n_stocks_best_company": int(stocks.shape[0]),
        # tables
        "table_top": _table(["Sector", "Companies", "Return a year", "Volatility", "Worst fall", "Sharpe", "95% range", "Chance of top 3"],
                            [[r.sector, int(r.n_companies), _sp(r.cagr), _p(r.volatility), _p(r.max_drawdown, 0), f"{r.sharpe:.2f}",
                              f"{r.sharpe_lo:.2f} to {r.sharpe_hi:.2f}", _p(r.p_top3, 0)] for r in ranked.head(8).itertuples()], "lrrrrrrr"),
        "table_bottom": _table(["Sector", "Companies", "Return a year", "Volatility", "Worst fall", "Sharpe", "95% range", "Chance of top 3"],
                               [[r.sector, int(r.n_companies), _sp(r.cagr), _p(r.volatility), _p(r.max_drawdown, 0), f"{r.sharpe:.2f}",
                                 f"{r.sharpe_lo:.2f} to {r.sharpe_hi:.2f}", _p(r.p_top3, 0)] for r in ranked.tail(4).itertuples()], "lrrrrrrr"),
        "table_market": _table(["", "Return a year", "Volatility", "Worst fall", "Sharpe"],
                               [["Whole market", _sp(mk["cagr"]), _p(mk["volatility"]), _p(mk["max_drawdown"], 0), f"{mk['sharpe']:.2f}"],
                                ["Cash at the policy rate", _sp(safe["cagr"]), "", "", ""]], "lrrrr"),
        "table_years": _table(["", "Period", "Best sector", "Worst sector", "Whole market"], year_rows, "lllll"),
        "table_robust": _table(["Choice", "Kind", "Sectors compared", "Rank correlation", "Top-3 in common", "Main top sector"],
                               [[name, r.kind, int(r.sectors_compared), "" if pd.isna(r.rank_correlation) else f"{r.rank_correlation:.2f}", f"{int(r.top3_in_common)} of 3",
                                 "not in this analysis" if not r.top_tested else "still first" if r.same_top_sector
                                 else "still in the top 3" if r.main_top_sector_still_top3 else "falls out of the top 3"]
                                for name, r in robust.iterrows()], "llrrrl"),
        "table_funnel": _table(["Step", "Companies"], [[r.step, int(r.companies)] for r in funnel.itertuples()], "lr"),
        "table_unranked": _table(["Sector", "Qualifying companies"], [[r.sector, int(r.n_companies)] for r in unranked.itertuples()], "lr") if len(unranked) else "None.",
        "table_policy": _table(["Effective", "Rate", "How the date was set", "Source"],
                               [[r.effective_date, f"{r.policy_rate_pct:.2f}%", r.date_basis, f"[link]({r.source})"] for r in policy.itertuples()], "lrll"),
        "table_files": _table(["File", "Bytes", "SHA-256 (first 12)", "Source", "Retrieved"],
                              [[f"`data/raw/{k}`", f"{v['bytes']:,}", f"`{v['sha256'][:12]}`", v["source"].split("/")[2] if v["source"].startswith("http") else v["source"],
                                v["retrieved"][:10]] for k, v in manifest.items()], "lrlll"),
        "table_status": _table(["Status", "Companies"], [[k, int(v)] for k, v in status["status"].value_counts().items()], "lr"),
    }


def render_all() -> dict:
    values = context()
    return {path: render((TEMPLATE_DIR / name).read_text(encoding="utf-8"), values) for name, path in OUTPUTS.items()}


def build() -> None:
    for path, text in render_all().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"[docs] wrote {len(OUTPUTS)} documents")
