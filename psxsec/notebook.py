"""Build and run the notebook that walks through the analysis, using only the committed results.

`python -m psxsec notebook` needs the extra tools in requirements-notebook.txt. The notebook is kept with its outputs so it
can be read on GitHub without running anything; a test checks that its code is the code in this file and that no cell failed.
"""

from __future__ import annotations

import json

from . import config

PATH = config.NOTEBOOKS / "sector_risk_return.ipynb"


def _pc(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


SETUP = '''import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))
from psxsec import analysis, metrics  # noqa: E402  (the same functions the pipeline uses)

P = ROOT / "data" / "processed"
pd.options.display.float_format = "{:,.3f}".format
plt.rcParams.update({"figure.dpi": 100, "axes.spines.top": False, "axes.spines.right": False})

summary = json.loads((P / "summary.json").read_text())
table = pd.read_csv(P / "sector_summary.csv", dtype={"sector_code": str})
daily = pd.read_csv(P / "sector_daily_returns.csv", index_col=0, parse_dates=True)
safe = daily.pop("Safe return (policy rate)")
ranked = table[table["ranked"]].sort_values("sharpe", ascending=False).reset_index(drop=True)
market = table[table["sector"] == "Whole market"].iloc[0]
years = summary["window"]["years"]
ppy = len(daily) / years
print(f"{len(daily):,} market days, {summary['window']['base_date']} to {summary['window']['end_date']} ({years:.2f} years)")'''

FUNNEL = '''funnel = pd.read_csv(P / "universe_funnel.csv")
funnel'''

SECTOR_SIZES = '''status = pd.read_csv(P / "stock_status.csv", dtype={"sector_code": str})
sizes = status.groupby("sector")["status"].value_counts().unstack(fill_value=0)
sizes["total"] = sizes.sum(axis=1)
sizes.sort_values("qualifies", ascending=False)'''

TOY = '''# Three made-up companies over four days in the same month.
toy = pd.DataFrame({"A": [0.02, -0.01, 0.00, 0.03], "B": [0.00, 0.01, -0.02, 0.01], "C": [0.04, -0.03, 0.01, 0.00]},
                   index=pd.bdate_range("2024-01-01", periods=4))
toy["rebalanced every day (plain average)"] = analysis.equal_weight_return(toy[["A", "B", "C"]], rebalance="D")
toy["rebalanced monthly (used here)"] = analysis.equal_weight_return(toy[["A", "B", "C"]], rebalance="M")
toy  # the two agree on the first day of the month, then the monthly version lets the holdings drift'''

RECOMPUTE = '''# Recompute one sector's measures from its daily returns and check them against the results table.
name = ranked.loc[0, "sector"]
r = daily[name]
level = pd.concat([pd.Series([100.0], index=[pd.Timestamp(summary["window"]["base_date"])]), metrics.cumulative(r)])
recomputed = {
    "return a year": metrics.annualised_return(r, years),
    "volatility": metrics.volatility(r, ppy),
    "worst fall": metrics.max_drawdown(level)["max_drawdown"],
    "Sharpe ratio": metrics.sharpe(r - safe, ppy),
}
row = ranked.loc[0]
stored = {"return a year": row["cagr"], "volatility": row["volatility"], "worst fall": row["max_drawdown"], "Sharpe ratio": row["sharpe"]}
check = pd.DataFrame({"recomputed here": recomputed, "in the results table": stored})
assert np.allclose(check["recomputed here"], check["in the results table"], atol=1e-4), check
print(name)
check'''

RESULTS = '''columns = ["sector", "n_companies", "cagr", "volatility", "max_drawdown", "sharpe", "sharpe_lo", "sharpe_hi", "p_top3", "p_beats_market"]
shown = ranked[columns].rename(columns={"n_companies": "companies", "cagr": "return a year", "max_drawdown": "worst fall", "sharpe_lo": "sharpe 2.5%",
                                        "sharpe_hi": "sharpe 97.5%", "p_top3": "chance of top 3", "p_beats_market": "chance better than market"})
shown.index = shown.index + 1
shown'''

PLOTS = '''fig, axes = plt.subplots(1, 2, figsize=(13, 5))
ax = axes[0]
ax.scatter(ranked["volatility"] * 100, ranked["cagr"] * 100, s=30 + 4 * ranked["n_companies"], color="#1F3B57", alpha=0.8)
for _, r_ in ranked.iterrows():
    ax.annotate(r_["sector"], (r_["volatility"] * 100, r_["cagr"] * 100), xytext=(4, 3), textcoords="offset points", fontsize=7)
ax.scatter(market["volatility"] * 100, market["cagr"] * 100, marker="D", color="#E76F51", s=60)
ax.axhline(summary["safe"]["cagr"] * 100, color="#2A9D8F", lw=1)
ax.set_xlabel("volatility (% a year)")
ax.set_ylabel("return (% a year)")
ax.set_title("Risk and return by sector")
ax = axes[1]
s = ranked.sort_values("sharpe")
ax.hlines(range(len(s)), s["sharpe_lo"], s["sharpe_hi"], color="#B8C2CF", lw=3)
ax.scatter(s["sharpe"], range(len(s)), color="#1F3B57", zorder=3)
ax.axvline(market["sharpe"], color="#E76F51", ls="--")
ax.set_yticks(range(len(s)), s["sector"], fontsize=7)
ax.set_xlabel("Sharpe ratio, with 95% range")
ax.set_title("Return per unit of risk")
plt.tight_layout()
plt.show()'''

GROWTH = '''top3 = ranked["sector"].head(3).tolist()
levels = 100 * (1 + daily[[*top3, "Whole market"]]).cumprod()
cash = 100 * (1 + safe).cumprod()
ax = levels.plot(figsize=(9, 4.5), logy=True)
cash.plot(ax=ax, color="grey", ls="--", label="cash at the policy rate")
ax.set_ylabel("growth of 100 rupees (log scale)")
ax.legend()
plt.show()'''

BOOTSTRAP = '''# Resample the days in blocks of about 10 and recompute the Sharpe ratio each time (500 resamples here, 2,000 in the pipeline).
excess = (daily[[name]].sub(safe, axis=0))
draws = metrics.bootstrap_sharpe(excess, ppy, draws=500, mean_block=config_block, seed=1)[:, 0]
print(f"{name}: Sharpe {row['sharpe']:.2f}; 95% range from 500 resamples {np.percentile(draws, 2.5):.2f} to {np.percentile(draws, 97.5):.2f}; "
      f"pipeline (2,000 resamples) {row['sharpe_lo']:.2f} to {row['sharpe_hi']:.2f}")
plt.hist(draws, bins=30, color="#9AA5B1")
plt.axvline(row["sharpe"], color="#1F3B57")
plt.xlabel("Sharpe ratio in a resampled history")
plt.show()'''

RANKS = '''distribution = pd.read_csv(P / "sector_rank_distribution.csv", index_col=0)
top = distribution.loc[ranked["sector"].head(6)].iloc[:, :6]
top.columns = ["first" if c == "rank_1" else c.replace("rank_", "position ") for c in top.columns]
top  # the share of resampled histories in which each sector finished in each of the top positions'''

ROBUST = '''robust = pd.read_csv(P / "robustness_summary.csv")
robust'''

ROBUST_RANKS = '''sharpes = pd.read_csv(P / "robustness_sharpe.csv", index_col=0).loc[ranked["sector"]]
sharpes.rank(ascending=False, method="min").astype("Int64")'''


def cells() -> list[tuple[str, str]]:
    s = json.loads((config.PROCESSED / "summary.json").read_text(encoding="utf-8"))
    top = s["top_sharpe"][0]
    window = s["window"]
    intro = f"""# Which PSX sectors paid best for the risk?

**Question.** Over the five years from {window['base_date']} to {window['end_date']}, which sectors of the Pakistan Stock Exchange gave the best return for the risk?

**Approach.** Each sector is an equal-weighted portfolio (rebalanced monthly, dividends included) of its companies that trade regularly ({s['n_companies']} companies, {s['n_sectors_ranked']} ranked sectors). Risk is measured by volatility and by the worst fall from a peak; return per unit of risk by the Sharpe ratio, taking cash at the State Bank's policy rate as the safe alternative.

**Short answer.** By Sharpe ratio the leading sector is **{top['sector']}** ({top['sharpe']:.2f}, 95% range {top['lo']:.2f} to {top['hi']:.2f}) against {s['market']['sharpe']:.2f} for the whole market. It comes first in {_pc(top['p_top1'], 0)} of resampled histories, so the top group is a shortlist, not a winner.

This notebook uses only the results committed in `data/processed`, so it runs without downloading anything. The full pipeline (`python -m psxsec all`) rebuilds them from the raw prices. Nothing here is investment advice."""
    fx, market = s["quality"]["fx"], s["market"]
    limits = (f"## 8. Limits\n\n- Five years is short: the window spans the policy rate rising to {s['safe']['policy_rate_peak']:g}% and coming back down, "
              "and a sector's rank depends on when it was strong.\n"
              "- Only companies listed today are included; companies that were delisted are missing, which flatters returns.\n"
              "- Equal weights give small companies the same say as large ones.\n"
              "- Yahoo Finance is not an official source; dividends it does not record are missing.\n"
              f"- Returns are in rupees. Rupees per dollar went from {fx['base']:.1f} to {fx['end']:.1f}; in dollars the whole market returned "
              f"{_pc(market['usd_cagr'])} a year against {_pc(market['cagr'])} in rupees.\n"
              "- This describes the past and is not a recommendation to buy or sell anything.")
    return [
        ("markdown", intro),
        ("code", SETUP),
        ("markdown", "## 1. Who is in the analysis\n\nEvery company in the KSE All Share Index, minus investment funds, ETFs and property trusts. A company qualifies if it has a price on nearly every market day of the five years and traded on at least 90% of them. The rule removes stocks whose price hardly ever changes because few trades happen: they can look safer than they are."),
        ("code", FUNNEL),
        ("code", SECTOR_SIZES),
        ("markdown", "## 2. How a sector index is built\n\nA sector index holds equal amounts of each of its companies on the first day of every month and lets the holdings drift with prices until the next month; its daily return is the change in value (price change plus dividends). A small company counts as much as a large one at the start of each month. Putting the weights back to equal every day, which is the plain average of the companies' returns, would flatter shares that trade rarely, so the monthly version is used."),
        ("code", TOY),
        ("markdown", "## 3. The measures\n\nThe functions in `psxsec/metrics.py` compute them. As a check, the cell below recomputes the leading sector's numbers from its daily returns and compares them with the results table."),
        ("code", RECOMPUTE),
        ("markdown", "## 4. The results\n\nSectors ranked by Sharpe ratio. 'Chance of top 3' and 'chance better than market' come from the resampling in section 6."),
        ("code", RESULTS),
        ("code", PLOTS),
        ("code", GROWTH),
        ("markdown", "## 5. Ups and downs\n\nThe figures in `docs/figures` show the worst fall of each sector, the year-by-year returns and how much of the return came from dividends. The interactive dashboard has the same views for every sector."),
        ("markdown", "## 6. How sure can we be?\n\nFive years is one history. To see how much the ranking depends on luck, the days are resampled in blocks of about 10 (to keep short streaks together) and the Sharpe ratio recomputed. Doing this for all sectors at once gives each sector's chance of finishing first or in the top three."),
        ("code", "config_block = 10\n" + BOOTSTRAP),
        ("code", RANKS),
        ("markdown", "## 7. Do other choices change the answer?\n\nThe analysis was repeated using only KSE-100 companies, looser and tighter trading rules, rebalancing every day, weekly instead of daily returns, dropping each sector's best company, leaving out companies whose prices were corrected, the typical company instead of the average, each half of the window, and trimming three months from either end. 'Rank correlation' is 1 when a choice gives the same order as the main result."),
        ("code", ROBUST),
        ("code", ROBUST_RANKS),
        ("markdown", limits),
    ]


def _merge_streams(notebook) -> None:
    """Join consecutive printed outputs of a cell into one. The kernel may deliver a line and its newline separately, which would
    make the saved file differ from run to run for no reason."""
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        merged = []
        for output in cell.outputs:
            if merged and output.output_type == "stream" and merged[-1].output_type == "stream" and merged[-1].name == output.name:
                merged[-1].text += output.text
            else:
                merged.append(output)
        cell.outputs = merged


def build(execute: bool = True) -> None:
    import nbformat
    from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

    notebook_cells = []
    for number, (kind, source) in enumerate(cells(), 1):
        cell = new_code_cell(source) if kind == "code" else new_markdown_cell(source)
        cell["id"] = f"cell-{number:02d}"
        notebook_cells.append(cell)
    notebook = new_notebook(cells=notebook_cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                                           "language_info": {"name": "python"}})
    if execute:
        from nbclient import NotebookClient
        config.NOTEBOOKS.mkdir(parents=True, exist_ok=True)
        NotebookClient(notebook, timeout=600, kernel_name="python3", record_timing=False,
                       resources={"metadata": {"path": str(config.NOTEBOOKS)}}).execute()
        _merge_streams(notebook)
    text = nbformat.writes(notebook)
    PATH.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")      # Unix line endings on every machine


def run() -> None:
    build(execute=True)
    print(f"[notebook] wrote {PATH.relative_to(config.ROOT)}")
