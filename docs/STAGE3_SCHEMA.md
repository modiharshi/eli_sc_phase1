# Stage 3: canonical schema, transformation rules and validation plan

For review before any Postgres load (Stage 4). Nothing is loaded into a database yet. The DDL in `db/migrations/` was applied to a scratch PostgreSQL 16 server to prove it is valid, and the transformation writes Parquet files to `build/` (git-ignored, rebuilt from `raw/`).

Results of running this design are in `docs/STAGE3_VALIDATION.md`.

## 1. Principles (from the review decisions)

1. **Vanga is canonical** for judgment records and metadata. Vaquill enriches with judges, language-specific chunks and assembled text.
2. **Identity:** one canonical judgment per distinct Vanga `path` after dedupe. `judgment_id` is the uuid5 of the path, so it is stable across rebuilds. The INSC id is **not** a key; matching uses normalised INSC id **plus citation** (and decision date as a confirmation).
3. **Nothing forced:** a match that is ambiguous, whose citation differs, or whose date disagrees goes to `match_review_queue` and is **not merged**.
4. **Raw is immutable:** `raw/` is only read. `raw/MANIFEST.sha256` records the hash of all 43,786 files; `04_manifest.py` re-verifies it. Staging tables keep every source row verbatim.
5. **Missing means NULL.** No value is invented. The OCR-junk Vanga `description` is not used for any canonical field (it stays in `source_vanga_raw`).
6. **Provenance for every canonical value** in `judgment_field_provenance`; every disagreement in `field_conflicts`.

## 2. Tables (migrations 0001 to 0005)

| table | grain | key | purpose |
|---|---|---|---|
| `source_vanga_raw` | one row per Vanga parquet row (43,552) | `source_row_id`; unique `(year_folder, path)`; one canonical copy per `path` | verbatim record as JSON, incl. misfiled duplicates, with `is_canonical_copy` and `dedupe_reason` |
| `source_vaquill_raw` | one row per Vaquill case | `vaquill_case_id` | verbatim case-level metadata as JSON (constant across chunks, verified) |
| `judgment` | one row per canonical judgment | `judgment_id`; unique `vanga_path` | canonical record (columns below) |
| `judgment_source_map` | one per judgment | `judgment_id`; unique `vaquill_case_id` | match method, confidence and status |
| `judgment_field_provenance` | judgment × tracked field | `(judgment_id, field_name)` | chosen source, chosen value, other source's value, reason |
| `field_conflicts` | one per disagreement | unique `(judgment_id, field_name)` | every source disagreement and how it was handled |
| `match_review_queue` | one per unmerged match | `review_id` | ambiguous, citation-conflict, date-conflict and orphan cases, with candidates |
| `judgment_judge` | judgment × bench position | `(judgment_id, position)` | raw and normalised judge name, source |
| `judgment_identifier` | judgment × identifier | unique `(type, value, judgment_id)` | INSC, SCR citation, CNR, Vanga path, NC display |
| `judgment_language` | judgment × language | `(judgment_id, language_code)` | PDF listed by Vanga vs text available from Vaquill, chunk counts |
| `judgment_chunk` | Vaquill chunk | **`(judgment_id, language_code, chunk_index)`**; unique `vaquill_chunk_id` | raw chunks, header kept |
| `judgment_text` | judgment × language | `(judgment_id, language_code)` | assembled text with completeness and quality counters |
| `downloads`, `pipeline_runs`, `merge_report`, `review_audit` | operational | | file checksums, run log, build metrics, review decisions |
| `legislation_act`, `legislation_section` | act / section | | loaded from `in_central_legislation.parquet` in Stage 4 |
| `judgment_paragraph`, `citation_mention`, `cites_edge`, `judgment_statute` | Phase 2 stubs | | created empty with foreign keys |

### `judgment` columns

