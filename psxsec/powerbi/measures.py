"""DAX measures for the Power BI report.

This list is the single source: model.py writes it into the semantic model and measures_text() writes
powerbi/measures.dax so the DAX can be read without opening Power BI.

Rules learned the hard way (in the first Power BI report of this portfolio and in this one). Measures live in a table called
_Measures (the name "Measures" is rejected); a year-filtered measure must keep the year in a VAR, because filtering a column by
a measure inside CALCULATE makes the measure invalid; the table called levels must be written 'levels' in DAX, because
Power BI reads the bare word as a keyword ("the syntax for 'levels' is incorrect"); and a count that can be zero is wrapped in
COALESCE so a card shows 0 and not "(Blank)".
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass


@dataclass(frozen=True)
class Measure:
    name: str
    folder: str
    fmt: str | None
    dax: str


FRACTION = "0.0%"       # values stored as fractions (0.123 means 12.3%)
WHOLE_PCT = "0%"
WHOLE = "#,0"
ONE = "0.0"
TWO = "0.00"
THREE = "0.000"
SIGNED = "+0.00;-0.00"
TEXT = "General"

M = Measure


def count_where(table: str, column: str, op: str, bound: str) -> str:
    """The rows of a table that pass a test, as 0 (not blank) when none do."""
    return f"COALESCE ( CALCULATE ( COUNTROWS ( {table} ), {table}[{column}] {op} {bound} ), 0 )"


# The two lines drawn on the "pick a series" charts until the reader picks one to eight series of their own.
DEFAULT_SERIES = '{ "Whole market", "Cash at the policy rate" }'

MEASURES: list[Measure] = [
    # ------------------------------------------------------------------ The whole market
    M("Market Return a Year", "The whole market", FRACTION, "MAX ( market[market_cagr] )"),
    M("Cash Return a Year", "The whole market", FRACTION, "MAX ( market[cash_cagr] )"),
    M("Market Excess Return a Year", "The whole market", FRACTION, "[Market Return a Year] - [Cash Return a Year]"),
    M("Market Volatility", "The whole market", FRACTION, "MAX ( market[market_volatility] )"),
    M("Market Worst Fall", "The whole market", WHOLE_PCT, "MAX ( market[market_max_drawdown] )"),
    M("Market Sharpe", "The whole market", TWO, "MAX ( market[market_sharpe] )"),
    M("Market Return in Dollars a Year", "The whole market", FRACTION, "MAX ( market[market_usd_cagr] )"),
    M("Companies Analysed", "The whole market", "0", "MAX ( market[n_companies] )"),
    M("Top Sector by Sharpe", "The whole market", TEXT, "SELECTEDVALUE ( market[top_sector] )"),
    M("Top Sector Sharpe", "The whole market", TWO, "MAX ( market[top_sharpe] )"),

    # ------------------------------------------------------------------ Return and risk of a sector
    M("Sector Count", "Return and risk", "0", "COUNTROWS ( sectors )"),
    M("Return a Year", "Return and risk", FRACTION, "AVERAGE ( sectors[cagr] )"),
    M("Volatility", "Return and risk", FRACTION, "AVERAGE ( sectors[volatility] )"),
    M("Worst Fall", "Return and risk", WHOLE_PCT, "AVERAGE ( sectors[max_drawdown] )"),
    M("Sharpe Ratio", "Return and risk", TWO, "AVERAGE ( sectors[sharpe] )"),
    M("Sharpe Ratio Low", "Return and risk", TWO, "AVERAGE ( sectors[sharpe_lo] )"),
    M("Sharpe Ratio High", "Return and risk", TWO, "AVERAGE ( sectors[sharpe_hi] )"),
    M("Companies", "Return and risk", WHOLE, "SUM ( sectors[n_companies] )"),
    M("Dividend Points", "Return and risk", FRACTION, "AVERAGE ( sectors[dividend_points] )"),
    M("Return in Dollars a Year", "Return and risk", FRACTION, "AVERAGE ( sectors[usd_cagr] )"),
    M("Rank by Sharpe", "Return and risk", "0", "AVERAGE ( sectors[rank_sharpe] )"),
    M("Sectors Clearly Better Than Market", "Return and risk", "0", count_where("sectors", "p_beats_market", ">=", "0.95")),
    M("Sectors Clearly Worse Than Market", "Return and risk", "0", count_where("sectors", "p_beats_market", "<=", "0.05")),
    M("Sector Year Return", "Return and risk", WHOLE_PCT, "AVERAGE ( year_returns[period_return] )"),
    M("Market Year Return", "Return and risk", WHOLE_PCT, """
