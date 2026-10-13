# Decisions and discrepancies

Each entry says what the prompt assumed, what the real data showed, and what was chosen. Newest at the bottom.

## Environment

| # | Decision | Why |
|---|---|---|
| E1 | **Localhost only, no AWS, no Hugging Face token.** The platform runs on Docker Compose on one machine. No cloud provisioning, billing alarm, S3 backup or public HTTPS in this phase. | User instruction. Replaces Stage 0 items 2 to 5 and the S3 parts of Stages 6 and 8. |
| E2 | Vanga is fetched anonymously over HTTPS with `aws s3 sync --no-sign-request`. The AWS credentials in the sandbox are deliberately unset in the script. | The bucket is public. The provided keys were invalid. |
| E3 | Vaquill was downloaded anonymously with `curl -C -` from `huggingface.co`. No token was needed when it was downloaded, although the dataset is marked gated (`gated: auto`). | The download worked without credentials. If access is later withdrawn, set `HF_TOKEN`; the script uses it when present. |
| E4 | Downloads and processing happen in a temporary cloud sandbox. `raw/` is git-ignored. If the sandbox is recycled, `raw/` is lost and both download scripts must be re-run (they resume). | Data is too large for git. |

## Stage 1 and 2 discrepancies

| # | Prompt said | Data shows | Chosen |
|---|---|---|---|
| D1 | Vaquill Supreme Court file name contains `supreme`. | `in_supreme-court_judgments.parquet`. | Used as is. |
| D2 | Verify Vaquill files with `SHA256SUMS.json`. | The upstream file lists only `in_kerala_judgments.parquet`. | Recorded our own SHA-256 in `raw/vaquill/SHA256_LOCAL.txt`; this proves integrity of our copy, not equality with the publisher's. File size matched the server's `content-length`. |
| D3 | Vanga metadata: keep the PDF URL fields. | There are none. `raw_html` has only `href='#'`; no `judis/` or `jonew/` string exists in any field of either source; Vaquill `source_url` is 100% empty. | `judgment.pdf_url` is empty until Stage 8, then derived from `path` and `year` and the S3 key layout, after confirming that layout. The `judis/` to `jonew/` fix is not needed on this data. |
| D4 | Fields: `diary_number`, `case_number`, `bench`, `date_of_registration`. | No diary number in either source. `case_number`, `bench`, `date_of_registration`, `source_url`, `description` are 100% empty in Vaquill. | These canonical columns stay empty and are reported as "no source", not as merge failures. |
| D5 | Vaquill is chunk-level with one row per chunk. | True, but it also holds **regional-language chunk sets** (16 language codes). | Chunk key is (`case_id`, `language_code`, `chunk_index`). `judgment_text` uses the English set; 1,418 cases (3.83%, 93% from the 2000s) have no English set and are flagged. |
| D6 | Wrong years such as 1902 instead of 2002. | No decision date is before 1950-01-28 or in the future in either source. The year problem that exists is `year` is a law-report year, not the decision year (23.78% of Vanga rows, 14.51% of Vaquill rows differ). | Decision year is always derived from the parsed decision date. |
| D7 | Same judgment under more than one decision date. | Not found within a path (0). 70 INSC ids carry several dates, but they are separate reports sharing one INSC id (96 ids, a different citation for every one). | INSC id is not a unique key in Vanga; match on INSC id plus citation, review queue for the rest. |
| D8 | Vanga is one row per judgment. | 43,552 rows for 38,371 distinct `path`. All 5,181 duplicated paths are copies filed under two `year=` folders. | Keep the copy whose partition year equals its decision-date year. This selects exactly one copy for every duplicated path (verified). Copies differ only in `raw_html`, `available_languages` and `scraped_at`. |
| D9 | Match tier 1 is diary number plus year, or PDF path / `source_url`. | No diary number, no PDF path or `source_url` on the Vaquill side. | Tier 1 becomes the normalised INSC `case_id` (space to underscore) plus citation. Tiers 2 and 3 are re-assessed in Stage 3 once the data is loaded. |
| D10 | (not in the prompt) Vanga JSON has a `citation_year` the parquet lacks. | Present in every JSON file; **identical to the parquet `year` column on all 43,552 rows**, so it carries no extra information. | Kept inside `source_vanga_raw.raw` for completeness. |
| D11 | 152 Vanga rows have an empty `case_id` and `nc_display`. | None match Vaquill on title plus date. | They are keyed on `path`. They stay Vanga-only. |
| D12 | `text_original` holds the original text. | Identical to `text` on all 1,113,313 rows. Every chunk starts with a `Case: ... Section: ...` header added by Vaquill. | Keep `text_original` as delivered (nothing is dropped). Strip the header when assembling `judgment_text`. |
| D13 | `bench_strength` could be an independent field. | It always equals `len(judges)` in Vaquill. | Store it, but flag it as derived. |