| column | source and rule |
|---|---|
| `judgment_id` | uuid5 of `vanga_path` |
| `vanga_path`, `vanga_year_folder` | Vanga `path`; folder of the canonical copy |
| `insc_id` | Vanga `case_id` (`1960 INSC 103`), NULL if empty. Not unique |
| `title`, `petitioner`, `respondent`, `citation`, `disposal`, `court` | Vanga value; if empty, Vaquill value; else NULL. The other value is kept as `alt_value` when they differ |
| `decision_date` | Vanga `DD-MM-YYYY` parsed; Vaquill date only as fallback |
| `decision_year` | **always `year(decision_date)`**, enforced by a CHECK constraint |
| `vanga_year_field`, `vaquill_year_field` | the source `year` columns as delivered. Never used for `decision_year` |
| `cnr`, `available_languages` | Vanga only (language tokens lower-cased; `ENG` becomes `en`) |
| `bench_strength` | derived: number of judges on the chosen list; NULL if none |
| `case_number`, `diary_number`, `pdf_url` | no source in either dataset: always NULL (`pdf_url` is for Stage 8) |
| `text_status` | `english` / `translation_only` / `none` (derived from `judgment_text`) |
| `match_status` | `matched` / `in_review` / `vanga_only` |
| `quality_flags` | `empty_insc_id`, `insc_id_shared`, `insc_year_differs_from_decision_year`, `report_year_differs_from_decision_year`, `not_in_vaquill`, `no_english_text`, `no_text`, `incomplete_english_text` |

## 3. Transformation rules

**3.1 Duplicate Vanga rows.** 5,181 paths appear twice, once in the right `year=` folder and once in a wrong one. Keep the copy whose folder year equals the year of its parsed decision date. Both copies stay in `source_vanga_raw`; the other is marked `misfiled_copy`.

**3.2 Matching** (applied to canonical Vanga rows only), per Vaquill case:

1. candidates = canonical Vanga rows with the same normalised INSC id (space to underscore);
2. keep candidates whose whitespace- and case-normalised citation equals the Vaquill citation;
3. exactly one and the decision dates agree: **matched** (confidence 1.00);
4. exactly one but the dates differ: queue `date_conflict`, no merge;
5. more than one: queue `ambiguous_match`, no merge;
6. none, but candidates exist: queue `citation_conflict`, no merge;
7. no candidate at all: queue `vaquill_orphan`.

Vanga rows with no match keep `match_method` `none:empty_insc_id` (152 rows have no id), `none:shared_insc_id_citation_differs` (another report with the same id was matched) or `none:no_vaquill_candidate`.

**3.3 Field filling.** Per field: Vanga value if non-empty, else Vaquill value, else NULL. Both-non-empty and different (after whitespace/case normalisation) is a conflict: Vanga is kept, Vaquill is preserved, the row goes to `field_conflicts`.

**3.4 Years.** `decision_year` derives from the parsed date only. Both source `year` fields are kept. A difference between Vanga `year` and Vaquill `year` is logged as a `source_year` conflict with one fixed rule: *decision_year is derived from decision_date, both source years are kept as delivered*. This is deterministic and needs no human decision.

**3.5 Judges.** Vaquill's structured list when matched and non-empty, otherwise Vanga's comma-separated string split on commas. Normalised name = upper-case, whitespace collapsed. Position is the order in the list. A difference in the two sets is a `judges` conflict.

**3.6 Chunks.** Kept per language. Key `(judgment_id, language_code, chunk_index)`. Two lossless storage choices, both asserted at build time: case-level metadata (title, judges, ...) is stored once in `source_vaquill_raw` instead of repeating on 1.1M rows (verified constant per case); `text_original` is stored NULL where it equals `text` (true for every row). The raw `text`, offsets, pages and section columns are byte-identical to the Parquet, **including the `Case: ... Section: ...` header**.

**3.7 Text assembly** (into `judgment_text`, never into `judgment_chunk`):

1. strip the header `Case: <line>\nSection: <line>\n\n` from each chunk;
2. a chunk body is the slice `text[char_start:char_end]` of the full text, but neighbouring windows overlap by tens of characters or leave a 1 to 2 character gap, so chunks are **placed by offset** instead of concatenated;
3. overlapped characters are compared with the text already assembled (mismatches are counted);
4. a gap of 1 to 2 characters becomes that many newlines (whitespace trimmed from chunk ends); a larger gap means missing text: the set is flagged `is_complete = false`, not repaired;
5. one text per judgment and language. English is `language_code = 'en'`.

