"""Constants shared by every stage: where the data come from, how companies are grouped, and the rules of the analysis."""

from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
REFERENCE = ROOT / "data" / "reference"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
DOCS = ROOT / "docs"
FIGURES = DOCS / "figures"
DASHBOARD = ROOT / "dashboard"
NOTEBOOKS = ROOT / "notebooks"
TEMPLATES = Path(__file__).resolve().parent / "templates"
MANIFEST = RAW / "MANIFEST.json"

SEED = 42

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# The Pakistan Stock Exchange data portal's screener lists every listed company with its sector code and the indices it
# belongs to (ALLSHR is the KSE All Share Index, KSE100 the KSE-100).
SCREENER_URL = "https://dps.psx.com.pk/screener"
SCREENER_FILE = "psx/screener.html"
USER_AGENT = "psx-sector-risk-return/1.0 (personal data-analysis portfolio project)"

# Daily prices come from Yahoo Finance through the yfinance package; a PSX symbol such as OGDC becomes OGDC.KA.
YAHOO_SUFFIX = ".KA"
PRICES_FILE = "yahoo/daily_prices.csv.gz"
DOWNLOAD_START = date(2021, 8, 1)   # a little before the window, so the first return is never missing
DOWNLOAD_END = date(2026, 10, 29)   # exclusive end, as Yahoo reads it

# Rupees per US dollar, from Yahoo Finance, only to show returns in dollars as well as rupees.
FX_SYMBOL = "PKR=X"
FX_FILE = "yahoo/usdpkr.csv"

POLICY_RATE_FILE = REFERENCE / "policy_rate.csv"
UNIVERSE_FILE = REFERENCE / "universe.csv"

# ---------------------------------------------------------------------------
# The window and the rules
# ---------------------------------------------------------------------------
# The analysis covers the five years of returns ending on WINDOW_END. The base date is the last market day on or before
# five years earlier, so the first return is the day after it.
WINDOW_END = date(2026, 10, 27)
WINDOW_YEARS = 5

# A company is analysed only if it has a price on almost every market day of the window and actually traded on most of them.
MIN_HISTORY_SHARE = 0.98
MIN_TRADED_SHARE = 0.90
TRADED_SHARE_CHECKS = (0.80, 0.95)   # the other thresholds tried in the robustness checks
MIN_SECTOR_STOCKS = 4                # a sector with fewer qualifying companies is shown but not ranked
MIN_KSE100_SECTOR_STOCKS = 3         # the same rule for the KSE-100 cross-check, which has fewer companies per sector

# Cleaning the prices. The exchange limits a share's move in one day to a few percent or Re 1, whichever is larger, so a bigger
# move is a corporate action that the price series did not adjust for (a bonus issue, a share split) or a data error.
SPIKE_RATIO = 1.5      # a price this far above or below the day before (as a ratio) ...
SPIKE_DAYS = 3         # ... for up to this many days, and then back to within SPIKE_BACK of where it was, is a bad price
SPIKE_BACK = 1.15
JUMP_RATIO = 1.15      # a one-day price change of this ratio up (or the same move down) ...
JUMP_RUPEES = 1.05     # ... that is also larger than this many rupees (Re 1 plus a little for rounding) is beyond the daily limit: price return set to zero

# Market days: dates on which at least this many companies traded. PSX holidays appear in Yahoo's data as days with no trading.
MIN_TRADING_COMPANIES = 50

# Bootstrap: resample days in blocks of about 10 so that the short-run ups and downs of the market are kept together.
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_BLOCK = 10

# The market model and the macro model use weekly and monthly returns, which are less affected by shares that trade late than daily
# ones. The numbers of lags are the numbers of weeks or months over which the errors are allowed to be related.
BOOTSTRAP_BLOCK_WEEKS = 4
HAC_LAGS_WEEKLY = 4
HAC_LAGS_MONTHLY = 3

# The out-of-sample test: every month, hold the TOP_SECTORS sectors with the best Sharpe ratio over the last LOOKBACK_MONTHS months.
# The other look-back windows and counts are tried only to show how much the answer depends on these choices.
LOOKBACK_MONTHS = 12
TOP_SECTORS = 3
LOOKBACK_CHECKS = (6, 24)
TOP_CHECKS = (5,)
STRATEGIES = {"equal_weight": "Equal weight, all sectors", "winners": "Best sectors of the past year", "losers": "Worst sectors of the past year",
              "min_variance": "Minimum variance", "inverse_volatility": "Inverse volatility", "market": "Whole market"}

# How many groups to cut the sectors into when clustering them by correlation, and the letters the documents use for them
CLUSTERS = 4
GROUP_LETTERS = "ABCDEFGH"

# ---------------------------------------------------------------------------
# Sectors (PSX's own sector codes)
# ---------------------------------------------------------------------------
SECTORS = {
    "0801": "Automobile assemblers", "0802": "Automobile parts", "0803": "Cable and electrical goods", "0804": "Cement",
    "0805": "Chemicals", "0806": "Close-end mutual funds", "0807": "Commercial banks", "0808": "Engineering",
    "0809": "Fertilizer", "0810": "Food and personal care", "0811": "Glass and ceramics", "0812": "Insurance",
    "0813": "Investment banks and securities", "0814": "Jute", "0815": "Leasing companies", "0816": "Leather and tanneries",
    "0818": "Miscellaneous", "0819": "Modarabas", "0820": "Oil and gas exploration", "0821": "Oil and gas marketing",
    "0822": "Paper and packaging", "0823": "Pharmaceuticals", "0824": "Power generation and distribution", "0825": "Refinery",
    "0826": "Sugar", "0827": "Synthetic and rayon", "0828": "Technology and communication", "0829": "Textile composite",
    "0830": "Textile spinning", "0831": "Textile weaving", "0832": "Tobacco", "0833": "Transport",
    "0834": "Vanaspati and allied", "0835": "Woollen", "0836": "Real estate investment trusts", "0837": "Exchange traded funds",
    "0838": "Property", "0839": "Apparel",
}
# Shorter names for crowded charts; any sector not listed here keeps its full name.
SHORT_NAMES = {
    "Automobile assemblers": "Auto assemblers", "Automobile parts": "Auto parts", "Cable and electrical goods": "Cables & electrical",
    "Commercial banks": "Banks", "Food and personal care": "Food & personal care", "Glass and ceramics": "Glass & ceramics",
    "Investment banks and securities": "Investment banks", "Oil and gas exploration": "Oil & gas exploration",
    "Oil and gas marketing": "Oil & gas marketing", "Paper and packaging": "Paper & packaging",
    "Power generation and distribution": "Power", "Synthetic and rayon": "Synthetic & rayon",
    "Technology and communication": "Technology", "Vanaspati and allied": "Vanaspati",
}
# Investment vehicles rather than operating companies: left out of everything.
NOT_OPERATING = ("0806", "0836", "0837")
# A catch-all, not a sector: its companies count in the whole-market line but the group is not ranked.
UNRANKED = ("0818",)

# ---------------------------------------------------------------------------
# Palette shared by the figures and the dashboard
# ---------------------------------------------------------------------------
NAVY, TEAL, ORANGE, AMBER, GREY, PURPLE = "#1F3B57", "#2A9D8F", "#E76F51", "#E9C46A", "#9AA5B1", "#7B4FA3"
PLOTLY_JS = "https://cdn.plot.ly/plotly-3.5.0.min.js"
