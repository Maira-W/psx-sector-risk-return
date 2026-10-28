# Methodology

This page explains every step from the raw data to the numbers in the dashboard, and the judgement calls made along the way. It describes analysis of the past and is not investment advice.

## 1. The question

Over the 5 years from 27 October 2021 to 27 October 2026, which sectors of the Pakistan Stock Exchange gave the best return for the risk? "Best for the risk" is measured by the **Sharpe ratio**: the average return above what cash would have earned, divided by how much that return bounced around, scaled to a year. Volatility and the worst fall from a peak are shown alongside, because one number never tells the whole story.

## 2. Who is in the analysis

The universe is every company in the **KSE All Share Index** on 2026-10-28, as listed on the Pakistan Stock Exchange data portal, with the sector the exchange gives it. The portal lists 752 instruments (shares, rights issues, bonds and others); 549 are in the All Share Index, of which 100 are also in the KSE-100.

| Step | Companies |
| --- | ---: |
| Listings on the PSX data portal (shares, rights, bonds and others) | 752 |
| In the KSE All Share Index | 549 |
| Operating companies (funds, ETFs and REITs removed) | 538 |
| Prices found on Yahoo Finance | 435 |
| A price on nearly every market day of the five years | 422 |
| Traded on at least 90% of market days (qualify) | 209 |

The rules, in order:

1. **Operating companies only.** Close-end mutual funds, exchange traded funds and real estate investment trusts are investment vehicles, not businesses in a sector, and are removed.
2. **A price on nearly every market day.** A company must have a price on at least 98% of the market days in the window, including the first, and one in the last five days. This removes companies listed during the window and those with long gaps.
3. **Traded on at least 90% of market days.** Where a share does not trade, Yahoo carries the last price forward. A share that rarely trades therefore shows a flat price, which can make it look less volatile (and so better per unit of risk) than it is. The 90% rule removes 213 companies on this ground. The threshold was fixed before returns were looked at, and the results are repeated at 80% and 95% (section 8).
4. **Sectors need 4 qualifying companies to be ranked.** Smaller ones are listed but not ranked: Leather and tanneries, Modarabas, Apparel, Textile weaving, Tobacco and Cable and electrical goods. "Miscellaneous" is a catch-all of unrelated companies, not a sector, so it is not ranked; its companies do count in the whole-market line.

| Status | Companies |
| --- | ---: |
| traded on too few days | 213 |
| qualifies | 209 |
| no prices on Yahoo Finance | 103 |
| listed after the start of the window | 12 |
| prices missing on too many days | 1 |

The list is a **snapshot of today's membership**, not of the index five years ago. See the limits in section 9.

## 3. Prices and returns

Daily prices, volume and dividends come from Yahoo Finance (`yfinance` 1.7.0, retrieved 2026-10-28) for 538 companies; Yahoo had data for 435 of them.