CALCULATE (
    AVERAGE ( market_years[period_return] ),
    TREATAS ( VALUES ( year_returns[period_index] ), market_years[period_index] )
)"""),
    M("Highlight Level", "Return and risk", "0", "AVERAGE ( levels_top[level] )"),
    M("Selected Level", "Return and risk", "0", f"""
VAR picked = COUNTROWS ( ALLSELECTED ( 'levels'[series] ) )
VAR shown = SELECTEDVALUE ( 'levels'[series] )
RETURN
    IF ( picked <= 8 || shown IN {DEFAULT_SERIES}, AVERAGE ( 'levels'[level] ), BLANK () )"""),
    M("Selected Drawdown", "Return and risk", ONE, f"""
VAR picked = COUNTROWS ( ALLSELECTED ( 'levels'[series] ) )
VAR shown = SELECTEDVALUE ( 'levels'[series] )
RETURN
    IF ( picked <= 8 || shown IN {DEFAULT_SERIES}, AVERAGE ( 'levels'[drawdown_pct] ), BLANK () )"""),

    # ------------------------------------------------------------------ How sure
    M("Chance of First", "How sure", WHOLE_PCT, "AVERAGE ( sectors[p_top1] )"),
    M("Chance of Top 3", "How sure", WHOLE_PCT, "AVERAGE ( sectors[p_top3] )"),
    M("Chance Better Than Market", "How sure", WHOLE_PCT, "AVERAGE ( sectors[p_beats_market] )"),
    M("Sectors With a 10% Chance of First", "How sure", "0", count_where("sectors", "p_top1", ">=", "0.1")),
    M("Top Sector Chance of First", "How sure", WHOLE_PCT, "MAX ( market[top_p1] )"),
    M("Rank in Each Analysis", "How sure", "0", "AVERAGE ( rank_choices[position] )"),
    M("Method Rank Correlation (median)", "How sure", TWO, "MAX ( market[method_rank_correlation_median] )"),
    M("Method Rank Correlation (lowest)", "How sure", TWO, "MAX ( market[method_rank_correlation_min] )"),
    M("Date Rank Correlation (lowest)", "How sure", TWO, "MAX ( market[period_rank_correlation_min] )"),
    M("First vs Second Half Correlation", "How sure", TWO, "MAX ( market[half_correlation] )"),

    # ------------------------------------------------------------------ Skill or luck
    M("Beta", "Skill or luck", TWO, "AVERAGE ( sectors[beta] )"),
    M("Alpha a Year", "Skill or luck", WHOLE_PCT, "AVERAGE ( sectors[alpha] )"),
    M("Alpha t", "Skill or luck", ONE, "AVERAGE ( sectors[alpha_t] )"),
    M("Alpha p Alone", "Skill or luck", THREE, "AVERAGE ( sectors[alpha_p] )"),
    M("Alpha p Corrected", "Skill or luck", THREE, "AVERAGE ( sectors[alpha_p_adjusted] )"),
    M("Alpha q", "Skill or luck", THREE, "AVERAGE ( sectors[alpha_q] )"),
    M("Sortino Ratio", "Skill or luck", TWO, "AVERAGE ( sectors[sortino] )"),
    M("Bad Day Loss", "Skill or luck", FRACTION, "AVERAGE ( sectors[cvar_95] )"),
    M("Up Capture", "Skill or luck", WHOLE_PCT, "AVERAGE ( sectors[up_capture] )"),
    M("Down Capture", "Skill or luck", WHOLE_PCT, "AVERAGE ( sectors[down_capture] )"),
    M("Deflated Sharpe", "Skill or luck", TWO, "AVERAGE ( sectors[dsr] )"),
    M("Longest Fall (months)", "Skill or luck", "0", "AVERAGE ( sectors[longest_fall_months] )"),
    M("Alpha Significant Alone", "Skill or luck", "0", count_where("sectors", "alpha_p", "<", "0.05")),
    M("Alpha Significant After Correction", "Skill or luck", "0", count_where("sectors", "alpha_p_adjusted", "<", "0.05")),
    M("Alpha Significant Looser Rule", "Skill or luck", "0", count_where("sectors", "alpha_q", "<", "0.05")),
    M("Best Alpha", "Skill or luck", WHOLE_PCT, "MAX ( market[best_alpha] )"),
    M("Best Alpha Sector", "Skill or luck", TEXT, "SELECTEDVALUE ( market[best_alpha_sector] )"),
    M("Best Alpha p Corrected", "Skill or luck", THREE, "MAX ( market[best_alpha_p_adjusted] )"),
    M("Best Deflated Sharpe", "Skill or luck", TWO, "MAX ( market[best_dsr] )"),
    M("Luck Bar for Sharpe", "Skill or luck", TWO, "MAX ( market[expected_best_sharpe] )"),

    # ------------------------------------------------------------------ What moves the sectors
    M("Rate Effect", "What moves the sectors", TWO, "AVERAGE ( sectors[rate_beta] )"),
    M("Rupee Effect", "What moves the sectors", TWO, "AVERAGE ( sectors[fx_beta] )"),
    M("Market Share of Variation", "What moves the sectors", FRACTION, "MAX ( market[pc1_share] )"),
    M("Effective Bets", "What moves the sectors", ONE, "MAX ( market[effective_bets] )"),
    M("Average Correlation", "What moves the sectors", TWO, "MAX ( market[mean_correlation] )"),
    M("Average Correlation Without Market", "What moves the sectors", TWO, "MAX ( market[residual_mean_correlation] )"),
    M("Sectors Reacting to Rates", "What moves the sectors", "0", "MAX ( market[n_rate_fdr] )"),
    M("Sectors Reacting to the Rupee", "What moves the sectors", "0", "MAX ( market[n_fx_fdr] )"),
    M("Component Share", "What moves the sectors", FRACTION, "AVERAGE ( components[share] )"),
    M("Component 1 Loading", "What moves the sectors", TWO, "AVERAGE ( sectors[component_1] )"),
    M("Component 2 Loading", "What moves the sectors", TWO, "AVERAGE ( sectors[component_2] )"),

    # ------------------------------------------------------------------ Could the ranking have been used?
    M("Strategy Level", "Out of sample", "0", "AVERAGE ( strategy_levels[level] )"),
    M("Winners Sharpe", "Out of sample", TWO, """
