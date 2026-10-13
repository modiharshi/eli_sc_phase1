# Source profile

Generated from `pipeline/02_profile_vanga.py` (2026-10-13). Machine-readable detail is in `docs/profile/`.

## Vanga (Dattam Labs, `s3://indian-supreme-court-judgments`, anonymous)

| | |
|---|---|
| Objects downloaded | 231 (77 `metadata.parquet`, 77 `metadata.tar`, 77 `metadata.index.json`), checksummed in `docs/manifests/vanga_downloads.csv` |
| Raw JSON | 43,552 files unpacked from the tars into `raw/vanga/metadata/json/` (identical set to the bucket's `metadata/json/`) |
| Size on disk | parquet 47 MB, tar 257 MB, JSON 338 MB |
| Year partitions | 77 (1950 to 2026) |
| Rows | 43,552 |
| Distinct judgments (`path`) | **38,371** |
| Decision dates | 1950-03-14 to 2026-09-01, all parse as `DD-MM-YYYY` |
| Columns | 17 parquet + `year` partition; JSON files hold only `path`, `citation_year`, `nc_display`, `scraped_at`, `raw_html` |

Rows and files per year: `docs/profile/vanga_per_year.csv`. Every parquet `path` has a matching JSON file and vice versa.

**No PDFs or judgment tars were downloaded** (Stage 8 only).

## Vaquill (Open India Law, Hugging Face `vaquill/open-india-law`)

**Not downloaded.** The dataset is gated and `huggingface.co` is blocked by this environment's network policy (proxy 403), and `HF_TOKEN` is not set. Files needed: `in_supreme-court_judgments.parquet`, `in_central_legislation.parquet`, `SHA256SUMS.json`.
