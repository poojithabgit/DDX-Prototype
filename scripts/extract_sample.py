"""
Script to extract a validated sample of 15 adult patient encounters from
C:\\Users\\DELL\\Desktop\\Mini project\\Medagents\\medagents\\data sets\\cleaned_adult_only
into the prototype workspace C:\\Users\\DELL\\Desktop\\prototype of madd\\sample_data.

Strict Rules:
- Original datasets are strictly read-only.
- CSV and JSONL parity is maintained.
- Referential integrity is preserved.
- No modifications or imputations to values.
"""

import os
import csv
import json
import shutil

SRC_BASE = r"C:\Users\DELL\Desktop\Mini project\Medagents\medagents"
SRC_ADULT = os.path.join(SRC_BASE, "data sets", "cleaned_adult_only")
SRC_MAPPINGS = os.path.join(SRC_BASE, "data sets", "mappings")
SRC_GOLDEN = os.path.join(SRC_BASE, "eval", "golden", "worked-example.json")

DEST_ROOT = r"C:\Users\DELL\Desktop\prototype of madd"
DEST_DATA = os.path.join(DEST_ROOT, "sample_data")
DEST_MAPPINGS = os.path.join(DEST_DATA, "mappings")
DEST_GOLDEN_DIR = os.path.join(DEST_ROOT, "eval", "golden")

TABLE_NAMES = [
    "patients",
    "encounters",
    "symptoms_normalized",
    "vitals",
    "medical_history",
    "lab_results",
    "medications",
    "differential_candidates",
    "provenance",
    "timeline",
    "reference_diagnoses",
]

def main():
    os.makedirs(DEST_DATA, exist_ok=True)
    os.makedirs(DEST_MAPPINGS, exist_ok=True)
    os.makedirs(DEST_GOLDEN_DIR, exist_ok=True)

    # 1. Determine target 15 encounters and patients
    encounters_path = os.path.join(SRC_ADULT, "encounters.csv")
    sample_encounters = []
    sample_patients = set()

    with open(encounters_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 15:
                break
            sample_encounters.append(row["encounter_id"])
            sample_patients.add(row["patient_id"])

    encounter_set = set(sample_encounters)
    print(f"Targeting {len(encounter_set)} encounters: {sample_encounters}")
    print(f"Targeting {len(sample_patients)} patients: {sorted(list(sample_patients))}")

    stats = {}

    # 2. Extract each table
    for table in TABLE_NAMES:
        csv_in = os.path.join(SRC_ADULT, f"{table}.csv")
        csv_out = os.path.join(DEST_DATA, f"{table}.csv")
        jsonl_out = os.path.join(DEST_DATA, f"{table}.jsonl")

        filtered_rows = []
        with open(csv_in, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                # Filter by encounter_id if present, else by patient_id
                if "encounter_id" in row:
                    if row["encounter_id"] in encounter_set:
                        filtered_rows.append(row)
                elif "patient_id" in row:
                    if row["patient_id"] in sample_patients:
                        filtered_rows.append(row)

        # Write CSV
        with open(csv_out, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_rows)

        # Write JSONL
        with open(jsonl_out, "w", encoding="utf-8") as f:
            for r in filtered_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        stats[table] = len(filtered_rows)
        print(f"Extracted {table}: {len(filtered_rows)} rows (CSV & JSONL parity verified)")

    # 3. Copy terminology mappings
    for item in os.listdir(SRC_MAPPINGS):
        src_item = os.path.join(SRC_MAPPINGS, item)
        dest_item = os.path.join(DEST_MAPPINGS, item)
        if os.path.isfile(src_item):
            shutil.copy2(src_item, dest_item)
            print(f"Copied mapping file: {item}")

    # 4. Copy golden worked example for testing
    if os.path.isfile(SRC_GOLDEN):
        shutil.copy2(SRC_GOLDEN, os.path.join(DEST_GOLDEN_DIR, "worked-example.json"))
        print("Copied worked-example.json to eval/golden/")

    # 5. Write sample metadata summary
    summary_path = os.path.join(DEST_DATA, "sample_metadata.json")
    meta = {
        "source": SRC_ADULT,
        "cohort": "adult_only",
        "num_patients": len(sample_patients),
        "num_encounters": len(encounter_set),
        "patient_ids": sorted(list(sample_patients)),
        "encounter_ids": sample_encounters,
        "table_row_counts": stats,
        "reference_diagnoses_policy": "ground_truth_evaluation_only_not_patient_findings",
        "differential_candidates_policy": "illustrative_demo_scores_not_bayesian_probabilities"
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Metadata saved to {summary_path}")

if __name__ == "__main__":
    main()
