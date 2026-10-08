# data/

> ⚠️ **IMPORTANT:** All of the datafiles are excluded from this repository due to size and for privacy. Download them from the shared Google Drive folder and place them inside a folder named `data/` (following the structure above) before running the pipeline or notebooks: [Google Drive](https://drive.google.com/drive/folders/1S5HNbGpkxreGC_kPnD-coFSqL1GdTISk?usp=drive_link).

## Structure

```
data/
├── edcom/      # Raw EDCOM-provided files (see edcom/README.md)
├── exports/    # Final per-question output tables (see exports/README.md)
├── external/   # Raw reused DepEd / PSA datasets (enrollment, coordinates, poverty, population, geodata)
└── *.parquet   # Processed analysis tables (listed below)
```

## Processed files in `data/`

Parquet versions of the processed tables are listed below. Each `sned_access_*` table also has a `.csv` copy.

| File                                   | Relevance                                                                                                                                                                     |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| sned_database_tidy_long.parquet        | SNED Database reshaped to one row per school × level × program × diagnosis type × category × grade × sex (~66M rows); base for learner counts and disability profiles (Q1–Q6) |
| sned_facility_roster.parquet           | Roster of ILRCs, SPED Centers, and SNED-implementing schools with coordinates and PSGC codes; the facility list for 3 km access (Q3–Q6)                                       |
| sned_access_public_summary.parquet     | Per public school: number of facilities within 3 km, nearest facility distance, and 3 km access flag (Q4–Q6)                                                                  |
| sned_access_public_pairs.parquet       | Facility–public school pairs within 3 km, with road and haversine distances (Q4)                                                                                              |
| sned_access_public_lgu_counts.parquet  | Per municipality: public schools with and without 3 km access (Q4–Q6)                                                                                                         |
| sned_access_pubpriv_summary.parquet    | Same as the public summary, with private schools included in the population (Q4–Q6)                                                                                           |
| sned_access_pubpriv_pairs.parquet      | Same as the public pairs, with private schools included (Q4)                                                                                                                  |
| sned_access_pubpriv_lgu_counts.parquet | Same as the public municipality counts, with private schools included (Q4–Q6)                                                                                                 |
