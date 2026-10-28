# Methodology

This page explains every step from the raw data to the numbers in the dashboard, and the judgement calls made along the way. It describes analysis of the past and is not investment advice.

## 1. The question

Over the {{years:.0f}} years from {{base_date}} to {{end_date}}, which sectors of the Pakistan Stock Exchange gave the best return for the risk? "Best for the risk" is measured by the **Sharpe ratio**: the average return above what cash would have earned, divided by how much that return bounced around, scaled to a year. Volatility and the worst fall from a peak are shown alongside, because one number never tells the whole story.

## 2. Who is in the analysis

The universe is every company in the **KSE All Share Index** on {{screener_retrieved}}, as listed on the Pakistan Stock Exchange data portal, with the sector the exchange gives it. The portal lists {{n_listings}} instruments (shares, rights issues, bonds and others); {{n_all_share}} are in the All Share Index, of which {{n_kse100}} are also in the KSE-100.

{{table_funnel}}

![From every listing to the companies analysed](figures/09_universe.png)

The rules, in order:

1. **Operating companies only.** Close-end mutual funds, exchange traded funds and real estate investment trusts are investment vehicles, not businesses in a sector, and are removed.
2. **A price on nearly every market day.** A company must have a price on at least {{min_history:.0f}}% of the market days in the window, including the first, and one in the last five days. This removes companies listed during the window and those with long gaps.
3. **Traded on at least {{min_traded:.0f}}% of market days.** Where a share does not trade, Yahoo carries the last price forward. A share that rarely trades therefore shows a flat price, which can make it look less volatile (and so better per unit of risk) than it is. The {{min_traded:.0f}}% rule removes {{n_thin}} companies on this ground. The threshold was fixed before returns were looked at, and the results are repeated at 80% and 95% (section 8).
4. **Sectors need {{min_sector}} qualifying companies to be ranked.** Smaller ones are listed but not ranked: {{unranked}}. "Miscellaneous" is a catch-all of unrelated companies, not a sector, so it is not ranked; its companies do count in the whole-market line.

{{table_status}}

The list is a **snapshot of today's membership**, not of the index five years ago. See the limits in section 13.

## 3. Prices and returns

Daily prices, volume and dividends come from Yahoo Finance (`yfinance` {{yf_version}}, retrieved {{retrieved}}) for {{n_requested}} companies; Yahoo had data for {{n_prices}} of them.

