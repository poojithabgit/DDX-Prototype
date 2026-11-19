# Phase 0 – Document Review (Updated)

## 1. Trust‑tier inconsistency

**Source – `docs/ARCHITECTURE.md`**
- Section *"4. Trust tiers (how much each kind of fact is believed)"* defines tiers T1‑T6 (lines 158‑166). The table lists:
  - T1 – Confirmed by clinician (history, exam)
  - T2 – Lab result from the LIS (electronic)
  - T3 – Radiologist's report
  - T4 – OCR lab value **after** clinician confirmation
  - T5 – Imaging model output (after OOD check)
  - T6 – Unconfirmed LLM extraction, OCR or ASR (cannot move scores)
- In the narrative description of **Stage 3: Human checkpoint 1** the document says:
  > *"After confirmation: the transcript facts become **T1**, the OCR lab values become **T4**"* (lines 61‑64).
  This refers to the **current data flow** for the fever‑patient example – no radiology results are present, so only tiers T1‑T4 are generated.

**Source – `docs/GLOSSARY.md`**
- The glossary entry for *"Trust tier"* is not present; however the **introductory paragraph in the architecture** (line 158) states:
  > *"When sources disagree, the higher tier wins..."*
- The **Phase 0 Completion Report** previously quoted the glossary as saying *"T1–T5 can affect scores"* – this appears to be an outdated statement derived from an earlier version of the design where T5 (radiology) was expected to be used.

### Resolution / Explanation
- **Both statements are internally consistent when interpreted in context**:
  1. **Architecture definition**: T1‑T5 are **capable** of influencing scores (the trust‑tier table includes them). T6 cannot.
  2. **Current pipeline (the worked example)**: Only facts from **transcripts** (T1) and **OCR‑derived lab values** (T4) are present, because no radiology or imaging model output is available. Therefore the narrative says *"confirmed facts become T1‑T4"* – it is describing the **tiers that actually appear** in this case, not a limitation on the tiers themselves.
- Consequently, there is **no contradiction** in the source documents; the glossary‑derived statement that *"T1‑T5 can affect scores"* remains correct, and the architecture narrative simply reflects the concrete tiers used for the example.
- **Open question**: The glossary does not explicitly list the tier definitions; the only formal definition lives in `ARCHITECTURE.md`. If a separate glossary entry for “trust tier” is expected, it is missing.

---

## 2. Golden worked‑example verification

| Item | Source (Markdown) | Source (JSON) | Independently calculated | Match? |
|------|-------------------|---------------|--------------------------|--------|
| **Dengue – prior** | `prior 0.20` (line 106) | `"prior": 0.20` (line 48) | 0.20 | ✅ |
| **Dengue – LRs** | CBC pattern LR 4.0, retro‑orbital pain LR 1.5 (lines 106‑108) | `lr: 4.0` and `lr: 1.5` (lines 51‑52) | 4.0, 1.5 | ✅ |
| **Dengue – odds** | `0.25 → odds 1.00 → odds 1.50` → final odds **1.5** (line 108) | `"expected_odds": 1.5` (line 54) | 1.5 | ✅ |
| **Dengue – p_raw** | `p_raw = 1.50 / 2.50 = 0.60` (line 109) | `"expected_p_raw": 0.600` (line 55) | 0.600 | ✅ |
| **Leptospirosis – prior** | `prior 0.04` (line 115) | `"prior": 0.04` (line 59) | 0.04 | ✅ |
| **Leptospirosis – LRs** | Paddy work LR 2.0, myalgia LR 1.3, jaundice absent LR‑ 0.8 (lines 117‑119) | `lr: 2.0`, `lr: 1.3`, `lr: 0.8` (lines 61‑63) | 2.0, 1.3, 0.8 | ✅ |
| **Leptospirosis – odds** | `0.0417 → odds 0.0867` (line 119) | `"expected_odds": 0.0867` (line 65) | 0.0867 | ✅ |
| **Leptospirosis – p_raw** | `p_raw = 0.0867 / 1.0867 = 0.080` (line 119‑120) | `"expected_p_raw": 0.080` (line 66) | 0.080 | ✅ |
| **Scrub typhus – prior** | `prior 0.06` (line 125) | `"prior": 0.06` (line 70) | 0.06 | ✅ |
| **Scrub typhus – LRs** | Agricultural work LR 1.8, thrombocytopenia LR 1.5 (lines 126‑127) | `lr: 1.8`, `lr: 1.5` (lines 72‑73) | 1.8, 1.5 | ✅ |
| **Scrub typhus – odds** | `0.0638 → odds 0.1723` (line 128‑129) | `"expected_odds": 0.1723` (line 78) | 0.1723 | ✅ |
| **Scrub typhus – p_raw** | `p_raw = 0.1723 / 1.1723 = 0.147` (line 129‑130) | `"expected_p_raw": 0.147` (line 79) | 0.147 | ✅ |
| **Outer round 2 – Dengue odds** | `1.50 x NS1+ LR 20 → odds 30.0` (line 188‑189) | `"expected_odds": 30.0` (line 102) | 30.0 | ✅ |
| **Outer round 2 – Dengue p_raw** | `p_raw = 0.968` (line 188‑189) | `"expected_p_raw": 0.968` (line 103) | 0.968 | ✅ |
| **Outer round 2 – Scrub typhus odds** | `0.1723 x eschar‑ LR 0.6 → odds 0.1034` (line 189‑190) | `"expected_odds": 0.1034` (line 111) | 0.1034 | ✅ |
| **Outer round 2 – Scrub typhus p_raw** | `p_raw = 0.094` (line 189‑190) | `"expected_p_raw": 0.094` (line 112) | 0.094 | ✅ |
| **Top‑tests (expected)** | NS1, IgM, malaria antigen, repeat CBC (lines 154‑160) | `"expected_top_tests": ["Dengue NS1 antigen","Scrub typhus IgM","Malaria antigen / smear","Repeat CBC + haematocrit"]` (line 85) | list matches exactly | ✅ |
| **Top‑question (expected)** | "Search for an eschar" (line 162‑163) | `"expected_top_question": "Search for an eschar"` (line 86) | matches | ✅ |
| **Must‑not‑miss status after outer round 2** | Severe dengue **active**, severe malaria **ruled_out** (lines 180‑182) | `"expected_must_not_miss_status": {"Severe malaria": "ruled_out", "Severe dengue": "active"}` (lines 115‑118) | matches | ✅ |

**No discrepancies** were found between the markdown worked example and the golden JSON source.

---

## 3. Extraction‑script status (live HAPI test)
The user executed:
```
python scripts\extract_patient_data.py --patient-id 1149
```
Results on the running HAPI server:
- `patient_summary.json` – contains **1** patient entry.
- `observations.json` – contains **3,181** Observation entries.
- `conditions.json` – contains **113** Condition entries.

All three files were written to `phase0_fhir\output\` and contain the correct FHIR resource IDs and subject references. This confirms that the extraction script works end‑to‑end against a live HAPI instance (read‑only GET operations only).

---

## 4. Open questions
1. **Glossary missing “trust‑tier” entry** – the glossary does not define the trust‑tier concept; the definition lives only in `ARCHITECTURE.md`.
2. **Missing architecture diagram** – `../architecture.svg` referenced in `ARCHITECTURE.md` is not present in the repository.

---

*Prepared by Antigravity on 2026‑11‑19.*
