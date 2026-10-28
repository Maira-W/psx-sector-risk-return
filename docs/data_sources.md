# Data sources

Three sources feed the analysis. This page says what each one is, how it was obtained, what it is used for, and what was wrong with it.

## At a glance

| File | Bytes | SHA-256 (first 12) | Source | Retrieved |
| --- | ---: | --- | --- | --- |
| `data/raw/psx/screener.html` | 701,462 | `2a7b711fcee6` | dps.psx.com.pk | 2026-10-28 |
| `data/raw/yahoo/daily_prices.csv.gz` | 6,595,283 | `1cc9cdfb96a9` | Yahoo Finance via yfinance 1.7.0 | 2026-10-28 |
| `data/raw/yahoo/usdpkr.csv` | 35,332 | `48e39f1b55a0` | Yahoo Finance via yfinance 1.7.0 (PKR=X) | 2026-10-28 |

The raw files are **not stored in this repository.** The prices and the exchange's page belong to their sources, and the exchange's terms for redistributing market data were not checked in detail, so the repository holds the code, the list of companies and sectors, the policy-rate table, and results computed from the prices, not the prices themselves. `python -m psxsec ingest` downloads them again; `python -m psxsec verify` compares any raw file that is present with the fingerprint in [`data/raw/MANIFEST.json`](../data/raw/MANIFEST.json).

## 1. Companies and sectors: Pakistan Stock Exchange data portal

- **What:** the screener page at `https://dps.psx.com.pk/screener` lists every instrument with its sector code, the indices it belongs to, market capitalisation and other fields. Only the symbol, name, sector and index membership are used, and they are kept in [`data/reference/universe.csv`](../data/reference/universe.csv).
- **Retrieved:** 2026-10-28, with a handful of plain requests that say what they are (no attempt was made to look like a browser). The site returned "not found" for a robots file.
- **Used for:** which companies are in the KSE All Share Index (549) and in the KSE-100 (100), and which sector each belongs to. The sector classification is the exchange's own (38 codes).
- **Problems and judgement calls:**
  - The page lists 752 instruments, but only 549 are in the All Share Index. The rest are rights issues, bonds and similar and are ignored.
  - It is a **snapshot of today's membership**; the index five years ago had different members.
  - Three of the sector codes are investment vehicles (close-end mutual funds, exchange traded funds, real estate investment trusts) and are removed.
  - The company-to-sector mapping is whatever the exchange shows today. A company that changed sector during the window is counted in its current sector throughout.

## 2. Prices, volume and dividends: Yahoo Finance

- **What:** daily close, adjusted close, volume, dividends and stock splits for each symbol with the suffix `.KA`, through the `yfinance` package (1.7.0), retrieved 2026-10-28.
- **Used for:** every return in the analysis (579,383 price rows in all). The exchange rate (rupees per US dollar, Yahoo symbol `PKR=X`, same source and date) is used to show returns in dollars as well as rupees (it went from 174.5 to 276.8 over the window) and, as its percentage change from one month end to the next, as one of the inputs to the interest-rate and rupee model (methodology, section 10).
- **Problems found:**
  - **Missing companies.** Yahoo had no data for 103 of the 538 operating companies asked for (for example AASM, ABSON, AHCL, ALTN, AMSL, ANNT, APOT, ARMG, AVN, AZMT, BAPLR1 and BBFL). They are listed in the manifest and in [`data/processed/stock_status.csv`](../data/processed/stock_status.csv). 5 of them are KSE-100 companies (AHCL, BML, ENGROH, GAL and HUBC), which weakens the KSE-100 cross-check a little.
  - **Holidays.** Yahoo lists PSX holidays as rows with no volume and the previous price. They are dropped (a date counts as a market day only if at least 50 companies traded).
  - **Quiet shares.** Where a share does not trade, the previous price is carried forward. 213 companies traded on fewer than 90% of market days and are excluded for that reason.
  - **Wrong prices and unadjusted corporate actions.** Some shares show a price at a fifth or a tenth of its true level for a few days, and some show a one-day jump that a share cannot make (a bonus issue or split that was not adjusted for). 110 such events in 70 qualifying companies are corrected by fixed rules (see the [methodology](methodology.md)) and listed in [`data/processed/price_corrections.csv`](../data/processed/price_corrections.csv).
  - **Dividend-adjusted prices.** Yahoo's adjusted close is invalid for PHDL (it goes negative, because of a dividend larger than the share price) and treats very large dividends differently from the standard holding-period return. Total returns are therefore computed from the close and the dividend column, and Yahoo's adjusted close is used only as a cross-check: they agree to within half a point of daily return on 99.98% of stock-days.
  - **Dividends.** Dividends that Yahoo does not record are missing, so dividend contributions may be understated. 10 recorded dividends are dated on days that are not market days (a weekend or a holiday); they are credited to the next market day.
  - **Not an official source.** Yahoo's data can contain errors that the checks above would not catch.

Why Yahoo Finance? It is free, covers most of the market and carries adjusted prices. A licensed data feed from the exchange or a vendor would be preferable for anything beyond a study like this one.

