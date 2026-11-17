"""
src/reasoning/kb.py

Read-only Knowledge Base (KB) for Medagents.
Holds curated medical knowledge (likelihood ratios, priors, must-not-miss entries, reference ranges).
Follows docs/05-knowledge-base.md and docs/INTERFACES.md section 6:
- The KB is strictly read-only at runtime.
- Numbers come only from reviewed sources.
- No write method is exposed.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.common.models import ClinicalCode, LREntry, LREntrySource
from src.common.types import LRQuality, LRSourceType


class MNMEntry(BaseModel):
    """Must-not-miss condition rule entry."""
    model_config = {"extra": "forbid"}

    condition: str
    complaint: str
    alert_threshold: float = Field(..., ge=0.0, le=1.0)
    red_flag_findings: List[str]
    rule_out_tests: List[str]


class KB(BaseModel):
    """Knowledge Base containing reviewed clinical reasoning rules and likelihood ratios."""
    model_config = {"extra": "forbid"}

    version: str = "kb-0.1.0"
    is_provisional_placeholder: bool = Field(
        True,
        description="Explicit flag: Current entries are illustrative/provisional placeholders from documentation, not approved clinical ground-truth."
    )
    status_label: str = Field(
        "PROVISIONAL_ILLUSTRATIVE_BENCHMARK",
        description="Safety label prohibiting presentation as independently validated clinical values."
    )
    lr_entries: List[LREntry] = Field(default_factory=list)
    mnm_entries: List[MNMEntry] = Field(default_factory=list)
    priors_table: Dict[str, float] = Field(default_factory=dict)

    @classmethod
    def create_default(cls) -> "KB":
        """Construct the reference clinical knowledge base for adult acute fever in India."""
        # 1. Likelihood ratios based on golden evaluation and clinical literature (docs/05-knowledge-base.md)
        lrs = [
            # Dengue: Thrombocytopenia
            LREntry(
                id="lr-dengue-thrombocytopenia",
                disease=ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
                finding=ClinicalCode(system="SNOMED-CT", code="307077003", display="Thrombocytopenia"),
                finding_group="cbc_dengue_pattern",
                lr_positive=3.0,
                lr_negative=0.5,
                population="adults with acute fever, endemic area, outpatient",
                source=LREntrySource(
                    type=LRSourceType.SYSTEMATIC_REVIEW,
                    citation="WHO Dengue Guidelines for Diagnosis, Treatment, Prevention and Control 2009",
                ),
                quality=LRQuality.HIGH,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
            # Dengue: Leukopenia
            LREntry(
                id="lr-dengue-leukopenia",
                disease=ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
                finding=ClinicalCode(system="SNOMED-CT", code="84828003", display="Leukopenia"),
                finding_group="cbc_dengue_pattern",
                lr_positive=2.0,
                lr_negative=0.6,
                population="adults with acute fever, endemic area, outpatient",
                source=LREntrySource(
                    type=LRSourceType.SYSTEMATIC_REVIEW,
                    citation="WHO Dengue Guidelines 2009",
                ),
                quality=LRQuality.HIGH,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
            # Dengue: Retro-orbital pain
            LREntry(
                id="lr-dengue-retro-orbital-pain",
                disease=ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
                finding=ClinicalCode(system="SNOMED-CT", code="386661006", display="Retro-orbital pain"),
                lr_positive=1.5,
                lr_negative=0.7,
                population="adults with acute fever",
                source=LREntrySource(
                    type=LRSourceType.RATIONAL_CLINICAL,
                    citation="JAMA Rational Clinical Examination: Does this patient have dengue?",
                ),
                quality=LRQuality.MODERATE,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
            # Dengue: Fever
            LREntry(
                id="lr-dengue-fever",
                disease=ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
                finding=ClinicalCode(system="SNOMED-CT", code="386661006", display="Fever"),
                lr_positive=1.8,
                lr_negative=0.1,
                population="adults with acute fever",
                source=LREntrySource(
                    type=LRSourceType.SYSTEMATIC_REVIEW,
                    citation="National Guidelines for Clinical Management of Dengue Fever, NVBDCP",
                ),
                quality=LRQuality.HIGH,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
            # Malaria: Fever with chills / rigors
            LREntry(
                id="lr-malaria-chills",
                disease=ClinicalCode(system="SNOMED-CT", code="85940003", display="Malaria"),
                finding=ClinicalCode(system="SNOMED-CT", code="43724002", display="Chill"),
                lr_positive=2.2,
                lr_negative=0.4,
                population="adult acute fever",
                source=LREntrySource(
                    type=LRSourceType.SYSTEMATIC_REVIEW,
                    citation="NVBDCP Malaria Treatment Guidelines",
                ),
                quality=LRQuality.HIGH,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
            # Scrub typhus: Eschar
            LREntry(
                id="lr-scrub-typhus-eschar",
                disease=ClinicalCode(system="SNOMED-CT", code="17160007", display="Scrub typhus"),
                finding=ClinicalCode(system="SNOMED-CT", code="271809000", display="Eschar"),
                lr_positive=15.0,
                lr_negative=0.6,
                population="acute fever in endemic rural India",
                source=LREntrySource(
                    type=LRSourceType.STUDY,
                    citation="Clinical Profile and Predictors of Mortality in Scrub Typhus",
                ),
                quality=LRQuality.HIGH,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
            # Leptospirosis: Paddy field / occupational water exposure
            LREntry(
                id="lr-leptospirosis-exposure",
                disease=ClinicalCode(system="SNOMED-CT", code="23502006", display="Leptospirosis"),
                finding=ClinicalCode(system="SNOMED-CT", code="224363007", display="Flood water exposure"),
                lr_positive=2.0,
                lr_negative=0.5,
                population="adults with acute fever in monsoon",
                source=LREntrySource(
                    type=LRSourceType.STUDY,
                    citation="Epidemiology and Clinical Manifestations of Leptospirosis in India",
                ),
                quality=LRQuality.MODERATE,
                reviewed_by=["clinical-lead-01", "clinical-reviewer-02"],
                version="kb-0.1.0",
            ),
        ]

        # 2. Must-not-miss list for acute undifferentiated fever
        mnm = [
            MNMEntry(
                condition="Severe dengue",
                complaint="acute_fever",
                alert_threshold=0.15,
                red_flag_findings=[
                    "Hypotension", "Severe abdominal pain", "Persistent vomiting",
                    "Mucosal bleeding", "Lethargy",
                ],
                rule_out_tests=["Repeat haematocrit and platelets", "Serial blood pressure"],
            ),
            MNMEntry(
                condition="Severe malaria",
                complaint="acute_fever",
                alert_threshold=0.10,
                red_flag_findings=[
                    "Altered sensorium", "Jaundice", "Seizures", "Severe anaemia",
                ],
                rule_out_tests=["Peripheral blood smear", "Malaria rapid diagnostic test"],
            ),
            MNMEntry(
                condition="Bacterial sepsis",
                complaint="acute_fever",
                alert_threshold=0.10,
                red_flag_findings=[
                    "Hypotension", "Tachypnea", "Altered mental status", "Oliguria",
                ],
                rule_out_tests=["Blood cultures", "Serum lactate"],
            ),
            MNMEntry(
                condition="Bacterial meningitis",
                complaint="acute_fever",
                alert_threshold=0.05,
                red_flag_findings=[
                    "Neck stiffness", "Altered sensorium", "Seizures", "Purpuric rash",
                ],
                rule_out_tests=["Lumbar puncture CSF analysis"],
            ),
        ]

        # 3. Base epidemiological priors
        priors = {
            "Dengue fever": 0.20,
            "Scrub typhus": 0.06,
            "Leptospirosis": 0.04,
            "Malaria": 0.08,
            "Enteric fever": 0.05,
            "Bacterial sepsis": 0.02,
        }

        return cls(lr_entries=lrs, mnm_entries=mnm, priors_table=priors)

    def lr_for_finding_disease(
        self,
        disease_name_or_code: str,
        finding_code_or_name: str,
    ) -> Optional[LREntry]:
        """Lookup likelihood ratio entry matching disease and finding."""
        d_norm = disease_name_or_code.strip().lower()
        f_norm = finding_code_or_name.strip().lower()

        for entry in self.lr_entries:
            d_match = (
                entry.disease.code.lower() == d_norm or
                entry.disease.display.lower() == d_norm or
                d_norm in entry.disease.display.lower()
            )
            f_match = (
                entry.finding.code.lower() == f_norm or
                entry.finding.display.lower() == f_norm or
                f_norm in entry.finding.display.lower()
            )
            if d_match and f_match:
                return entry
        return None

    def must_not_miss(self, complaint: str = "acute_fever") -> List[MNMEntry]:
        """Return must-not-miss entries for presenting complaint."""
        return [m for m in self.mnm_entries if m.complaint.lower() == complaint.lower()]

    def is_must_not_miss_condition(self, condition_name: str) -> bool:
        """Check if condition is in the must-not-miss catalog."""
        c_norm = condition_name.strip().lower()
        for m in self.mnm_entries:
            if m.condition.lower() == c_norm or c_norm in m.condition.lower():
                return True
        return False
