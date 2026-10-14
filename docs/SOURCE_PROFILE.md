# Source profile (Stage 1 one-pager, written late and from the files on disk)

| | Vanga (Dattam Labs) | Vaquill (Open India Law) |
|---|---|---|
| What was downloaded | `metadata/` only: JSON, tar and parquet. No PDFs. | `in_supreme-court_judgments.parquet` and `in_central_legislation.parquet` only |
| Files | JSON 43,552 files (232 MB); tar 154 files (268 MB); parquet 77 files (49 MB); 77 `year=` folders, 1950 to 2026 | 2 files |
| Rows | 43,552 rows in 77 parquet files, equal to the JSON file count (5,181 are misfiled duplicates of the same judgment under a second year folder; 38,371 distinct judgments) | Judgments: 1,113,313 rows × 31 columns, one row per text chunk, 37,014 distinct `case_id`; 3.76 GB. Legislation: 74,484 rows × 29 columns |
| Licence | CC-BY-4.0 (see `LICENCES.md`) | CC BY 4.0 data, Apache-2.0 scripts (see `LICENCES.md`) |
| Integrity | `raw/MANIFEST.sha256` lists all 43,786 raw files; `pipeline/04_manifest.py` re-verifies it | `SHA256SUMS.json` upstream lists only the Kerala file; our own hashes are in `raw/vaquill/SHA256_LOCAL.txt` (`DECISIONS.md` D2) |

Column-level profile, null rates and the field mapping are in `SCHEMA_COMPARISON.md`. Discrepancies from the brief are `DECISIONS.md` D1 to D13.
