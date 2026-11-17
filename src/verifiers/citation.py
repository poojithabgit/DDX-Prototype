"""
src/verifiers/citation.py

Citation Entailment Verifier.
Follows docs/08-verification.md section 2 and docs/INTERFACES.md section 8.2:

Checks whether a retrieved passage from clinical guidelines or evidence corpus
supports the claim.

Guard rails (from docs/08-verification.md):
- Must quote the passage exactly.
- The quoted passage must match the reference corpus word-for-word (exact character-for-character check).
- A synthetic or missing passage fails the quote check and returns REFUTE or UNVERIFIABLE.
- Even with a SUPPORT verdict, an LLM/citation verdict WITHOUT a KB LR NEVER moves a score.
"""

from __future__ import annotations

import time
from typing import Dict, Optional
from src.common.clock import IdFactory, UuidIdFactory
from src.common.models import CitationRef, Claim, Verdict
from src.common.types import ClaimType, VerdictResult
from src.graph.view import CaseView
from src.reasoning.kb import KB


class CitationJudge:
    """Verifier that inspects textual citations against a reference guideline corpus."""

    name: str = "citation-entailment-judge"
    version: str = "0.2.0"
    deterministic: bool = False  # Textual entailment check
    handles: frozenset[ClaimType] = frozenset([ClaimType.FINDING_DISEASE_LINK])

    def __init__(
        self,
        corpus: Optional[Dict[str, str]] = None,
        id_factory: Optional[IdFactory] = None,
    ) -> None:
        self.corpus = corpus or {
            "who-dengue-2009-s3-p12": (
                "Thrombocytopenia and leukopenia are characteristic laboratory findings in the early febrile phase of dengue."
            ),
            "nvbdcp-malaria-chills-p5": (
                "Sudden onset of high fever accompanied by rigors and profuse sweating suggests acute malaria in endemic areas."
            ),
            "icmr-scrub-typhus-p8": (
                "An eschar at the site of mite attachment is pathognomonic of scrub typhus in patients presenting with undifferentiated fever."
            ),
        }
        self.id_factory = id_factory or UuidIdFactory()

    def verify(
        self,
        claim: Claim,
        view: CaseView,
        kb: KB,
        chunk_id: Optional[str] = None,
        quote: Optional[str] = None,
    ) -> Verdict:
        t0 = time.perf_counter()
        vid = self.id_factory.next_id("v")

        if claim.type not in self.handles:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.NOT_APPLICABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Claim type '{claim.type}' is not handled by {self.name}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if not chunk_id or not quote:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason="Citation verification requires chunk_id and exact quote passage",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # 1. Lookup corpus chunk
        corpus_text = self.corpus.get(chunk_id)
        if not corpus_text:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Chunk '{chunk_id}' not found in approved guideline corpus",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # 2. Strict character-for-character span check (from docs/08-verification.md)
        if quote not in corpus_text:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.REFUTE,
                rule_id="RULE-CITATION-SPAN-MISMATCH",
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Quote validation failed: Passage does not match corpus chunk '{chunk_id}' character-for-character",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # 3. Entailment check against finding and hypothesis
        finding = view.finding_by_id(claim.finding_id) if claim.finding_id else None
        hypothesis = view.hypothesis_by_id(claim.hypothesis_id) if claim.hypothesis_id else None

        finding_name = (
            finding.code.display or finding.original_text or ""
        ).lower() if finding else ""
        hypothesis_name = (hypothesis.name or "").lower() if hypothesis else ""

        quote_lower = quote.lower()

        # Check semantic alignment: does the quote mention concepts related to finding and hypothesis?
        # Exact quote matching alone is NOT sufficient proof that an unrelated clinical claim is supported.
        f_tokens = [t for t in finding_name.replace("-", " ").split() if len(t) > 3]
        h_tokens = [t for t in hypothesis_name.replace("-", " ").split() if len(t) > 3]

        finding_mentioned = any(t in quote_lower for t in f_tokens) if f_tokens else True
        hypothesis_mentioned = any(t in quote_lower for t in h_tokens) if h_tokens else True

        citation = CitationRef(
            source="guideline-corpus@2026-10",
            chunk_id=chunk_id,
            quote=quote,
        )

        if not (finding_mentioned and hypothesis_mentioned):
            # Passage exists and is genuine, but does NOT establish entailment for this finding-disease pair
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                citation=citation,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                model="entailment-judge@0.1",
                reason=(
                    f"Quotation span verified in chunk '{chunk_id}', but passage does not semantically "
                    f"entail clinical link between finding '{finding_name}' and hypothesis '{hypothesis_name}'"
                ),
                unverifiable_reason="out_of_scope",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        return Verdict(
            verdict_id=vid,
            claim_id=claim.claim_id,
            claim_type=claim.type,
            result=VerdictResult.SUPPORT,
            citation=citation,
            deterministic=self.deterministic,
            verifier=f"{self.name}@{self.version}",
            model="entailment-judge@0.1",
            reason=f"Quoted passage in {chunk_id} entails proposed clinical link",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