## Stage 3 decisions (from the review of the Stage 2 comparison)

| # | Decision | Why |
|---|---|---|
| S1 | Vanga is the canonical source; Vaquill enriches with full text, judges list and language-specific chunks. | Review decision 1. Vaquill is a subset of Vanga by judgment coverage. |
| S2 | `judgment_id` = uuid5 of the Vanga `path` (fixed namespace). | Stable across rebuilds, no sequence state, one id per distinct report. |
| S3 | Matching key is normalised INSC id plus citation, confirmed by decision date. Anything else is queued, not merged. | Review decision 2. INSC ids are shared by 96 distinct reports. |
| S4 | Folder-year rule removes the 5,181 misfiled duplicate rows from the canonical set. All raw rows stay in `source_vanga_raw`. | Review decision 3. |
| S5 | `decision_year` = year of the parsed decision date, enforced by a CHECK. Both source `year` fields are kept. Source-year disagreements are logged as `source_year` conflicts with one fixed rule. | Review decision 3. |
| S6 | `text_status` (`english` / `translation_only` / `none`) and `judgment_language` separate "no English text" from "no text at all". Judgments without text are kept with full metadata. | Review decision 4. |
| S7 | Chunk key is (`judgment_id`, `language_code`, `chunk_index`). `judgment_chunk.text` keeps the `Case: ... Section: ...` header; it is removed only in `judgment_text`. | Review decision 5. |
| S8 | Chunks are placed by `char_start` offset when assembling text, not concatenated. | In a 300-case sample about 79% of neighbouring chunk windows overlap and about 21% leave a gap (the sampled gaps were 2 characters), so plain concatenation would duplicate text. Gap sizes are measured over all data in the build (`small_gap_count`, `large_gap_count`). |
| S9 | Case-level Vaquill metadata is stored once per case in `source_vaquill_raw` instead of on every chunk row; `text_original` is NULL where it equals `text`. | Both are lossless (metadata constant per case: 0 exceptions; `text_original` equal to `text` on 100% of rows) and avoid duplicating about 4 GB of text. Asserted at every build. Easy to reverse if you want the columns repeated. |
| S10 | `case_number`, `diary_number`, `pdf_url` are NULL columns; Vanga `description` (OCR junk) is not used. | Review decision 6. |
| S11 | `bench_strength` is derived from the chosen judges list, with provenance `derived`. | Vaquill's own value is `len(judges)`; Vanga has none. |
| S12 | Postgres is not loaded and no secondary indexes are built in this stage. The migrations were checked on a scratch PostgreSQL 16 only. | Review boundary: schema, transformation and validation first. |

## Open questions for the user

- With Vaquill a strict subset of Vanga (0 Vaquill-only judgments, near-total field agreement), the merge mostly attaches Vaquill's full text and judges list to Vanga's records. Confirm that is the intended shape before Stage 3.
- Vanga has 1,109 judgments with no Vaquill record (mostly 2025 to 2026 and the 2008 and 2006 gaps). They get no full text until another source is found.
