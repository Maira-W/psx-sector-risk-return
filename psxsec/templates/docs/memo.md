# Which PSX sectors paid best for the risk?

*A memo for anyone deciding which parts of the Pakistan Stock Exchange to study first. Five years, {{base_date}} to {{end_date}}. This is analysis of the past and is not investment advice.*

## Bottom line

- **By return per unit of risk, the leaders were {{top3_list}}** (Sharpe ratio; the whole market scored {{mkt_sharpe:.2f}}). {{top1}} returned {{top1_cagr:.1f}}% a year with a worst fall of {{top1_mdd:.0f}}%.
- **{{certainty}}** Its Sharpe ratio of {{top1_sharpe:.2f}} has a 95% range of {{top1_lo:.2f}} to {{top1_hi:.2f}}, and {{top5_overlap}}
- **The whole market returned {{mkt_cagr:.1f}}% a year against {{safe_cagr:.1f}}% for cash** at the State Bank's policy rate, with a worst fall of {{mkt_mdd:.0f}}%. {{n_above}} of {{n_sectors_ranked}} sectors were very likely better than the market per unit of risk and {{n_below}} very likely worse; the other {{n_unclear}} cannot be told apart from it.
- **{{rob_verdict}}** The top sector stays in the top three in {{rob_top3}} of the {{rob_tested}} alternative ways of doing the analysis in which it is included.

## What was measured

Each sector is an equal-weighted portfolio (equal amounts of each company at the start of every month, dividends included) of its companies that trade regularly: {{n_qualify}} companies in {{n_sectors}} ranked sectors, out of {{n_all_share}} in the KSE All Share Index. Companies that rarely trade, or that Yahoo Finance has no prices for, are left out, which is why {{n_qualify}} of {{n_operating}} operating companies remain; the largest groups left out are listed in the [data sources](data_sources.md). Return is the compound annual growth rate; risk is volatility and the worst fall from a peak; return per unit of risk is the Sharpe ratio, taking cash at the policy rate (which ranged from {{policy_start}}% to {{policy_peak}}% and ended at {{policy_end}}%) as the safe alternative. The [methodology](methodology.md) gives the details and the judgement calls.

## The results

{{table_market}}

The eight sectors with the best Sharpe ratio:

{{table_top}}

The four with the weakest:

{{table_bottom}}

"Chance of top 3" is the share of 2,000 resampled histories in which the sector finished in the top three by Sharpe ratio. All ranked sectors are in [`data/processed/sector_summary.csv`](../data/processed/sector_summary.csv) and on the [dashboard](https://maira-w.github.io/psx-sector-risk-return/).

![Risk and return by sector](figures/01_risk_vs_return.png)

![Sharpe ratio by sector with 95% ranges](figures/02_sharpe_ranking.png)

## What is solid and what is not

**{{return_heading}}** {{best_cagr_sector}} had the highest return ({{best_cagr:.1f}}% a year); it ranks {{best_cagr_rank}} of {{n_sectors_ranked}} by Sharpe ratio (1 is best), with volatility of {{best_cagr_vol:.0f}}% and a worst fall of {{best_cagr_fall:.0f}}%.

**{{falls_heading}}** {{n_deeper_than_20}} of {{n_sectors_ranked}} sectors fell more than 20% from a peak at some point. The deepest fall was {{deepest:.0f}}% in {{deepest_sector}}; the shallowest was {{shallow:.0f}}% in {{shallow_sector}}, against {{mkt_mdd:.0f}}% for the whole market. {{n_still_down}} sectors were still below their old peak at the end of the window.

![Worst fall from a peak, by sector](figures/04_worst_falls.png)

**Where the ranking is uncertain.** {{certainty}} Resampling the days says how much of the ranking could be luck within this one history; it cannot say what a different five years would do.

![Where each sector is likely to finish](figures/06_rank_range.png)

**It depends on the period.** {{n_leaders}} different sectors led the five twelve-month periods. {{rotation_verdict}} The rank correlation between the first-half and second-half orderings is {{half_corr:.2f}}; {{first_half_top}} had the best Sharpe ratio in the first half and {{second_half_top}} in the second. {{period_verdict}} Across the {{per_n}} choices that change the dates (each half, starting three months later, ending three months earlier), the rank correlation with the main result has a median of {{per_median:.2f}} and a minimum of {{per_min:.2f}}.

{{table_years}}

![Year-by-year returns](figures/05_year_by_year.png)

**How much it depends on method.** {{rob_verdict}} Across {{rob_n}} alternative ways of doing the analysis (who is included, how the index is built, how returns are measured), the rank correlation with the main result has a median of {{rob_median:.2f}} and a minimum of {{rob_min:.2f}}.

{{table_robust}}

![How the ranking moves under other choices](figures/07_robustness.png)

**{{div_heading}}** In the typical sector dividends supplied about {{div_typical_share:.0f}}% of the annual return ({{div_median:.1f}} percentage points), and {{div_max:.1f}} points in {{div_max_sector}}. For the whole market that is {{div_market_share:.0f}}% of its return.

## What this suggests

These are ways to use the numbers, not recommendations to buy or sell anything.

1. **Use the ranking to choose where to look first.** {{top5_names}} are the five best by Sharpe ratio and a reasonable shortlist for closer study (company accounts, valuations and what drove each sector's run). {{use_it}}
2. **Weigh the worst fall as well as the return.** Anyone holding a sector would have lived through the fall in the table above, and {{n_still_down}} sectors had not regained their old peak by the end of the window.
3. **Look at how much sectors move together.** The average correlation between sector returns was {{corr_mean:.2f}}. The lowest was {{corr_low:.2f}}, between {{corr_low_a}} and {{corr_low_b}}. {{corr_to_market_low_sector}} moved least with the market ({{corr_to_market_low:.2f}}).
4. **Do not lean on last period's leader.** Between the first and second half the rank correlation was {{half_corr:.2f}}, so a sector's record over one stretch has been {{persistence}} to the next.

## What would change the answer

- **A different window.** The window spans the policy rate rising from {{policy_start}}% to {{policy_peak}}% and later coming down to {{policy_end}}%; another five years would rank the sectors differently.
- **Delisted companies.** Including companies that left the exchange would probably lower returns.
- **Value weights.** An index weighted by company size would be driven by the largest companies in each sector.
- **Better data.** The exchange's own prices, with complete dividend records, would replace Yahoo Finance.
- **Dollar returns.** All returns here are in rupees. For a foreign investor the picture differs: {{usd_note}}.

## Not investment advice

This memo describes what happened. Past performance does not predict future returns, and nothing here is a recommendation to buy or sell any security.
