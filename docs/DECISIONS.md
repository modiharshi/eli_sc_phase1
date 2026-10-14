# Decisions and discrepancies

Each entry says what the prompt assumed, what the real data showed, and what was chosen. Newest at the bottom.

## Environment

| # | Decision | Why |
|---|---|---|
| E1 | **Localhost only, no AWS, no Hugging Face token.** The platform runs on Docker Compose on one machine. No cloud provisioning, billing alarm, S3 backup or public HTTPS in this phase. | User instruction. Replaces Stage 0 items 2 to 5 and the S3 parts of Stages 6 and 8. |
| E2 | Vanga is fetched anonymously over HTTPS with `aws s3 sync --no-sign-request`. The AWS credentials in the sandbox are deliberately unset in the script. | The bucket is public. The provided keys were invalid. |
| E3 | Vaquill was downloaded anonymously with `curl -C -` from `huggingface.co`. No token was needed when it was downloaded, although the dataset is marked gated (`gated: auto`). | The download worked without credentials. If access is later withdrawn, set `HF_TOKEN`; the script uses it when present. |
| E4 | Downloads and processing happen in a temporary cloud sandbox. `raw/` is git-ignored. If the sandbox is recycled, `raw/` is lost and both download scripts must be re-run (they resume). | Data is too large for git. |
| E5 | Ponytail plugin pinned to v5.2.0 (commit `2961b52f…`), installed **disabled** by the Cloud Setup script (`infra/ponytail_setup.sh`, user scope) and verified by commit SHA and per-file hashes without running plugin code; then **activated by the user's explicit instruction** by setting `enabledPlugins` to `true` in committed `.claude/settings.json` (auto-update off, default mode off); it installs nothing (cloud sessions ignore declared plugins). Persistence depends on the environment snapshot; `env` default-off is documented, not observed. See `docs/PONYTAIL.md`. | User decision; safe-by-default design. |

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

## Stage 4 decisions (load, constraints, indexes)

| # | Decision | Why |
|---|---|---|
| S13 | **NUL characters.** The raw Vaquill data has U+0000 in 37 chunks (36 Hindi, 1 Malayalam; 10 judgments, none English), which PostgreSQL text cannot store. In the database copy each NUL is replaced one-for-one by U+2400 (`␀`); every changed value is listed in `text_sanitization_log` (47 rows: 37 chunks, 10 assembled texts). Raw Parquet and the Stage 3 build output keep the original bytes. | Found by the loader's pre-check before anything was written. A length-preserving, logged, reversible substitution keeps offsets valid and avoids dropping data. It is the only place where the database text differs from the build output. The fingerprint check hashes the database against the parquet with the same replacement applied. **Open for review.** |
| S14 | Migration `0006_text_quality.sql` adds `chunks_contiguous`, `offset_drift_chunks` and `incompleteness_reason` to `judgment_text`, the `judgment_retrieval_status` view and the `text_sanitization_log` table. Migrations 0001 to 0005 are unchanged. | Review decisions 3 and 5: completeness, overlap disagreement and offset drift are tracked per text, separately from language availability, and are visible to retrieval and evaluation. The build was extended to produce the columns; two builds were identical. |
| S15 | The 277 vs 276 discrepancy: **277 is the number of incomplete text sets** (verified build output and database). 276 counted only sets with a text gap larger than 2 characters; one more set has missing chunks without a gap. Reconciled in the Stage 4 report with exact set arithmetic. | Review decision 4. |
| S16 | Local PostgreSQL 16 on port 5433, 127.0.0.1 only, password authentication, roles `eli_admin` and `eli_readonly`, `wal_level = minimal`. The load is one transaction. Backups are `pg_dump`. | Localhost deployment (E1). Minimal WAL makes the bulk load faster and keeps WAL from filling the 22 GB of free disk. |
| S17 | Legislation (`legislation_act` 1,568 rows, `legislation_section` 74,484 rows) is loaded from the Vaquill file. Act-level columns were checked to be constant per act, so nothing is lost. | These tables were part of the approved schema and the Stage 3 plan said they load in Stage 4. It is not an alternate judgment text source. |
| S18 | Secondary indexes are chosen by measurement: each candidate is built alone, its size and build time recorded, and it is kept only if an affected query gets at least 3x and at least 5 ms faster at p50, or it fixes a missed target. Everything measured, including dropped candidates, is in the Stage 4 report. | Review decision 6: no speculative indexes. Two borderline drops are noted in the report. |
| S19 | English full-text search uses a stored `judgment_text.tsv_en` tsvector column with a GIN index. An index on the expression `to_tsvector('english', text)` was built and measured too; ranked queries on it took 10 to 165 s. **Only English is indexed.** Other languages have no full-text index and no search configuration. | Measured: see the Stage 4 report. Non-English retrieval is out of scope for this stage. |
| S20 | Search behaviour limits are visible, not repaired: incomplete sets, overlap disagreements and offset drift stay as delivered and are exposed through `judgment_text` and `judgment_retrieval_status`. | Review decision 3. |

## Stage 5 and 6 decisions (frontend, quick wins)

