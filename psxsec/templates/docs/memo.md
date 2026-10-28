# Which PSX sectors paid best for the risk?

*A memo for anyone deciding which parts of the Pakistan Stock Exchange to study first. Five years, {{base_date}} to {{end_date}}. This is analysis of the past and is not investment advice.*

## Bottom line

- **By return per unit of risk, the leaders were {{top3_list}}** (Sharpe ratio; the whole market scored {{mkt_sharpe:.2f}}). {{top1}} returned {{top1_cagr:.1f}}% a year with a worst fall of {{top1_mdd:.0f}}%.
- **{{certainty}}** Its Sharpe ratio of {{top1_sharpe:.2f}} has a 95% range of {{top1_lo:.2f}} to {{top1_hi:.2f}}, and {{top5_overlap}}
- **The whole market returned {{mkt_cagr:.1f}}% a year against {{safe_cagr:.1f}}% for cash** at the State Bank's policy rate, with a worst fall of {{mkt_mdd:.0f}}%. {{n_above}} of {{n_sectors_ranked}} sectors were very likely better than the market per unit of risk and {{n_below}} very likely worse; the other {{n_unclear}} cannot be told apart from it.
- **{{rob_verdict}}** The top sector stays in the top three in {{rob_top3}} of the {{rob_tested}} alternative ways of doing the analysis in which it is included.
- **{{alpha_head}}** {{alpha_detail}} {{alpha_best_sector}} has the largest alpha, {{alpha_best:+.0f}}% a year, with a p-value of {{alpha_best_padj:.3f}} once all {{n_sectors_ranked}} sectors are allowed for.
- **{{oos_head}}** Each month, holding the {{wf_top}} sectors with the best record over the previous {{wf_lookback}} months gave a Sharpe ratio of {{win_sharpe:.2f}} against {{eq_sharpe:.2f}} for equal weights, over {{wf_months}} months and without looking ahead.
- **What moves the sectors.** {{structure_verdict}} {{macro_verdict}}

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

