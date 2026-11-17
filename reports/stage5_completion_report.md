# Medagents Prototype — Stage 5 Completion Report

**Date:** 2026-11-17  
**Stage:** Stage 5 — Deterministic Bayesian Reasoning Engine  
**Status:** COMPLETED & VERIFIED — 99 / 99 Tests Passing (100%)  
**Workspace:** `C:\Users\DELL\Desktop\prototype of madd`  
**Original Project:** `C:\Users\DELL\Desktop\Mini project\Medagents\medagents` (Strictly Unmodified / Read-Only)

---

## 1. Executive Summary

Stage 5 delivers the **Deterministic Bayesian Reasoning Engine** for the Medagents prototype, adhering to `docs/07-reasoning-and-scoring.md` section B and `docs/INTERFACES.md` section 8.4.

The Bayesian reasoning engine computes diagnostic hypothesis scores using Bayes' theorem in odds and log-odds space. It is a research and engineering demonstration built on synthetic data, and is strictly **not** a clinically validated diagnostic system. All probability bands (`HIGH`, `MODERATE`, `LOW`, `VERY_LOW`) are unvalidated demonstration bands for interface and algorithm verification, not clinical risk classifications.

In strict compliance with the architecture and safety specifications:
1. **Mathematical Grounding:** Posterior probabilities are calculated deterministically via math, never through LLM text or estimations.
2. **Critical Trust-Tier & Synthetic Provenance Invariants:**
   - Unconfirmed T6 findings are **strictly excluded** from participating in Bayesian updates.
   - Synthetic-provenance findings (e.g. from synthetic extractors, synthetic labels, or reference datasets) are **strictly barred from influencing scores**, even if assigned a high trust tier (T1) or confirmed by a clinician.
   - Only eligible, non-synthetic clinical evidence can affect Bayesian scores.
3. **Correlated Evidence Grouping:** Findings belonging to a shared `finding_group` (such as `cbc_dengue_pattern`) use a single combined likelihood ratio (or the single strongest LR), preventing naive Bayesian double-counting.
4. **Direction Agreement Safeguards:** Evidence claims where the verifier verdict direction disagrees with the likelihood ratio direction (e.g. proposing 'supports' when LR < 1) default to $LR = 1.0$ (no score change) and flag the KB entry for clinical review.
5. **Must-Not-Miss Condition Visibility:** Must-not-miss conditions remain independently tracked and visible regardless of how low their posterior probability scores rank.
6. **Full Calculation Provenance:** Every score update retains a detailed `LRTrailEntry` history preserving finding IDs, applied LRs, KB entry IDs, and verification verdict IDs.

---

## 2. Files Created and Modified

### New Modules Created in `src/reasoning/`:
- `src/reasoning/bayes.py`: Pure deterministic mathematical primitives:
  - `prob_to_odds(p)`: Converts prior probability to odds: $\text{odds} = \frac{p}{1 - p}$.
  - `odds_to_prob(odds)`: Converts odds to probability: $p = \frac{\text{odds}}{1 + \text{odds}}$.
  - `prob_to_log_odds(p)` and `log_odds_to_prob(log_odds)`: Numerically stable sigmoid and logit conversions.
  - `update_odds(prior_odds, lr)`: Updates odds with a single likelihood ratio: $\text{posterior\_odds} = \text{prior\_odds} \times LR$.
  - `sequential_bayes_update(prior, lrs)`: Multi-step sequential Bayesian update returning final odds, final probability, and step-by-step intermediate probabilities.
- `src/reasoning/scorer.py`: High-level Bayesian scoring engine:
  - `ScoreResult`: Pydantic result model holding hypothesis ID, must-not-miss status, prior, $p_{\text{raw}}$, $p_{\text{calibrated}}$, clinical probability `Band`, `lr_trail`, and flagged KB entries.
  - `assign_band(prob)`: Maps probabilities to clinical bands (`HIGH` $\ge 0.50$, `MODERATE` $0.20-0.49$, `LOW` $0.05-0.19$, `VERY_LOW` $< 0.05$).
  - `clip_if_expert_opinion(lr, quality)`: Clamps weak expert-opinion LRs to $[0.5, 2.0]$.
  - `score_hypothesis(hypothesis, view, kb)`: Scores a candidate hypothesis against verified findings in the CaseView.
  - `score_all_hypotheses(view, kb)`: Evaluates all candidates in the CaseView, returning ranked scored results and unscored candidates.

### Modified Files:
- `src/reasoning/__init__.py`: Exported Bayesian mathematical and scoring interfaces.

### New Test Suite:
- `tests/test_stage5_bayes.py`: 16 comprehensive unit and integration tests covering probability/odds conversions, numerical stability, sequential updates, T6 exclusion, synthetic provenance exclusion, golden worked-example parity, correlated finding groups, direction disagreements, and must-not-miss visibility.

---

## 3. Mathematical Parity with Golden Worked Example (Synthetic Demonstration)

