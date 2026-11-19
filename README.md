# Medagents — Clinical Decision-Support Research Prototype

Medagents is a research prototype exploring a clinician-supervised workflow for adult acute undifferentiated fever in Indian outpatient and emergency-care settings.

The project brings together structured clinical data, evidence extraction, a case graph, and deterministic reasoning to help organise clinical information and support clinician review. It is a research demonstration—not an autonomous diagnostic system and not a clinically validated medical device.

## Project organisation

The repository contains two related workstreams.

### Main prototype — Stages 1–5

The main prototype is organised across the repository root rather than inside one folder:

- `src/` — application modules, including ingestion, graph, reasoning, verification, and UI components
- `tests/` — automated tests
- `scripts/` — supporting and demonstration scripts
- `schemas/` — data schemas
- `sample_data/` — sample inputs for development and demonstration
- `eval/` — evaluation-related material
- `reports/` — stage completion and review reports
- `app.py` — Streamlit application entry point

Stage-specific completion and review reports are kept in `reports/`.

### Phase 0 — FHIR and data preparation

The separate `phase0_fhir/` directory contains the foundational FHIR data preparation work:

- Synthea synthetic patient data generation and audit utilities
- HAPI FHIR import and resource-count scripts
- Patient-level FHIR extraction scripts
- Phase 0 documentation and audit reports

Related DDXPlus dataset documentation and selected metadata are stored in `data_sources/ddxplus/`.

## Key design principles

- **Clinician oversight:** Clinicians review extracted facts, uncertain findings, differential considerations, and suggested next steps.
- **Deterministic scoring:** Probability calculations are handled by deterministic Bayes-rule logic using reviewed priors and likelihood ratios; an LLM does not calculate probabilities.
- **Evidence provenance:** Clinical facts should retain traceable source information.
- **Unconfirmed extraction is not evidence:** Unconfirmed extracted findings must not change scores.
- **Safety visibility:** Must-not-miss conditions remain visible until addressed using the defined evidence and review process.
- **Append-only case history:** Case Graph changes are recorded as events rather than silently overwriting prior history.

## Data and research limitations

- Synthea data is synthetic and does not represent real patients.
- DDXPlus is also a synthetic research dataset; it is not an India-specific clinical population.
- Synthetic examples and illustrative scores must not be interpreted as clinical performance or real-world probability estimates.
- The prototype has not been clinically validated and must not be used to make patient-care decisions.

## Run the Streamlit demonstration

From the repository root, create and activate a Python virtual environment, install the project's required dependencies, and run:

```powershell
streamlit run app.py
```

The app is normally available at:

```text
http://localhost:8501
```

Use the dependency files included in the repository, if present, to install the project's packages. Phase 0 scripts may have additional requirements described in `phase0_fhir/README.md`.

## Phase 0 documentation

Start with:

- [Phase 0 FHIR README](phase0_fhir/README.md)
- [Synthea FHIR audit](phase0_fhir/reports/SYNTHEA_FHIR_AUDIT.md)
- [DDXPlus audit](data_sources/ddxplus/DDXPLUS_AUDIT_FINAL.md)

## Repository status

This repository contains a research prototype and supporting implementation, tests, sample data, and audit documentation. The presence of a stage report or passing software test does not establish clinical validity.

## Disclaimer

**For research and demonstration only.** This software is not a substitute for professional medical judgement, clinical examination, local clinical guidelines, or emergency care. Do not use it to diagnose, treat, or triage real patients.
