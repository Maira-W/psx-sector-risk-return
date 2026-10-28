"""The interactive dashboard: one HTML file with the data inside, Plotly from a CDN, and no server."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from . import config
from .analysis import MARKET

PAGE = config.TEMPLATES / "dashboard.html"
CASH = "Safe return (policy rate)"
DAILY_SCALE = 100_000          # daily returns travel as whole numbers of a thousandth of a percent (1e-5), which keeps the file small


def _records(frame: pd.DataFrame, digits: int) -> list[dict]:
    return json.loads(frame.round(digits).to_json(orient="records"))


def _clean(value):
    """Strict JSON has no NaN or infinity, so a number that could not be worked out travels as null."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def payload() -> dict:
    p = config.PROCESSED
    sectors = pd.read_csv(p / "sector_summary.csv", dtype={"sector_code": str})
    stocks = pd.read_csv(p / "stock_summary.csv")
    daily = pd.read_csv(p / "sector_daily_returns.csv", index_col=0, parse_dates=True)
    summary = json.loads((p / "summary.json").read_text(encoding="utf-8"))
    base = pd.Timestamp(summary["window"]["base_date"])

    levels = pd.concat([pd.DataFrame([[100.0] * daily.shape[1]], index=[base], columns=daily.columns), 100 * (1 + daily).cumprod()])
    drawdown = levels / levels.cummax() - 1
    weekly = levels.resample("W-FRI").last()
    weekly_drawdown = drawdown.resample("W-FRI").min()

    robust = pd.read_csv(p / "robustness_sharpe.csv", index_col=0)
    ranked = sectors[sectors["ranked"]].sort_values("sharpe", ascending=False)["sector"].tolist()
    ranks = robust.loc[ranked].rank(ascending=False, method="min")
    corr = pd.read_csv(p / "sector_correlations.csv", index_col=0).loc[[*ranked, MARKET], [*ranked, MARKET]]
    policy = pd.read_csv(config.POLICY_RATE_FILE)

    keep = ["symbol", "company", "sector", "in_kse100", "traded_share", "total_return", "cagr", "volatility", "sharpe", "max_drawdown",
            "price_cagr", "dividend_points"]

    strategies = pd.read_csv(p / "walk_forward_daily_returns.csv", index_col=0, parse_dates=True)
    before = daily.index[daily.index < strategies.index[0]].max()               # the day the strategies start from, at 100
    growth = pd.concat([pd.DataFrame([[100.0] * strategies.shape[1]], index=[before], columns=strategies.columns),
                        100 * (1 + strategies).cumprod()]).resample("W-FRI").last()
    information = pd.read_csv(p / "walk_forward_ic.csv", index_col=0, parse_dates=True)["information_coefficient"]
    adjusted = pd.read_csv(p / "market_adjusted_correlations.csv", index_col=0)
    presets = pd.read_csv(p / "portfolio_presets.csv", index_col=0)[ranked]
    scaled = (daily[[*ranked, MARKET]] * DAILY_SCALE).round().astype(int)

    return _clean({
        "sectors": _records(sectors, 5),
        "stocks": _records(stocks[keep], 4),
        "weeks": [d.strftime("%Y-%m-%d") for d in weekly.index],
        "levels": {c: [round(float(v), 1) for v in weekly[c]] for c in weekly.columns},
        "drawdowns": {c: [round(float(v) * 100, 1) for v in weekly_drawdown[c]] for c in weekly_drawdown.columns},
        "cashName": CASH, "marketName": MARKET,
        "rankedOrder": ranked,
        "robust": {"choices": list(robust.columns), "ranks": [[None if np.isnan(v) else int(v) for v in row] for row in ranks.to_numpy()]},
        "robustSummary": _records(pd.read_csv(p / "robustness_summary.csv"), 3),
        "corr": {"names": list(corr.columns), "matrix": [[round(float(v), 2) for v in row] for row in corr.to_numpy()]},
        "funnel": _records(pd.read_csv(p / "universe_funnel.csv"), 0),
        "policy": _records(policy[["effective_date", "policy_rate_pct"]], 2),
        "shortNames": config.SHORT_NAMES,
        "daily": {"scale": DAILY_SCALE, "dates": [d.strftime("%Y-%m-%d") for d in daily.index], "returns": {c: scaled[c].tolist() for c in scaled.columns},
                  "safe": [round(float(v), 8) for v in daily[CASH]]},          # cash changes slowly, so rounding it would not average out
        "presets": {name: [round(float(v), 9) for v in presets.loc[name]] for name in presets.index},
        "walkForward": {"names": config.STRATEGIES, "weeks": [d.strftime("%Y-%m-%d") for d in growth.index],
                        "levels": {c: [round(float(v), 1) for v in growth[c]] for c in growth.columns},
                        "icDates": [d.strftime("%Y-%m-%d") for d in information.index], "ic": [round(float(v), 4) for v in information]},
        "structure": {"names": list(adjusted.columns), "matrix": [[round(float(v), 3) for v in row] for row in adjusted.to_numpy()], "letters": config.GROUP_LETTERS},
        "stats": summary,
    })


def render() -> str:
    page = PAGE.read_text(encoding="utf-8")
    data = json.dumps(payload(), separators=(",", ":"), allow_nan=False)
    return page.replace("__PLOTLY__", config.PLOTLY_JS).replace("__DATA__", data.replace("</", "<\\/"))


def build() -> None:
    config.DASHBOARD.mkdir(parents=True, exist_ok=True)
    (config.DASHBOARD / "dashboard.html").write_text(render(), encoding="utf-8", newline="\n")
    (config.ROOT / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=dashboard/dashboard.html">'
        '<title>PSX sector risk and return</title><p><a href="dashboard/dashboard.html">Open the dashboard</a></p></html>\n',
        encoding="utf-8", newline="\n")
    print(f"[dashboard] {(config.DASHBOARD / 'dashboard.html').stat().st_size / 1e3:,.0f} kB")
