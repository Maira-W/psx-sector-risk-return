"""The measures of return and risk, as small functions that can be tested on a case with a known answer.

Every function takes plain pandas or numpy objects and returns numbers; nothing here reads a file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cumulative(returns: pd.Series | pd.DataFrame, base: float = 100.0):
    """Growth of `base` rupees invested at the start, one value per return date."""
    return base * (1 + returns).cumprod()


def total_return(returns: pd.Series | pd.DataFrame):
    return (1 + returns).prod() - 1


def annualised_return(returns, years: float):
    """Compound annual growth rate over `years` years."""
    return (1 + total_return(returns)) ** (1 / years) - 1


def periods_per_year(n_returns: int, years: float) -> float:
    return n_returns / years


def volatility(returns, ppy: float):
    """Annualised standard deviation of the returns."""
    return returns.std(ddof=1) * np.sqrt(ppy)


def sharpe(excess, ppy: float):
    """Average excess return over its standard deviation, annualised. `excess` is the return minus the safe return."""
    return excess.mean() / excess.std(ddof=1) * np.sqrt(ppy)


def max_drawdown(level: pd.Series) -> dict:
    """The worst fall from a peak to a later low, with its dates.

    `level` is a growth-of-100 series that starts at the base date. Recovery is the first date after the low on which the
    level is back at the old peak; it is None if that has not happened by the end.
    """
    running_peak = level.cummax()
    drawdown = level / running_peak - 1
    trough = drawdown.idxmin()
    peak = level.loc[:trough].idxmax()
    after = level.loc[trough:]
    recovered = after[after >= level.loc[peak]]
    return {"max_drawdown": float(drawdown.min()), "peak_date": peak, "trough_date": trough,
            "recovery_date": recovered.index[0] if len(recovered) else None,
            "drawdown_now": float(drawdown.iloc[-1])}


def drawdown_series(level: pd.Series) -> pd.Series:
    return level / level.cummax() - 1


def calmar(cagr: float, mdd: float) -> float:
    """Annual return per unit of the worst fall."""
    return cagr / abs(mdd) if mdd < 0 else float("nan")


def sortino(excess, ppy: float):
    """Like the Sharpe ratio, but only the days that fall short of cash count as risk: mean excess return over the root of the
    average squared shortfall, scaled to a year."""
    values = np.asarray(excess, dtype=float)
    return values.mean() / np.sqrt(np.mean(np.minimum(values, 0.0) ** 2)) * np.sqrt(ppy)


def moments(returns) -> tuple[float, float]:
    """Skewness and (raw) kurtosis of a return series; a normal distribution has skewness 0 and kurtosis 3."""
    values = np.asarray(returns, dtype=float)
    centred = values - values.mean()
    spread = values.std()
    return float(np.mean(centred ** 3) / spread ** 3), float(np.mean(centred ** 4) / spread ** 4)


def tail_risk(returns, level: float = 0.95) -> tuple[float, float]:
    """Value at risk and expected shortfall: the one-day return that is bettered on `level` of days, and the average return on
    the worse days beyond it. Both are returns, so a loss is negative."""
    values = np.asarray(returns, dtype=float)
    cutoff = np.quantile(values, 1 - level)
    return float(cutoff), float(values[values <= cutoff].mean())


def capture_ratios(returns: pd.Series, benchmark: pd.Series) -> tuple[float, float]:
    """Average return in the periods when the benchmark rose, over the benchmark's own average in those periods (up capture),
    and the same for the periods when it fell (down capture). Above 1 in the up periods and below 1 in the down periods is best."""
    up, down = benchmark > 0, benchmark < 0
    return float(returns[up].mean() / benchmark[up].mean()), float(returns[down].mean() / benchmark[down].mean())


def longest_drawdown_days(level: pd.Series) -> int:
    """The most market days in a row that a growth-of-100 series spent below an earlier peak."""
    below = (level < level.cummax()).to_numpy()
    longest = run = 0
    for flag in below:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest


# ---------------------------------------------------------------------------
# The safe rate
# ---------------------------------------------------------------------------
def rate_in_force(dates: pd.DatetimeIndex, policy: pd.DataFrame) -> np.ndarray:
    """The policy rate (percent a year) that applied on each date: the latest change on or before it."""
    effective = pd.DatetimeIndex(policy["effective_date"])
    position = effective.searchsorted(dates, side="right") - 1
    if (position < 0).any():
        raise ValueError(f"the policy rate table starts after {dates[position < 0][0].date()}")
    return policy["policy_rate_pct"].to_numpy()[position]


def safe_return(dates: pd.DatetimeIndex, base_date: pd.Timestamp, policy: pd.DataFrame) -> pd.Series:
    """What cash earning the policy rate would have earned over each return period, by simple accrual.

    The return on date t covers the calendar days since the previous market day (3 across a weekend), earning the rate
    that applied on that previous day.
    """
    previous = pd.DatetimeIndex([base_date, *dates[:-1]])
    days = (dates - previous).days.to_numpy()
    return pd.Series(rate_in_force(previous, policy) / 100 * days / 365, index=dates, name="safe")


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------
def stationary_bootstrap_indices(n: int, draws: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Row numbers for `draws` resampled histories of length n, in blocks of random length (mean `mean_block`).

    Each step either carries on to the next day (probability 1 - 1/mean_block) or jumps to a random day. Keeping short runs
    of days together preserves the way markets move in streaks. The history wraps round at its end.
    """
    jump = rng.random((draws, n)) < 1 / mean_block
    jump[:, 0] = True
    start = rng.integers(0, n, size=(draws, n))
    index = np.empty((draws, n), dtype=np.int64)
    index[:, 0] = start[:, 0]
    for t in range(1, n):
        index[:, t] = np.where(jump[:, t], start[:, t], (index[:, t - 1] + 1) % n)
    return index


def bootstrap_sharpe(excess: pd.DataFrame, ppy: float, draws: int, mean_block: float, seed: int, chunk: int = 100) -> np.ndarray:
    """Sharpe ratios of every column in `draws` resampled histories (the same days for every column). Shape (draws, columns)."""
    values = excess.to_numpy()
    n = len(values)
    rng = np.random.default_rng(seed)
    index = stationary_bootstrap_indices(n, draws, mean_block, rng)
    out = np.empty((draws, values.shape[1]))
    for start in range(0, draws, chunk):
        sample = values[index[start:start + chunk]]            # (chunk, n, columns)
        out[start:start + chunk] = sample.mean(axis=1) / sample.std(axis=1, ddof=1) * np.sqrt(ppy)
    return out


def ranks(values: np.ndarray) -> np.ndarray:
    """1 for the largest value in each row, 2 for the next, and so on (ties get the lower number)."""
    order = (-values).argsort(axis=1, kind="stable")
    out = np.empty_like(order)
    rows = np.arange(values.shape[0])[:, None]
    out[rows, order] = np.arange(1, values.shape[1] + 1)
    return out


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Rank correlation between two sets of scores for the same sectors."""
    both = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(both) < 3:
        return float("nan")
    return float(both.rank().corr(method="pearson").iloc[0, 1])