CALCULATE ( AVERAGE ( strategies[sharpe] ), strategies[strategy_key] = "winners" )"""),
    M("Equal Weight Sharpe", "Out of sample", TWO, """
CALCULATE ( AVERAGE ( strategies[sharpe] ), strategies[strategy_key] = "equal_weight" )"""),
    M("Winners p Alone", "Out of sample", THREE, """
CALCULATE ( AVERAGE ( strategies[vs_equal_p] ), strategies[strategy_key] = "winners" )"""),
    M("Winners p Corrected", "Out of sample", THREE, """
CALCULATE ( AVERAGE ( strategies[vs_equal_p_adjusted] ), strategies[strategy_key] = "winners" )"""),
    M("Minimum Variance Sharpe", "Out of sample", TWO, """
CALCULATE ( AVERAGE ( strategies[sharpe] ), strategies[strategy_key] = "min_variance" )"""),
    M("Minimum Variance p Corrected", "Out of sample", THREE, """
CALCULATE ( AVERAGE ( strategies[vs_equal_p_adjusted] ), strategies[strategy_key] = "min_variance" )"""),
    M("Information Coefficient", "Out of sample", SIGNED, "AVERAGE ( info_coeff[information_coefficient] )"),
    M("Months Tested", "Out of sample", "0", "MAX ( market[wf_months] )"),
    M("Months Pointing the Right Way", "Out of sample", WHOLE_PCT, """
