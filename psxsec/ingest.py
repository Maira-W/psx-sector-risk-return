"""Download the raw data once and keep a fingerprint of every file.

Two downloads: the PSX data portal's screener page (every listed company, its sector and the indices it belongs to) and
daily prices from Yahoo Finance for each company in the All Share Index. The raw files are not stored in the repository
(see docs/data_sources.md); data/raw/MANIFEST.json records the source, time, size and SHA-256 of each one.
The policy rate in data/reference is typed in by hand from SBP announcements, with a source for every row.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
import shutil
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import config

ROUNDS = 3
PAUSE = 0.3
MAX_EMPTY_SHARE = 0.4
CACHE = "yahoo/_cache"
YAHOO_COLUMNS = {"Close": "close", "Adj Close": "adj_close", "Volume": "volume", "Dividends": "dividend", "Stock Splits": "split"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# The PSX listing
# ---------------------------------------------------------------------------
def parse_screener(page: str) -> pd.DataFrame:
    """One row per listing on the screener: symbol, company, sector code and the indices it belongs to."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", page, re.S):
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        if not cells:  # the header row
            continue
        if len(cells) != 11:
            raise ValueError(f"a screener row has {len(cells)} cells, expected 11: {tr[:100]}")
        symbol = re.search(r'data-order="([^"]*)"', cells[0][0]).group(1)
        company = htmllib.unescape(re.search(r'data-title="([^"]*)"', cells[0][1]).group(1)).strip()
        sector = re.sub(r"<[^>]+>", "", cells[1][1]).strip()
        indices = re.sub(r"<[^>]+>", "", cells[2][1]).strip()
        rows.append((symbol, company, sector, indices))
    listings = pd.DataFrame(rows, columns=["symbol", "company", "sector_code", "indices"])
    if listings["symbol"].duplicated().any():
        raise ValueError("duplicate symbols on the screener page")
    return listings


def universe_from_listings(listings: pd.DataFrame) -> pd.DataFrame:
    """The companies in the KSE All Share Index, with their sector and whether they are also in the KSE-100."""
    members = listings[listings["indices"].str.split(",").map(lambda tokens: "ALLSHR" in tokens)].copy()
    unknown = set(members["sector_code"]) - set(config.SECTORS)
    if unknown:
        raise ValueError(f"sector codes not in config.SECTORS: {sorted(unknown)}")
    members["in_kse100"] = members["indices"].str.split(",").map(lambda tokens: "KSE100" in tokens)
    members["sector"] = members["sector_code"].map(config.SECTORS)
    return members[["symbol", "company", "sector_code", "sector", "in_kse100"]].sort_values("symbol").reset_index(drop=True)


