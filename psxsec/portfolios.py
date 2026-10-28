"""Portfolio tools: how to weight sectors, how to test a rule out of sample, and how the sectors group together.

Everything works on plain pandas and numpy objects; nothing here reads a file.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from . import stats


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------
def shrunk_covariance(returns) -> tuple[np.ndarray, float]:
    """The covariance of the columns, pulled towards a plain target (the same variance for every column and no correlation).

    The amount of pulling is the one that the Ledoit-Wolf (2004) formula says minimises the expected error. With 22 sectors and a
    year of days the ordinary covariance is noisy, and an optimiser amplifies the noise. Returns the matrix and the amount.
    """
    x = np.asarray(returns, dtype=float)
    n, p = x.shape
    x = x - x.mean(axis=0)
    sample = x.T @ x / n
    mean_variance = np.trace(sample) / p
    spread = np.sum((sample - mean_variance * np.eye(p)) ** 2) / p
    noise = (np.sum(np.sum(x ** 2, axis=1) ** 2) / n ** 2 - np.sum(sample ** 2) / n) / p
    intensity = min(noise, spread) / spread if spread > 0 else 1.0
    return intensity * mean_variance * np.eye(p) + (1 - intensity) * sample, float(intensity)


def project_simplex(v: np.ndarray) -> np.ndarray:
    """The closest point to v among weights that are not negative and add up to one."""
    ordered = np.sort(v)[::-1]
    running = np.cumsum(ordered) - 1
    position = np.arange(1, len(v) + 1)
    last = np.nonzero(ordered - running / position > 0)[0][-1]
    return np.maximum(v - running[last] / (last + 1), 0.0)


def min_variance(cov: np.ndarray, iterations: int = 4000) -> np.ndarray:
    """Weights that are not negative, add up to one and make the portfolio's variance as small as possible.

    Found by accelerated projected gradient descent: step downhill, then pull the result back onto the allowed weights.
    """
    count = len(cov)
    step = 1 / (2 * np.linalg.eigvalsh(cov).max())
    weights = np.full(count, 1 / count)
    guess, momentum = weights.copy(), 1.0
    for _ in range(iterations):
        new = project_simplex(guess - step * 2 * cov @ guess)
        new_momentum = (1 + np.sqrt(1 + 4 * momentum ** 2)) / 2
        guess = new + (momentum - 1) / new_momentum * (new - weights)
        if np.abs(new - weights).sum() < 1e-13:
            weights = new
            break
        weights, momentum = new, new_momentum
    return weights


def inverse_volatility(cov: np.ndarray) -> np.ndarray:
    """Weights in proportion to one over each column's volatility: a simple form of risk parity."""
    weights = 1 / np.sqrt(np.diag(cov))
    return weights / weights.sum()