| # | Decision | Why |
|---|---|---|
| S21 | **Stack: FastAPI plus server-rendered Jinja2 pages, plain CSS, about 15 lines of JavaScript (copy buttons). No React, no Node build.** The brief said "React or Next.js"; this is a deviation. | One process, nothing to build, every page testable with plain HTTP and one headless-browser pass, charts are inline SVG. The app is table- and text-heavy, not interaction-heavy. Reversible: the API in `api/rest.py` already serves JSON for a future SPA. |
| S22 | **Login:** local username and password, argon2 hashes, server-side sessions (12 h, random 256-bit token stored hashed), cookie `HttpOnly` and `SameSite=Strict`, same-origin check on POST, five failed logins per user per ten minutes lock that user out for the window. The server binds to 127.0.0.1 only. Accounts: `python -m api.manage create-user NAME ROLE`. | Approved by you. Roles: admin, tester, viewer; review decisions, hide-judgment, API keys and benchmark query lists are admin-only. |
| S23 | **Three database roles.** `eli_readonly` for every read (search, explorer, SQL console), `eli_app` for writes to app tables only (sessions, bookmarks, notes, error reports, review decisions, API usage, hide list) and `eli_admin` only in the CLI and pipeline. `app_user`, `app_session` and `api_key` are unreadable by `eli_readonly` and are not listed in the explorer. | Least privilege; the SQL console cannot read password hashes or keys. |
| S24 | **NUL (S13) accepted.** The raw files keep the original bytes. The 37 NUL chunks belong to **10 judgments** (not 37), none with English text. Their texts are labelled `noisy` (reason `contains_substituted_nul`). | Your decision 1. The "37" in the instruction is the chunk count; the judgment count is 10. |
| S25 | **`title_fuzzy`:** one change, `pg_trgm.similarity_threshold` 0.3 to 0.4 for typo-tolerant title search. Same run, 100 titles with one typo each: 0.3 gives p50 176 ms, p95 357 ms; 0.4 gives p50 54 ms, p95 197 ms (target 300 ms); the original title is still returned in the top 20 for 100 of 100. The app sets 0.4 per request for `title_fuzzy` and its text search; the database default is unchanged. `pipeline/12_title_fuzzy_check.py`, `logs/title_fuzzy_check.json`. | Your decision 2. Target now met. |
| S26 | **English-only full-text index** accepted. Non-English texts show their language and, where a judgment has no English text, the label "no English text" (search results and judgment page). A language-neutral index is a later task. | Your decision 3. |
| S27 | **Incomplete or inconsistent English texts** (112 at Stage 4; the quality table's "fair" set has 117 including other causes) stay visible, are badged "incomplete text" and their relevance score is halved. Filter "only incomplete text" is available. | Your decision 4. |
| S28 | **Judgments without English text** (1,357 with none, 1,418 translation-only) remain metadata-only. A targeted Vanga PDF download with OCR for just those is **planned after Stage 6 and waits for your approval**; nothing was downloaded. | Your decision 5. |
| S29 | **Bench size.** Both sources list one judge for 91% of judgments, so `bench_strength` under-counts (Kesavananda Bharati lists 1 judge, not 13). Migration 0009 adds `judgment_bench_estimate` read from the text header (88% coverage, 91% agreement where the source lists 2 or more) and the view `judgment_bench`. The Bench finder uses the larger of the two and labels header-based values as estimates. `judgment.bench_strength` is unchanged. See `BENCH_ESTIMATE.md`. | Without it the Constitution Bench finder cannot find Constitution Benches. This reads only text already loaded; it is not an alternate text source. **Open: confirm you are happy with an estimate being used.** |
| S30 | **Stage 7 parts done now:** attribution footer, "not the official record" banner on judgment pages and in every export, admin hide-judgment (removes from search, API, exports and facets; audit row in `review_audit`; `judgment_hidden`), `pg_dump` script writing to `/var/backups/eli`. **Deferred:** HTTPS, S3 backups, the public takedown form (`takedown_request` exists). The sandbox has no cron or systemd, so `infra/backup_loop.sh` is a sleep-until-02:15 loop that stops if the container restarts. | Your instruction. |
| S31 | **Time-to-decision analytics: unavailable**, because `date_of_registration` is in neither source (0 rows). The page says so. | Brief rule: do not fake it. |
| S32 | **v3 gaps** found and closed by migrations 0008 and 0009 without a reload: `docs/V3_GAP_ANALYSIS.md`. `07_load_postgres.py` now applies migrations 0001 to 0006 only; 0007 is applied by `09_index_benchmark.py --apply` and 0008 onward by `11_derive.py`, so a `--rebuild` followed by `09 --apply` and `11_derive.py` reproduces the full state. | Keeps matviews and derived tables out of the load transaction. |
| S33 | `docs/LICENCES.md` and `docs/SOURCE_PROFILE.md` (Stage 1 deliverables) were missing and are now written. The AWS registry page could not be fetched (proxy denied), so the Vanga licence statement comes from its GitHub README. | Honest record of what was and was not read. |

## Open questions for the user

Settled in review: merge shape, storage optimisations, NUL handling, `title_fuzzy`, English-only index, incomplete-text display, metadata-only judgments, local login, Stage 7 scope. Still open:

1. **Bench size estimate (S29).** Confirm that a header-based estimate, labelled as such, is acceptable for the Constitution Bench finder.
2. **Targeted PDF download** for the 2,775 judgments without English text (S28): your approval is planned after Stage 6, which is now done. Needed from you: yes or no, and whether OCR may use a local tool (tesseract) or must wait for the Stage 9 LLM budget.
3. **Borderline indexes (S18).** Unchanged from Stage 4.
4. **Licence conditions.** `LICENCES.md` flags that the Hugging Face gating form was not read; please read it once before any public use.
