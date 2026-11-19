import os, json, datetime, sys

root = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\phase0_fhir\\synthea\\output_phase0\\fhir"
report_path = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\phase0_fhir\\reports\\SYNTHEA_FHIR_AUDIT.md"

# Gather patient files (exclude hospital/practitioner)
patient_files = []
for fname in os.listdir(root):
    if fname.lower().endswith('.json') and 'hospitalinformation' not in fname.lower() and 'practitionerinformation' not in fname.lower():
        patient_files.append(fname)

patients = []
for fname in sorted(patient_files):
    path = os.path.join(root, fname)
    with open(path, 'r', encoding='utf-8') as f:
        bundle = json.load(f)
    # Find the Patient resource (first one)
    patient_res = None
    for entry in bundle.get('entry', []):
        res = entry.get('resource', {})
        if res.get('resourceType') == 'Patient':
            patient_res = res
            break
    if not patient_res:
        continue
    pid = patient_res.get('id')
    birth = patient_res.get('birthDate')
    gender = patient_res.get('gender')
    deceased_bool = patient_res.get('deceasedBoolean')
    deceased_dt = patient_res.get('deceasedDateTime')
    # Compute age as of audit date 2026-11-19
    age = None
    if birth:
        try:
            bdate = datetime.datetime.strptime(birth, "%Y-%m-%d").date()
            today = datetime.date(2026, 11, 19)
            age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
        except Exception:
            age = None
    alive = not (deceased_bool is True or deceased_dt)
    patients.append({
        'file': fname,
        'id': pid,
        'birth': birth,
        'age': age,
        'gender': gender,
        'deceased_bool': deceased_bool,
        'deceased_dt': deceased_dt,
        'alive': alive,
    })

# Summaries
total_patients = len(patients)
living = sum(1 for p in patients if p['alive'])
deceased = total_patients - living
aged_18_80 = sum(1 for p in patients if p['age'] is not None and 18 <= p['age'] <= 80)

# Build markdown table
lines = []
lines.append("| File | Patient ID | Birth Date | Age | Gender | Deceased? | Alive? |")
lines.append("|---|---|---|---|---|---|---|")
for p in patients:
    deceased_str = "Yes" if (p['deceased_bool'] or p['deceased_dt']) else "No"
    alive_str = "Yes" if p['alive'] else "No"
    lines.append(f"| {p['file']} | {p['id']} | {p['birth'] or ''} | {p['age'] if p['age'] is not None else ''} | {p['gender'] or ''} | {deceased_str} | {alive_str} |")

table_md = "\n".join(lines)

# Read existing report
with open(report_path, 'r', encoding='utf-8') as f:
    report = f.read()

# Replace generation command line (look for "-aa 18-80")
report = report.replace("-aa 18-80", "-a 18-80")

# Replace population conclusion section (lines starting with "## Generation Request vs Actual" up to next blank line)
import re
pattern = r"## Generation Request vs Actual[\s\S]*?(?=\n##|\Z)"
replacement = f"## Generation Request vs Actual\n\n- Requested living patients: 10\n- Generated living patients: {living}\n- Deceased patients exported: {deceased}\n- Total Patient resources: {total_patients}\n- No extra living patients beyond the requested population."
report = re.sub(pattern, replacement, report)

# Replace the patient demographics table section (look for "## Patient Demographics Details" and replace whole section)
pattern2 = r"## Patient Demographics Details[\s\S]*?(?=\n##|\Z)"
new_section = f"## Patient Demographics Details (Population‑size check)\n\n{table_md}\n"
report = re.sub(pattern2, new_section, report)

# Write back updated report
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)
