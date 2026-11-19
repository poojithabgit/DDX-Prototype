import os, json, hashlib
import pandas as pd

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def get_header(path):
    with open(path, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
    return first_line.split(',')

def count_rows_and_samples(path, sample_n=3):
    row_count = 0
    samples = []
    for chunk in pd.read_csv(path, chunksize=100000):
        row_count += len(chunk)
        if len(samples) < sample_n:
            needed = sample_n - len(samples)
            samples.extend(chunk.head(needed).to_dict(orient='records'))
    return row_count, samples

def main():
    base = r"C:\\Users\\DELL\\Desktop\\prototype of madd\\data_sources\\ddxplus"
    extracts = {
        'train': os.path.join(base, 'train_extracted', 'release_train_patients'),
        'validate': os.path.join(base, 'validate_extracted', 'release_validate_patients'),
        'test': os.path.join(base, 'test_extracted', 'release_test_patients')
    }
    csv_info = {}
    for key, path in extracts.items():
        header = get_header(path)
        rows, samples = count_rows_and_samples(path)
        csv_info[key] = {
            'path': path,
            'size_bytes': os.path.getsize(path),
            'header': header,
            'col_count': len(header),
            'row_count': rows,
            'sample_rows': samples,
            'sha256': sha256_file(path)
        }
    # JSON metadata
    evid_path = os.path.join(base, 'release_evidences.json')
    cond_path = os.path.join(base, 'release_conditions.json')
    with open(evid_path, 'r', encoding='utf-8') as f:
        evidences = json.load(f)
    with open(cond_path, 'r', encoding='utf-8') as f:
        conditions = json.load(f)
    ev_count = len(evidences)
    type_dist = {}
    for ev in evidences.values():
        t = ev.get('data_type') or ev.get('type') or ev.get('evidence_type')
        if t:
            type_dist[t] = type_dist.get(t, 0) + 1
    path_count = len(conditions)
    # Sample condition entry
    sample_condition = next(iter(conditions.values())) if conditions else None
    # Hashes for JSON files
    json_hashes = {
        'evidences_json': sha256_file(evid_path),
        'conditions_json': sha256_file(cond_path)
    }
    result = {
        'csv_info': csv_info,
        'evidence_definitions_count': ev_count,
        'evidence_type_distribution': type_dist,
        'pathology_count': path_count,
        'sample_condition': sample_condition,
        'json_hashes': json_hashes
    }
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