def fetch_screener(destination: Path) -> bytes:
    request = urllib.request.Request(config.SCREENER_URL, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return body


# ---------------------------------------------------------------------------
# Yahoo Finance prices
# ---------------------------------------------------------------------------
def _tidy(frame: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """Yahoo's columns renamed, with no dividends or splits recorded shown as 0, and one row per day."""
    frame = frame.rename(columns=YAHOO_COLUMNS).reindex(columns=list(YAHOO_COLUMNS.values()))
    frame[["dividend", "split"]] = frame[["dividend", "split"]].fillna(0.0)
    frame = frame[frame["close"].notna()]
    if frame.empty:
        return None
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    frame.index.name = "date"
    return frame.assign(symbol=symbol).reset_index()


def _single(symbol: str) -> pd.DataFrame | None:
    """One company's daily record from Yahoo Finance, or None if Yahoo has nothing for the symbol."""
    import yfinance as yf
    history = yf.Ticker(symbol + config.YAHOO_SUFFIX).history(
        start=config.DOWNLOAD_START.isoformat(), end=config.DOWNLOAD_END.isoformat(), auto_adjust=False, actions=True, timeout=30)
    return None if history.empty else _tidy(history, symbol)


def fetch_fx(destination: Path) -> pd.DataFrame:
    """Rupees per US dollar, daily, over the same dates; tried in rounds like the share prices."""
    import yfinance as yf
    for round_number in range(1, ROUNDS + 1):
        history = yf.Ticker(config.FX_SYMBOL).history(start=config.DOWNLOAD_START.isoformat(), end=config.DOWNLOAD_END.isoformat(),
                                                      auto_adjust=False, timeout=30)
        if not history.empty:
            fx = history[["Close"]].rename(columns={"Close": "rupees_per_dollar"})
            fx.index = pd.to_datetime(fx.index).tz_localize(None).normalize()
            fx.index.name = "date"
            destination.parent.mkdir(parents=True, exist_ok=True)
            fx.to_csv(destination, lineterminator="\n")
            return fx
        time.sleep(5 * round_number)
    raise RuntimeError(f"Yahoo Finance gave no data for {config.FX_SYMBOL}: run the command again later")


def _cache_path(symbol: str) -> Path:
    return config.RAW / CACHE / (re.sub(r"[^A-Za-z0-9_-]", "_", symbol) + ".csv")


def fetch_prices(symbols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Daily close, adjusted close, volume, dividends and splits for every symbol; also the symbols Yahoo has nothing for.

    One company at a time: Yahoo times out when many are asked for at once. The yfinance package also answers a timeout with
    an empty result, the same as for a symbol it does not know, so an empty answer is not believed until it has been given in
    ROUNDS separate rounds. Each company is saved as soon as it arrives, so an interrupted download carries on where it stopped.
    """
    (config.RAW / CACHE).mkdir(parents=True, exist_ok=True)
    pending = [s for s in symbols if not _cache_path(s).exists()]
    for round_number in range(1, ROUNDS + 1):
        if not pending:
            break
        still = []
        for number, symbol in enumerate(pending, 1):
            try:
                frame = _single(symbol)
            except Exception as error:  # a network problem: treat it like an empty answer and try again next round
                print(f"[ingest] {symbol}: {type(error).__name__}", flush=True)
                frame = None
            if frame is None:
                still.append(symbol)
            else:
                frame.to_csv(_cache_path(symbol), index=False, lineterminator="\n")
            time.sleep(PAUSE * round_number)
            if number % 50 == 0:
                print(f"[ingest] round {round_number}: {number}/{len(pending)} symbols tried", flush=True)
        print(f"[ingest] round {round_number}: {len(pending) - len(still)} of {len(pending)} had data; {len(still)} gave an empty answer", flush=True)
        pending = still
        if pending and round_number < ROUNDS:
            time.sleep(10)
    if len(pending) > MAX_EMPTY_SHARE * len(symbols):
        raise RuntimeError(f"Yahoo Finance gave no data for {len(pending)} of {len(symbols)} symbols, which looks like an outage: run the command again later")
    for symbol in pending:  # an empty file records that Yahoo has no data for the symbol
        _cache_path(symbol).write_text("")
    frames = [pd.read_csv(_cache_path(s), parse_dates=["date"]) for s in symbols if _cache_path(s).stat().st_size]
    prices = pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    return prices, sorted(s for s in symbols if not _cache_path(s).stat().st_size)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def _entry(path: Path, source: str, **extra) -> dict:
    return {"bytes": path.stat().st_size, "sha256": sha256(path), "source": source,
            "retrieved": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), **extra}


def run(refresh: bool = False) -> None:
    import yfinance as yf

    screener_path, prices_path = config.RAW / config.SCREENER_FILE, config.RAW / config.PRICES_FILE
    manifest = json.loads(config.MANIFEST.read_text(encoding="utf-8")) if config.MANIFEST.exists() else {"files": {}}

    if refresh or not screener_path.exists():
        fetch_screener(screener_path)
    listings = parse_screener(screener_path.read_text(encoding="utf-8"))
    universe = universe_from_listings(listings)
    config.REFERENCE.mkdir(parents=True, exist_ok=True)
    universe.to_csv(config.UNIVERSE_FILE, index=False, lineterminator="\n")
    manifest["files"][config.SCREENER_FILE] = _entry(
        screener_path, config.SCREENER_URL, listings=len(listings), in_all_share=len(universe),
        in_kse100=int(universe["in_kse100"].sum()))
    print(f"[ingest] {len(listings)} listings, {len(universe)} in the All Share Index, {int(universe['in_kse100'].sum())} in the KSE-100", flush=True)

    wanted = universe[~universe["sector_code"].isin(config.NOT_OPERATING)]["symbol"].tolist()
    if refresh:
        shutil.rmtree(config.RAW / CACHE, ignore_errors=True)
    if refresh or not prices_path.exists():
        prices, missing = fetch_prices(wanted)
        prices_path.parent.mkdir(parents=True, exist_ok=True)
        prices.to_csv(prices_path, index=False, compression="gzip", lineterminator="\n")
        manifest["files"][config.PRICES_FILE] = _entry(
            prices_path, "Yahoo Finance via yfinance " + yf.__version__, symbols_requested=len(wanted),
            symbols_with_data=int(prices["symbol"].nunique()), symbols_without_data=missing, rows=len(prices),
            first_date=str(prices["date"].min().date()), last_date=str(prices["date"].max().date()))
        print(f"[ingest] prices for {prices['symbol'].nunique()} of {len(wanted)} symbols, {len(prices):,} rows; none for {len(missing)}", flush=True)

    fx_path = config.RAW / config.FX_FILE
    if refresh or not fx_path.exists():
        fx = fetch_fx(fx_path)
        manifest["files"][config.FX_FILE] = _entry(fx_path, f"Yahoo Finance via yfinance {yf.__version__} ({config.FX_SYMBOL})", rows=len(fx),
                                                   first_date=str(fx.index.min().date()), last_date=str(fx.index.max().date()))
        print(f"[ingest] rupees per dollar: {len(fx)} days", flush=True)

    config.MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def verify() -> list[str]:
    """Problems found in the raw files that are present. Files that are absent are not a problem: they are not stored in git."""
    manifest = json.loads(config.MANIFEST.read_text(encoding="utf-8"))["files"]
    problems, absent = [], 0
    for name, entry in manifest.items():
        path = config.RAW / name
        if not path.exists():
            absent += 1
        elif sha256(path) != entry["sha256"]:
            problems.append(f"{name}: checksum differs from the manifest")
    if absent:
        print(f"[verify] {absent} of {len(manifest)} raw files are not on this machine (run `python -m psxsec ingest` to download them)")
    return problems
