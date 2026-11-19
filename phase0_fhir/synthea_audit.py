import os
import json
from collections import Counter

# Paths
root = r"C:\Users\DELL\Desktop\prototype of madd\phase0_fhir\synthea\output_phase0\fhir"
report_dir = r"C:\Users\DELL\Desktop\prototype of madd\phase0_fhir\reports"
os.makedirs(report_dir, exist_ok=True)
report_path = os.path.join(report_dir, "SYNTHEA_FHIR_AUDIT.md")

patient_files = []
other_files = []
for fname in os.listdir(root):
    if not fname.lower().endswith('.json'):
        continue
    if fname.lower() in ("hospitalinformation.json", "practitionerinformation.json"):
        other_files.append(fname)
    else:
        patient_files.append(fname)

total_json_files = len(patient_files) + len(other_files)

bundle_type_counts = Counter()
resource_type_counts = Counter()
patient_ids = set()
errors = []

for fname in patient_files:
    path = os.path.join(root, fname)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        errors.append(f"Failed to parse {fname}: {e}")
        continue
    if data.get("resourceType") != "Bundle":
        errors.append(f"{fname} does not have resourceType Bundle (found {data.get('resourceType')})")
        continue
    btype = data.get("type", "unknown")
    bundle_type_counts[btype] += 1
    entries = data.get("entry", [])
    for entry in entries:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "unknown")
        resource_type_counts[rtype] += 1
        if rtype == "Patient":
            pid = resource.get("id")
            if not pid:
                identifiers = resource.get("identifier", [])
                if identifiers:
                    pid = identifiers[0].get("value")
            if pid:
                patient_ids.add(pid)
        # transaction request check
        if btype == "transaction" and "request" not in entry:
            errors.append(f"{fname} transaction entry missing request field.")

# Write report
with open(report_path, "w", encoding="utf-8") as out:
    out.write("# Synthea FHIR Bundle Audit\n\n")
    out.write("## Summary\n")
    out.write(f"- Total JSON files: {total_json_files}\n")
    out.write(f"- Patient-specific bundle files: {len(patient_files)}\n")
    out.write(f"- Unique patient IDs: {len(patient_ids)}\n")
    out.write(f"- Total Observations: {resource_type_counts.get('Observation',0)}\n")
    out.write(f"- Total Conditions: {resource_type_counts.get('Condition',0)}\n")
    out.write(f"- Total Encounters: {resource_type_counts.get('Encounter',0)}\n")
    other = sum(v for k, v in resource_type_counts.items() if k not in ('Observation','Condition','Encounter','Patient','Bundle'))
    out.write(f"- Other resource types (excluding Patient, Observation, Condition, Encounter): {other}\n\n")
    out.write("## Bundle Type Distribution\n")
    for btype, cnt in bundle_type_counts.items():
        out.write(f"- {btype}: {cnt}\n")
    out.write("\n")
    out.write("## Validation Errors / Warnings\n")
    if errors:
        for e in errors:
            out.write(f"- {e}\n")
    else:
        out.write("- None detected.\n")
    out.write("\n")
    out.write("## Explanation of 11 patient bundles vs requested 10\n")
    if len(patient_files) != 10:
        out.write(f"The dataset contains {len(patient_files)} patient bundle files.\n")
    if len(patient_ids) < len(patient_files):
        out.write(f"Some bundles share the same patient ID, indicating duplicates. Unique patient IDs: {len(patient_ids)}.\n")
    else:
        out.write("Each bundle appears to contain a distinct patient.\n")
    out.write("\n")
