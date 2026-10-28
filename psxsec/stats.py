"""Statistics beyond the basic measures: regression with robust standard errors, a test that allows for having looked at many
sectors, and the uncertainty of the Sharpe ratio itself. Plain numpy; nothing here reads a file."""

from __future__ import annotations

from dataclasses import dataclass
from math import e, sqrt
from statistics import NormalDist

import numpy as np

from . import metrics

EULER_GAMMA = 0.5772156649015329
NORMAL = NormalDist()


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------
@dataclass
class Fit:
    coef: np.ndarray
    se: np.ndarray        # Newey-West standard errors, which allow for autocorrelation and changing spread in the errors
    cov: np.ndarray
    t: np.ndarray
    r2: float
    n: int


def ols(y, x, lags: int = 0) -> Fit:
    """Least squares of y on the columns of x (include a column of ones for a constant), with Newey-West standard errors.

    `lags` is how many lags of autocorrelation to allow for; 0 gives plain heteroskedasticity-robust errors.
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n, k = x.shape
    bread = np.linalg.inv(x.T @ x)
    coef = bread @ x.T @ y
    resid = y - x @ coef
    score = x * resid[:, None]
    middle = score.T @ score
    for lag in range(1, lags + 1):
        cross = score[lag:].T @ score[:-lag]
        middle += (1 - lag / (lags + 1)) * (cross + cross.T)
    cov = bread @ middle @ bread * n / (n - k)
    se = np.sqrt(np.diag(cov))
    total = np.sum((y - y.mean()) ** 2)
    return Fit(coef, se, cov, coef / se, float(1 - np.sum(resid ** 2) / total) if total > 0 else float("nan"), n)


def market_model(excess, market_excess, lags: int = 4) -> dict:
    """Regress a series of excess returns on the market's excess return this period and last period (the Dimson correction).

    Shares that trade thinly react to the market a little late, so the market's return last period carries part of the
    sensitivity; beta is the sum of the two slopes. Returns alpha (per period), beta, their standard errors and R squared.
    """
    y = np.asarray(excess, dtype=float)[1:]
    x = np.asarray(market_excess, dtype=float)
    design = np.column_stack([np.ones(len(y)), x[1:], x[:-1]])
    fit = ols(y, design, lags)
    beta_variance = fit.cov[1, 1] + fit.cov[2, 2] + 2 * fit.cov[1, 2]
    return {"alpha": float(fit.coef[0]), "alpha_se": float(fit.se[0]), "alpha_t": float(fit.t[0]), "beta": float(fit.coef[1] + fit.coef[2]),
            "beta_se": float(sqrt(beta_variance)), "r2": fit.r2, "n": fit.n}


def normal_p(t) -> np.ndarray:
    """Two-sided p-value of a t-statistic, using the normal distribution (the samples used here are large enough)."""
    return np.array([2 * (1 - NORMAL.cdf(abs(float(value)))) for value in np.atleast_1d(t)])


def benjamini_hochberg(p) -> np.ndarray:
    """Adjusted p-values that control the false discovery rate when many hypotheses are tested at once."""
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    ranked = p[order] * len(p) / np.arange(1, len(p) + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(p)
    out[order] = np.minimum(adjusted, 1.0)
    return out


# ---------------------------------------------------------------------------
# Many sectors at once
# ---------------------------------------------------------------------------
def batch_alpha(y: np.ndarray, x0: np.ndarray, x1: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Many market-model regressions at once: each column of y on a constant and the matching columns of x0 (market this period)
    and x1 (market last period). Returns alpha, its ordinary standard error and beta (the two slopes added), one per column."""
    n = y.shape[0]
    design = np.stack([np.ones_like(y), x0, x1], axis=2)                       # (n, columns, 3)
    gram = np.einsum("nsi,nsj->sij", design, design)
    inverse = np.linalg.inv(gram)
    coef = np.einsum("sij,sj->si", inverse, np.einsum("nsi,ns->si", design, y))
    resid = y - np.einsum("nsi,si->ns", design, coef)
    sigma2 = (resid ** 2).sum(axis=0) / (n - 3)
    return coef[:, 0], np.sqrt(sigma2 * inverse[:, 0, 0]), coef[:, 1] + coef[:, 2]


def alpha_reality_check(y: np.ndarray, x0: np.ndarray, x1: np.ndarray, draws: int = 2000, mean_block: float = 4, seed: int = 42) -> dict:
    """Alpha of every column against the market, with p-values that allow for having looked at all of them.

    The best of many sectors looks good by luck alone, so the usual p-value is too kind. This resamples the weeks in blocks
    (keeping the market and the sector together), re-estimates every alpha around its own estimate, and records the largest
    t-statistic in each resample. A sector's adjusted p-value is how often the largest of all of them is at least as big as
    its own (the single-step max-t method of Romano and Wolf, in the spirit of White's reality check).
    """
    alpha, se, _ = batch_alpha(y, x0, x1)
    t = alpha / se
    index = metrics.stationary_bootstrap_indices(len(y), draws, mean_block, np.random.default_rng(seed))
    largest = np.empty(draws)
    for b in range(draws):
        rows = index[b]
        alpha_b, se_b, _ = batch_alpha(y[rows], x0[rows], x1[rows])
        largest[b] = np.max(np.abs((alpha_b - alpha) / se_b))
    adjusted = np.array([(1 + np.sum(largest >= abs(value))) / (draws + 1) for value in t])
    return {"alpha": alpha, "se": se, "t": t, "p_adjusted": adjusted, "largest_t": largest}


# ---------------------------------------------------------------------------
# How much to believe a Sharpe ratio
# ---------------------------------------------------------------------------
def probabilistic_sharpe(sharpe: float, n: int, skew: float, kurtosis: float, benchmark: float = 0.0) -> float:
    """Probability that the true Sharpe ratio is above `benchmark`, given an estimate from n periods of returns with this
    skewness and (raw) kurtosis. All Sharpe ratios here are per period, not annualised (Bailey and Lopez de Prado, 2012)."""
    spread = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe ** 2
    return NORMAL.cdf((sharpe - benchmark) * sqrt(n - 1) / sqrt(spread))


def expected_max_sharpe(trial_sharpes, trials: int | None = None) -> float:
    """The best Sharpe ratio one would expect among `trials` strategies that all have no skill, given how widely their
    estimated Sharpe ratios are spread (per period). This is the bar a best-of-many result has to clear."""
    values = np.asarray(trial_sharpes, dtype=float)
    count = trials or len(values)
    return float(values.std(ddof=1) * ((1 - EULER_GAMMA) * NORMAL.inv_cdf(1 - 1 / count) + EULER_GAMMA * NORMAL.inv_cdf(1 - 1 / (count * e))))


def deflated_sharpe(sharpe: float, n: int, skew: float, kurtosis: float, trial_sharpes) -> float:
    """Probability that the true Sharpe ratio beats what the best of all the strategies tried would reach by luck alone."""
    return probabilistic_sharpe(sharpe, n, skew, kurtosis, expected_max_sharpe(trial_sharpes))