DIVIDE (
    CALCULATE ( COUNTROWS ( info_coeff ), info_coeff[information_coefficient] > 0 ),
    COUNTROWS ( info_coeff )
)"""),

    # ------------------------------------------------------------------ Preset portfolios
    M("Preset Weight", "Preset portfolios", FRACTION, "AVERAGE ( presets[weight] )"),
    M("Preset Level", "Preset portfolios", "0", "AVERAGE ( preset_levels[level] )"),
    M("Preset Return a Year", "Preset portfolios", FRACTION, "AVERAGE ( preset_stats[cagr] )"),
    M("Preset Volatility", "Preset portfolios", FRACTION, "AVERAGE ( preset_stats[volatility] )"),
    M("Preset Worst Fall", "Preset portfolios", WHOLE_PCT, "AVERAGE ( preset_stats[max_drawdown] )"),
    M("Preset Sharpe", "Preset portfolios", TWO, "AVERAGE ( preset_stats[sharpe] )"),
]


# One line for each measure a report reader is likely to hover over. Shown as the measure description in Power BI.
DESCRIPTIONS = {
    "Market Return a Year": "Compound annual return of the whole market (every qualifying company, equal-weighted, dividends included).",
    "Cash Return a Year": "What cash would have earned at the State Bank of Pakistan's policy rate, compounded.",
    "Market Sharpe": "Return above cash per unit of risk for the whole market, scaled to a year.",
    "Return a Year": "Compound annual return of the sector index (equal-weighted, rebalanced monthly, dividends included).",
    "Volatility": "Standard deviation of daily returns, scaled to a year.",
    "Worst Fall": "The largest drop from a peak to a later low of the sector's growth-of-100 series.",
    "Sharpe Ratio": "Average daily return above cash divided by its standard deviation, scaled to a year.",
    "Sharpe Ratio Low": "Lower end of the 95% range from resampling the days 2,000 times.",
    "Sharpe Ratio High": "Upper end of the 95% range from resampling the days 2,000 times.",
    "Chance of First": "Share of the 2,000 resampled histories in which the sector had the best Sharpe ratio.",
    "Chance of Top 3": "Share of the 2,000 resampled histories in which the sector was in the top three by Sharpe ratio.",
    "Chance Better Than Market": "Share of the resampled histories in which the sector's Sharpe ratio beat the whole market's.",
    "Selected Level": "Growth of 100 rupees for the series picked in the list (one to eight). Until something is picked it draws the whole market and cash.",
    "Selected Drawdown": "How far below its previous high each picked series was, in percent (one to eight). Until something is picked it draws the whole market and cash.",
    "Rank in Each Analysis": "Position by Sharpe ratio (1 is best) under the main analysis and each of the twelve other ways of doing it.",
    "Beta": "How strongly the sector follows the rest of the market (every company outside that sector); 1 means one for one.",
    "Alpha a Year": "Return a year that the rest of the market does not explain (weekly market model with the Dimson correction).",
    "Alpha p Alone": "Two-sided p-value of the alpha, tested for this sector on its own (Newey-West errors).",
    "Alpha p Corrected": "p-value after allowing for having looked at every ranked sector (Romano-Wolf resampling test).",
    "Alpha q": "False-discovery-rate version of the p-value (Benjamini-Hochberg): a looser rule that lets a small share of false findings through.",
    "Deflated Sharpe": "Chance that the true Sharpe ratio beats what the best of all the sectors would reach by luck alone.",
    "Bad Day Loss": "Average return on the worst 5% of days (expected shortfall at 95%).",
    "Up Capture": "Sector's average gain in the months the rest of the market rose, as a share of the market's own.",
    "Down Capture": "Sector's average loss in the months the rest of the market fell, as a share of the market's own.",
    "Alpha Significant After Correction": "Sectors whose alpha stays significant at 5% once the test allows for looking at all of them.",
    "Luck Bar for Sharpe": "The Sharpe ratio the best of all the sectors would be expected to reach if none had any skill.",
    "Rate Effect": "Extra return in a month, in percent, for each percentage point the policy rate rose, with the rest of the market held fixed.",
    "Rupee Effect": "Extra return in a month, in percent, for each 1% the rupee weakened against the dollar, with the rest of the market held fixed.",
    "Market Share of Variation": "Share of all the variation in sector returns carried by the first principal component, the market-wide movement.",
    "Effective Bets": "How many equally important independent sources of risk would give the same concentration of variance.",
    "Average Correlation Without Market": "Average correlation between two sectors after the part the rest of the market explains is taken out.",
    "Strategy Level": "Growth of 100 rupees of a rule that chooses weights each month using only the previous 12 months.",
    "Winners Sharpe": "Sharpe ratio of holding the three sectors with the best past Sharpe ratio, chosen anew each month.",
    "Winners p Corrected": "p-value of that rule's Sharpe ratio against equal weights, multiplied by the five comparisons made.",
    "Information Coefficient": "Rank correlation between the sectors' Sharpe ratios over the previous 12 months and their returns in the next month.",
    "Preset Weight": "Share of the portfolio in the sector. The presets are worked out with hindsight from the whole five years.",
}


def measure_lines(measure: Measure) -> list[str]:
    """The DAX of one measure as lines, indented relative to the first line."""
    return [ln.rstrip() for ln in textwrap.dedent(measure.dax).strip("\n").splitlines() if ln.strip()]


def measures_text() -> str:
    """powerbi/measures.dax: every measure, grouped by folder, ready to paste into Power BI Desktop."""
    out = ["// Measures for the PSX sector risk and return report. Generated by `python -m psxsec report`.",
           "// All measures live in a table called _Measures. A year-filtered measure keeps the year in a VAR:",
           "// filtering a column by a measure inside CALCULATE makes the measure invalid in Power BI.",
           "// The table called levels is written 'levels' in DAX, because the bare word is read as a keyword.", ""]
    folder = None
    for m in MEASURES:
        if m.folder != folder:
            folder = m.folder
            out += [f"// ---------- {folder} ----------", ""]
        if m.name in DESCRIPTIONS:
            out.append(f"// {DESCRIPTIONS[m.name]}")
        lines = measure_lines(m)
        if len(lines) == 1:
            out.append(f"{m.name} = {lines[0]}")
        else:
            out.append(f"{m.name} =")
            out += lines
        out.append("")
    return "\n".join(out)