## 3. The safe rate: State Bank of Pakistan policy rate

- **What:** the SBP policy rate, typed in by hand as a table of changes ([`data/reference/policy_rate.csv`](../data/reference/policy_rate.csv)) with a source for every row.
- **How the dates were set:** where an SBP circular or a news report gave the effective date, that date is used; otherwise the day after the announcement is assumed. A difference of a day or two changes the cash return by a few thousandths of a percentage point.
- **Why typed in:** the State Bank's website refuses automated requests, so the series could not be downloaded. Every change was checked against at least one dated news report or SBP circular found by search; the sources are linked below. Nothing was scraped from the SBP site.
- **Used for:** the "safe" return in the Sharpe ratio and, as its change from one month end to the next, as an input to the interest-rate and rupee model. The policy rate stands in for a risk-free rate; Treasury bill yields were close to it but were not available in a downloadable form.

| Effective | Rate | How the date was set | Source |
| --- | ---: | --- | --- |
| 2021-10-01 | 7.25% | effective date reported | [link](https://www.dawn.com/news/1647427) |
| 2021-11-22 | 8.75% | effective date reported (announced 2021-11-19) | [link](https://www.dawn.com/news/1659110/sbp-lifts-interest-rate-to-875pc) |
| 2021-12-15 | 9.75% | announced 2021-12-14; next day assumed | [link](https://tribune.com.pk/story/2333848/entertainment) |
| 2022-04-08 | 12.25% | announced 2022-04-07; next day assumed | [link](https://profit.pakistantoday.com.pk/2022/04/07/sbp-hikes-policy-rate-by-250-bps-to-12-25) |
| 2022-05-24 | 13.75% | SBP circular: effective 2022-05-24 | [link](https://www.sbp.org.pk/circulars/dmmd-circular-no-09-of-2022) |
| 2022-07-08 | 15.00% | announced 2022-07-07; next day assumed | [link](https://arynews.tv/sbp-jacks-up-interest-rate-to-15pc/) |
| 2022-11-26 | 16.00% | announced 2022-11-25; next day assumed | [link](https://www.sbp.org.pk/circulars/dmmd-circular-no-20-of-2022) |
| 2023-01-24 | 17.00% | SBP circular: effective 2023-01-24 | [link](https://www.sbp.org.pk/circulars/dmmd-circular-no-01-of-2023) |
| 2023-03-03 | 20.00% | announced 2023-03-02; next day assumed | [link](https://www.dawn.com/news/1740099) |
| 2023-04-05 | 21.00% | announced 2023-04-04; next day assumed | [link](https://www.dawn.com/news/1761889/sbp-springs-surprise-interest-rate-hike-of-100bps) |
| 2023-06-27 | 22.00% | SBP circular: effective 2023-06-27 | [link](https://www.sbp.org.pk/circulars/dmmd-circular-no-10-of-2023) |
| 2024-06-11 | 20.50% | effective date reported (announced 2024-06-10) | [link](https://profit.pakistantoday.com.pk/2024/06/10/sbp-cuts-policy-rate-by-150bps-to-20-5) |
| 2024-07-30 | 19.50% | effective date reported (announced 2024-07-29) | [link](https://www.dawn.com/news/1848892) |
| 2024-09-13 | 17.50% | effective date reported (announced 2024-09-12) | [link](https://www.dawn.com/news/1858509/sbp-cuts-key-policy-rate-by-200bps-to-175pc) |
| 2024-11-05 | 15.00% | effective date reported (announced 2024-11-04) | [link](https://www.zameen.com/news/sbp-lowers-policy-rate-to-15.html) |
| 2024-12-17 | 13.00% | effective date reported (announced 2024-12-16) | [link](https://tribune.com.pk/story/2516535/sbp-slashes-policy-rate-amid-falling-inflation) |
| 2025-01-28 | 12.00% | effective date reported (announced 2025-01-27) | [link](https://www.dawn.com/news/1888017) |
| 2025-05-06 | 11.00% | effective date reported (announced 2025-05-05) | [link](https://propakistani.pk/2025/05/05/sbp-cuts-key-interest-rate-by-1/) |
| 2025-12-16 | 10.50% | effective date reported (announced 2025-12-15) | [link](https://www.dawn.com/news/1961265) |
| 2026-04-28 | 11.50% | effective date reported (announced 2026-04-27) | [link](https://profit.pakistantoday.com.pk/2026/04/27/sbp-raises-policy-rate-by-100-bps-to-11-5-after-three-years-as-inflation-risks-mount/) |
| 2026-10-27 | 12.00% | announced 2026-10-26; next day assumed | [link](https://tradingeconomics.com/pakistan/interest-rate) |

## What was not used

- **The KSE-100 index level or the All Share Index level.** Yahoo Finance returned nothing for `^KSE`, the one index symbol tried, so the whole-market line is built from the companies themselves.
- **Market capitalisation, free float and valuations** on the screener page. They are a snapshot of today and would add look-ahead bias to a five-year study.
- **Company accounts, news and analyst forecasts.**
