# Medagents Prototype — Stage 3 Completion Report (Updated)

**Date:** 2026-11-17  
**Stage:** Stage 3 — Case Graph (Shared Memory & Event Log)  
**Status:** COMPLETED & VERIFIED — 65 / 65 Tests Passing (100%)  
**Workspace:** `C:\Users\DELL\Desktop\prototype of madd`  
**Original Project:** `C:\Users\DELL\Desktop\Mini project\Medagents\medagents` (Strictly Unmodified / Read-Only)

---

## 1. Executive Summary

Stage 3 implementation provides the Case Graph architecture as specified in `docs/04-case-graph.md` and `docs/INTERFACES.md` section 3. The Case Graph serves as the auditable, append-only blackboard and shared memory for each patient encounter.

State changes are captured exclusively as immutable, sequenced events. The current case state is reconstructed dynamically by replaying events from sequence 1, guaranteeing full traceability, auditability, encounter isolation, and deterministic replay.

Following the read-only safety review, three targeted improvements were implemented and validated:
1. **Clinician identity validation**: Rejection of empty or whitespace-only clinician identities.
2. **Graph edge validation**: Validation of source and destination node existence in the active encounter view prior to appending edges.
3. **Missing test coverage**: Unit tests for empty clinician rejection, duplicate hypothesis prevention, historical replay (`target_version=K`), and graph edge referential validation.

All safety rules—specifically preventing automatic promotion of T6 trust-tier findings, barring unconfirmed findings from moving scores, enforcing writer permission boundaries, and eliminating benchmark diagnosis leaks—remain strictly enforced.

---

## 2. Files Created and Modified

### Prototype Workspace Files:
- `src/common/clock.py`: Injected `Clock` and `IdFactory` protocols with `FixedClock` and `DeterministicIdFactory`.
- `src/common/models.py`: `PatientContext`, `Edge`, and `Event` Pydantic models.
- `src/common/errors.py`: Exceptions including `PermissionDenied`, `StaleVersion`, `ImplausibleValue`, `CaseGraphError`, and `EventReplayError`.
- `src/graph/events.py`: `EventType` enum defining audit trail events (`CONTEXT_SET`, `FINDING_ADDED`, `FINDING_CONFIRMED`, `FINDING_REJECTED`, `FINDING_EDITED`, `HYPOTHESIS_ADDED`, `HYPOTHESIS_STATUS_CHANGED`, `HYPOTHESIS_RESCORED`, `CLAIM_ADDED`, `VERDICT_ADDED`, `EDGE_ADDED`).
- `src/graph/view.py`: `CaseView` immutable point-in-time snapshot with `has_node()`, `claim_by_id()`, `verdict_by_id()`, `confirmed_findings()`, `verdict_for()`, `top_hypotheses()`.
- `src/graph/store.py`: `EventStore` partitioned append-only event store with sequence verification, duplicate ID detection, and version-targeted event replay.
- `src/graph/client.py`: Scoped `GraphClient` with clinician identity validation, edge node referential checks, writer role permissions, schema validation, and optimistic concurrency.
- `src/graph/__init__.py`: Package export for graph modules.
- `tests/test_stage3_case_graph.py`: 15 integration and unit tests covering all Stage 3 requirements and safety improvements.
- `reports/stage3_completion_report.md`: Updated completion report.
- `reports/stage3_final_review.md`: Detailed review of changes and architectural invariants.

---

## 3. Case Graph Implementation Details

1. **Append-Only Event Store (`EventStore`)**:
   - Encounters are strictly isolated into distinct event streams.
   - Each event carries an `event_id`, `encounter_id`, strict 1-based monotonic `sequence`, ISO timestamp `at`, actor name/version `actor`, event `type`, `target`, `payload`, and optional before/after/because fields.
   - Concurrency control is supported via `expected_version`, raising `StaleVersion` if a race condition occurs.
2. **Deterministic Event Replay (`replay`)**:
   - State reconstruction replays the event log from sequence 1 up to any specified target version (`target_version=K`).
   - Reconstructed `CaseView` models are frozen/immutable.
3. **Role-Based Permission Matrix (`GraphClient`)**:
   - Enforces `docs/04-case-graph.md` section 5 write permissions:
     - Ingestion: May add `Finding` (T6/natural), and write `contradicts` / `derived_from` edges.
     - Checkpoint 1: May confirm or edit findings.
     - Proposer (LLM): May add hypotheses with `origin=LLM`, and add claims.
     - KB Lookup / MNM: May add hypotheses with `origin=KB` or `origin=MNM`.
     - Verifiers: May add `Verdict` records.
     - Scorer: May update scores on hypotheses (`update_scores`).
     - Planner: May add graph edges (`discriminates`, `rules_out`, `recommends`).
     - Clinician Checkpoint 2: May set hypothesis status (`confirmed_by_clinician`, `ruled_out`).
   - Unauthorized writes immediately raise `PermissionDenied`.
