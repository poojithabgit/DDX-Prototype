#!/usr/bin/env python3
"""extract_patient_data.py

Extract patient, observation, and condition data from a local HAPI FHIR server.

Usage:
    python extract_patient_data.py --patient-id 1149

The script connects to the HAPI FHIR endpoint at
    http://127.0.0.1:8080/fhir

It performs **read‑only** GET requests, handling pagination via Bundle "next" links.
All results are saved under ``phase0_fhir/output/`` as JSON files:
    - patient_summary.json
    - observations.json
    - conditions.json

The script does **not** perform any POST/PUT/PATCH/DELETE operations.
"""

import argparse
import json
import os
import sys
from urllib.parse import urljoin, urlencode

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:8080/fhir"
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def log_error(message: str) -> None:
    sys.stderr.write(f"ERROR: {message}\n")

def get_json(url: str, params: dict = None) -> dict:
    """Perform a GET request and return the parsed JSON.
    Raises a RuntimeError with a clear message on failure.
    """
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"GET request to {url} failed: {exc}") from exc

def fetch_all_pages(search_url: str, params: dict = None) -> list:
    """Fetch a FHIR search result (Bundle) handling pagination.
    Returns a list of resources (the ``entry.resource`` objects).
    """
    resources = []
    url = search_url
    while url:
        bundle = get_json(url, params)
        # Extract resources from entries
        for entry in bundle.get("entry", []):
            if "resource" in entry:
                resources.append(entry["resource"])
        # Find next link
        next_url = None
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                next_url = link.get("url")
                break
        url = next_url
        # Params are only needed for the first request
        params = None
    return resources

def extract_patient(patient_id: str) -> dict:
    url = urljoin(BASE_URL + "/", f"Patient/{patient_id}")
    patient = get_json(url)
    # Build a concise summary dictionary
    name = ""
    if patient.get("name"):
        # Take the first name entry and concatenate given + family
        first = patient["name"][0]
        given = " ".join(first.get("given", []))
        family = first.get("family", "")
        name = f"{given} {family}".strip()
    summary = {
        "id": patient.get("id"),
        "name": name,
        "gender": patient.get("gender"),
        "birthDate": patient.get("birthDate"),
    }
    return summary

def extract_observations(patient_id: str) -> list:
    search_url = urljoin(BASE_URL + "/", "Observation")
    params = {"patient": patient_id}
    resources = fetch_all_pages(search_url, params)
    extracted = []
    for obs in resources:
        # Value[x] handling – we look for the first key starting with "value"
        value_field = next((k for k in obs.keys() if k.startswith("value")), None)
        value = None
        value_type = None
        unit = None
        if value_field:
            value_obj = obs[value_field]
            # Primitive types (valueString, valueBoolean, valueInteger, etc.)
            if isinstance(value_obj, (str, int, float, bool)):
                value = value_obj
                value_type = value_field
            # Complex types like valueQuantity, valueCodeableConcept
            elif isinstance(value_obj, dict):
                if "value" in value_obj:
                    value = value_obj["value"]
                elif "coding" in value_obj:
                    # Take first coding display if present
                    coding = value_obj.get("coding", [])[0] if value_obj.get("coding") else {}
                    value = coding.get("display") or coding.get("code")
                value_type = value_field
                unit = value_obj.get("unit")
        # Effective dateTime / period / onset
        effective = obs.get("effectiveDateTime") or obs.get("issued") or obs.get("effectivePeriod", {}).get("start")
        extracted.append({
            "id": obs.get("id"),
            "code": (obs.get("code", {}).get("coding", [{}])[0].get("code")),
            "codeDisplay": (obs.get("code", {}).get("coding", [{}])[0].get("display")),
            "value": value,
            "valueType": value_type,
            "unit": unit,
            "effective": effective,
            "subject": obs.get("subject", {}).get("reference"),
        })
    return extracted

def extract_conditions(patient_id: str) -> list:
    search_url = urljoin(BASE_URL + "/", "Condition")
    params = {"patient": patient_id}
    resources = fetch_all_pages(search_url, params)
    extracted = []
    for cond in resources:
        extracted.append({
            "id": cond.get("id"),
            "code": (cond.get("code", {}).get("coding", [{}])[0].get("code")),
            "codeDisplay": (cond.get("code", {}).get("coding", [{}])[0].get("display")),
            "clinicalStatus": cond.get("clinicalStatus", {}).get("coding", [{}])[0].get("code"),
            "onsetDate": cond.get("onsetDateTime"),
            "recordedDate": cond.get("recordedDate"),
            "subject": cond.get("subject", {}).get("reference"),
        })
    return extracted

def save_json(data, filename):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {filename} ({len(data) if isinstance(data, list) else 1} entries) to {path}")

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Extract FHIR data for a given patient ID from a local HAPI server.")
    parser.add_argument("--patient-id", required=True, help="HAPI Patient resource ID (e.g., 1149)")
    args = parser.parse_args()

    patient_id = args.patient_id

    try:
        patient_summary = extract_patient(patient_id)
        observations = extract_observations(patient_id)
        conditions = extract_conditions(patient_id)
    except RuntimeError as exc:
        log_error(str(exc))
        sys.exit(1)

    # Write results
    save_json(patient_summary, "patient_summary.json")
    save_json(observations, "observations.json")
    save_json(conditions, "conditions.json")

if __name__ == "__main__":
    main()
