"""Thirteen static figures for the README and the memo (docs/figures)."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.ticker import MaxNLocator, NullFormatter  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from . import config  # noqa: E402
from .analysis import MARKET  # noqa: E402

plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 160, "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#9AA5B1", "axes.titleweight": "bold",
                     "axes.titlesize": 12.5, "axes.titlelocation": "left", "font.family": "DejaVu Sans"})

SOURCE = "Sources: PSX data portal (companies and sectors); Yahoo Finance (prices); SBP policy rate. Equal-weighted sector indexes."
SHORT_CHOICE = {" of the window": "", "Without each sector's best company": "Without best company",
                "Without companies with price corrections": "Without corrected companies"}


def short(name: str) -> str:
    return config.SHORT_NAMES.get(name, name)


def _save(fig, name: str, note: str | None = SOURCE) -> None:
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    if note:
        fig.text(0.01, 0.005, note, fontsize=7.5, color="#5B6575", ha="left", va="bottom")
    fig.savefig(config.FIGURES / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _title(ax, title: str, sub: str, lift: float = 0.0) -> None:
    """A title and a grey subtitle above the axes. `lift` (a fraction of the axes height) makes room for labels along the top."""
    height = ax.get_position().height * ax.figure.get_figheight() * 72           # axes height in points
    ax.set_title(title, pad=(0.02 + lift) * height + 16)                         # keeps the title above the subtitle
    ax.text(0, 1.02 + lift, sub, transform=ax.transAxes, fontsize=9, color="#5B6575", va="bottom")


def _label_points(ax, points: list[tuple]) -> None:
    """Label scatter points so that labels do not overlap: each tries a few positions around its point and takes the first free one."""
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    candidates = []
    for radius in (8, 20, 34, 50):                  # positions around the point, nearest first; a thin line joins far labels to their dots
        for angle in (20, -20, 160, -160, 90, -90, 50, -50, 130, -130):
            dx, dy = radius * np.cos(np.radians(angle)), radius * np.sin(np.radians(angle))
            candidates.append((dx, dy, "left" if dx > 3 else "right" if dx < -3 else "center", "bottom" if dy > 3 else "top" if dy < -3 else "center", radius > 8))
    taken = []
    for x, y, *_ in points:          # the dots themselves are in the way too
        px, py = ax.transData.transform((x, y))
        taken.append(Bbox([[px - 7, py - 7], [px + 7, py + 7]]))

    def put(x, y, text, colour, weight, spec):
        dx, dy, ha, va, leader = spec
        return ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=7.5, color=colour, fontweight=weight,
                           arrowprops=dict(arrowstyle="-", color="#B8C2CF", lw=0.6, shrinkA=0, shrinkB=3) if leader else None)

    for x, y, text, colour, weight in points:
        for spec in candidates:
            label = put(x, y, text, colour, weight, spec)
            box = label.get_window_extent(renderer).expanded(1.06, 1.35)
            if not any(box.overlaps(other) for other in taken):
                taken.append(box)
                break
            label.remove()
        else:  # nowhere is free: put it in the first position anyway
            put(x, y, text, colour, weight, candidates[0])


def load() -> dict:
    p = config.PROCESSED
    table = pd.read_csv(p / "sector_summary.csv", dtype={"sector_code": str})
    return {
        "table": table, "ranked": table[table["ranked"]].sort_values("sharpe", ascending=False),
        "daily": pd.read_csv(p / "sector_daily_returns.csv", index_col=0, parse_dates=True),
        "dist": pd.read_csv(p / "sector_rank_distribution.csv", index_col=0),
        "robust": pd.read_csv(p / "robustness_sharpe.csv", index_col=0), "funnel": pd.read_csv(p / "universe_funnel.csv"),
        "summary": json.loads((p / "summary.json").read_text(encoding="utf-8")),
        "strategies": pd.read_csv(p / "walk_forward_daily_returns.csv", index_col=0, parse_dates=True),
        "strategy_table": pd.read_csv(p / "walk_forward_summary.csv", index_col="strategy"),
        "ic": pd.read_csv(p / "walk_forward_ic.csv", index_col=0, parse_dates=True)["information_coefficient"],
        "adjusted_corr": pd.read_csv(p / "market_adjusted_correlations.csv", index_col=0),
    }


def fig_risk_return(t: pd.DataFrame, market: pd.Series, safe_cagr: float) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 6.0))
    top3 = set(t.head(3)["sector"])
    for r in t.itertuples():
        colour = config.NAVY if r.sector in top3 else config.GREY
        ax.scatter(r.volatility * 100, r.cagr * 100, s=40 + 4 * r.n_companies, color=colour, alpha=0.85, edgecolor="white", linewidth=0.7, zorder=3)
    ax.scatter(market["volatility"] * 100, market["cagr"] * 100, marker="D", s=70, color=config.ORANGE, edgecolor="white", zorder=4)
    xs = np.array([0, t["volatility"].max() * 100 * 1.1])
    for s in (0.5, 1.0, 1.5):          # lines of equal Sharpe ratio, all starting from the safe return
        ax.plot(xs, safe_cagr * 100 + s * xs, color="#C9D1DB", lw=0.9, ls="--", zorder=1)
        ax.text(xs[1], safe_cagr * 100 + s * xs[1], f" Sharpe {s:g}", fontsize=7.5, color="#8A94A3", va="center")
    ax.axhline(safe_cagr * 100, color=config.TEAL, lw=1.1)
    ax.text(0.5, safe_cagr * 100 + 0.8, f"cash at the policy rate: {safe_cagr * 100:.1f}% a year", fontsize=8, color=config.TEAL)
    ax.set_xlabel("Risk: annual volatility (%)")
    ax.set_ylabel("Return: compound annual growth (%)")
    ax.set_xlim(0, xs[1] * 1.0)
    _label_points(ax, [(market["volatility"] * 100, market["cagr"] * 100, "Whole market", config.ORANGE, "bold")]
                  + [(r.volatility * 100, r.cagr * 100, short(r.sector), "#1F2937" if r.sector in top3 else "#5B6575", "normal") for r in t.itertuples()])
    rho = t["volatility"].rank().corr(t["cagr"].rank())              # rank correlation
    verdict = ("Sectors with more risk have mostly earned more" if rho >= 0.5 else "Higher risk has not reliably meant higher return" if rho > -0.2
               else "Sectors with more risk have mostly earned less")
    _title(ax, verdict, f"Each dot is a sector (bigger dot, more companies); rank correlation of risk and return {rho:.2f}. Dashed lines: equal return per unit of risk")
    _save(fig, "01_risk_vs_return.png")


def fig_sharpe(t: pd.DataFrame, market: pd.Series) -> None:
    s = t.sort_values("sharpe")
    fig, ax = plt.subplots(figsize=(7.6, 0.27 * len(s) + 1.8))
    y = np.arange(len(s))
    ax.hlines(y, s["sharpe_lo"], s["sharpe_hi"], color="#B8C2CF", lw=2.4, zorder=2)
    ax.scatter(s["sharpe"], y, color=[config.NAVY if p >= 0.95 else config.GREY for p in s["p_beats_market"]], s=38, zorder=3)
    ax.axvline(market["sharpe"], color=config.ORANGE, lw=1.3, ls="--")
    ax.text(market["sharpe"], len(s) - 0.3, " whole market", color=config.ORANGE, fontsize=8, va="bottom")
    ax.axvline(0, color="#9AA5B1", lw=0.8)
    ax.set_yticks(y, [short(n) for n in s["sector"]], fontsize=8.5)
    ax.set_xlabel("Sharpe ratio (return above cash, per unit of risk)")
    verdict = "A clear leader on return per unit of risk" if s["p_top1"].max() >= 0.6 else "The top of the ranking cannot be separated with confidence"
    _title(ax, verdict, "Dot: Sharpe ratio over the five years. Bar: 95% range from resampling. Dark dot: very likely better than the whole market")
    _save(fig, "02_sharpe_ranking.png")


def fig_growth(daily: pd.DataFrame, t: pd.DataFrame, base: str) -> None:
    levels = pd.concat([pd.DataFrame([[100.0] * len(daily.columns)], index=[pd.Timestamp(base)], columns=daily.columns),
                        100 * (1 + daily).cumprod()])
    weekly = levels.resample("W-FRI").last()
    show = [*t.head(3)["sector"], *t.tail(2)["sector"]]
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    palette = [config.NAVY, config.TEAL, config.PURPLE, config.AMBER, config.ORANGE]
    for name, colour in zip(show, palette, strict=False):
        ax.plot(weekly.index, weekly[name], color=colour, lw=1.8, label=short(name))
    ax.plot(weekly.index, weekly[MARKET], color="#333333", lw=2.2, label="Whole market")
    cash = 100 * (1 + daily["Safe return (policy rate)"]).cumprod()
    cash = pd.concat([pd.Series([100.0], index=[pd.Timestamp(base)]), cash]).resample("W-FRI").last()
    ax.plot(cash.index, cash, color=config.GREY, lw=1.4, ls="--", label="Cash at the policy rate")
    ax.set_yscale("log")
    ax.set_yticks([100, 200, 400, 800, 1600], ["100", "200", "400", "800", "1,600"])
    ax.set_ylabel("Growth of 100 rupees (log scale)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _title(ax, "The best and worst sectors by Sharpe ratio, against the market and cash", "Weekly; dividends reinvested; sectors rebalanced monthly")
    _save(fig, "03_growth_of_100.png")


def fig_drawdowns(t: pd.DataFrame, market: pd.Series) -> None:
    s = t.sort_values("max_drawdown", ascending=False)
    fig, ax = plt.subplots(figsize=(7.6, 0.27 * len(s) + 1.8))
    y = np.arange(len(s))
    ax.barh(y, s["max_drawdown"] * 100, color=[config.TEAL if v > market["max_drawdown"] else config.GREY for v in s["max_drawdown"]])
    for i, r in enumerate(s.itertuples()):
        recovered = "recovered" if isinstance(r.recovery_date, str) else "not yet recovered"
        ax.text(r.max_drawdown * 100 - 1, i, f"{r.max_drawdown * 100:.0f}%  ({r.peak_date[:7]} to {r.trough_date[:7]}, {recovered})",
                va="center", ha="right", fontsize=7.3, color="#1F2937")
    ax.axvline(market["max_drawdown"] * 100, color=config.ORANGE, lw=1.3, ls="--")
    ax.set_yticks(y, [short(n) for n in s["sector"]], fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(s["max_drawdown"].min() * 100 * 1.95, 3)
    ax.set_xlabel("Worst fall from a peak to a later low (%)")
    deep = int((s["max_drawdown"] < -0.2).sum())
    _title(ax, f"{deep} of {len(s)} sectors fell more than 20% from a peak", "Teal: shallower than the whole market (dashed line)")
    _save(fig, "04_worst_falls.png")


def fig_years(t: pd.DataFrame, edges: list[str]) -> None:
    s = t.sort_values("sharpe", ascending=False)
    values = s[[f"year{k}" for k in range(1, 6)]].to_numpy() * 100
    fig, ax = plt.subplots(figsize=(7.6, 0.27 * len(s) + 1.8))
    ax.imshow(values, aspect="auto", cmap="RdYlGn", norm=TwoSlopeNorm(vmin=-40, vcenter=0, vmax=120))
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, f"{values[i, j]:+.0f}", ha="center", va="center", fontsize=7.5, color="#1F2937")
    ax.set_yticks(range(len(s)), [short(n) for n in s["sector"]], fontsize=8.5)
    ax.set_xticks(range(5), [f"Year {k}\nto {pd.Timestamp(edges[k]):%b %Y}" for k in range(1, 6)], fontsize=8)
    ax.xaxis.tick_top()
    for spine in ax.spines.values():
        spine.set_visible(False)
    leaders = len({s["sector"].iloc[int(np.argmax(values[:, k]))] for k in range(5)})
    _title(ax, f"{leaders} different sectors led the five years", "Return in each twelve-month period of the window, %; sectors in order of Sharpe ratio", lift=0.09)
    _save(fig, "05_year_by_year.png")


def fig_rank_range(t: pd.DataFrame) -> None:
    s = t.sort_values("rank_median")
    fig, ax = plt.subplots(figsize=(7.6, 0.27 * len(s) + 1.8))
    y = np.arange(len(s))
    ax.hlines(y, s["rank_lo"], s["rank_hi"], color="#B8C2CF", lw=4, zorder=2)
    ax.scatter(s["rank_median"], y, color=config.NAVY, s=30, zorder=3)
    ax.scatter(s["rank_sharpe"], y, marker="|", color=config.ORANGE, s=90, zorder=4)
    ax.set_yticks(y, [f"{short(n)}  ({p * 100:.0f}% first)" for n, p in zip(s["sector"], s["p_top1"], strict=False)], fontsize=8.3)
    ax.invert_yaxis()
    ax.set_xlim(0.5, len(s) + 0.5)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Position among the sectors by Sharpe ratio (1 = best)")
    _title(ax, "Where each sector is likely to finish", "Bar: 95% range of positions when the days are resampled. Dot: median. Orange tick: actual rank")
    _save(fig, "06_rank_range.png")


def fig_robustness(robust: pd.DataFrame, ranked: pd.DataFrame) -> None:
    order = ranked["sector"].tolist()
    ranks = robust.loc[order].rank(ascending=False, method="min")
    fig, ax = plt.subplots(figsize=(8.4, 0.27 * len(order) + 2.3))
    ax.imshow(ranks.to_numpy(), aspect="auto", cmap="YlGnBu_r", vmin=1, vmax=len(order))
    for i in range(ranks.shape[0]):
        for j in range(ranks.shape[1]):
            v = ranks.iloc[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=7, color="white" if v <= len(order) * 0.45 else "#1F2937")
    labels = []
    for column in ranks.columns:
        for old, new in SHORT_CHOICE.items():
            column = column.replace(old, new)
        labels.append(column)
    ax.set_yticks(range(len(order)), [short(n) for n in order], fontsize=8.3)
    ax.set_xticks(range(ranks.shape[1]), labels, rotation=40, ha="left", fontsize=7.5)
    ax.xaxis.tick_top()
    for spine in ax.spines.values():
        spine.set_visible(False)
    _title(ax, "How the ranking moves when the choices change",
           "Rank by Sharpe ratio among the sectors present under each choice (1 = best); blank where a sector has too few companies", lift=0.24)
    _save(fig, "07_robustness.png")


def fig_dividends(t: pd.DataFrame) -> None:
    s = t.sort_values("cagr")
    fig, ax = plt.subplots(figsize=(7.6, 0.27 * len(s) + 1.8))
    y = np.arange(len(s))
    ax.barh(y, s["price_cagr"] * 100, color=config.NAVY, label="Price change")
    ax.barh(y, s["dividend_points"] * 100, left=s["price_cagr"].clip(lower=0) * 100, color=config.AMBER, label="Dividends")
    ax.set_yticks(y, [short(n) for n in s["sector"]], fontsize=8.5)
    ax.axvline(0, color="#9AA5B1", lw=0.8)
    ax.set_xlabel("Compound annual return (%)")
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    _title(ax, f"Dividends supplied {s['dividend_points'].median() * 100:.1f} points of annual return in the typical sector", "Annual return split into price change and dividends")
    _save(fig, "08_dividends.png", SOURCE + " Dividends as recorded by Yahoo Finance.")


def fig_funnel(funnel: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    y = np.arange(len(funnel))[::-1]
    ax.barh(y, funnel["companies"], color=config.NAVY, height=0.62)
    for yy, n in zip(y, funnel["companies"], strict=False):
        ax.text(n + 8, yy, f"{n}", va="center", fontsize=9)
    ax.set_yticks(y, funnel["step"], fontsize=8.3)
    ax.set_xlim(0, funnel["companies"].max() * 1.12)
    _title(ax, "From every listing to the companies analysed", "Number of companies left after each rule")
    _save(fig, "09_universe.png")


def fig_alpha_beta(t: pd.DataFrame, summary: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 6.0))
    raw = t["alpha_p"] < 0.05
    adjusted = t["alpha_p_adjusted"] < 0.05
    colours = [config.NAVY if a else config.AMBER if r else config.GREY for a, r in zip(adjusted, raw, strict=True)]
    ax.errorbar(t["beta"], t["alpha"] * 100, yerr=1.96 * t["alpha_se"] * 100, fmt="none", ecolor="#C9D1DB", elinewidth=1.3, zorder=1)
    ax.scatter(t["beta"], t["alpha"] * 100, s=40 + 4 * t["n_companies"], c=colours, edgecolor="white", linewidth=0.7, zorder=3)
    ax.axhline(0, color="#9AA5B1", lw=0.9)
    ax.axvline(1, color="#C9D1DB", lw=0.9, ls="--")
    ax.set_xlabel("Beta: how strongly the sector follows the rest of the market (1 = one for one)")
    ax.set_ylabel("Alpha: return a year not explained by the market (%)")
    _label_points(ax, [(r.beta, r.alpha * 100, short(r.sector), "#1F2937" if adjusted[r.Index] or raw[r.Index] else "#5B6575", "normal") for r in t.itertuples()])
    handles = [plt.Line2D([0], [0], marker="o", ls="", color=c, markersize=7) for c in (config.NAVY, config.AMBER, config.GREY)]
    ax.legend(handles, ["still significant after allowing for 22 sectors", "significant on its own, not after the correction", "not significant"],
              loc="lower left", frameon=False, fontsize=8)
    a = summary["alpha"]
    on_own = a["alpha_raw_positive"] + a["alpha_raw_negative"]
    verdict = (f"No alpha holds up once all {len(t)} sectors are tested together" if a["alpha_adjusted_significant"] == 0 and on_own > 0 else
               f"{a['alpha_adjusted_significant']} of {len(t)} sectors keep a significant alpha after the correction" if a["alpha_adjusted_significant"]
               else "No sector has an alpha that looks real")
    sub = (f"{on_own} of {len(t)} look significant on their own (amber). " if on_own else "") + "Bigger dot, more companies. Lines: 95% range"
    _title(ax, verdict, sub)
    _save(fig, "10_alpha_and_beta.png", SOURCE + "\nAlpha and beta: weekly returns of each sector against the rest of the market (the market without that sector).")


def _out_of_sample_verdict(table: pd.DataFrame) -> str:
    row = table.loc["winners"]
    gain = f"{row['sharpe']:.2f} against {table.loc['equal_weight', 'sharpe']:.2f}"
    if row["vs_equal_p"] < 0.05:
        return f"Holding last year's best sectors beat equal weighting out of sample ({gain})"
    if row["sharpe_vs_equal"] > 0:
        return f"Last year's best sectors beat equal weighting ({gain}), but not by enough to rule out luck"
    return f"Last year's best sectors did not beat equal weighting ({gain})"


def fig_out_of_sample(strategies: pd.DataFrame, table: pd.DataFrame, ic: pd.Series, summary: dict) -> None:
    fig, (ax, ay) = plt.subplots(1, 2, figsize=(11.0, 4.9), gridspec_kw={"width_ratios": [1.7, 1]}, layout="constrained")
    fig.get_layout_engine().set(rect=(0, 0.04, 1, 0.96))
    levels = 100 * (1 + strategies).cumprod()
    colours = {"equal_weight": config.GREY, "winners": config.NAVY, "losers": config.ORANGE, "min_variance": config.TEAL, "inverse_volatility": config.AMBER,
               "market": "#333333"}
    for name in ("equal_weight", "winners", "losers", "min_variance", "market"):
        ax.plot(levels.index, levels[name], color=colours[name], lw=2.1 if name in ("winners", "min_variance") else 1.5, label=config.STRATEGIES[name],
                ls="--" if name == "market" else "-")
    ax.set_yscale("log")
    ax.set_yticks([100, 200, 400, 800], ["100", "200", "400", "800"])
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("Growth of 100 rupees (log scale)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title(f"Each rule sees only the past {summary['walk_forward']['lookback_months']} months", fontsize=10, pad=8)
    ay.bar(ic.index, ic.to_numpy(), width=22, color=[config.TEAL if v > 0 else config.ORANGE for v in ic], alpha=0.85)
    mean = summary["walk_forward"]["ic"]["mean"]
    ay.axhline(mean, color="#333333", lw=1.2, ls="--")
    ay.axhline(0, color="#9AA5B1", lw=0.8)
    ay.text(0.02, 0.03, f"dashed line: average {mean:+.2f} (t = {summary['walk_forward']['ic']['t']:.1f})", transform=ay.transAxes, fontsize=8,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5})
    ay.xaxis.set_major_locator(mdates.YearLocator())
    ay.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ay.set_ylabel("Correlation of the past ranking\nwith the next month's return")
    ay.set_title("Did the past predict the next month?", fontsize=10, pad=8)
    fig.suptitle(_out_of_sample_verdict(table), x=0.01, ha="left", fontweight="bold", fontsize=12.5)
    _save(fig, "11_out_of_sample.png")


def fig_rates_rupee(t: pd.DataFrame, summary: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 0.27 * len(t) + 2.0), sharey=True)
    fig.subplots_adjust(left=0.17, right=0.985, top=0.88, bottom=0.14, wspace=0.06)
    order = t.sort_values("rate_beta")["sector"].tolist()
    macro = summary["macro"]
    for ax, key, label, fdr in [(axes[0], "rate", "per 1 point higher policy rate", macro["rate_fdr"]), (axes[1], "fx", "per 1% weaker rupee", macro["fx_fdr"])]:
        s = t.set_index("sector").loc[order]
        y = np.arange(len(s))
        colours = [config.NAVY if sector in fdr else config.AMBER if p < 0.05 else config.GREY for sector, p in zip(s.index, s[f"{key}_p"], strict=True)]
        ax.errorbar(s[f"{key}_beta"], y, xerr=1.96 * s[f"{key}_se"], fmt="none", ecolor="#C9D1DB", elinewidth=1.6, zorder=1)
        ax.scatter(s[f"{key}_beta"], y, c=colours, s=36, zorder=3)
        ax.axvline(0, color="#9AA5B1", lw=0.9)
        ax.set_xlabel(f"Extra return (%) {label}")
        ax.set_title("Interest rates" if key == "rate" else "The rupee", fontsize=10.5, pad=8, loc="left", fontweight="bold")
    axes[0].set_yticks(np.arange(len(order)), [short(n) for n in order], fontsize=8.5)
    handles = [plt.Line2D([0], [0], marker="o", ls="", color=c, markersize=7) for c in (config.NAVY, config.AMBER, config.GREY)]
    fig.legend(handles, [f"still significant after allowing for {len(t)} sectors", "significant on its own only", "not significant"], loc="lower center",
               bbox_to_anchor=(0.5, 0.03), ncol=3, frameon=False, fontsize=8)
    rate_n, fx_n = len(macro["rate_fdr"]), len(macro["fx_fdr"])
    if rate_n + fx_n == 0:
        verdict = f"No sector reacts clearly to interest rates or the rupee once all {len(t)} are tested together"
    else:
        verdict = f"Tested together, {rate_n} of {len(t)} sectors react clearly to interest rates and {fx_n} to the rupee"
    fig.suptitle(verdict, x=0.01, y=0.985, ha="left", va="top", fontweight="bold", fontsize=12.5)
    fig.text(0.01, 0.93, f"Monthly returns above cash, controlling for the rest of the market ({macro['months']} months). Lines: 95% range", fontsize=9, color="#5B6575")
    _save(fig, "12_rates_and_rupee.png")


def fig_structure(summary: dict, adjusted: pd.DataFrame) -> None:
    s = summary["structure"]
    fig, (ax, ay) = plt.subplots(1, 2, figsize=(11.2, 6.1), gridspec_kw={"width_ratios": [1, 2.1]}, layout="constrained")
    fig.get_layout_engine().set(rect=(0, 0.04, 1, 0.96))
    shares = np.array(s["shares"]) * 100
    ax.bar(np.arange(1, len(shares) + 1), shares, color=[config.NAVY] + [config.GREY] * (len(shares) - 1))
    for i, v in enumerate(shares, 1):
        ax.text(i, v + 0.8, f"{v:.0f}%", ha="center", fontsize=8)
    ax.set_xticks(np.arange(1, len(shares) + 1))
    ax.set_xlabel("Component (the first is the market)")
    ax.set_ylabel("Share of all the variation in sector returns (%)")
    ax.set_title(f"Like {s['effective_bets']:.1f} independent bets, not {len(adjusted)}", fontsize=10.5, loc="left", fontweight="bold", pad=8)
    names = [short(n) for n in adjusted.index]
    matrix = adjusted.to_numpy().copy()
    np.fill_diagonal(matrix, np.nan)                       # a sector's correlation with itself says nothing
    colours = plt.get_cmap("RdBu_r").copy()
    colours.set_bad("#F3F4F6")
    image = ay.imshow(matrix, cmap=colours, vmin=-0.3, vmax=0.3, aspect="auto")
    fig.colorbar(image, ax=ay, shrink=0.72, pad=0.09, label="Correlation of daily returns after taking out the market")
    ay.set_xticks(range(len(names)), names, rotation=60, ha="right", fontsize=7.5)
    ay.set_yticks(range(len(names)), names, fontsize=7.5)
    edge = 0
    for letter, group in zip(config.GROUP_LETTERS, s["groups"], strict=False):
        ay.text(len(names) - 0.35, edge + (len(group) - 1) / 2, letter, ha="left", va="center", fontsize=9, fontweight="bold", color="#1F2937", clip_on=False)
        edge += len(group)
        if edge < len(names):
            ay.axhline(edge - 0.5, color="#1F2937", lw=1.1)
            ay.axvline(edge - 0.5, color="#1F2937", lw=1.1)
    for spine in ay.spines.values():
        spine.set_visible(False)
    pair = s["strongest_pairs"][0]
    ay.set_title(f"With the market taken out, the strongest link is\n{short(pair['first'])} and {short(pair['second'])} ({pair['correlation']:.2f})",
                 fontsize=10.5, loc="left", fontweight="bold", pad=8)
    fig.suptitle(f"{s['pc1_share'] * 100:.0f}% of the variation in sector returns is one market-wide movement", x=0.01, ha="left", fontweight="bold", fontsize=12.5)
    _save(fig, "13_sector_structure.png", SOURCE + " Right: groups (A, B, ...) from average-linkage clustering of the correlations.")


def make_all() -> None:
    d = load()
    t, market = d["ranked"], d["table"].set_index("sector").loc[MARKET]
    safe_cagr = d["summary"]["safe"]["cagr"]
    fig_risk_return(t, market, safe_cagr)
    fig_sharpe(t, market)
    fig_growth(d["daily"], t, d["summary"]["window"]["base_date"])
    fig_drawdowns(t, market)
    fig_years(t, d["summary"]["window"]["year_edges"])
    fig_rank_range(t)
    fig_robustness(d["robust"], t)
    fig_dividends(t)
    fig_funnel(d["funnel"])
    fig_alpha_beta(t, d["summary"])
    fig_out_of_sample(d["strategies"], d["strategy_table"], d["ic"], d["summary"])
    fig_rates_rupee(t, d["summary"])
    fig_structure(d["summary"], d["adjusted_corr"])
    print(f"[charts] {len(list(config.FIGURES.glob('*.png')))} figures written")