The engine achieves exact parity with `docs/07-reasoning-and-scoring.md` Part C and `eval/golden/worked-example.json` (all values are synthetic demonstration values):

### Patient Encounter (Synthetic Benchmark Case):
Adult presenting with acute undifferentiated fever (4 days), retro-orbital pain, thrombocytopenia (platelets 45), and leukopenia (WBC 3.2).

### Calculation Trace for Dengue Fever:
1. **Prior:** $p_0 = 0.20 \implies \text{prior\_odds} = \frac{0.20}{0.80} = 0.25$ (illustrative benchmark prior).
2. **Correlated CBC Pattern:** Thrombocytopenia (`f-07`) + Leukopenia (`f-08`) in `cbc_dengue_pattern` $\implies$ combined $LR = 4.0$ (not $3.0 \times 2.0 = 6.0$).  
   $\text{odds}_1 = 0.25 \times 4.0 = 1.00$.
3. **Retro-orbital Pain:** `f-02` with $LR^+ = 1.50$.  
   $\text{odds}_2 = 1.00 \times 1.50 = 1.50$.
4. **Posterior Probability:**  
   $$p_{\text{raw}} = \frac{1.50}{1 + 1.50} = \mathbf{0.60} \quad (60\%)$$
5. **Clinical Band:** `Band.HIGH` (unvalidated demonstration band).

This test passed with exact precision in `test_golden_worked_example_parity`.

---

## 4. Test Suite Execution Output

The complete prototype test suite across all five stages was executed:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\DELL\Desktop\prototype of madd
plugins: anyio-4.15.1, asyncio-0.26.0
collected 99 items

tests/test_schemas.py (8 tests) ........................................ PASSED [  8%]
tests/test_stage1_sample.py (17 tests) ................................. PASSED [ 25%]
tests/test_stage2_extractor.py (9 tests) ............................... PASSED [ 34%]
tests/test_stage2_models.py (16 tests) ................................. PASSED [ 51%]
tests/test_stage3_case_graph.py (15 tests) ............................. PASSED [ 66%]
tests/test_stage4_verifiers.py (18 tests) .............................. PASSED [ 84%]
tests/test_stage5_bayes.py (16 tests):
  test_prob_odds_round_trip ............................................ PASSED [ 85%]
  test_invalid_priors_rejected ......................................... PASSED [ 86%]
  test_invalid_odds_and_lrs_rejected ................................... PASSED [ 87%]
  test_numerical_stability_extremes .................................... PASSED [ 88%]
  test_sequential_bayes_updates ........................................ PASSED [ 89%]
  test_neutral_lr_leaves_score_unchanged ............................... PASSED [ 90%]
  test_lr_directional_effects .......................................... PASSED [ 91%]
  test_reproducibility ................................................. PASSED [ 92%]
  test_expert_opinion_clipping ......................................... PASSED [ 93%]
  test_probability_band_assignment ..................................... PASSED [ 94%]
  test_t6_findings_strictly_excluded_from_scoring ...................... PASSED [ 95%]
  test_synthetic_provenance_finding_excluded_even_if_t1_confirmed ...... PASSED [ 96%]
  test_confirmed_t1_finding_moves_score ................................ PASSED [ 97%]
  test_golden_worked_example_parity .................................... PASSED [ 98%]
  test_must_not_miss_remains_visible_regardless_of_low_score ........... PASSED [ 99%]
  test_missing_prior_goes_to_unscored .................................. PASSED [100%]

======================== 99 passed, 1 warning in 2.51s ========================
```

- **Stage 1**: 25 tests PASSED
- **Stage 2**: 25 tests PASSED
- **Stage 3**: 15 tests PASSED
- **Stage 4**: 18 tests PASSED
- **Stage 5**: 16 tests PASSED
- **Total**: **99 / 99 PASSED (100% success rate)**

---

## 5. Safety Checks & Limitations

- **Research Demonstration Only:** This module demonstrates deterministic Bayesian updating over synthetic patient data and illustrative KB likelihood ratios. It is **not** approved for real clinical decision-making.
- **T6 Barrier:** Unconfirmed findings cannot move scores.
- **No Autonomous Ranking:** The system computes mathematically derived probabilities to support human clinician differential diagnosis; it does not declare a definitive diagnosis or suggest treatment.
- **Calibration Status:** Baseline calibration is currently an identity map ($p_{\text{calibrated}} = p_{\text{raw}}$). Real clinical deployment requires fitting isotonic regression or Platt scaling on an empirical tuning set.

---

## 6. Confirmation of Project Integrity

- **Original Project Untouched**: `C:\Users\DELL\Desktop\Mini project\Medagents\medagents` remains strictly read-only and unmodified.
- **Stage 1–4 Files Preserved**: All schemas, sample datasets, extractor logic, event store architecture, and verification dispatchers remain intact.
- **No Early Stage 6 Progression**: No API, UI screens, or treatment planners were implemented.