4. **Safety & T6 Invariant Enforcement**:
   - `confirm_finding()` requires non-empty clinician identity, marks a finding as `confirmed` or `edited`, but **never changes the trust tier from T6**.
   - `can_move_scores()` on findings remains `False` for T6 findings.
   - `CaseView.confirmed_findings()` strictly returns findings in tiers T1–T5 that are confirmed, guaranteeing that unconfirmed or synthetic T6 findings cannot participate in scoring.
   - Neither `reference_diagnoses` nor `differential_candidates` are ever ingested as clinical findings.

---

## 4. Event Types Implemented

| Event Type | Trigger Method | Key Payload / Fields |
| :--- | :--- | :--- |
| `CONTEXT_SET` | `set_context` | `PatientContext` (patient_id, age, sex, region, etc.) |
| `FINDING_ADDED` | `add_finding` | Serialized `Finding` (code, assertion, provenance, trust_tier=T6) |
| `FINDING_CONFIRMED` | `confirm_finding` | Updated `Finding` with `confirmation.status="confirmed"`, clinician ID, timestamp |
| `FINDING_EDITED` | `confirm_finding` (with edited) | Updated `Finding` with `confirmation.status="edited"`, original_value preserved |
| `HYPOTHESIS_ADDED` | `add_hypothesis` | `Hypothesis` (code, name, origin, must_not_miss, round) |
| `HYPOTHESIS_STATUS_CHANGED` | `set_hypothesis_status` | Status transition (e.g. `ruled_out`), reason |
| `HYPOTHESIS_RESCORED` | `update_scores` | Score fields (`prior`, `p_raw`, `p_calibrated`, `band`), `lr_trail`, `because` |
| `CLAIM_ADDED` | `add_claim` | `Claim` linking finding to hypothesis |
| `VERDICT_ADDED` | `add_verdict` | `Verdict` with result, verifier ID, citation/rule evidence |
| `EDGE_ADDED` | `add_edge` | `Edge` (type, src, dst, data) with node referential validation |

---

## 5. Test Suite Execution Results

All 65 tests across Stages 1, 2, and 3 passed:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\DELL\Desktop\prototype of madd
plugins: anyio-4.15.1, asyncio-0.26.0
collected 65 items

tests/test_schemas.py (8 tests) ........................................ PASSED [ 12%]
tests/test_stage1_sample.py (17 tests) ................................. PASSED [ 38%]
tests/test_stage2_extractor.py (9 tests) ............................... PASSED [ 52%]
tests/test_stage2_models.py (16 tests) ................................. PASSED [ 76%]
tests/test_stage3_case_graph.py (15 tests):
  test_event_appending_and_ordering .................................... PASSED [ 78%]
  test_replay_reconstructs_case_view ................................... PASSED [ 80%]
  test_encounter_isolation ............................................. PASSED [ 81%]
  test_t6_remains_t6_after_confirmation ................................ PASSED [ 83%]
  test_clinician_edited_finding ........................................ PASSED [ 84%]
  test_permission_matrix_enforcement ................................... PASSED [ 86%]
  test_duplicate_finding_rejected ...................................... PASSED [ 87%]
  test_invalid_finding_schema_rejected ................................. PASSED [ 89%]
  test_stale_version_rejected .......................................... PASSED [ 90%]
  test_full_graph_workflow ............................................. PASSED [ 92%]
  test_ingest_all_extracted_sample_findings_into_graph ................. PASSED [ 93%]
  test_empty_clinician_identity_rejected ............................... PASSED [ 95%]
  test_duplicate_hypothesis_rejected ................................... PASSED [ 96%]
  test_replay_to_target_version ........................................ PASSED [ 98%]
  test_edge_source_and_destination_validation .......................... PASSED [100%]

======================== 65 passed, 1 warning in 2.36s ========================
```

---

## 6. Confirmation of Project Integrity

- **Original Project Untouched**: The directory `C:\Users\DELL\Desktop\Mini project\Medagents\medagents` remains strictly read-only and unmodified.
- **Stage 1 & Stage 2 Work Preserved**: All schemas, sample datasets, mappings, extractor routines, and Stage 1 & 2 tests remain intact and verified.
- **No Early Stage 4 Progression**: No Bayesian scoring, LLM calls, disease ranking, or UI components have been implemented.

---

## 7. Next Steps

Stage 3 is complete, refined, and fully verified. Awaiting user review and authorization before proceeding to Stage 4.
