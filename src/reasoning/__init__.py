"""
src/reasoning/__init__.py
Package export for reasoning module.
"""

from src.reasoning.kb import KB, MNMEntry
from src.reasoning.bayes import (
    prob_to_odds,
    odds_to_prob,
    prob_to_log_odds,
    log_odds_to_prob,
    update_odds,
    sequential_bayes_update,
)
from src.reasoning.scorer import (
    ScoreResult,
    assign_band,
    clip_if_expert_opinion,
    score_hypothesis,
    score_all_hypotheses,
)

__all__ = [
    "KB",
    "MNMEntry",
    "prob_to_odds",
    "odds_to_prob",
    "prob_to_log_odds",
    "log_odds_to_prob",
    "update_odds",
    "sequential_bayes_update",
    "ScoreResult",
    "assign_band",
    "clip_if_expert_opinion",
    "score_hypothesis",
    "score_all_hypotheses",
]
