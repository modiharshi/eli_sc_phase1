# Schema comparison (Stage 2)

**Status: Vanga side complete. Vaquill side pending** (files not available, see `SOURCE_PROFILE.md`). The mapping table and the Vaquill chunk-consistency checks cannot be done until the Vaquill parquet is in `raw/vaquill/`.

## Vanga columns

Full profile with 3 samples each: `docs/profile/vanga_columns.csv`. Percentages over 43,552 rows.

| Column | Origin | Null/empty % | Distinct | Notes |
|---|---|---|---|---|
| title | parquet | 0 | 38,066 | `PETITIONER versus RESPONDENT` |
| petitioner | parquet | 0.04 | 31,245 | |
| respondent | parquet | 0.04 | 25,864 | |
| description | parquet | **97.3** | 1,156 | Only recent cases ("Issue for Consideration ...") |
| judge | parquet | 0.04 | 1,729 | Comma-separated bench |
| author_judge | parquet | **100** | 0 | Always empty. The author **is** recoverable: `raw_html` marks the author with a `*` tooltip on 33,469 judgments |
| citation | parquet | 0 | 38,371 | SCR only, e.g. `[1995] SUPP. 5 S.C.R. 500`. Unique per judgment |
| case_id | parquet | 0.35 | 38,124 | **Misnamed:** it is the neutral citation (`1995 INSC 759`), identical to `nc_display` on every row. Not a case number |
| cnr | parquet | 0 | 38,371 | `ESCR…` e-SCR number, unique per judgment |
| decision_date | parquet | 0 | 11,104 | String `DD-MM-YYYY`; 0 unparseable |
| disposal_nature | parquet | 2.48 | 32 | |
| court | parquet | 0 | 1 | Always "Supreme Court of India" |
| available_languages | parquet | 2.7 | 488 | e.g. `ENG,HIN,PUN` |
| raw_html | parquet | 0 | 43,076 | Scraped listing HTML. Holds fields missing from the parsed columns (below) |
| path | parquet | 0 | 38,371 | SCR volume/page key, e.g. `2023_14_935_958`; `S_` prefix = SCR Supplement (7,642). Best Vanga primary key |
| nc_display | parquet | 0.35 | 38,124 | `1995INSC759` |
| scraped_at | parquet | 0 | 43,552 | |
| year | partition | 0 | 77 | **Not the decision year for duplicates** (see below) |

### Fields only in `raw_html` (extracted by regex)

| Field | Coverage | Notes |
|---|---|---|
| Case No | 100% | e.g. `CIVIL APPEAL No. 5752/1995`; 37,670 distinct. **The real case number** |
| Bench | 100% | `2 Judges` (27,839), `3 Judges` (7,945), `5 Judges` (1,973) … 30 rows say just `Judges` |
| Coram with author marker | 99.96% | Author flagged on 33,469 judgments |
| Headnote snippet | 99.94% | Truncated headnote text, OCR noise in older years |
| Decision Date / Disposal | 100% / 97.5% | Identical to the parquet columns on every row |

## Known upstream issues, quantified

| Issue | Result |
|---|---|
| Same judgment under two years | **5,181 judgments (13.5%) appear twice**, once under the decision year and once under another year (usually the SCR report year). Both copies have identical parsed fields. This matches the ~14% "wrong year" figure from the earlier analysis. Every judgment has one copy in its true decision year. 44 rows sit more than one year away |
| Fix | Dedupe on `path`, and derive the year from the parsed decision date, never from the partition |
| Judgments filed under impossible years (e.g. 1902) | **None** in Vanga: all dates are 1950-03-14 to 2026-09-01 |
| Same neutral citation, different decision dates | **70 NCs** (96 NCs span more than one `path`). Example: `2016INSC496` is on a 2015 and a 2016 judgment in the same case. So NC is **not** a safe unique key for matching |
| Same case number, different decision dates | 491 case numbers. Usually separate judgments in the same matter, not errors |
| Same title + date, different `path` | 27 |
| `judis/NNNN.pdf` links needing `jonew/` | **Not present in Vanga** (the one hit for "judis" is the Latin phrase *coram non judis*). Vanga PDF keys are `path`-based. This issue must be Vaquill's; test it when Vaquill arrives |
| SCC / AIR identifiers | **None.** Only SCR (100%) and INSC (99.65%). This limits Phase 2 citation resolution, since most judgments cite SCC/AIR |

## Pending for Vaquill
- Every column with type, null %, distinct and samples.
- Distinct `case_id` count, and whether metadata is constant across a case's chunks.
- The mapping table: same field, Vanga only, Vaquill only, conflicting.
- The `judis/` → `jonew/` link test.
