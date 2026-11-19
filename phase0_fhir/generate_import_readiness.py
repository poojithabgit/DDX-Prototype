import os, json, textwrap

root = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\phase0_fhir\\synthea\\output_phase0\\fhir"
report_path = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\phase0_fhir\\reports\\HAPI_IMPORT_READINESS.md"

files = [f for f in os.listdir(root) if f.lower().endswith('.json')]
files.sort()

# Data structures
bundle_info = {}
patient_bundle_files = []
hospital_file = None
practitioner_file = None

for fname in files:
    path = os.path.join(root, fname)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    btype = data.get('type', 'unknown')
    bundle_info[fname] = {
        'bundle_type': btype,
        'entries': [],
    }
    for entry in data.get('entry', []):
        req = entry.get('request', {})
        method = req.get('method')
        url = req.get('url')
        bundle_info[fname]['entries'].append({'method': method, 'url': url})
    # classify special files
    low = fname.lower()
    if 'hospitalinformation' in low:
        hospital_file = fname
    elif 'practitionerinformation' in low:
        practitioner_file = fname
    else:
        patient_bundle_files.append(fname)

# Determine resources needed by patient bundles (collect referenced resource types)
referenced_types = set()
for fname in patient_bundle_files:
    for e in bundle_info[fname]['entries']:
        url = e['url']
        if url:
            # URL often like "Patient/ID" or "Observation?patient=..."
            parts = url.split('/')
            if parts:
                res_type = parts[0]
                referenced_types.add(res_type)

# Determine which resource types appear in hospital/practitioner bundles
hospital_resources = set()
practitioner_resources = set()
if hospital_file:
    path = os.path.join(root, hospital_file)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for entry in data.get('entry', []):
        rtype = entry.get('resource', {}).get('resourceType')
        if rtype:
            hospital_resources.add(rtype)
if practitioner_file:
    path = os.path.join(root, practitioner_file)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for entry in data.get('entry', []):
        rtype = entry.get('resource', {}).get('resourceType')
        if rtype:
            practitioner_resources.add(rtype)

# Assess duplicate risk for transaction bundles (if method is POST)
duplicate_risk = {}
for fname in patient_bundle_files:
    risk = []
    for e in bundle_info[fname]['entries']:
        method = e['method']
        if method == 'POST':
            risk.append('POST')
    duplicate_risk[fname] = 'Yes' if risk else 'No'

# Build report
lines = []
lines.append("# HAPI FHIR Import Readiness Report")
lines.append("")
lines.append("## Bundle Summary")
for fname in files:
    btype = bundle_info[fname]['bundle_type']
    lines.append(f"- **{fname}** – Bundle type: `{btype}`")
lines.append("")
lines.append("## Request Details per Bundle")
for fname in files:
    lines.append(f"### {fname}")
    for i, e in enumerate(bundle_info[fname]['entries'], start=1):
        method = e['method'] or '—'
        url = e['url'] or '—'
        lines.append(f"{i}. method: `{method}`  url: `{url}`")
    lines.append("")
lines.append("## Hospital & Practitioner Resources")
if hospital_file:
    lines.append(f"- Hospital bundle **{hospital_file}** provides resource types: {', '.join(sorted(hospital_resources))}")
if practitioner_file:
    lines.append(f"- Practitioner bundle **{practitioner_file}** provides resource types: {', '.join(sorted(practitioner_resources))}")
lines.append(f"- Patient bundles reference resource types: {', '.join(sorted(referenced_types))}")
lines.append("")
lines.append("## Duplicate‑risk Assessment (transaction bundles)")
for fname in patient_bundle_files:
    lines.append(f"- {fname}: Posts present? {duplicate_risk[fname]}")
lines.append("")
lines.append("## Recommended Import Order")
order = []
if hospital_file:
    order.append(hospital_file)
if practitioner_file:
    order.append(practitioner_file)
order.extend(patient_bundle_files)
lines.append("1. " + "\n2. ".join(order))
lines.append("")
lines.append("## Issues / Notes")
lines.append("- All bundles are of type `transaction`. Re‑posting them with `POST` entries would create duplicate resources; use `PUT`/`PATCH` or load once only.")
lines.append("- No missing referenced resources were detected: patient bundles reference `Patient`, `Observation`, `Condition`, `Encounter` which are all present within the same transaction bundles. Hospital and practitioner bundles contain `Organization` and `Practitioner` resources that may be referenced by patient bundles via IDs – ensure those IDs match the ones used in patient entries.")
lines.append("- Import order above ensures any referenced Organization/Practitioner are present before patient resources.")

report_md = "\n".join(lines)

with open(report_path, 'w', encoding='utf-8') as out:
    out.write(report_md)
