# PSX sector risk and return: which sectors paid best for the risk

[![tests](https://github.com/Maira-W/psx-sector-risk-return/actions/workflows/ci.yml/badge.svg)](https://github.com/Maira-W/psx-sector-risk-return/actions/workflows/ci.yml)
![python 3.11](https://img.shields.io/badge/python-3.11-blue)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-green)](LICENSE)

Over the five years from {{base_date}} to {{end_date}}, **which sectors of the Pakistan Stock Exchange gave investors the best return for the risk they carried?** This project builds an index for each sector from the {{n_qualify}} companies that trade regularly, measures return, volatility, the worst fall and the Sharpe ratio (return above cash per unit of risk), and says how sure the ranking is. It is analysis of the past, not investment advice.

| | |
|---|---|
| **Interactive dashboard** | [maira-w.github.io/psx-sector-risk-return](https://maira-w.github.io/psx-sector-risk-return/) (five tabs: the answer, sector scorecard, ups and downs, how sure are we, method) |
| **Notebook** | [`notebooks/sector_risk_return.ipynb`](notebooks/sector_risk_return.ipynb), a step-by-step walk-through with its outputs |
| **Memo** | [`docs/recommendation_memo.md`](docs/recommendation_memo.md) |
| **Method and data** | [methodology](docs/methodology.md) · [data sources](docs/data_sources.md) |
| **Results as CSV** | [`data/processed`](data/processed) (plain files for Excel or Power BI) |

## What the data show

1. **The whole market returned {{mkt_cagr:.1f}}% a year,** with volatility of {{mkt_vol:.0f}}% and a worst fall of {{mkt_mdd:.0f}}% (from {{mkt_peak}} to {{mkt_trough}}). Cash earning the State Bank's policy rate returned {{safe_cagr:.1f}}% a year over the same years (the policy rate began at {{policy_start}}%, peaked at {{policy_peak}}% and ended at {{policy_end}}%). The market's Sharpe ratio was {{mkt_sharpe:.2f}}.
2. **By return per unit of risk the leaders were {{top3_list}}.** {{top1}} returned {{top1_cagr:.1f}}% a year with volatility of {{top1_vol:.0f}}% and a worst fall of {{top1_mdd:.0f}}%. The weakest were {{bottom_list}}.
3. **{{certainty}}** {{n_above}} of the {{n_sectors_ranked}} ranked sectors are very likely better than the whole market ({{above}}) and {{n_below}} very likely worse.
4. **{{return_heading}}** {{best_cagr_sector}} had the highest return ({{best_cagr:.1f}}% a year) with volatility of {{best_cagr_vol:.0f}}% and a worst fall of {{best_cagr_fall:.0f}}%; it ranks {{best_cagr_rank}} of {{n_sectors_ranked}} by Sharpe ratio (1 is best).
5. **{{falls_heading}}** {{n_deeper_than_20}} of {{n_sectors_ranked}} sectors fell more than 20% from a peak at some point. The deepest was {{deepest_sector}} ({{deepest:.0f}}%), the shallowest {{shallow_sector}} ({{shallow:.0f}}%). {{n_still_down}} sectors were still below their old peak at the end of the window.
6. **{{div_heading}}** In the typical sector dividends supplied about {{div_typical_share:.0f}}% of the annual return ({{div_median:.1f}} percentage points); the most was {{div_max:.1f}} points in {{div_max_sector}}.
7. **{{rotation_verdict}}** {{n_leaders}} different sectors led the five twelve-month periods ({{leaders}}), and the rank correlation between the first and second half of the window is {{half_corr:.2f}} (1 would mean the same order). {{period_verdict}}
8. **{{rob_verdict}}** The ranking was repeated {{rob_n}} ways that change the method (KSE-100 companies only, looser and tighter trading rules, rebalancing every day, weekly returns, dropping each sector's best company, leaving out companies with price corrections, the typical company instead of the average). The rank correlation with the main result is {{rob_median:.2f}} at the median and {{rob_min:.2f}} at the lowest, and the top sector stays in the top three in {{rob_top3}} of the {{rob_tested}} in which it is included.

<table>
<tr>
<td width="50%"><a href="docs/figures/01_risk_vs_return.png"><img src="docs/figures/01_risk_vs_return.png" alt="Risk and return by sector"></a><br><sub>Risk and return by sector</sub></td>
<td width="50%"><a href="docs/figures/02_sharpe_ranking.png"><img src="docs/figures/02_sharpe_ranking.png" alt="Sharpe ratio by sector with 95% ranges"></a><br><sub>Return per unit of risk, with 95% ranges</sub></td>
</tr>
<tr>
<td><a href="docs/figures/03_growth_of_100.png"><img src="docs/figures/03_growth_of_100.png" alt="Growth of 100 rupees"></a><br><sub>Growth of 100 rupees: best and worst sectors, the market and cash</sub></td>
<td><a href="docs/figures/05_year_by_year.png"><img src="docs/figures/05_year_by_year.png" alt="Year-by-year returns"></a><br><sub>Year-by-year returns</sub></td>
</tr>
</table>

All nine figures are in [`docs/figures`](docs/figures).

## What to take from it

- **{{use_it}}** {{top5_names}} are the five best by Sharpe ratio. The leader's 95% range is {{top1_lo:.2f}} to {{top1_hi:.2f}}, and {{top5_overlap}}
- **Look at the worst fall as well as the return.** {{best_cagr_sector}} had the highest return and still fell {{best_cagr_fall:.0f}}% from a peak at one point.
- **Check what the return was made of.** Dividends supplied {{div_median:.1f}} points of the typical sector's annual return, and a sector index treats a small company like a large one.
- **Treat five years as one history.** The window spans the policy rate rising from {{policy_start}}% to {{policy_peak}}% and then coming down to {{policy_end}}%; a different five years would rank the sectors differently.

The [memo](docs/recommendation_memo.md) sets out the reasoning, what is solid, what is not, and what would change the answer.

## How it works

```
data/raw  ──build──▶  data/interim  ──analyze──▶  data/processed  ──report──▶  docs/figures · dashboard/ · docs/
 (downloaded;          (clean returns)             (results)                    (everything you open)
  fingerprinted)
```

| Stage | What it does |
|---|---|
| `ingest` | Downloads the PSX company and sector list and daily prices from Yahoo Finance for {{n_requested}} companies, and records a SHA-256 fingerprint, source and date for each file in [`data/raw/MANIFEST.json`](data/raw/MANIFEST.json). `verify` checks any raw file that is present. |
| `build` | Drops holidays, picks the five-year window, checks the prices (no duplicates, no zero prices), corrects wrong prices and unadjusted corporate actions by fixed rules (every correction is listed), and keeps the companies that trade regularly. |
| `analyze` | Builds the sector indexes, measures return and risk, resamples the days to say how sure the ranking is, and repeats everything under {{rob_n}} other choices. |
| `report` | Draws the figures, builds the dashboard and writes these documents. |
| `notebook` | Re-runs the notebook from the committed results (needs the extras in `requirements-notebook.txt`). |

The documents (including this file) are written from [`psxsec/templates`](psxsec/templates) and the results, so a number in the text cannot disagree with the data. Edit the template, not the output.

## Data

| Source | Used for | Retrieved |
|---|---|---|
| Pakistan Stock Exchange data portal (screener page) | Which companies are in the KSE All Share Index and the KSE-100, and each company's sector | {{screener_retrieved}} |
| Yahoo Finance, through `yfinance` {{yf_version}} | Daily prices, volume and dividends | {{retrieved}} |
| State Bank of Pakistan policy rate (typed in with a source for each change) | The safe rate in the Sharpe ratio | [`data/reference/policy_rate.csv`](data/reference/policy_rate.csv) |

The raw prices are **not stored in this repository**; they belong to their sources, and `python -m psxsec ingest` downloads them again. What is committed is the list of companies and sectors, the policy-rate table, and every result computed from the prices. Details and the data problems found are in [`docs/data_sources.md`](docs/data_sources.md).

## Quality checks

- **Prices are checked before use.** No duplicate rows, no price of zero or less, no negative volume; the window must end on a market day. Yahoo's prices also contain wrong prices (a share at a fifth of its level for a few days) and unadjusted bonus issues and splits; {{fix_n}} such events in {{fix_companies}} of the {{n_qualify}} qualifying companies are corrected by fixed rules and every one is listed in [`data/processed/price_corrections.csv`](data/processed/price_corrections.csv).
- **Total returns are computed from price and dividends, then cross-checked.** Each day's return is (price today + dividend paid today) ÷ price yesterday − 1. Against the returns implied by Yahoo's own dividend-adjusted prices they agree to within half a point on {{cc_days:.2f}}% of stock-days. Over five years the median company differs by {{cc_median:.2f}} points and {{cc_over5}} of {{cc_companies}} by more than 5; the two differ most for companies that paid very large dividends (the largest gap is {{cc_max_company}}, {{cc_max:.0f}} points). Yahoo's adjusted series is invalid for {{invalid_adj}} (it goes negative), which is why it is not used for returns.
- **Every headline measure can be recomputed** from the committed daily sector returns, and a test does that for every sector.
- **The sample rules were set before looking at returns** (the trading rule of {{min_traded:.0f}}% of days, the history rule, the minimum sector size), and the trading rule is also tested at 80% and 95%. The price-cleaning rules and the choice of monthly rebalancing were set afterwards, from inspecting the data (not from looking at which sector ranked where), and both are tested too.
- **Tests** cover the metrics on cases with known answers, the build and analysis on made-up markets, the committed results, the documents, the dashboard and the notebook. They run on every push.

## Limitations

- **Five years is short:** one cycle of the policy rate rising and falling, and the sector order depends on when each sector was strong.
- **Only companies listed today** are included. Companies delisted during the window are missing, which flatters returns; this is probably smaller than it would be with the KSE-100, whose members favour companies that have grown, but it is not zero.
- **Equal weights:** a small company counts as much as a large one.
- **Yahoo Finance is not an official source.** Dividends it does not record are missing, so dividend contributions may be understated.
- **Rupee returns:** {{usd_note}}.
- **Sectors with fewer than {{min_sector}} qualifying companies are not ranked** ({{unranked}}), and "Miscellaneous" is a catch-all, not a sector.
- **Past performance does not predict future returns.**

## Reproduce it

```bash
python -m venv .venv && .venv\Scripts\activate        # macOS or Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m psxsec ingest         # download the company list and prices (about half an hour; needs the internet)
python -m psxsec all            # build, analyze and report (a few minutes)
pytest                          # run the tests
```

The committed results are deterministic given the downloaded prices (seed {{seed}}). A fresh download later will differ a little: Yahoo revises dividends and splits, and the window is fixed to end on {{end_date}}, but companies can be delisted or restated. `python -m psxsec notebook` re-runs the notebook.

## Layout

```
psxsec/            the package: ingest, build, metrics, analysis, charts, dashboard, docs, notebook
  templates/       dashboard page and document templates
data/reference/    the company and sector list and the policy-rate table (with sources)
data/raw/          MANIFEST.json (the raw files themselves are downloaded, not stored)
data/processed/    results as CSV and JSON
docs/              memo, methodology, data sources, figures
dashboard/         the interactive dashboard (one HTML file)
notebooks/         the walk-through notebook
tests/             pytest suite
.github/workflows/ continuous integration
```

## Licence

The code and documents are released under the [MIT licence](LICENSE). The data belong to their sources (the Pakistan Stock Exchange, Yahoo Finance and the State Bank of Pakistan); see [`docs/data_sources.md`](docs/data_sources.md). This is not investment advice.
