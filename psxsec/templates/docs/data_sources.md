# Data sources

Three sources feed the analysis. This page says what each one is, how it was obtained, what it is used for, and what was wrong with it.

## At a glance

{{table_files}}

The raw files are **not stored in this repository.** The prices and the exchange's page belong to their sources, and the exchange's terms for redistributing market data were not checked in detail, so the repository holds the code, the list of companies and sectors, the policy-rate table, and results computed from the prices, not the prices themselves. `python -m psxsec ingest` downloads them again; `python -m psxsec verify` compares any raw file that is present with the fingerprint in [`data/raw/MANIFEST.json`](../data/raw/MANIFEST.json).

## 1. Companies and sectors: Pakistan Stock Exchange data portal

- **What:** the screener page at `https://dps.psx.com.pk/screener` lists every instrument with its sector code, the indices it belongs to, market capitalisation and other fields. Only the symbol, name, sector and index membership are used, and they are kept in [`data/reference/universe.csv`](../data/reference/universe.csv).
- **Retrieved:** {{screener_retrieved}}, with a handful of plain requests that say what they are (no attempt was made to look like a browser). The site returned "not found" for a robots file.
- **Used for:** which companies are in the KSE All Share Index ({{n_all_share}}) and in the KSE-100 ({{n_kse100}}), and which sector each belongs to. The sector classification is the exchange's own (38 codes).
- **Problems and judgement calls:**
  - The page lists {{n_listings}} instruments, but only {{n_all_share}} are in the All Share Index. The rest are rights issues, bonds and similar and are ignored.
  - It is a **snapshot of today's membership**; the index five years ago had different members.
  - Three of the sector codes are investment vehicles (close-end mutual funds, exchange traded funds, real estate investment trusts) and are removed.
  - The company-to-sector mapping is whatever the exchange shows today. A company that changed sector during the window is counted in its current sector throughout.

## 2. Prices, volume and dividends: Yahoo Finance

- **What:** daily close, adjusted close, volume, dividends and stock splits for each symbol with the suffix `.KA`, through the `yfinance` package ({{yf_version}}), retrieved {{retrieved}}.
- **Used for:** every return in the analysis ({{n_rows:,}} price rows in all). The exchange rate (rupees per US dollar, Yahoo symbol `PKR=X`, same source and date) is used only to show returns in dollars as well as rupees: it went from {{fx_base:.0f}} to {{fx_end:.0f}} over the window.
- **Problems found:**
  - **Missing companies.** Yahoo had no data for {{n_no_price_requested}} of the {{n_requested}} operating companies asked for (for example {{no_price}}). They are listed in the manifest and in [`data/processed/stock_status.csv`](../data/processed/stock_status.csv). {{n_kse100_no_data}} of them are KSE-100 companies ({{kse100_no_data}}), which weakens the KSE-100 cross-check a little.
  - **Holidays.** Yahoo lists PSX holidays as rows with no volume and the previous price. They are dropped (a date counts as a market day only if at least {{min_trading_companies}} companies traded).
  - **Quiet shares.** Where a share does not trade, the previous price is carried forward. {{n_thin}} companies traded on fewer than {{min_traded:.0f}}% of market days and are excluded for that reason.
  - **Wrong prices and unadjusted corporate actions.** Some shares show a price at a fifth or a tenth of its true level for a few days, and some show a one-day jump that a share cannot make (a bonus issue or split that was not adjusted for). {{fix_n}} such events in {{fix_companies}} qualifying companies are corrected by fixed rules (see the [methodology](methodology.md)) and listed in [`data/processed/price_corrections.csv`](../data/processed/price_corrections.csv).
  - **Dividend-adjusted prices.** Yahoo's adjusted close is invalid for {{invalid_adj}} (it goes negative, because of a dividend larger than the share price) and treats very large dividends differently from the standard holding-period return. Total returns are therefore computed from the close and the dividend column, and Yahoo's adjusted close is used only as a cross-check: they agree to within half a point of daily return on {{cc_days:.2f}}% of stock-days.
  - **Dividends.** Dividends that Yahoo does not record are missing, so dividend contributions may be understated. {{moved_div}} recorded dividends are dated on days that are not market days (a weekend or a holiday); they are credited to the next market day.
  - **Not an official source.** Yahoo's data can contain errors that the checks above would not catch.

Why Yahoo Finance? It is free, covers most of the market and carries adjusted prices. A licensed data feed from the exchange or a vendor would be preferable for anything beyond a study like this one.

## 3. The safe rate: State Bank of Pakistan policy rate

- **What:** the SBP policy rate, typed in by hand as a table of changes ([`data/reference/policy_rate.csv`](../data/reference/policy_rate.csv)) with a source for every row.
- **How the dates were set:** where an SBP circular or a news report gave the effective date, that date is used; otherwise the day after the announcement is assumed. A difference of a day or two changes the cash return by a few thousandths of a percentage point.
- **Why typed in:** the State Bank's website refuses automated requests, so the series could not be downloaded. Every change was checked against at least one dated news report or SBP circular found by search; the sources are linked below. Nothing was scraped from the SBP site.
- **Used for:** the "safe" return in the Sharpe ratio. The policy rate stands in for a risk-free rate; Treasury bill yields were close to it but were not available in a downloadable form.

{{table_policy}}

## What was not used

- **The KSE-100 index level or the All Share Index level.** Yahoo Finance returned nothing for `^KSE`, the one index symbol tried, so the whole-market line is built from the companies themselves.
- **Market capitalisation, free float and valuations** on the screener page. They are a snapshot of today and would add look-ahead bias to a five-year study.
- **Company accounts, news and analyst forecasts.**
