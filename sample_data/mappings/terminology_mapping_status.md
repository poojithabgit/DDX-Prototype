# Medical Terminology Mapping Status Report

**Project:** Agentic Differential Diagnosis System (`Medagents`)  
**Phase:** Phase 2 — Medical Terminology Mapping Preparation  
**Generated Date:** November 2026  
**Status:** Complete — Pending Clinician Lead Review

---

## 1. Executive Summary

In Phase 2, all 57 clinical symptom codes, 13 laboratory investigations, and 20 diagnostic condition codes were audited and mapped against authoritative international terminology standards:
- **SNOMED CT International Edition** (for symptoms, clinical signs, and disorder concepts)
- **Regenstrief LOINC & Unified Code for Units of Measure (UCUM)** (for laboratory test codes and standard units)
- **WHO ICD-10 & CDC ICD-10-CM** (for diagnostic classification, explicitly distinguishing international WHO codes from US Clinical Modifications)

Strict rules were enforced: no approximate matches were automatically approved, unmapped concepts were preserved with justification, and concepts with ambiguity or context-loss were flagged as **provisional** for clinical lead sign-off.

---

## 2. High-Level Mapping Statistics

| Domain | Total Inspected | Verified | Provisional | Unmapped | Primary Target Terminology |
|:---|:---:|:---:|:---:|:---:|:---|
| **Symptoms & Findings** | 57 | 50 | 5 | 2 | SNOMED CT International Edition |
| **Laboratory Tests** | 13 | 13 | 0 | 0 | Regenstrief LOINC / UCUM |
| **Diagnostic Conditions** | 20 | 15 | 5 | 0 | WHO ICD-10 / ICD-10-CM / SNOMED CT |
| **TOTAL** | **90** | **78** | **10** | **2** | — |

- **Overall Verification Rate:** 78/90 (86.7%)
- **Provisional (Requires Review):** 10/90 (11.1%)
- **Unmapped (Missing Clinical Detail):** 2/90 (2.2%)

---

## 3. Authoritative Sources Used

1. **SNOMED CT International Edition:** SNOMED International Browser (release 2024–2026), NLM UTS.
2. **Regenstrief LOINC (v2.77+):** Official LOINC search database (`loinc.org`).
3. **Unified Code for Units of Measure (UCUM):** Regenstrief / UCUM specification.
4. **World Health Organization (WHO) ICD-10:** Official WHO International Classification of Diseases (2019/2016).
5. **CDC / CMS ICD-10-CM:** US National Center for Health Statistics Clinical Modification (2024–2026).

---

## 4. Concepts Requiring Manual Clinical Review

### A. Unmapped Concepts (2 items)
These concepts cannot be assigned standard codes without inventing medical information:
1. **`SYM-0014` (`family_history_positive`):**
   - *Reason:* Unspecified family history. In SNOMED CT, family history requires context (e.g. family history of diabetes, hypertension, cardiovascular disease). Mapping to an arbitrary disease is clinically invalid.
   - *Action for Clinician Lead:* Confirm whether this finding should be mapped to the generic `57177007` (*Family history of disorder*) or linked to specific comorbidities from `medical_history`.
2. **`SYM-0056` (`weight_change`):**
   - *Reason:* The direction of weight change is unspecified (weight loss vs weight gain). In SNOMED CT, involuntary weight loss (`89362005`) has high diagnostic significance for TB and malignancy, whereas weight gain (`8943002`) indicates fluid retention or metabolic changes.
   - *Action for Clinician Lead:* Clarify whether the clinical questionnaire recorded gain or loss.

### B. Provisional Concepts (11 items)

#### Symptoms (5 items):
1. **`SYM-0016` (`feeling_on_edge`):** Mapped provisionally to SNOMED `247926002` (*Feeling nervous*). Colloquial psych/somatic term; requires clinical confirmation.
2. **`SYM-0028` (`lower_abdominal_discomfort`):** Mapped provisionally to SNOMED `247355005` (*Lower abdominal pain*). Discomfort vs pain distinction needs clinical signoff.
3. **`SYM-0029` (`mild_wheeze`):** Mapped provisionally to base finding SNOMED `56018004` (*Wheezing*). The severity qualifier (*mild*) was stripped to avoid non-standard post-coordination.
4. **`SYM-0036` (`neck_tension`):** Mapped provisionally to SNOMED `249940004` (*Muscle tension*). Must be confirmed whether this represents meningeal neck stiffness (`271681002`) or cervical musculotendinous strain.
5. **`SYM-0052` (`upper_abdominal_discomfort`):** Mapped provisionally to SNOMED `247354009` (*Epigastric pain*). Discomfort vs pain nuance requires signoff.

