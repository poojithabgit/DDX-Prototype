# Medagents Prototype — Stage 3 Final Architecture & Safety Review

**Date:** 2026-11-17  
**Stage:** Stage 3 — Case Graph (Shared Memory & Event Log)  
**Status:** FULLY APPROVED & IMPLEMENTED  
**Workspace:** `C:\Users\DELL\Desktop\prototype of madd`  
**Original Project:** `C:\Users\DELL\Desktop\Mini project\Medagents\medagents` (Strictly Unmodified / Read-Only)

---

## 1. Overview of Changes

Following the read-only safety inspection of the initial Stage 3 implementation, three targeted improvements were identified and applied to guarantee strict alignment with `docs/04-case-graph.md`, `docs/INTERFACES.md`, and clinical safety invariants.

### Fix 1: Clinician Identity Validation
- **Problem:** `GraphClient.confirm_finding()` previously accepted any string for `by`, which could allow an empty string `""` or whitespace `"   "`.
- **Solution:** Added explicit validation in `GraphClient.confirm_finding()`:
  ```python
  if not by or not by.strip():
      raise ValueError("Clinician identity 'by' is required and cannot be empty or whitespace.")
  ```
- **Safety Invariant:** Clinician attribution is mandatory for all Checkpoint 1 confirmation events. T6 trust tiers are never automatically promoted.

### Fix 2: Graph Edge Referential Validation
- **Problem:** `GraphClient.add_edge()` checked the edge type against the allowed vocabulary, but did not verify whether the referenced `src` and `dst` nodes existed in the encounter graph view.
- **Solution:**
  1. Extended `CaseView` with `claim_by_id()`, `verdict_by_id()`, and `has_node(node_id)` to check findings, hypotheses, claims, and verdicts.
  2. In `GraphClient.add_edge()`, added referential validation:
     - `src` node must exist in the active encounter view.
     - `dst` node must exist in the active encounter view, except for `derived_from` edges which can point to an external source document or FHIR resource ID as specified in `docs/04-case-graph.md` section 2.
- **Safety Invariant:** Prevents orphaned edges and illegal dangling relations.

### Fix 3: Addition of Targeted Tests
Four new test cases were added to `tests/test_stage3_case_graph.py`, expanding the test suite from 61 to 65 tests:
1. `test_empty_clinician_identity_rejected`: Verifies that empty strings, whitespace strings, and tabs/newlines are rejected with `ValueError`.
2. `test_duplicate_hypothesis_rejected`: Verifies that attempting to register an already existing hypothesis ID raises `ValueError`.
3. `test_replay_to_target_version`: Verifies that `store.replay(enc_id, target_version=K)` faithfully reconstructs the historical case state at version $K < N$.
4. `test_edge_source_and_destination_validation`: Verifies that edges between non-existent nodes are rejected, while allowing valid edges and `derived_from` source references.

---

## 2. Invariants and Architectural Guarantees

1. **Append-Only Immutability**:
   - `EventStore` only supports appending deep-copied `Event` instances and sequential replay. Events cannot be modified or deleted.
2. **Deterministic Time-Travel Replay**:
   - Replaying the immutable event sequence reconstructs an exact, frozen `CaseView` at any historical point.
3. **Partitioned Encounter Isolation**:
   - Every encounter maintains an isolated event log. Events from one patient encounter cannot bleed into or reference another.
4. **Monotonic Event Sequencing**:
   - Sequence numbering is strictly 1-based and monotonically increasing per encounter ($1, 2, \dots, N$). Out-of-order or duplicate sequence numbers are rejected.
5. **Optimistic Concurrency Control**:
   - Writers can specify `expected_version`. If a concurrent write has occurred, `StaleVersion` is raised, prompting the caller to re-read and retry.
6. **Role-Based Permission Enforcement**:
   - Writers are strictly bounded by the permissions matrix in `docs/04-case-graph.md` section 5. Unauthorized writes raise `PermissionDenied`.
7. **Schema Conformance**:
   - All written entities (`Finding`, `Hypothesis`, `Claim`, `Verdict`) are verified against draft 2020-12 JSON schemas before appending.
8. **Trust-Tier Safety Invariant**:
   - Synthetic unvalidated data extracted in Stage 2 enters at tier `T6` with `confirmation.status = "pending"`.
   - Clinician confirmation records the clinician identity and sets `status = "confirmed"`, but **never promotes the trust tier from T6**.
   - `Finding.can_move_scores()` evaluates to `False` for all T6 findings.
   - `CaseView.confirmed_findings()` returns only findings in tiers T1–T5 that are confirmed, completely barring T6 findings from participating in diagnostic scoring.

---

## 3. Test Suite Verification

The full test suite was executed across all three stages:
- **Stage 1 (Schema & Ingestion Sample)**: 25 tests
- **Stage 2 (Models & Finding Extractor)**: 25 tests
- **Stage 3 (Case Graph & Safety Invariants)**: 15 tests
- **Total**: 65 tests, **100% passing (65/65)** in 2.36s.

---

## 4. Current Limitations & Scope Boundary

- **Persistence Layer**: `EventStore` is currently an in-memory implementation partitioned by encounter. For production deployment, it maps directly to PostgreSQL tables (`events`, `nodes`, `edges`) as described in `docs/04-case-graph.md` section 6.
- **Downstream Capabilities**: As per scope instructions, Stage 3 does not include:
  - LLM hypothesis proposer calls (Stage 4).
  - Verifier implementations (Stage 4).
  - Bayesian likelihood ratio scoring (Stage 4).
  - Clinician UI or presentation screens (Stage 5).

---

## 5. Conclusion

Stage 3 is complete, verified, and adheres to all safety, architectural, and read-only constraints. All 65 tests pass. Ready for Stage 4 authorization.