# ---------------------------------------------------------------------------
# Holding a portfolio
# ---------------------------------------------------------------------------
def month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The last market day of every calendar month in `index`."""
    last = pd.Series(index, index=index).groupby(index.to_period("M")).last()
    return pd.DatetimeIndex(last.to_numpy())


def rebalanced_portfolio(returns: pd.DataFrame, weights: pd.Series | pd.DataFrame) -> pd.Series:
    """Daily return of a portfolio that is set to its target weights on the first day of each month and then left to drift.

    `weights` is one Series (the same target every month) or a DataFrame whose index is the months, as pandas periods, in which
    each target applies. A month without a row is left out of the result.
    """
    month = returns.index.to_period("M")
    pieces = []
    for period in pd.unique(month):
        if isinstance(weights, pd.Series):
            target = weights
        elif period in weights.index:
            target = weights.loc[period]
        else:
            continue
        block = returns[month == period]
        value = (1 + block).cumprod().to_numpy() @ target.reindex(block.columns).to_numpy()
        previous = np.concatenate([[1.0], value[:-1]])
        pieces.append(pd.Series(value / previous - 1, index=block.index))
    return pd.concat(pieces)


def average_turnover(returns: pd.DataFrame, weights: pd.DataFrame) -> float:
    """Average share of the portfolio bought (and sold) each month to get back to the target weights from where the holdings
    had drifted to."""
    month = returns.index.to_period("M")
    turnover, drifted = [], None
    for period in weights.index:
        target = weights.loc[period]
        if drifted is not None:
            turnover.append(0.5 * float(np.abs(target - drifted).sum()))
        block = returns[month == period]
        end_value = (1 + block).prod().reindex(target.index).to_numpy() * target.to_numpy()
        drifted = pd.Series(end_value / end_value.sum(), index=target.index)
    return float(np.mean(turnover))


# ---------------------------------------------------------------------------
# A rule tested out of sample
# ---------------------------------------------------------------------------
Rule = Callable[[pd.DataFrame, pd.Series], pd.Series]


def equal_weight_rule(window: pd.DataFrame, safe: pd.Series) -> pd.Series:
    return pd.Series(1 / window.shape[1], index=window.columns)


def top_sharpe_rule(count: int, worst: bool = False) -> Rule:
    """Hold the `count` sectors with the best (or, for a control, the worst) Sharpe ratio over the look-back window."""
    def rule(window: pd.DataFrame, safe: pd.Series) -> pd.Series:
        excess = window.sub(safe, axis=0)
        ratio = excess.mean() / excess.std(ddof=1)
        chosen = ratio.nsmallest(count) if worst else ratio.nlargest(count)
        return pd.Series(1 / count, index=chosen.index).reindex(window.columns, fill_value=0.0)
    return rule


def min_variance_rule(window: pd.DataFrame, safe: pd.Series) -> pd.Series:
    return pd.Series(min_variance(shrunk_covariance(window)[0]), index=window.columns)


def inverse_volatility_rule(window: pd.DataFrame, safe: pd.Series) -> pd.Series:
    return pd.Series(inverse_volatility(shrunk_covariance(window)[0]), index=window.columns)


def walk_forward(returns: pd.DataFrame, safe: pd.Series, rules: dict[str, Rule], lookback_months: int, first_date: pd.Timestamp) -> dict:
    """Test rules for choosing weights without ever looking ahead.

    On the last market day of each month, every rule sees only the previous `lookback_months` months of returns and names the
    weights to hold for the following month. Those holdings are then followed through that month. The same days also give the
    information coefficient: the rank correlation between each sector's Sharpe ratio over the look-back window and its return
    above cash in the following month, which says whether past performance had any grip on what came next.
    """
    weights: dict[str, dict] = {name: {} for name in rules}
    coefficients = {}
    month = returns.index.to_period("M")
    for end in month_ends(returns.index)[:-1]:
        start = end - pd.DateOffset(months=lookback_months)
        if start < first_date:                       # not yet a full look-back window
            continue
        window = returns[(returns.index > start) & (returns.index <= end)]
        window_safe = safe.loc[window.index]
        following = end.to_period("M") + 1
        for name, rule in rules.items():
            weights[name][following] = rule(window, window_safe)
        excess = window.sub(window_safe, axis=0)
        past = excess.mean() / excess.std(ddof=1)
        ahead = returns[month == following]
        future = (1 + ahead).prod() - 1 - ((1 + safe.loc[ahead.index]).prod() - 1)
        coefficients[end] = past.rank().corr(future.rank())
    frames = {name: pd.DataFrame(table).T.sort_index() for name, table in weights.items()}
    daily = pd.DataFrame({name: rebalanced_portfolio(returns, frame) for name, frame in frames.items()})
    return {"weights": frames, "returns": daily, "ic": pd.Series(coefficients, name="information_coefficient")}


# ---------------------------------------------------------------------------
# How the sectors group together
# ---------------------------------------------------------------------------
def principal_components(returns: pd.DataFrame) -> dict:
    """Principal components of the correlations between the columns.

    `share` is the part of all the variation that each component explains; the first is usually the market itself.
    `effective_bets` is the number of equally important independent sources of risk that would give the same concentration of
    variance: it equals the number of columns if they are uncorrelated and 1 if they all move together.
    """
    values, vectors = np.linalg.eigh(np.corrcoef(returns.to_numpy(), rowvar=False))
    order = values.argsort()[::-1]
    values, vectors = values[order], vectors[:, order]
    vectors = vectors * np.where(vectors.sum(axis=0) < 0, -1.0, 1.0)         # make the first component mostly positive
    return {"eigenvalues": values, "share": values / values.sum(), "loadings": pd.DataFrame(vectors, index=returns.columns),
            "effective_bets": float(values.sum() ** 2 / (values ** 2).sum())}


def average_linkage(corr: np.ndarray) -> list[tuple[int, int, float]]:
    """Hierarchical clustering by correlation, with the distance sqrt((1 - correlation) / 2) and average linkage.

    Returns the merges in the order made as (first, second, distance); the clusters formed are numbered n, n + 1, ... in turn.
    """
    count = len(corr)
    distance = np.sqrt(np.clip(0.5 * (1 - np.asarray(corr)), 0, None))
    members = {i: [i] for i in range(count)}
    active, merges, new = set(range(count)), [], count
    while len(active) > 1:
        best = None
        for a in sorted(active):
            for b in sorted(active):
                if a < b:
                    gap = float(np.mean([distance[i, j] for i in members[a] for j in members[b]]))
                    if best is None or gap < best[0]:
                        best = (gap, a, b)
        gap, a, b = best
        members[new] = members[a] + members[b]
        merges.append((a, b, gap))
        active -= {a, b}
        active.add(new)
        new += 1
    return merges


def leaf_order(merges: list[tuple[int, int, float]], count: int) -> list[int]:
    """The columns in an order that keeps each cluster together, from the merges."""
    def walk(node: int) -> list[int]:
        if node < count:
            return [node]
        first, second, _ = merges[node - count]
        return walk(first) + walk(second)
    return walk(count + len(merges) - 1)


def cut_clusters(merges: list[tuple[int, int, float]], count: int, clusters: int) -> list[int]:
    """Cluster number (0, 1, ...) of each column when the merges are stopped at `clusters` groups; numbered in leaf order."""
    parent = {i: i for i in range(count + len(merges))}

    def find(node: int) -> int:
        while parent[node] != node:
            node = parent[node]
        return node

    for step, (first, second, _) in enumerate(merges[: count - clusters]):
        parent[find(first)] = parent[find(second)] = count + step
    roots = [find(i) for i in leaf_order(merges, count)]
    number = {root: k for k, root in enumerate(dict.fromkeys(roots))}
    labels = [0] * count
    for column in range(count):
        labels[column] = number[find(column)]
    return labels


def summarise_ic(ic: pd.Series, lags: int = 2) -> dict:
    """Average information coefficient with its t-statistic, allowing for months that are related to each other."""
    fit = stats.ols(ic.to_numpy(), np.ones((len(ic), 1)), lags)
    return {"mean": float(fit.coef[0]), "t": float(fit.t[0]), "share_positive": float((ic > 0).mean()), "months": int(len(ic))}
