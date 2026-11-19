import json, os, sys, urllib.request, urllib.parse

BASE = "http://localhost:8080/fhir"

def get_json(url):
    try:
        with urllib.request.urlopen(url) as resp:
            return json.load(resp)
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_patient.py <PatientID>")
        sys.exit(1)
    patient_id = sys.argv[1]
    # Observations
    obs_url = f"{BASE}/Observation?patient={patient_id}"
    obs_bundle = get_json(obs_url)
    observations = []
    if obs_bundle and obs_bundle.get('entry'):
        for entry in obs_bundle['entry']:
            res = entry.get('resource', {})
            code = res.get('code', {}).get('coding', [{}])[0].get('code')
            display = res.get('code', {}).get('coding', [{}])[0].get('display')
            value = None
            unit = None
            if 'valueQuantity' in res:
                value = res['valueQuantity'].get('value')
                unit = res['valueQuantity'].get('unit')
            elif 'valueString' in res:
                value = res['valueString']
            effective = res.get('effectiveDateTime') or (res.get('effectivePeriod', {}).get('start'))
            observations.append({
                'code': code,
                'display': display,
                'value': value,
                'unit': unit,
                'effective': effective
            })
    # Conditions
    cond_url = f"{BASE}/Condition?patient={patient_id}"
    cond_bundle = get_json(cond_url)
    conditions = []
    if cond_bundle and cond_bundle.get('entry'):
        for entry in cond_bundle['entry']:
            res = entry.get('resource', {})
            code = res.get('code', {}).get('coding', [{}])[0].get('code')
            display = res.get('code', {}).get('coding', [{}])[0].get('display')
            clinical_status = res.get('clinicalStatus', {}).get('coding', [{}])[0].get('code')
            conditions.append({
                'code': code,
                'display': display,
                'clinical_status': clinical_status
            })
    # Save JSON and CSV
    out_dir = os.path.join(os.path.dirname(__file__), 'extracted')
    os.makedirs(out_dir, exist_ok=True)
    out_json = {
        'patient_id': patient_id,
        'observations': observations,
        'conditions': conditions
    }
    json_path = os.path.join(out_dir, f'patient_{patient_id}_data.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(out_json, f, indent=2)
    # CSV for observations
    csv_path = os.path.join(out_dir, f'patient_{patient_id}_observations.csv')
    try:
        import csv
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['code','display','value','unit','effective'])
            writer.writeheader()
            for o in observations:
                writer.writerow(o)
    except Exception as e:
        print(f"Failed to write CSV: {e}")
    print(f"Extraction completed. JSON: {json_path}, Observations CSV: {csv_path}")

if __name__ == '__main__':
    main()
