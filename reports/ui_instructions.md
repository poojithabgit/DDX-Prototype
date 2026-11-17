# Medagents Dashboard — UI Instructions

> ⚠️ **RESEARCH PROTOTYPE — SYNTHETIC DATA ONLY.**
> All patient records, priors, likelihood ratios and posterior scores are
> **illustrative demonstration values**. NOT for clinical decision-making.

---

## Prerequisites

Ensure the following are installed (already done in this workspace):

| Package | Version | Purpose |
|---|---|---|
| Python | 3.14.7 | Runtime |
| streamlit | 1.67.0 | Dashboard server |
| plotly | 7.1.0 | Interactive charts |
| pandas | 3.1.1 | Data tables |

---

## How to Launch

Open **Windows PowerShell** and run:

```powershell
Set-Location "C:\Users\DELL\Desktop\prototype of madd"
streamlit run app.py
```

Streamlit will start and print a local URL — typically:

```
Local URL: http://localhost:8501
Network URL: http://192.168.x.x:8501
```

Your browser should open automatically. If not, navigate to **http://localhost:8501** manually.

---

## Dashboard Pages

| # | Page | Description |
|---|---|---|
| 1 | Overview | Pipeline metrics, encounter selector, run button |
| 2 | Patient Encounter | Symptoms, vitals, labs, history for the selected encounter |
| 3 | Clinical Findings | Full filtered findings table with trust tier distribution |
| 4 | Verification | Claims table, verdict outcomes, deterministic verifier results |
| 5 | Differential Diagnosis | Prior vs Posterior comparison chart, band summary |
| 6 | Bayesian Analysis | Step-by-step Bayes' theorem calculations per hypothesis |
| 7 | Must-Not-Miss Conditions | MNM KB entries, flagged conditions, verifier verdicts |
| 8 | Case Graph | Append-only event log, historical replay slider |
| 9 | Safety Audit | Full invariant checklist, dynamic provenance audit |

---

## Running the Demonstration

1. Launch the dashboard with `streamlit run app.py`.
2. In the left sidebar, **select an encounter** from the dropdown.
3. Click **▶ Run Demonstration**.
4. The full Stages 1–5 pipeline runs in the backend.
5. Navigate through all 9 pages to explore the results.

---

## Safety Notices

| Invariant | Behaviour |
|---|---|
| Synthetic provenance | Findings from `prototype-extractor` are T6 and **excluded from Bayesian scoring** |
| Simulated confirmation | Clinician checkpoint 1 is simulated. T6 findings **remain T6** after confirmation |
| Bayesian scores | Computed deterministically in `src/reasoning/scorer.py`. **Never estimated by the UI** |
| Must-Not-Miss | Always flagged independently of posterior score rank |
| Band labels | HIGH/MODERATE/LOW/VERY_LOW are **unvalidated demo thresholds**, not clinical classifications |

### What "No likelihood ratios applied. Effective LR Product: 1.00" means

All sample data findings carry synthetic provenance (extractor = `prototype-extractor-v0.1`).
The Bayesian engine excludes these findings from LR updates.
Posterior scores equal baseline priors for all hypotheses.

This is the **SAFETY BARRIER ENGAGING CORRECTLY** — not an error.

---

## Running the Full Test Suite

```powershell
Set-Location "C:\Users\DELL\Desktop\prototype of madd"
python -m pytest tests -v --tb=short
```

Expected: **99 passed, 1 warning**

---

## Running the Terminal Demo (Alternative)

```powershell
Set-Location "C:\Users\DELL\Desktop\prototype of madd"
python .\scripts\run_demo.py
```

---

## Known Limitations

- The dashboard runs only on `localhost` (Windows local server).
- All data is synthetic — no real patient data is processed.
- Scores are illustrative and have not been clinically validated.
- Stage 6 is not implemented; the prototype covers Stages 1–5 only.
