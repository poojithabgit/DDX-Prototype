import csv

with open('sample_data/symptoms_normalized.csv', encoding='utf-8') as f:
    syms = list(csv.DictReader(f))
present = [s for s in syms if s['assertion'] == 'present']
absent  = [s for s in syms if s['assertion'] == 'absent']
prov_map = [s for s in syms if s['mapping_status'] == 'provisional']
print(f'Symptoms present: {len(present)}, absent: {len(absent)}, provisional mapping: {len(prov_map)}')
print('Sample absent:', absent[0])
print('Sample provisional:', prov_map[0] if prov_map else 'None')
print()

with open('sample_data/vitals.csv', encoding='utf-8') as f:
    vitals = list(csv.DictReader(f))
print('Vitals temps:', [v['temperature_c'] for v in vitals])
print('Vitals SpO2:', [v['spo2_percent'] for v in vitals])
print()

with open('sample_data/lab_results.csv', encoding='utf-8') as f:
    labs = list(csv.DictReader(f))
for lab in labs:
    unit_match = lab['unit'] == lab['ucum_unit']
    print(lab['encounter_id'], lab['test_name'], 'val=' + lab['value'],
          'unit=' + lab['unit'], 'reflo=' + lab['reference_low'],
          'refhi=' + lab['reference_high'], 'unit_match=' + str(unit_match))