- **Total return.** The daily return is (close + dividend paid that day) ÷ previous close − 1, the standard holding-period return, from Yahoo's split-adjusted *close* (Yahoo appears to record PSX bonus issues as splits: ratios such as 1.10 and 1.25 appear in its data) and its dividend column. The price return is the change in the close alone; the difference between the two is the dividend contribution. Yahoo's own dividend-adjusted close is *not* used: it is invalid for {{invalid_adj}} (it goes negative) and treats very large dividends differently. It serves as a cross-check instead (section 13).
- **Market days.** Yahoo lists PSX holidays as rows with no volume and the previous price carried forward. A date counts as a market day only if at least {{min_trading_companies}} companies traded on it. That leaves {{market_days:,}} market days over {{years:.2f}} years, about {{per_year:.0f}} a year.
- **The window.** The base date is {{base_date}}, the last market day on or before five years before the end date. The first return is the day after it and the last is on {{end_date}}.
- **Gaps.** A missing price is filled with the previous one (a zero return) after the company has passed the history rule above.
- **Cleaning.** Yahoo's prices contain errors, and corporate actions that it has not adjusted for. The exchange limits a share's move in one day to a percentage of the previous close (7.5% from 2020, with later reports of 10%) or Re 1, whichever is larger, so two kinds of move cannot be real. Both are corrected by fixed rules, and every correction is listed in [`data/processed/price_corrections.csv`](../data/processed/price_corrections.csv).
  1. *A bad price.* A price that is at least {{spike_ratio}} times (or at most 1/{{spike_ratio}} of) the day before on every day of a run of up to {{spike_days}} days, and then comes back to within {{spike_back_pct:.0f}}% of where it was, is replaced by the price before the run ({{fix_bad}} cases; for example Lucky Cement's price shows a fifth of its value for three days in February 2025).
  2. *A move beyond the daily limit.* A one-day change of at least {{jump_pct:.0f}}% up (or the same move down, {{jump_down_pct:.0f}}%) that is also larger than Rs {{jump_rupees}} (Re 1, the exchange's floor for the limit, plus a little for rounding) is outside the limit, so it is an unadjusted bonus issue or share split, or a data error. The day's price return is set to zero and only a dividend, if any, counts ({{fix_jump}} cases). The rupee condition keeps genuine moves in cheap shares, where Re 1 can be a large percentage. Because the same move up and down is caught, a wrong price level that starts and ends inside the data is corrected at both ends.

  In all, {{fix_n}} corrections were made in {{fix_companies}} of the {{n_qualify}} qualifying companies ({{fix_share:.0f}}%). Unadjusted corporate actions smaller than the thresholds (a 10% bonus issue, say) cannot be told from ordinary moves and remain in the data.

## 4. Sector indexes

A sector index holds **equal amounts of each qualifying company at the start of every month** and lets the holdings drift with prices until the next month (monthly rebalancing). Its daily return is the change in the value of that portfolio. The **whole market** line is the same portfolio over all {{n_qualify}} qualifying companies, including those in small sectors and "Miscellaneous".

Equal weights were chosen because the question is about the sector, not about its biggest company: a value-weighted index of the banking sector is mostly a handful of banks. The cost is that a small, hardly traded company counts as much as a large one; the trading rule limits this.

Monthly rather than daily rebalancing is deliberate. Putting the weights back to equal every day flatters shares that trade rarely, because a price that bounces between the bid and the ask looks like a return when it is averaged every day, and nobody rebalances daily. The effect is largest for {{reb_sector}}: {{reb_daily:.0f}}% a year with daily rebalancing, {{reb_monthly:.0f}}% with monthly rebalancing (used here) and {{reb_never:.0f}}% never rebalanced. The results table carries the daily and never-rebalanced returns (`cagr_daily_rebalanced`, `cagr_buy_and_hold`) so the effect can be seen, and "Rebalanced every day" is one of the other choices tested in section 8.

## 5. The measures

| Measure | Definition |
|---|---|
| Return a year | Compound annual growth rate: (1 + total return)^(1 / years) − 1 |
| Volatility | Standard deviation of daily returns × √(market days per year) |
| Worst fall | The largest drop from a peak of the growth-of-100 series to a later low, with its dates; "recovered" if the old peak was regained |
| Sharpe ratio | (average daily return − average daily safe return) ÷ standard deviation of that difference × √(market days per year) |
| Return by year | Compound return in each of five consecutive twelve-month periods from the base date |
| Beta, alpha | Of the sector's weekly return above cash on the rest of the market's, this week and last (section 9) |
| Correlation | Of daily returns, between two sectors or a sector and the market |

**The safe return** is what cash would have earned at the State Bank's policy rate. Each return period (a day, or a weekend and a day) accrues the rate in force on the previous market day, simply: rate × calendar days ÷ 365. The policy rate went from {{policy_start}}% to a peak of {{policy_peak}}% and ended at {{policy_end}}%; cash returned {{safe_cagr:.1f}}% a year. The table of changes, with a source for every row, is in [data sources](data_sources.md). The policy rate stands in for a risk-free rate; Treasury bill yields were close to it but are not freely available in a form that can be downloaded.

## 6. How sure can we be?

A ranking from one five-year history may owe a lot to the order in which things happened. To see how much:

- The days are **resampled** {{draws}} times with a *stationary block bootstrap*: the resampled history is built from runs of consecutive days whose lengths vary randomly with an average of {{block}}, so that short streaks of ups and downs stay together. The same resampled days are used for every sector, which keeps their relationships.
- In each resampled history every sector's Sharpe ratio is computed and the sectors are ranked. This gives each sector a **95% range for its Sharpe ratio** (the 2.5th to 97.5th percentile), a **95% range for its position** in the ranking, the **chance it finishes first** and **in the top three**, and the **chance it beats the whole market**. "Very likely better" means at least 95% of resampled histories.

{{certainty}}

## 7. What the bootstrap cannot do

It resamples the days of one history, so it cannot show what a different economic regime would have done, and it treats the choice of window as given. It is a measure of luck within this history, not a forecast.

## 8. Other choices

The whole analysis was repeated with one choice changed at a time. The rank correlation compares each ranking with the main one (1 is the same order).

{{table_robust}}

For the {{rob_n}} choices about *method*, the rank correlation with the main result has a median of {{rob_median:.2f}} and a minimum of {{rob_min:.2f}}, and the main top sector stays in the top three in {{rob_top3}} of the {{rob_tested}} in which it is included (a choice can remove it: a sector needs {{min_sector}} qualifying companies to be ranked). For the {{per_n}} choices about *dates*, the median is {{per_median:.2f}} and the minimum {{per_min:.2f}}. {{period_verdict}}

- **KSE-100 companies only** uses the {{n_kse100_qualify}} KSE-100 companies that qualify, and sectors with at least {{min_kse100_sector}} of them ({{kse_sectors}} sectors). {{kse_top_phrase}}
- **Must trade on 80% or 95% of days** moves the trading rule either way.
- **Rebalanced every day** puts the weights back to equal every day instead of every month.
- **Weekly returns** compound each company's daily returns into Friday-to-Friday weeks before averaging, which reduces the effect of stale prices.
- **Without each sector's best company** drops the single best performer in every sector, to test whether one stock carries the result.
- **Typical company (median)** replaces the sector index with the median Sharpe ratio of its companies.
- **First and second half, start 3 months later, end 3 months earlier** test sensitivity to the dates. The rank correlation between the first-half and second-half orderings is {{half_corr:.2f}}.
{{large_bullet}}

## 9. Skill or luck? Beta, alpha and a correction for testing many sectors

A high Sharpe ratio can come from moving with a rising market, or from carrying little of the market's risk, as well as from doing something special. This section separates them.

- **The rest of the market.** For each sector the benchmark is every qualifying company *outside* that sector, equal-weighted and rebalanced monthly, so a sector is never compared with itself.
- **The market model.** Weekly (Friday to Friday) returns above cash, {{weeks}} weeks. For each sector: excess return this week = alpha + b0 × the rest of the market's excess return this week + b1 × its excess return last week + error. Including last week's market return (the Dimson correction) catches shares that trade late, which would otherwise look less sensitive to the market than they are. **Beta is b0 + b1.** Alpha is the intercept, multiplied by the {{weeks_per_year:.1f}} weeks in a year. The standard errors allow for errors that are related across up to {{hac_weekly}} weeks and for spread that changes over time (Newey and West).
- **Why weekly.** Daily returns of thinly traded shares are blurred by the order in which prices update; weekly returns are less affected.
- **Looking at many sectors.** The p-value of the best of {{n_sectors_ranked}} sectors is too kind: with {{n_sectors_ranked}} chances, at least one sector passes the usual 5% test by luck in about {{naive_flag:.0f}}% of cases. The correction is the single-step max-t method of Romano and Wolf, in the spirit of White's reality check. The weeks are resampled in blocks (average {{block_weeks}} weeks, {{draws}} draws, keeping each sector's weeks and the market's together), every sector's alpha is re-estimated around its own estimate, and the largest t-statistic over all {{n_sectors_ranked}} sectors is recorded in each draw. A sector's corrected p-value is how often that largest t-statistic is at least as big as the sector's own. With no real alpha anywhere, the largest t-statistic would exceed {{null_t:.2f}} one time in twenty. A test on made-up markets of pure noise checks that the correction rarely flags a sector.
- **A looser rule.** The false discovery rate (Benjamini and Hochberg) accepts that a small share of the findings may be false, and so lets more through; it is `alpha_q` in the results table. {{fdr_note}}
- **Deflated Sharpe ratio.** The probabilistic Sharpe ratio (Bailey and López de Prado, 2012) is the probability that the true Sharpe ratio exceeds a benchmark, given the number of returns and their skewness and kurtosis. The deflated version (2014) sets the benchmark at the Sharpe ratio that the best of {{n_sectors_ranked}} sectors with no skill would be expected to reach, which here is {{expected_best_sharpe:.2f}}. It answers: could the best sector's Sharpe ratio be luck?
- **More measures of risk.** The Sortino ratio (only days below cash count as risk); the one-day value at risk and expected shortfall at 95% (`var_95`, and `cvar_95`, the average return on the worst 5% of days); skewness and excess kurtosis; the longest time spent below a previous peak, in months; and up and down capture (a sector's average gain in the months when the rest of the market rose, and its average loss in the months it fell, as shares of the market's own).

Result: {{alpha_head}} {{alpha_detail}} The [memo](recommendation_memo.md) has the table for every sector.

## 10. Interest rates and the rupee

For each full calendar month ({{macro_months}} of them), the sector's return above cash is regressed on the rest of the market's return above cash, the change in the policy rate in percentage points, and the change in rupees per dollar in percent (positive: a weaker rupee). The coefficients are in percent of monthly return, for one point more on the policy rate and for a rupee that is 1% weaker. The standard errors allow for {{hac_monthly}} months of dependence. Two p-values are shown for each effect: on its own, and corrected for testing {{n_sectors_ranked}} sectors (the false discovery rate). The monthly exchange rate is Yahoo's `PKR=X`, the same source as the dollar returns; the policy rate is the typed-in table. The rate changed in {{macro_changes}} of the {{macro_months}} months. {{macro_verdict}}

These are estimates from {{macro_months}} months, so they are imprecise, and a result that is significant one at a time can easily disappear after the correction.

## 11. How the sectors group

- **Principal components** of the correlation matrix of the sectors' daily returns above cash show how many independent bets there are. The first component carries {{pc1:.0f}}% of the variation. The effective number of bets, (the sum of the eigenvalues)² ÷ the sum of their squares, is {{effective_bets:.1f}}.
- **Groups.** Almost everything the sectors share is the market, so clustering their raw correlations only separates a few odd sectors from the rest. Instead, each sector's daily return above cash is regressed on the rest of the market's return today and yesterday, and the leftovers are clustered. The distance between two sectors is √((1 − correlation) ÷ 2), the clusters are joined by average linkage, and the tree is cut into {{n_groups}} groups. The number of groups is a choice made for readability, not estimated. With the market taken out, the average correlation between two sectors is {{corr_resid:.2f}} (it was {{corr_raw:.2f}} before) and the leftovers behave like {{resid_bets:.1f}} independent bets.

## 12. Could the ranking have been used? The walk-forward test

- **The rule.** On the last market day of each month a rule sees only the previous {{wf_lookback}} months of daily returns and sets weights for the next month. The portfolio is put back to those weights on the first day of the month and then left to drift. The first month with a full look-back is {{wf_first}}, and {{wf_months}} months are tested.
- **The rules.** *Best sectors of the past year*: equal weight in the {{wf_top}} sectors with the best Sharpe ratio over the look-back. *Worst sectors of the past year*: the {{wf_top}} with the worst, as a control (if the past meant nothing, it would do as well as the best). *Minimum variance*: the weights that make the portfolio's variance as small as possible, not negative and adding to one, from a covariance matrix pulled towards a plain target (shrinkage, in the style of Ledoit and Wolf; solved by projected gradient). *Inverse volatility*: weights in proportion to one over each sector's volatility. *Equal weight* in all {{n_sectors_ranked}} sectors is the reference, and the whole market is shown as well.
- **The comparison.** Each rule's Sharpe ratio is compared with equal weight's by resampling the days (block bootstrap, {{draws}} draws), which gives a 95% range and a p-value for the difference. Five comparisons are made, so the corrected p-value multiplies by five (Bonferroni: the simplest and most cautious correction).
- **The information coefficient.** Each month, the rank correlation between the sectors' Sharpe ratios over the look-back and their returns in the month that followed. Its average, with a t-statistic that allows for related months, says whether the past ranking pointed the right way.
- **Other choices.** The look-back is also set to 6 and 24 months and the number of sectors to 5, to show how much the answer depends on them. The main settings ({{wf_lookback}} months, {{wf_top}} sectors) were set as conventional defaults and not tuned to the results.
- **Turnover.** The average share of the portfolio bought and sold each month to get back to the target weights. Trading costs are not deducted.
- **The builder.** The dashboard's portfolio builder runs the same monthly rebalancing over the whole five years from the daily returns in the page. Its presets are chosen with hindsight from those years, so it shows what diversification does and is not a test.
- **What it cannot do.** The test looks forward in time only. It does not fix survivorship (today's companies), it cannot show what another five years would do, and five comparisons on one history are still one history.

Result: {{oos_head}} {{ic_verdict}}

## 13. Judgement calls and known limits

- **Survivorship.** Only companies listed today are included. A company that was delisted, merged or collapsed during the window is missing, and its returns, probably poor, are missing with it. The bias is probably smaller than for the KSE-100, whose members are chosen for their size and so favour companies that have grown, but it is not zero.
- **Yahoo Finance.** It is a convenient source, not an official one. Dividends it does not record are missing from total returns. {{fix_n}} price corrections were needed in {{fix_companies}} qualifying companies (section 3); a correction missed or mishandled would distort the sector it is in, which is why "Without companies with price corrections" is one of the other choices tested. The computed total returns agree with those implied by Yahoo's adjusted close to within half a point of daily return on {{cc_days:.2f}}% of stock-days ({{cc_companies}} companies compared, {{div_events}} dividend events); over five years the median company differs by {{cc_median:.2f}} points and {{cc_over5}} by more than 5, mostly companies that paid very large dividends (largest: {{cc_max_company}}, {{cc_max:.0f}} points). {{moved_div}} dividends are dated on days that are not market days and are credited to the next market day.
- **Rupee returns.** All returns are in rupees. For a foreign investor the picture differs: {{usd_note}}. The dollar figure is the rupee return deflated by the change in the exchange rate (Yahoo Finance, `PKR=X`) between the first and last day of the window, and is in the results table as `usd_cagr`.
- **Taxes, costs and liquidity** are ignored. Some sectors are far easier to trade than others.
- **What was fixed in advance and what was not.** The sample rules ({{min_history:.0f}}% history, {{min_traded:.0f}}% trading, {{min_sector}} companies per sector) and the safe rate were chosen before returns were examined. The price-cleaning thresholds were set later, after inspecting the largest one-day moves in the data (not sector results), and monthly rebalancing replaced daily rebalancing after it became clear that daily rebalancing flatters thinly traded shares; the daily version is in the robustness table. Many choices were tested, so that table is the honest guide to how much any single result depends on them. The second layer's settings (a {{wf_lookback}}-month look-back, {{wf_top}} sectors, {{hac_weekly}} weekly and {{hac_monthly}} monthly lags, blocks of {{block_weeks}} weeks, {{n_groups}} groups) were set as conventional defaults and not tuned to the results; alternatives for the first two are in the memo.
- **Many tests on one history.** The second layer estimates many things from the same five years ({{weeks}} weeks, {{macro_months}} months, {{wf_months}} months out of sample). The corrections limit false findings from looking at many sectors and rules; they cannot make the history longer.
- **Description, not prediction.** Nothing here says what returns will be.

## 14. Reproducibility

Everything is deterministic given the downloaded prices: the bootstrap uses seed {{seed}}. The raw prices are not stored in the repository (see [data sources](data_sources.md)), so a fresh download will differ a little from the one used for the committed results: Yahoo revises dividends and splits, and companies may be delisted. Tests recompute every headline measure from the committed daily sector returns, so the results can be audited without the raw prices.
