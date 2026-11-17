"""
src/reasoning/bayes.py

Deterministic Bayesian calculations in probability and odds space.
Follows docs/07-reasoning-and-scoring.md section B1 and Part E:
- Prior probability to prior odds conversion: odds = p / (1 - p)
- Log-odds evidence accumulation: log_odds = log(prior_odds) + sum(log(LR_i))
- Posterior odds to posterior probability conversion: p = odds / (1 + odds)
- Numerical stability safeguards (clipping, math.log, math.exp)
- Strict validation of priors (0 < p < 1) and likelihood ratios (LR > 0)
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple


# Numerical bounds to prevent overflow / division by zero
MIN_PROBABILITY = 1e-9
MAX_PROBABILITY = 1.0 - 1e-9
MIN_LOG_ODDS = -30.0   # corresponds to p ~ 9.3e-14
MAX_LOG_ODDS = 30.0    # corresponds to p ~ 1.0 - 9.3e-14


def prob_to_odds(p: float) -> float:
    """Convert probability p in (0, 1) to odds = p / (1 - p).

    Raises:
        ValueError: If p is not strictly between 0 and 1.
    """
    if not isinstance(p, (int, float)) or math.isnan(p) or math.isinf(p):
        raise ValueError(f"Probability must be a finite number, got {p}")
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"Prior probability must be strictly between 0 and 1 exclusive, got {p}")

    p_clamped = min(max(p, MIN_PROBABILITY), MAX_PROBABILITY)
    return p_clamped / (1.0 - p_clamped)


def odds_to_prob(odds: float) -> float:
    """Convert odds >= 0 to probability p = odds / (1 + odds).

    Raises:
        ValueError: If odds < 0 or non-finite.
    """
    if not isinstance(odds, (int, float)) or math.isnan(odds) or math.isinf(odds):
        raise ValueError(f"Odds must be a finite non-negative number, got {odds}")
    if odds < 0.0:
        raise ValueError(f"Odds cannot be negative, got {odds}")

    return odds / (1.0 + odds)


def prob_to_log_odds(p: float) -> float:
    """Convert probability to log-odds (logit)."""
    odds = prob_to_odds(p)
    return math.log(odds)


def log_odds_to_prob(log_odds: float) -> float:
    """Convert log-odds to probability using numerically stable sigmoid."""
    if not isinstance(log_odds, (int, float)) or math.isnan(log_odds):
        raise ValueError(f"Log-odds must be a finite number, got {log_odds}")

    clamped_log_odds = min(max(log_odds, MIN_LOG_ODDS), MAX_LOG_ODDS)
    # 1 / (1 + exp(-x))
    if clamped_log_odds >= 0:
        z = math.exp(-clamped_log_odds)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(clamped_log_odds)
        return z / (1.0 + z)


def update_odds(prior_odds: float, likelihood_ratio: float) -> float:
    """Update prior odds with a single likelihood ratio: posterior_odds = prior_odds * LR.

    Raises:
        ValueError: If prior_odds < 0, LR <= 0, or non-finite.
    """
    if not isinstance(prior_odds, (int, float)) or math.isnan(prior_odds) or prior_odds < 0:
        raise ValueError(f"Prior odds must be non-negative finite number, got {prior_odds}")
    if not isinstance(likelihood_ratio, (int, float)) or math.isnan(likelihood_ratio) or likelihood_ratio <= 0:
        raise ValueError(f"Likelihood ratio must be strictly positive (> 0), got {likelihood_ratio}")

    return prior_odds * likelihood_ratio


def sequential_bayes_update(
    prior_probability: float,
    likelihood_ratios: Sequence[float],
) -> Tuple[float, float, List[float]]:
    """Compute Bayesian update sequentially across a series of likelihood ratios.

    Args:
        prior_probability: Starting prior p0 in (0, 1).
        likelihood_ratios: Sequence of positive likelihood ratios.

    Returns:
        (posterior_odds, posterior_probability, intermediate_probabilities)
    """
    initial_odds = prob_to_odds(prior_probability)
    current_log_odds = math.log(initial_odds)
    intermediate_probs: List[float] = []

    for lr in likelihood_ratios:
        if not isinstance(lr, (int, float)) or math.isnan(lr) or lr <= 0:
            raise ValueError(f"Likelihood ratio must be strictly positive (> 0), got {lr}")

        current_log_odds += math.log(lr)
        current_log_odds = min(max(current_log_odds, MIN_LOG_ODDS), MAX_LOG_ODDS)
        intermediate_probs.append(log_odds_to_prob(current_log_odds))

    final_prob = log_odds_to_prob(current_log_odds)
    final_odds = math.exp(min(max(current_log_odds, MIN_LOG_ODDS), MAX_LOG_ODDS))
    return final_odds, final_prob, intermediate_probs
