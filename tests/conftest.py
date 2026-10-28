import json

import pandas as pd
import pytest

from psxsec import config


@pytest.fixture(scope="session")
def summary():
    return json.loads((config.PROCESSED / "summary.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sectors():
    return pd.read_csv(config.PROCESSED / "sector_summary.csv", dtype={"sector_code": str})


@pytest.fixture(scope="session")
def daily():
    return pd.read_csv(config.PROCESSED / "sector_daily_returns.csv", index_col=0, parse_dates=True)


@pytest.fixture(scope="session")
def stocks():
    return pd.read_csv(config.PROCESSED / "stock_summary.csv")


@pytest.fixture(scope="session")
def status():
    return pd.read_csv(config.PROCESSED / "stock_status.csv", dtype={"sector_code": str})


@pytest.fixture(scope="session")
def universe():
    return pd.read_csv(config.UNIVERSE_FILE, dtype={"sector_code": str})


@pytest.fixture(scope="session")
def manifest():
    return json.loads(config.MANIFEST.read_text(encoding="utf-8"))["files"]