#### Conditions (6 items):
1. **`SYN-013` (`iron_deficiency_pattern`):** Mapped provisionally to WHO ICD-10 `D50.9` and SNOMED `87522002` (*Iron deficiency anemia*). Term says *pattern* rather than confirmed anemia diagnosis.
2. **`SYN-014` (`type2_diabetes_followup`):** Mapped provisionally to WHO ICD-10 `E11.9` / ICD-10-CM `E11.9` (primary disease) with encounter code `Z09`. Combines chronic disease with followup encounter status.
3. **`SYN-015` (`hypertension_followup`):** Mapped provisionally to WHO ICD-10 `I10` / ICD-10-CM `I10` with encounter code `Z09`.
4. **`SYN-018` (`anxiety_symptom_episode`):** Mapped provisionally to WHO ICD-10 `F41.9` and SNOMED `197480006` (*Anxiety state*). Specifies *symptom episode* rather than confirmed disorder.
5. **`SYN-019` (`osteoarthritis_pattern`):** Mapped provisionally to WHO ICD-10 `M19.9` and SNOMED `396275006` (*Osteoarthritis*). Term says *pattern*; anatomic site is unspecified.
6. **`SYN-020` (`nonspecific_fatigue`):** Mapped to WHO ICD-10 `R53` / ICD-10-CM `R53.83` / SNOMED `84229001`. Documented as a symptom/sign code rather than definitive etiology.

---

## 5. WHO ICD-10 vs ICD-10-CM Documentation

For Indian clinical settings, **WHO ICD-10** is the recommended international standard for hospital morbidity reporting. Significant divergences between WHO ICD-10 and ICD-10-CM were identified and recorded:

| Condition Code | Condition Name | WHO ICD-10 Code & Display | ICD-10-CM Code & Display | Clinical Divergence Note |
|:---|:---|:---|:---|:---|
| `SYN-005` | `asthma_exacerbation` | **`J45.9`** (*Asthma, unspecified*) | **`J45.901`** (*Unspecified asthma with acute exacerbation*) | ICD-10-CM provides a dedicated 6-character exacerbation code (`J45.901`); WHO ICD-10 stops at 4 characters (`J45.9`). |
| `SYN-006` | `allergic_rhinitis` | **`J30.4`** (*Allergic rhinitis, unspecified*) | **`J30.9`** (*Allergic rhinitis, unspecified*) | WHO uses `J30.4`; US CM uses `J30.9`. |
| `SYN-009` | `migraine` | **`G43.9`** (*Migraine, unspecified*) | **`G43.909`** (*Migraine without status migrainosus*) | ICD-10-CM has 6-character granularity. |
| `SYN-010` | `tension_type_headache` | **`G44.2`** (*Tension-type headache*) | **`G44.209`** (*Tension-type headache, not intractable*) | ICD-10-CM has 6-character granularity. |
| `SYN-012` | `acute_low_back_pain` | **`M54.5`** (*Low back pain*) | **`M54.50`** (*Low back pain, unspecified*) | ICD-10-CM split M54.5 into M54.50, M54.51, M54.59 in 2021; WHO remains M54.5. |
| `SYN-020` | `nonspecific_fatigue` | **`R53`** (*Malaise and fatigue*) | **`R53.83`** (*Other fatigue*) | ICD-10-CM adds 5th character subclassification. |

---

## 6. Generated Files in `medagents/data sets/mappings/`

1. [symptoms_snomed_mapping.csv](file:///c:/Users/DELL/Desktop/Mini project/Medagents/medagents/data%20sets/mappings/symptoms_snomed_mapping.csv) (57 rows, 9 columns)
2. [labs_loinc_mapping.csv](file:///c:/Users/DELL/Desktop/Mini project/Medagents/medagents/data%20sets/mappings/labs_loinc_mapping.csv) (13 rows, 10 columns)
3. [conditions_icd10_snomed_mapping.csv](file:///c:/Users/DELL/Desktop/Mini project/Medagents/medagents/data%20sets/mappings/conditions_icd10_snomed_mapping.csv) (20 rows, 13 columns)
4. [terminology_mapping_status.md](file:///c:/Users/DELL/Desktop/Mini project/Medagents/medagents/data%20sets/mappings/terminology_mapping_status.md) (Full audit and governance report)

Phase 2 is complete. Original files and schemas remain 100% unaltered.