![Each sector's annual return split into price change and dividends](figures/08_dividends.png)

## Is it skill or luck?

A sector can rank high because it moves with a rising market, or because it carries little of the market's risk, without having done anything special. To separate these, each sector's weekly return above cash is set against the weekly return of the rest of the market (every company outside that sector, equal-weighted). **Beta** is how strongly the sector follows the rest of the market; **alpha** is the return a year that is left over. The median beta was {{beta_median:.2f}}, from {{beta_low:.2f}} for {{beta_low_sector}} to {{beta_high:.2f}} for {{beta_high_sector}}, and the rest of the market explains a median {{r2_median:.0f}}% of a sector's weekly ups and downs. {{beta_verdict}}

**{{alpha_head}}** {{alpha_detail}} The correction matters because the best of {{n_sectors_ranked}} sectors looks good by chance: even if none had any alpha, the largest t-statistic among {{n_sectors_ranked}} would exceed {{null_t:.2f}} one time in twenty, so a sector has to beat that bar, not the usual 1.96. {{alpha_best_sector}} has the largest alpha, {{alpha_best:+.0f}}% a year (t = {{alpha_best_t:.1f}}; p = {{alpha_best_p:.3f}} on its own, {{alpha_best_padj:.3f}} after the correction). {{alpha_worst_sector}} has the lowest, {{alpha_worst:+.0f}}% a year (p = {{alpha_worst_p:.4f}} on its own, {{alpha_worst_padj:.3f}} after the correction). {{fdr_note}}

{{table_alpha}}

The Sharpe ratio gets the same treatment. With no skill at all, the best Sharpe ratio among {{n_sectors_ranked}} sectors would be expected to reach about {{expected_best_sharpe:.2f}}, given how widely their Sharpe ratios are spread; the best actual one is {{top1_sharpe:.2f}}. The *deflated Sharpe ratio* turns that into a probability that the true Sharpe ratio is above the luck bar: {{dsr_best:.2f}} for {{dsr_best_sector}}, where 0.95 would be convincing, and {{dsr_reach}}.

![Alpha and beta by sector](figures/10_alpha_and_beta.png)

## What moves the sectors?

**One market, and a few small groups.** {{structure_verdict}} The first principal component carries {{pc1:.0f}}% of the variation in sector returns, the second {{pc2:.0f}}% and the third {{pc3:.0f}}%. After the market is taken out, the sectors that still move together fall into {{n_groups}} groups (found by clustering; they describe these five years and are not a classification):

{{table_groups}}

The five strongest links beyond the market:

{{table_pairs}}

![One market, and the groups that remain](figures/13_sector_structure.png)

**Interest rates and the rupee.** For each of the {{macro_months}} full months, a sector's return above cash is explained by the rest of the market's return, the change in the State Bank's policy rate (it changed in {{macro_changes}} of those months) and the change in rupees per dollar. {{macro_verdict}} {{rate_detail}} {{fx_detail}}

{{table_macro}}

Effects are in percent of return in a month, for one percentage point more on the policy rate and for a rupee that is 1% weaker. They are estimated from {{macro_months}} months, so the ranges are wide (see the figure), and the market, rates and the rupee together explain a median {{macro_r2:.0f}}% of a sector's monthly return above cash.

![Interest rates and the rupee](figures/12_rates_and_rupee.png)

## Could you have used the ranking?

The ranking looks back over five years. To see whether it could have been used, a rule is run month by month: on the last day of each month it chooses weights using only the previous {{wf_lookback}} months, and the portfolio is held through the next month. That gives {{wf_months}} months of results, from {{wf_first}}, that the rule could not have known in advance. Five rules are compared with the whole market and with holding all {{n_sectors_ranked}} sectors equally: the {{wf_top}} sectors with the best past Sharpe ratio, the {{wf_top}} with the worst (a control), minimum variance, and inverse volatility.

{{table_walk_forward}}

The range and the p-value come from resampling the days {{draws}} times; "p corrected" multiplies by the five comparisons made.

**{{oos_head}}** Holding the {{wf_top}} sectors with the best past Sharpe ratio returned {{win_cagr:.0f}}% a year with a Sharpe ratio of {{win_sharpe:.2f}}, against {{eq_cagr:.0f}}% and {{eq_sharpe:.2f}} for equal weights: a difference of {{win_diff:+.2f}} in the Sharpe ratio (p = {{win_p:.3f}}; {{win_padj:.3f}} after allowing for five comparisons). The worst {{wf_top}} returned a Sharpe ratio of {{lose_sharpe:.2f}}. The rank correlation between the past Sharpe ratios and the next month's returns averaged {{ic_mean:+.2f}} (t = {{ic_t:.1f}}) and was positive in {{ic_pos:.0f}}% of months. {{ic_verdict}}

The same rule with other look-backs and numbers of sectors was ahead of equal weights in {{sens_ahead}} of {{sens_n}} choices and clearly ahead (p below 0.05) in {{sens_clear}}:

{{table_sensitivity}}

{{mv_verdict}} A rule that favours low-risk sectors does best in a window in which low-risk sectors did well. {{low_beta_link}}

![Out-of-sample growth of 100 for each rule](figures/11_out_of_sample.png)

The comparisons between rules are fairer than their levels: every rule uses today's surviving companies, which lifts all of them alike, and five years is one history. The dashboard has a portfolio builder (monthly rebalanced; its presets are worked out in hindsight from the whole five years) to see what diversification does. It is a way to explore, not a test.

## What this suggests

These are ways to use the numbers, not recommendations to buy or sell anything.

1. **Use the ranking to choose where to look first.** {{top5_names}} are the five best by Sharpe ratio and a reasonable shortlist for closer study (company accounts, valuations and what drove each sector's run). {{use_it}}
2. **Weigh the worst fall as well as the return.** Anyone holding a sector would have lived through the fall in the table above, and {{n_still_down}} sectors had not regained their old peak by the end of the window.
3. **Look at how much sectors move together.** The average correlation between sector returns was {{corr_mean:.2f}}. The lowest was {{corr_low:.2f}}, between {{corr_low_a}} and {{corr_low_b}}. {{corr_to_market_low_sector}} moved least with the market ({{corr_to_market_low:.2f}}).
4. **Do not lean on last period's leader.** Between the first and second half the rank correlation was {{half_corr:.2f}}, so a sector's record over one stretch has been {{persistence}} to the next.
5. **Think in bets, not sector names.** The {{n_sectors_ranked}} sectors behave like {{effective_bets:.1f}} independent bets, so two sectors in the same group diversify each other less than their names suggest.
6. **Do not read a good record as skill, and be careful with a rule built on last year's winners.** {{alpha_head}} {{oos_head}}

## What would change the answer

- **A different window.** The window spans the policy rate rising from {{policy_start}}% to {{policy_peak}}% and later coming down to {{policy_end}}%; another five years would rank the sectors differently.
- **More history.** The alpha tests rest on {{weeks}} weeks and the out-of-sample test on {{wf_months}} months. A longer record, or other markets, is what would separate skill from luck.
- **Delisted companies.** Including companies that left the exchange would probably lower returns.
- **Value weights.** An index weighted by company size would be driven by the largest companies in each sector.
- **Better data.** The exchange's own prices, with complete dividend records, would replace Yahoo Finance.
- **Dollar returns.** All returns here are in rupees. For a foreign investor the picture differs: {{usd_note}}.

## Not investment advice

This memo describes what happened. Past performance does not predict future returns, and nothing here is a recommendation to buy or sell any security.
