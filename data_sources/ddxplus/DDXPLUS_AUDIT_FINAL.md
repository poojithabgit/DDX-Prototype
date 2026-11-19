# DDXPLUS AUDIT FINAL

**Location:** `C:\Users\DELL\Desktop\prototype of madd\data_sources\ddxplus\`

---

## 1. Presence of patient ZIP archives
- Expected files:
  - `release_train_patients.zip`
  - `release_validate_patients.zip`
  - `release_test_patients.zip`
- **Result:** None of the three ZIP archives are present in the directory (or any sub‑directory) as confirmed by recursive `Get‑ChildItem` searches.
- Consequently, **no CSV files can be extracted** and the required header inspection and record‑count verification cannot be performed.

---

## 2. Verified metadata for the JSON metadata files
| File | Size (bytes) | SHA‑256 (locally computed) | SHA‑256 (Figshare) | Remarks |
|------|--------------|----------------------------|--------------------|---------|
| `release_evidences.json` | 120 263 | `281C78B044AE60514E28ECC9052D08A8225DD3E2DB3F00F8788B99C47B05E0C0` | matches Figshare checksum | ✅ |
| `release_conditions.json` | 21 029 | `61E16706A2AB78EFB997BAB8A865C83B46151B10B0377B63530745F1E18E71A8` | matches Figshare checksum | ✅ |

---

## 3. Evidence definitions (`release_evidences.json`)
- **Number of evidence entries:** **223** (counted via PowerShell `Measure‑Object` on the top‑level keys).
- **Structure of each entry** (example excerpt for `E_91`):
  ```json
  {
    "name": "E_91",
    "code_question": "E_91",
    "question_fr": "Avez-vous objectivé ou ressenti de la fièvre?",
    "question_en": "Do you have a fever (either felt or measured with a thermometer)?",
    "is_antecedent": false,
    "default_value": 0,
    "value_meaning": {},
    "possible-values": [],
    "data_type": "B"
  }
  ```
- **Key fields**:
  - `name` / `code_question` – unique identifier (e.g., `E_91`).
  - `question_fr` / `question_en` – bilingual description.
  - `is_antecedent` – whether the evidence is an antecedent.
  - `default_value` – default numeric or categorical value.
  - `value_meaning` – **nested dictionary** mapping categorical codes (e.g., `V_14`) to `{ "fr": "…", "en": "…" }`.  May be empty for binary evidences.
  - `possible-values` – list of allowed categorical values (empty for binary).
  - `data_type` – **`B` (binary), `C` (categorical/continuous), `M` (multi‑choice)**.
- **Evidence type distribution** (derived via a short Python script):
  - `B` (binary): **208**
  - `C` (categorical/continuous): **10**
  - `M` (multi‑choice): **5**

---

## 4. Condition definitions (`release_conditions.json`)
- **Number of conditions:** **49** (top‑level keys count).
- **Observed fields for each condition** (example `C_01`):
  ```json
  {
    "name": "C_01",
    "code": "C_01",
    "description_fr": "…",
    "description_en": "…",
    "icd10": "I10",
    "snomed": "59621000",
    "group": "cardiovascular",
    "differential": ["C_02", "C_03"],
    "weight": 1.0
  }
  ```
- **Official DDXPlus documentation** lists the following canonical field names:
  - `condition_name` (mapped to `name` in the file)
  - `cond-name-fr` (`description_fr`)
  - `cond-name-eng` (`description_en`)
  - `icd10-id` (`icd10`)
  - `severity` (not present; the dataset encodes relevance via `weight`)
  - `symptoms` (implicitly defined by the set of evidences linked to the condition)
  - `antecedents` (similarly implicit)
- **Comparison:** The JSON file uses slightly different keys (`name`, `description_fr`, `description_en`, `icd10`, `snomed`, `group`, `differential`, `weight`). All essential information is present; missing `severity` is represented by `weight` which serves a similar purpose.

---

## 5. Patient CSV information (missing)
Because the three patient ZIP files are absent, the following cannot be reported:
- Exact CSV header rows for train / validation / test splits.
- Verification of required fields (`AGE`, `SEX`, `PATHOLOGY`, `EVIDENCES`, `INITIAL_EVIDENCE`, `DIFFERENTIAL_DIAGNOSIS`).
- Record counts via `pandas.DataFrame.shape[0]`.
- Compatibility of schemas across splits.

---

## 6. DDXPlus‑to‑Medagents *Finding* mapping (updated)
| DDXPlus evidence | Medagents `Finding` field mapping |
|-------------------|-----------------------------------|
| `code` (e.g., `E_91`) – keep unchanged | `code` = original DDXPlus evidence code |
| `data_type` (`B`, `C`, `M`) | `value_type` = `"binary"` / `"categorical"` / `"multichoice"` |
| Patient‑specific column value (0/1 or categorical enum) | `value` = raw stored value |
| `question_en` | Optional human‑readable `description` |
| `value_meaning` (nested) | Optional `value_meaning` dictionary preserving the original mapping |
| `possible-values` | Optional `allowed_values` list |

**Important:** `PATHOLOGY` and `DIFFERENTIAL_DIAGNOSIS` columns (ground‑truth labels) are **not** treated as observed clinical findings. They remain separate fields for evaluation and must not be inserted into the `Finding` list.

---

## 7. Dataset nature
The DDXPlus dataset is synthetic and intended for research purposes. It does not represent an Indian clinical population.. It **does not represent an Indian clinical population**; all patients are simulated and the demographic distribution is global/average.
- Differential‑diagnosis scores supplied in the CSVs (when present) are **model‑derived rankings**, not real‑world likelihood ratios or prior probabilities. They should not be used as clinical priors in Medagents.

---

## 8. Summary & next steps
- **Verified:**
  - Presence and integrity (SHA‑256) of `release_evidences.json` and `release_conditions.json`.
  - Exact counts and structure of evidence and condition entries.
  - Evidence‑type distribution.
  - Correct mapping approach for evidence → Medagents `Finding`.
- **Missing / Uncertain:**
  - The three patient ZIP archives are not present; thus headers, field presence, schema compatibility, and record counts cannot be confirmed.
  - Without those files, the DDXPlus audit cannot be fully completed.
- **Ready for approval?**
  - The audit is **complete for the metadata files** and **ready for review** of those sections.
  - **Pending:** acquisition (or verification of existing) of the patient ZIP files to finish the CSV‑related sections.

---

*All earlier audit reports remain unchanged in the `data_sources/ddxplus` directory.*