**3.8 Text status.** `english`: an `en` chunk set exists. `translation_only`: chunk sets exist but none is English. `none`: no Vaquill text at all. Judgments with no usable text still have complete metadata rows and are found by metadata search.

## 4. Validation plan (implemented in `pipeline/06_validate_stage3.py`)

| group | checks |
|---|---|
| A raw | manifest re-verified; Vanga parquet = JSON = staged rows; JSON/parquet fields identical; staged JSON reproduces the parquet values |
| B counts and duplicates | judgments = distinct paths = canonical copies; ids are the recomputed uuid5; one canonical copy per path; folder-year rule holds for every duplicate; no duplicate `(insc_id, citation)` |
| C matching | matched + queued = all Vaquill cases; judgments = matched + in_review + vanga_only; independent re-derivation from raw gives the same matches; queue contents; no orphans; matched pairs agree on date |
| D chunks | key uniqueness; all raw chunks present; per-case counts equal; raw columns byte-identical; `text_original` loss is lossless; chunk-set completeness |
| E text | one text per language set; no header left; overlap agreement; length reconciliation; positional check on 1,500 random texts |
| F language | text_status reconciliation; no-English vs no-text distinguished; metadata complete for judgments without text; coverage by decade and language |
| G years | `decision_year` = year(`decision_date`); source years retained; conflicts listed with the rule |
| H provenance | every field tracked for every judgment; stored value = chosen value; conflicts surfaced; NULL policy; identifier uniqueness; null rates before and after |
| I reproducibility | two builds produce identical table contents |
| J schema | every Parquet column exists in the migration DDL (scratch PostgreSQL 16) |

A check ends as PASS, FAIL, or EXCEPTION (a measured deviation with a written explanation). The script exits non-zero on any FAIL.

## 5. Stage 4 additions and how to reconstruct the source rows

Schema changes since this document was approved are additive (`db/migrations/0006_text_quality.sql`, `0007_indexes.sql`):

* `judgment_text` gains `chunks_contiguous`, `offset_drift_chunks` and `incompleteness_reason` (`complete`, `missing_chunks`, `text_gap`, `missing_chunks_and_text_gap`), with a CHECK that ties them to `is_complete` and `large_gap_count`. Completeness, overlap disagreement (`overlap_mismatches`) and offset drift are independent columns and independent of language availability (`judgment_language`).
* `judgment_retrieval_status` (view): one row per judgment with language availability and English text quality side by side.
* `text_sanitization_log`: every text value in which NUL was replaced (see below).
* Secondary indexes and the stored `judgment_text.tsv_en` full-text column (migration 0007, chosen by measurement).

Reconstruction rules (the database is lossless relative to the Vaquill parquet except for the NUL substitution below):

| to recover | rule |
|---|---|
| a raw Vaquill row | case-level columns from `source_vaquill_raw.raw` (JSON) joined on `vaquill_case_id`, chunk columns from `judgment_chunk` |
| `text_original` | equals `text` wherever it is NULL (asserted at build time for every row; 0 rows differ) |
| a chunk's original `text` with NUL bytes | for rows listed in `text_sanitization_log`, replace every U+2400 with U+0000. U+2400 occurs nowhere else in the data (checked), so no position list is needed |
| a raw Vanga row | `source_vanga_raw.raw` (JSON of the 18 parquet columns plus `citation_year`), keyed by `(year_folder, path)`; misfiled duplicates are kept with `is_canonical_copy = false` |
| assembled text | `judgment_text.text` was built from `judgment_chunk` by the rules in section 3.7; it is never edited, and the header-free text can be rebuilt from the chunks to check it |
| why a text is incomplete | `incompleteness_reason`, `large_gap_count`, `chunks_contiguous` |

Nothing in Stage 4 repairs missing chunks, gaps, overlap disagreements or offset drift. They are exposed, not fixed.
