import os, json, hashlib, sys
import pandas as pd

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def inspect_csv(path):
    # Get header and column count
    df_header = pd.read_csv(path, nrows=0)
    columns = list(df_header.columns)
    col_count = len(columns)
    # Count rows using chunks
    row_count = 0
    sample_rows = []
    for i, chunk in enumerate(pd.read_csv(path, chunksize=100000)):
        row_count += len(chunk)
        if i == 0:
            sample_rows = chunk.head(3).to_dict(orient='records')
    # Identify key fields (heuristic)
    lower_cols = [c.lower() for c in columns]
    def find_field(possible):
        for c in columns:
            if any(p in c.lower() for p in possible):
                return c
        return None
    pid = find_field(['id', 'patient'])
    age = find_field(['age'])
    sex = find_field(['sex'])
    pathology = find_field(['pathology', 'diag'])
    evidences = find_field(['evidence', 'evidences'])
    init_evidence = find_field(['initial', 'init_evidence'])
    diff_diag = find_field(['differential', 'diff'])
    return {
        'path': path,
        'size_bytes': os.path.getsize(path),
        'columns': columns,
        'col_count': col_count,
        'row_count': row_count,
        'sample_rows': sample_rows,
        'identified_fields': {
            'patient_id': pid,
            'age': age,
            'sex': sex,
            'pathology': pathology,
            'evidences': evidences,
            'initial_evidence': init_evidence,
            'differential_diagnosis': diff_diag,
        }
    }

def inspect_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def main():
    base = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\data_sources\\ddxplus"
    extracts = {
        'train': os.path.join(base, 'train_extracted', 'release_train_patients'),
        'validate': os.path.join(base, 'validate_extracted', 'release_validate_patients'),
        'test': os.path.join(base, 'test_extracted', 'release_test_patients'),
    }
    csv_infos = {k: inspect_csv(p) for k, p in extracts.items()}
    # Check schema equality
    schemas = [info['columns'] for info in csv_infos.values()]
    schemas_identical = all(schemas[0] == s for s in schemas[1:])
    # JSON metadata
    evid_path = os.path.join(base, 'release_evidences.json')
    cond_path = os.path.join(base, 'release_conditions.json')
    evidences = inspect_json(evid_path)
    conditions = inspect_json(cond_path)
    # Evidence definitions count and type distribution
    ev_count = len(evidences)
    # Assuming each evidence dict has a 'type' key
    type_dist = {}
    for ev in evidences:
        t = ev.get('type') or ev.get('evidence_type') or ev.get('value_type')
        if t:
            type_dist[t] = type_dist.get(t, 0) + 1
    # Pathology count (conditions)
    path_count = len(conditions)
    # Hashes
    zip_files = {
        'train_zip': os.path.join(base, 'release_train_patients.zip'),
        'validate_zip': os.path.join(base, 'release_validate_patients.zip'),
        'test_zip': os.path.join(base, 'release_test_patients.zip'),
    }
    hashes = {name: sha256_file(p) for name, p in zip_files.items()}
    # hashes of extracted csvs
    for k, info in csv_infos.items():
        hashes[f"{k}_csv"] = sha256_file(info['path'])
    # hashes of json metadata
    hashes['evidences_json'] = sha256_file(evid_path)
    hashes['conditions_json'] = sha256_file(cond_path)
    # Output results
    result = {
        'extracted_files': csv_infos,
        'schemas_identical': schemas_identical,
        'json_metadata': {
            'evidence_definitions_count': ev_count,
            'evidence_type_distribution': type_dist,
            'pathology_count': path_count,
            'evidences_path': evid_path,
            'conditions_path': cond_path,
        },
        'hashes': hashes,
    }
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
