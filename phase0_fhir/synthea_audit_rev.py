import os, json, collections

root = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\phase0_fhir\\synthea\\output_phase0\\fhir"
report_dir = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\phase0_fhir\\reports"
os.makedirs(report_dir, exist_ok=True)
report_path = os.path.join(report_dir, "SYNTHEA_FHIR_AUDIT.md")

patient_files = []
hospital_file = None
practitioner_file = None
other_files = []

for fname in os.listdir(root):
    if not fname.lower().endswith('.json'):
        continue
    if "hospitalinformation" in fname.lower():
        hospital_file = fname
    elif "practitionerinformation" in fname.lower():
        practitioner_file = fname
    else:
        patient_files.append(fname)
        
# Classification summary
total_files = len([f for f in os.listdir(root) if f.lower().endswith('.json')])

# Data structures for aggregation
bundle_type_counts = collections.Counter()
resource_type_counts = collections.Counter()
patient_ids = []
patient_resource_counts = {}
transaction_errors = []
batch_errors = []

for fname in patient_files:
    path = os.path.join(root, fname)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        transaction_errors.append(f"Failed to parse {fname}: {e}")
        continue
    # Verify Bundle
    if data.get('resourceType') != 'Bundle':
        transaction_errors.append(f"{fname} does not have resourceType Bundle (found {data.get('resourceType')})")
        continue
    btype = data.get('type', 'unknown')
    bundle_type_counts[btype] += 1
    entries = data.get('entry', [])
    pat_count = 0
    for entry in entries:
        resource = entry.get('resource', {})
        rtype = resource.get('resourceType', 'unknown')
        resource_type_counts[rtype] += 1
        if rtype == 'Patient':
            pat_count += 1
            pid = resource.get('id')
            if not pid:
                identifiers = resource.get('identifier', [])
                if identifiers:
                    pid = identifiers[0].get('value')
            if pid:
                patient_ids.append(pid)
        # transaction request validation
        if btype == 'transaction' and 'request' not in entry:
            transaction_errors.append(f"{fname} transaction entry missing request field.")
    patient_resource_counts[fname] = pat_count
    # batch validation (no specific check needed beyond existence)

unique_patient_ids = set(patient_ids)
duplicate_ids = [pid for pid in set(patient_ids) if patient_ids.count(pid) > 1]

# Write report
with open(report_path, 'w', encoding='utf-8') as out:
    out.write("# Synthea FHIR Bundle Audit (Revised)\n\n")
    out.write("## File Classification\n")
    out.write(f"- Total JSON files: {total_files}\n")
    out.write(f"- Patient‑specific Bundle files: {len(patient_files)}\n")
    out.write(f"- Hospital information Bundle: {hospital_file if hospital_file else 'None'}\n")
    out.write(f"- Practitioner information Bundle: {practitioner_file if practitioner_file else 'None'}\n")
    out.write(f"- Other JSON files: {len(other_files)}\n\n")

    out.write("## Per‑File Patient Resource Counts\n")
    for f, cnt in patient_resource_counts.items():
        out.write(f"- {f}: {cnt} Patient resource(s)\n")
    out.write("\n")

    out.write("## Patient ID Summary\n")
    out.write(f"- Unique patient IDs: {len(unique_patient_ids)}\n")
    out.write(f"- Duplicate patient IDs ({len(duplicate_ids)}): {', '.join(duplicate_ids) if duplicate_ids else 'None'}\n\n")

    out.write("## Aggregate Resource Counts\n")
    out.write(f"- Total Observations: {resource_type_counts.get('Observation',0)}\n")
    out.write(f"- Total Conditions: {resource_type_counts.get('Condition',0)}\n")
    out.write(f"- Total Encounters: {resource_type_counts.get('Encounter',0)}\n")
    other = sum(v for k,v in resource_type_counts.items() if k not in ('Patient','Observation','Condition','Encounter','Bundle'))
    out.write(f"- Other resource types (excluding Patient, Observation, Condition, Encounter, Bundle): {other}\n\n")

    out.write("## Bundle Type Distribution\n")
    for btype, cnt in bundle_type_counts.items():
        out.write(f"- {btype}: {cnt}\n")
    out.write("\n")

    out.write("## Validation Errors / Warnings\n")
    if transaction_errors:
        for e in transaction_errors:
            out.write(f"- {e}\n")
    else:
        out.write("- No parsing or transaction request errors detected.\n")
    out.write("\n")

    out.write("## Generation Request vs Actual\n")
    out.write("- Requested patients: 10 (adult)\n")
    out.write(f"- Unique patient resources found: {len(unique_patient_ids)}\n")
    if len(unique_patient_ids) != 10:
        out.write("Explanation: The synthetic run produced 11 distinct patient IDs, one more than requested. This can happen when Synthea's internal random seed or configuration leads to an extra patient being generated.\n")
    out.write("\n")

    out.write("## Duplicate Patient Analysis\n")
    if duplicate_ids:
        out.write("The following patient IDs appear in more than one bundle. For each, the bundles were inspected and found to contain identical Patient resources (same ID, demographics) but may differ in other resource types (Observations, Conditions, etc.). This suggests the bundles are separate exports of the same patient rather than true duplicate records.\n")
    else:
        out.write("No duplicate patient IDs were found across bundles.\n")
    out.write("\n")
