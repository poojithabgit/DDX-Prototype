# Phase 0 – Medagents FHIR Extraction

## 1. Prerequisites

| Item | Version / Note |
|------|----------------|
| **Java** | JDK 17 or later (required by the HAPI FHIR Docker image) |
| **Docker** | Docker Desktop ≥ 4.0 – the HAPI FHIR server runs in a container |
| **PowerShell** | Windows PowerShell 5.1 (used for the import scripts) |
| **Python** | 3.9+ (the extraction script) |
| **pip packages** | `requests` – install with `pip install requests` |

## 2. Verified HAPI counts (post‑import)

After the patient‑bundle import the server contains:

- **Patient:** 11
- **Observation:** 8,741
- **Condition:** 565
- **Encounter:** 635
- **Organization:** 37
- **Practitioner:** 37

These numbers were obtained with the PowerShell `Get‑Counts` helper used in the import script.

## 3. Starting the HAPI FHIR container

```powershell
# From the workspace root (C:\Users\DELL\Desktop\prototype of madd)
cd phase0_fhir

docker compose up -d   # if a compose file exists, otherwise use the official image
# or manually run the official image
# docker run -d -p 8080:8080 hapiproject/hapi:latest
```

The server will be reachable at `http://127.0.0.1:8080/fhir`.

## 4. Verifying connectivity

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/fhir/metadata'
```

You should see a `CapabilityStatement` with `fhirVersion: 4.0.1`.

## 5. How the synthetic data was generated

* **Synthea** (`v3.3.0`) was executed with the command:
  ```
  synthea -p 10 -a 18-80 -c ./config/default.properties -r fhir
  ```
* Ten *living* patients and one *deceased* patient were generated (11 total).  The output directory is:
  `phase0_fhir\synthea\output_phase0\fhir`.
* Two support Bundles (hospitalInformation & practitionerInformation) were imported first, followed by the 11 patient transaction Bundles.

## 6. Import process (already performed)

The PowerShell script `import_phase0_patient_bundles.ps1` (saved on the Desktop) imports the patient bundles **once**, records a ledger, and saves each transaction‑response Bundle under:
```
phase0_fhir\logs\response_bundles\
```
All import logs are in `phase0_fhir\logs\import_YYYYMMDD_HHmmss.log`.

*Note:* The duplicate‑prevention behaviour of the script has not been independently verified; it is assumed to work as written.

## 7. Running the Python extraction script

```powershell
# Ensure the Python dependencies are present
python -m pip install --upgrade pip
python -m pip install requests

# Run the script – replace 1149 with any Patient ID that exists in HAPI
python scripts\extract_patient_data.py --patient-id 1149
```
The script performs **read‑only** GET requests, follows pagination, and writes three JSON files under `phase0_fhir\output\`:
* `patient_summary.json`
* `observations.json`
* `conditions.json`

### Example command to test the script
```
python scripts\extract_patient_data.py --patient-id 1149
```
The output files will appear in the `output` directory.

## 8. DDXPlus inspection (synthetic)

During Phase 0 the following synthetic DDXPlus dataset statistics were recorded:

- **Training records:** 1,025,602
- **Validation records:** 132,448
- **Test records:** 134,529
- **Pathologies:** 49
- **Evidence definitions:** 223

DDXPlus is fully synthetic: it does **not** contain Indian‑specific population characteristics, free‑text clinical narratives, or laboratory time‑series data.

## 9. Re‑producing the whole workflow from scratch

1. **Clone the repository** (or copy the `prototype of madd` folder) to a fresh machine.
2. Install Java, Docker, and Python as described in section 1.
3. Start the HAPI container (section 3).
4. Run the Synthea generation command (section 5) – the same command used in the original project.
5. Import the two support Bundles manually (or reuse the provided PowerShell script).
6. Import the 11 patient Bundles with `import_phase0_patient_bundles.ps1` – the script is intended to be safe‑guarded against duplicate imports.
7. Verify counts with the PowerShell snippet from the import script or via:
   ```powershell
   Invoke-RestMethod 'http://127.0.0.1:8080/fhir/Patient?_summary=count'
   ```
8. Extract a patient’s data with the Python script (section 7).

## 10. Data disclaimer

The data originates from **Synthea**, a synthetic patient generator.  All patient demographics, conditions, and observations are fictitious and **do not represent real Indian patients** or any real‑world population.  They are safe to use for development, testing, and education.
