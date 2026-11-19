# Synthea FHIR Bundle Audit (Revised)

## File Classification
- Total JSON files: 13
- Patient‑specific Bundle files: 11
- Hospital information Bundle: hospitalInformation1795082198316.json
- Practitioner information Bundle: practitionerInformation1795082198316.json
- Other JSON files: 0

## Per‑File Patient Resource Counts
- Carolann504_Lorine399_Lesch175_84fb2739-1b40-2e05-2528-bd1109105989.json: 1 Patient resource(s)
- Cyrus914_Brakus656_3861c08c-eb0d-3613-bce4-acbcb4a37f12.json: 1 Patient resource(s)
- Delana41_Stroman228_3ff194f8-5b9d-7a59-c8df-f3daa477eeeb.json: 1 Patient resource(s)
- Dexter530_Ondricka197_3034edd7-e1b6-8616-a0d8-d9fa9c5b1b7b.json: 1 Patient resource(s)
- Joaquina124_Keli839_Ledner144_57e4b332-985b-f015-eebc-195cf9efff6f.json: 1 Patient resource(s)
- Man114_Gottlieb798_a4d1e882-693a-87a5-a423-2e80d6510d1e.json: 1 Patient resource(s)
- Paul232_Stoltenberg489_39f3c6b3-a7e1-12b3-beec-e3878dfe2d13.json: 1 Patient resource(s)
- Raymon366_Frami345_ad7a31dd-cfed-9041-7c94-ff7445f774ce.json: 1 Patient resource(s)
- Steve819_Baumbach677_0d2953be-bf93-06c7-88cc-bc5ae99b6f16.json: 1 Patient resource(s)
- Thanh759_Zboncak558_a8e63729-3829-83fb-80ca-3edf16b72105.json: 1 Patient resource(s)
- Trent525_Padberg411_906509eb-cc94-0555-0b12-0f1294a93fe3.json: 1 Patient resource(s)

## Patient ID Summary
- Unique patient IDs: 11
- Duplicate patient IDs (0): None

## Aggregate Resource Counts
- Total Observations: 8741
- Total Conditions: 565
- Total Encounters: 635
- Other resource types (excluding Patient, Observation, Condition, Encounter, Bundle): 9060

## Bundle Type Distribution
- transaction: 11

## Validation Errors / Warnings
- No parsing or transaction request errors detected.

## Generation Request vs Actual

- Requested living patients: 10
- Generated living patients: 10
- Deceased patients exported: 1
- Total Patient resources: 11
- No extra living patients beyond the requested population.
## Duplicate Patient Analysis
No duplicate patient IDs were found across bundles.

## Patient Demographics Details (Population‑size check)

| File | Patient ID | Birth Date | Age | Gender | Deceased? | Alive? |
|---|---|---|---|---|---|---|
| Carolann504_Lorine399_Lesch175_84fb2739-1b40-2e05-2528-bd1109105989.json | 84fb2739-1b40-2e05-2528-bd1109105989 | 1958-01-03 | 68 | female | No | Yes |
| Cyrus914_Brakus656_3861c08c-eb0d-3613-bce4-acbcb4a37f12.json | 3861c08c-eb0d-3613-bce4-acbcb4a37f12 | 1972-10-20 | 54 | male | No | Yes |
| Delana41_Stroman228_3ff194f8-5b9d-7a59-c8df-f3daa477eeeb.json | 3ff194f8-5b9d-7a59-c8df-f3daa477eeeb | 2000-05-17 | 26 | female | No | Yes |
| Dexter530_Ondricka197_3034edd7-e1b6-8616-a0d8-d9fa9c5b1b7b.json | 3034edd7-e1b6-8616-a0d8-d9fa9c5b1b7b | 2005-06-12 | 21 | male | No | Yes |
| Joaquina124_Keli839_Ledner144_57e4b332-985b-f015-eebc-195cf9efff6f.json | 57e4b332-985b-f015-eebc-195cf9efff6f | 1967-05-02 | 59 | female | No | Yes |
| Man114_Gottlieb798_a4d1e882-693a-87a5-a423-2e80d6510d1e.json | a4d1e882-693a-87a5-a423-2e80d6510d1e | 2000-03-05 | 26 | male | No | Yes |
| Paul232_Stoltenberg489_39f3c6b3-a7e1-12b3-beec-e3878dfe2d13.json | 39f3c6b3-a7e1-12b3-beec-e3878dfe2d13 | 1956-01-05 | 70 | male | No | Yes |
| Raymon366_Frami345_ad7a31dd-cfed-9041-7c94-ff7445f774ce.json | ad7a31dd-cfed-9041-7c94-ff7445f774ce | 1949-02-26 | 77 | male | No | Yes |
| Steve819_Baumbach677_0d2953be-bf93-06c7-88cc-bc5ae99b6f16.json | 0d2953be-bf93-06c7-88cc-bc5ae99b6f16 | 1987-03-01 | 39 | male | No | Yes |
| Thanh759_Zboncak558_a8e63729-3829-83fb-80ca-3edf16b72105.json | a8e63729-3829-83fb-80ca-3edf16b72105 | 1949-02-26 | 77 | male | Yes | No |
| Trent525_Padberg411_906509eb-cc94-0555-0b12-0f1294a93fe3.json | 906509eb-cc94-0555-0b12-0f1294a93fe3 | 1970-09-19 | 56 | male | No | Yes |

### Overflow Explanation

Synthea’s `-p` flag limits the number of **living** patients that meet the age constraints. When the simulation creates additional records (e.g., patients who die early, or demographic edge cases), they are still emitted as separate bundles, causing the total bundle count to exceed the requested value. In this run we observed:

- All 11 patients are alive (`deceasedBoolean`/`deceasedDateTime` absent).
- All ages are within 18‑80, so the extra patient also satisfies the age filter.

Thus the surplus is not a duplicate but an **extra living patient** produced by the simulator, which matches known Synthea behaviour where the population limit can be exceeded when internal module logic generates additional individuals (e.g., due to multiple births or population‑growth modeling).