- **Total return.** The daily return is (close + dividend paid that day) ÷ previous close − 1, the standard holding-period return, from Yahoo's split-adjusted *close* (Yahoo appears to record PSX bonus issues as splits: ratios such as 1.10 and 1.25 appear in its data) and its dividend column. The price return is the change in the close alone; the difference between the two is the dividend contribution. Yahoo's own dividend-adjusted close is *not* used: it is invalid for PHDL (it goes negative) and treats very large dividends differently. It serves as a cross-check instead (section 9).
- **Market days.** Yahoo lists PSX holidays as rows with no volume and the previous price carried forward. A date counts as a market day only if at least 50 companies traded on it. That leaves 1,227 market days over 5.00 years, about 245 a year.
- **The window.** The base date is 27 October 2021, the last market day on or before five years before the end date. The first return is the day after it and the last is on 27 October 2026.
- **Gaps.** A missing price is filled with the previous one (a zero return) after the company has passed the history rule above.
- **Cleaning.** Yahoo's prices contain errors, and corporate actions that it has not adjusted for. The exchange limits a share's move in one day to a percentage of the previous close (7.5% from 2020, with later reports of 10%) or Re 1, whichever is larger, so two kinds of move cannot be real. Both are corrected by fixed rules, and every correction is listed in [`data/processed/price_corrections.csv`](../data/processed/price_corrections.csv).
  1. *A bad price.* A price that is at least 1.5 times (or at most 1/1.5 of) the day before on every day of a run of up to 3 days, and then comes back to within 15% of where it was, is replaced by the price before the run (11 cases; for example Lucky Cement's price shows a fifth of its value for three days in February 2025).
  2. *A move beyond the daily limit.* A one-day change of at least 15% up (or the same move down, 13%) that is also larger than Rs 1.05 (Re 1, the exchange's floor for the limit, plus a little for rounding) is outside the limit, so it is an unadjusted bonus issue or share split, or a data error. The day's price return is set to zero and only a dividend, if any, counts (99 cases). The rupee condition keeps genuine moves in cheap shares, where Re 1 can be a large percentage. Because the same move up and down is caught, a wrong price level that starts and ends inside the data is corrected at both ends.

  In all, 110 corrections were made in 70 of the 209 qualifying companies (33%). Unadjusted corporate actions smaller than the thresholds (a 10% bonus issue, say) cannot be told from ordinary moves and remain in the data.

## 4. Sector indexes

A sector index holds **equal amounts of each qualifying company at the start of every month** and lets the holdings drift with prices until the next month (monthly rebalancing). Its daily return is the change in the value of that portfolio. The **whole market** line is the same portfolio over all 209 qualifying companies, including those in small sectors and "Miscellaneous".

Equal weights were chosen because the question is about the sector, not about its biggest company: a value-weighted index of the banking sector is mostly a handful of banks. The cost is that a small, hardly traded company counts as much as a large one; the trading rule limits this.

Monthly rather than daily rebalancing is deliberate. Putting the weights back to equal every day flatters shares that trade rarely, because a price that bounces between the bid and the ask looks like a return when it is averaged every day, and nobody rebalances daily. The effect is largest for Insurance: 34% a year with daily rebalancing, 28% with monthly rebalancing (used here) and 21% never rebalanced. The results table carries the daily and never-rebalanced returns (`cagr_daily_rebalanced`, `cagr_buy_and_hold`) so the effect can be seen, and "Rebalanced every day" is one of the other choices tested in section 8.

## 5. The measures

| Measure | Definition |
|---|---|
| Return a year | Compound annual growth rate: (1 + total return)^(1 / years) − 1 |
| Volatility | Standard deviation of daily returns × √(market days per year) |
| Worst fall | The largest drop from a peak of the growth-of-100 series to a later low, with its dates; "recovered" if the old peak was regained |
| Sharpe ratio | (average daily return − average daily safe return) ÷ standard deviation of that difference × √(market days per year) |
| Return by year | Compound return in each of five consecutive twelve-month periods from the base date |
| Beta, correlation | Of the sector's excess return on the market's, and of daily returns |

**The safe return** is what cash would have earned at the State Bank's policy rate. Each return period (a day, or a weekend and a day) accrues the rate in force on the previous market day, simply: rate × calendar days ÷ 365. The policy rate went from 7.25% to a peak of 22.0% and ended at 12.0%; cash returned 16.3% a year. The table of changes, with a source for every row, is in [data sources](data_sources.md). The policy rate stands in for a risk-free rate; Treasury bill yields were close to it but are not freely available in a form that can be downloaded.

## 6. How sure can we be?

A ranking from one five-year history may owe a lot to the order in which things happened. To see how much:

- The days are **resampled** 2000 times with a *stationary block bootstrap*: the resampled history is built from runs of consecutive days whose lengths vary randomly with an average of 10, so that short streaks of ups and downs stay together. The same resampled days are used for every sector, which keeps their relationships.
- In each resampled history every sector's Sharpe ratio is computed and the sectors are ranked. This gives each sector a **95% range for its Sharpe ratio** (the 2.5th to 97.5th percentile), a **95% range for its position** in the ranking, the **chance it finishes first** and **in the top three**, and the **chance it beats the whole market**. "Very likely better" means at least 95% of resampled histories.

The top of the ranking is not secure. Fertilizer finishes first in only 54% of the resampled histories, and 3 sectors have at least a 10% chance of finishing first. Read the top group as a shortlist, not a winner.

## 7. What the bootstrap cannot do

It resamples the days of one history, so it cannot show what a different economic regime would have done, and it treats the choice of window as given. It is a measure of luck within this history, not a forecast.

## 8. Other choices

The whole analysis was repeated with one choice changed at a time. The rank correlation compares each ranking with the main one (1 is the same order).

| Choice | Kind | Sectors compared | Rank correlation | Top-3 in common | Main top sector |
| --- | --- | ---: | ---: | ---: | --- |
| KSE-100 companies only | method | 11 | 0.98 | 3 of 3 | still first |
| Must trade on 80% of days | method | 22 | 0.88 | 3 of 3 | still first |
| Must trade on 95% of days | method | 21 | 1.00 | 3 of 3 | still first |
| Without companies with price corrections | method | 17 | 0.97 | 3 of 3 | not in this analysis |
| Rebalanced every day | method | 22 | 0.97 | 3 of 3 | still first |
| Weekly returns | method | 22 | 0.99 | 3 of 3 | still first |
| Without each sector's best company | method | 22 | 0.96 | 3 of 3 | still first |
| Typical company (median) | method | 22 | 0.93 | 2 of 3 | still first |
| First half of the window | period | 22 | 0.83 | 2 of 3 | still first |
| Second half of the window | period | 22 | 0.60 | 1 of 3 | falls out of the top 3 |
| Start 3 months later | period | 22 | 0.98 | 3 of 3 | still first |
| End 3 months earlier | period | 22 | 0.97 | 3 of 3 | still first |

For the 8 choices about *method*, the rank correlation with the main result has a median of 0.97 and a minimum of 0.88, and the main top sector stays in the top three in 7 of the 7 in which it is included (a choice can remove it: a sector needs 4 qualifying companies to be ranked). For the 4 choices about *dates*, the median is 0.90 and the minimum 0.60. The ranking moves a fair amount with the dates used.

- **KSE-100 companies only** uses the 80 KSE-100 companies that qualify, and sectors with at least 3 of them (11 sectors). The top sector is the same as in the main result.
- **Must trade on 80% or 95% of days** moves the trading rule either way.
- **Rebalanced every day** puts the weights back to equal every day instead of every month.
- **Weekly returns** compound each company's daily returns into Friday-to-Friday weeks before averaging, which reduces the effect of stale prices.
- **Without each sector's best company** drops the single best performer in every sector, to test whether one stock carries the result.
- **Typical company (median)** replaces the sector index with the median Sharpe ratio of its companies.
- **First and second half, start 3 months later, end 3 months earlier** test sensitivity to the dates. The rank correlation between the first-half and second-half orderings is 0.16.
- **Without companies with price corrections** drops the 70 qualifying companies that have at least one correction (`data/processed/price_corrections.csv`), in case a correction missed or mishandled an event.

## 9. Judgement calls and known limits

- **Survivorship.** Only companies listed today are included. A company that was delisted, merged or collapsed during the window is missing, and its returns, probably poor, are missing with it. The bias is probably smaller than for the KSE-100, whose members are chosen for their size and so favour companies that have grown, but it is not zero.
- **Yahoo Finance.** It is a convenient source, not an official one. Dividends it does not record are missing from total returns. 110 price corrections were needed in 70 qualifying companies (section 3); a correction missed or mishandled would distort the sector it is in, which is why "Without companies with price corrections" is one of the other choices tested. The computed total returns agree with those implied by Yahoo's adjusted close to within half a point of daily return on 99.98% of stock-days (209 companies compared, 990 dividend events); over five years the median company differs by 0.11 points and 14 by more than 5, mostly companies that paid very large dividends (largest: FHAM, 54 points). 10 dividends are dated on days that are not market days and are credited to the next market day.
- **Rupee returns.** All returns are in rupees. For a foreign investor the picture differs: rupees per dollar went from 174 to 277, so in dollars the whole market returned 13.0% a year against 23.9% in rupees. The dollar figure is the rupee return deflated by the change in the exchange rate (Yahoo Finance, `PKR=X`) between the first and last day of the window, and is in the results table as `usd_cagr`.
- **Taxes, costs and liquidity** are ignored. Some sectors are far easier to trade than others.
- **What was fixed in advance and what was not.** The sample rules (98% history, 90% trading, 4 companies per sector) and the safe rate were chosen before returns were examined. The price-cleaning thresholds were set later, after inspecting the largest one-day moves in the data (not sector results), and monthly rebalancing replaced daily rebalancing after it became clear that daily rebalancing flatters thinly traded shares; the daily version is in the robustness table. Many choices were tested, so that table is the honest guide to how much any single result depends on them.
- **Description, not prediction.** Nothing here says what returns will be.

## 10. Reproducibility

Everything is deterministic given the downloaded prices: the bootstrap uses seed 42. The raw prices are not stored in the repository (see [data sources](data_sources.md)), so a fresh download will differ a little from the one used for the committed results: Yahoo revises dividends and splits, and companies may be delisted. Tests recompute every headline measure from the committed daily sector returns, so the results can be audited without the raw prices.
