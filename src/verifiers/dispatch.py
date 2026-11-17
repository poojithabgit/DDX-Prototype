"""
src/verifiers/dispatch.py

Targeted Verifier Dispatcher and Verdict Cache.
Follows docs/INTERFACES.md section 8.3 and docs/08-verification.md section 3 & 4.

Dispatches claims to appropriate verifiers by claim type:
- FINDING_DISEASE_LINK -> KBLinkChecker (fallback to CitationJudge if no entry)
- LAB_INTERPRETATION   -> LabInterpreterVerifier
- MNM_STATUS           -> MNMChecker
- FACT_CONSISTENCY     -> ConsistencyChecker

Disagreement and Arbitration Rules (docs/08-verification.md section 4):
- Deterministic result wins over LLM-judged result.
- Two LLM judges disagree -> UNVERIFIABLE.
- Disagreement between verdict direction and KB LR -> flag KB entry for review, LR = 1.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Dict, List, Optional, Tuple
from src.common.models import Claim, Verdict
from src.common.types import ClaimType, VerdictResult
from src.graph.view import CaseView
from src.reasoning.kb import KB
from src.verifiers.base import Verifier

logger = logging.getLogger(__name__)


class VerdictCache:
    """In-memory cache for claim verification results.

    Cached deterministically by:
    - Claim content (claim_id, type, finding_id, hypothesis_id, relation, round)
    - Relevant Finding state (value, unit, interpretation, assertion, confirmation, provenance)
    - Relevant Hypothesis state (name, status, origin, round)
    - Case Graph version
    - Knowledge Base version
    - Verifier name and version
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Verdict] = {}

    def _hash_entity(self, entity_data: dict) -> str:
        s = json.dumps(entity_data, sort_keys=True, default=str)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

    def _make_key(
        self,
        claim: Claim,
        view: CaseView,
        kb_version: str,
        verifier_name: str,
        verifier_version: str,
    ) -> str:
        # 1. Claim hash
        claim_data = claim.model_dump(mode="json")
        claim_hash = self._hash_entity(claim_data)

        # 2. Finding state hash (if referenced)
        finding = view.finding_by_id(claim.finding_id) if claim.finding_id else None
        finding_hash = self._hash_entity(finding.model_dump(mode="json")) if finding else "none"

        # 3. Hypothesis state hash (if referenced)
        hypothesis = view.hypothesis_by_id(claim.hypothesis_id) if claim.hypothesis_id else None
        hypothesis_hash = self._hash_entity(hypothesis.model_dump(mode="json")) if hypothesis else "none"

        # 4. Overall composite key
        return (
            f"claim:{claim_hash}|"
            f"find:{finding_hash}|"
            f"hyp:{hypothesis_hash}|"
            f"gver:{view.version}|"
            f"kb:{kb_version}|"
            f"v:{verifier_name}:{verifier_version}"
        )

    def get(
        self,
        claim: Claim,
        view: CaseView,
        kb_version: str,
        verifier_name: str,
        verifier_version: str,
    ) -> Optional[Verdict]:
        key = self._make_key(claim, view, kb_version, verifier_name, verifier_version)
        return self._cache.get(key)

    def set(
        self,
        claim: Claim,
        view: CaseView,
        kb_version: str,
        verifier_name: str,
        verifier_version: str,
        verdict: Verdict,
    ) -> None:
        key = self._make_key(claim, view, kb_version, verifier_name, verifier_version)
        self._cache[key] = verdict

    def clear(self) -> None:
        self._cache.clear()


def dispatch(
    claims: List[Claim],
    verifiers: List[Verifier],
    view: CaseView,
    kb: KB,
    cache: Optional[VerdictCache] = None,
) -> List[Verdict]:
    """Route claims to relevant verifiers and arbitrate disagreements.

    Follows docs/INTERFACES.md section 8.3:
    dispatch(claims, verifiers, view, kb, cache) -> list[Verdict]
    """
    results: List[Verdict] = []
    verdict_cache = cache or VerdictCache()

    for claim in claims:
        candidate_verdicts: List[Verdict] = []

        for verifier in verifiers:
            # Check if verifier handles this claim type
            if claim.type not in verifier.handles:
                continue

            # Check cache
            cached = verdict_cache.get(claim, view, kb.version, verifier.name, verifier.version)
            if cached is not None:
                candidate_verdicts.append(cached)
                continue

            # Execute verifier
            try:
                verdict = verifier.verify(claim, view, kb)
            except Exception as exc:
                logger.error("Verifier %s failed on claim %s: %s", verifier.name, claim.claim_id, exc)
                # Tool failure -> UNVERIFIABLE (docs/INTERFACES.md section 8.2)
                verdict = Verdict(
                    verdict_id=f"v-err-{claim.claim_id}",
                    claim_id=claim.claim_id,
                    claim_type=claim.type,
                    result=VerdictResult.UNVERIFIABLE,
                    deterministic=verifier.deterministic,
                    verifier=f"{verifier.name}@{verifier.version}",
                    reason=f"Verifier error: {exc}",
                    unverifiable_reason="tool_unavailable",
                )

            # Store in cache
            verdict_cache.set(claim, view, kb.version, verifier.name, verifier.version, verdict)
            candidate_verdicts.append(verdict)

        if not candidate_verdicts:
            # No verifier available for this claim type
            verdict = Verdict(
                verdict_id=f"v-na-{claim.claim_id}",
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.NOT_APPLICABLE,
                deterministic=True,
                verifier="dispatcher@0.1.0",
                reason=f"No active verifier handles claim type '{claim.type.value}'",
            )
            results.append(verdict)
            continue

        # Arbitrate disagreements (docs/08-verification.md section 4)
        # Rule 1: If both deterministic and non-deterministic ran, deterministic wins.
        det_verdicts = [v for v in candidate_verdicts if v.deterministic and v.result != VerdictResult.NOT_APPLICABLE]
        non_det_verdicts = [v for v in candidate_verdicts if not v.deterministic and v.result != VerdictResult.NOT_APPLICABLE]

        if det_verdicts:
            # Deterministic verdict wins
            primary = det_verdicts[0]
            if non_det_verdicts and non_det_verdicts[0].result != primary.result:
                logger.warning(
                    "Deterministic vs LLM disagreement on claim %s: deterministic=%s vs llm=%s. Using deterministic.",
                    claim.claim_id, primary.result.value, non_det_verdicts[0].result.value
                )
            results.append(primary)
        elif non_det_verdicts:
            # Only non-deterministic verifiers
            if len(non_det_verdicts) > 1 and non_det_verdicts[0].result != non_det_verdicts[1].result:
                # Two LLM judges disagree -> UNVERIFIABLE
                arb_verdict = Verdict(
                    verdict_id=f"v-disagree-{claim.claim_id}",
                    claim_id=claim.claim_id,
                    claim_type=claim.type,
                    result=VerdictResult.UNVERIFIABLE,
                    deterministic=False,
                    verifier="dispatcher@0.1.0",
                    reason="Judges disagreed on claim verification outcome",
                    unverifiable_reason="judges_disagree",
                )
                results.append(arb_verdict)
            else:
                results.append(non_det_verdicts[0])
        else:
            results.append(candidate_verdicts[0])

    return results
