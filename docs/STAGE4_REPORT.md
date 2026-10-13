# Stage 4 report: PostgreSQL load, constraints, indexes and timings

Loaded 2026-10-13; verified 2026-10-13 22:41:52 UTC. PostgreSQL 16.15 on this machine, listening on 127.0.0.1 only. Everything below is produced by `pipeline/07_load_postgres.py`, `08_verify_postgres.py`, `09_index_benchmark.py` and `10_stage4_report.py`; nothing is typed in by hand.

## Summary

| area | result |
|---|---|
| row counts, parquet vs database | all match (23/23 tables) |
| content fingerprints (hash of every row's content, both sides) | all identical (14/14) |
| constraints defined and validated | 75 constraints, all validated |
| foreign-key orphans | 0 across 24 foreign keys |
| negative tests (bad writes must be rejected) | 9/9 rejected as expected |
| logical integrity checks beyond foreign keys | 12/12 clean |
| bulk load (migrations + all COPY + commit) | 535.44 s load, 0.15 s migrations, 7.26 s commit, 2.44 s ANALYZE |
| database size | 6.51 GB after the load, 7.38 GB after the secondary indexes and the stored full-text column |

## 1. Load

One transaction: the six migrations, then `COPY` of every table in foreign-key order, then sequences, grants and the run log. Any error rolls everything back, so the database is either empty or completely loaded. The server runs with `wal_level = minimal` so that tables created in the load transaction skip WAL; backups use `pg_dump`, not replication.

| table | rows in parquet | rows loaded | seconds | rows/s |
|---|---|---|---|---|
| source_vanga_raw | 43,552 | 43,552 | 6.01 | 7,247 |
| source_vaquill_raw | 37,014 | 37,014 | 0.42 | 88,129 |
| judgment | 38,371 | 38,371 | 0.46 | 83,415 |
| judgment_source_map | 38,371 | 38,371 | 0.93 | 41,259 |
| judgment_field_provenance | 460,452 | 460,452 | 2.62 | 175,745 |
| field_conflicts | 3 | 3 | 0.0 | 3,000 |
| match_review_queue | 0 | 0 | 0.0 | 0 |
| judgment_judge | 44,405 | 44,405 | 0.34 | 130,603 |
| judgment_identifier | 191,599 | 191,599 | 1.79 | 107,039 |
| judgment_language | 141,924 | 141,924 | 1.03 | 137,790 |
| judgment_text | 135,156 | 135,156 | 252.99 | 534 |
| judgment_chunk | 1,113,313 | 1,113,313 | 256.99 | 4,332 |
| downloads | 43,786 | 43,786 | 0.2 | 218,930 |
| merge_report | 230 | 230 | 0.01 | 23,000 |
| text_sanitization_log | 47 | 47 | 9.77 | 5 |
| legislation_act | 1,568 | 1,568 | 0.01 | 156,800 |
| legislation_section | 74,484 | 74,484 | 1.59 | 46,845 |

Total: 556.75 s from start to finish (0.15 s for the migrations, 535.44 s for loading and commit-prep, 7.26 s commit, 2.44 s ANALYZE). The first load of the same data took 594.16 s; this one is the rebuild (`--rebuild`) used for the index experiment. Constraint-backed indexes (primary keys, unique) are maintained during the load and are therefore inside these timings; their rebuild time is reported in section 7.

### NUL characters: the one change made to the stored text

PostgreSQL text cannot contain U+0000. The raw Vaquill data does, in a few garbled chunks. In the **database copy only**, each NUL is replaced one-for-one by U+2400 (`␀`), so lengths and offsets are unchanged. Every affected value is listed in `text_sanitization_log`. The raw Parquet files, and the Stage 3 build outputs, still hold the original NULs, and the verification below hashes the database against the parquet with the same replacement applied. This departs from "byte-identical chunks" in the database for these rows only; say if you prefer another treatment.

| table | language | values changed | NUL characters |
|---|---|---|---|
| judgment_chunk | hin | 36 | 3134 |
| judgment_chunk | mal | 1 | 1 |
| judgment_text | hin | 9 | 3034 |
| judgment_text | mal | 1 | 1 |

## 2. Row counts before and after

| table | rows in parquet (before) | rows in database (after) | match | note |
|---|---|---|---|---|
| citation_mention | n/a | 0 | yes | not loaded by design (empty) |
| cites_edge | n/a | 0 | yes | not loaded by design (empty) |
| downloads | 43,786 | 43,786 | yes |  |
| field_conflicts | 3 | 3 | yes |  |
| judgment | 38,371 | 38,371 | yes |  |
| judgment_chunk | 1,113,313 | 1,113,313 | yes |  |
| judgment_field_provenance | 460,452 | 460,452 | yes |  |
| judgment_identifier | 191,599 | 191,599 | yes |  |
| judgment_judge | 44,405 | 44,405 | yes |  |
| judgment_language | 141,924 | 141,924 | yes |  |
| judgment_paragraph | n/a | 0 | yes | not loaded by design (empty) |
| judgment_source_map | 38,371 | 38,371 | yes |  |
| judgment_statute | n/a | 0 | yes | not loaded by design (empty) |
| judgment_text | 135,156 | 135,156 | yes |  |
| legislation_act | 1,568 | 1,568 | yes |  |
| legislation_section | 74,484 | 74,484 | yes |  |
| match_review_queue | 0 | 0 | yes |  |
| merge_report | 230 | 230 | yes |  |
| pipeline_runs | n/a | 5 | yes | written by the pipeline run log |
| review_audit | n/a | 0 | yes | not loaded by design (empty) |
| source_vanga_raw | 43,552 | 43,552 | yes |  |
| source_vaquill_raw | 37,014 | 37,014 | yes |  |
| text_sanitization_log | 47 | 47 | yes |  |

## 3. Content fingerprints (parquet vs database)

The same aggregate is computed by DuckDB on the parquet and by PostgreSQL on the table: counts, sums, and an MD5 over every row's content in a fixed order (for chunks and texts, the MD5 of every text value). Equal fingerprints mean the load changed nothing.

| table | result | parquet | database | seconds |
|---|---|---|---|---|
| judgment | identical | 38371, 76718772, 38123, 0e178d76461559e365c6f4d8a25bb9cc | 38371, 76718772, 38123, 0e178d76461559e365c6f4d8a25bb9cc | 0.2 |
| judgment arrays and flags | identical | d2b5c0b920bce38cfcc9d67b182805c9 | d2b5c0b920bce38cfcc9d67b182805c9 | 0.1 |
| judgment_chunk | identical | 1113313, 48277547757, 52226097858, 29109867, 0, 37014, df35607df24187cdf4a34a00af3bfd5e | 1113313, 48277547757, 52226097858, 29109867, 0, 37014, df35607df24187cdf4a34a00af3bfd5e | 46.1 |
| judgment_text | identical | 135156, 3706374236, 1113313, 565, 501, 134879, c269c03fd343bae18c7b03215429fa65 | 135156, 3706374236, 1113313, 565, 501, 134879, c269c03fd343bae18c7b03215429fa65 | 43.4 |
| judgment_field_provenance | identical | 460452, 543c6709d4d5918ad4593a0e6d0ec33e | 460452, 543c6709d4d5918ad4593a0e6d0ec33e | 1.1 |
| judgment_identifier | identical | 191599, f050f412ea51a177e8e4d66fa9ef1652 | 191599, f050f412ea51a177e8e4d66fa9ef1652 | 0.3 |
| judgment_judge | identical | 44405, c804212d1d408e3c6342d6e99fbf15c1 | 44405, c804212d1d408e3c6342d6e99fbf15c1 | 0.1 |
| judgment_language | identical | 141924, 1113313, 139691, 135156, d3b3c958cea9f23964fb93b75bb37131 | 141924, 1113313, 139691, 135156, d3b3c958cea9f23964fb93b75bb37131 | 0.2 |
| judgment_source_map | identical | 38371, 37014, 7db0f81bb06c152baceabc489e9f9608 | 38371, 37014, 7db0f81bb06c152baceabc489e9f9608 | 0.1 |
| source_vanga_raw (keys + JSON fields) | identical | 43552, 648df13502d688973f5fa92b4bd83139 | 43552, 648df13502d688973f5fa92b4bd83139 | 3.0 |
| source_vaquill_raw (keys + JSON fields) | identical | 37014, 1113313, adfc67c9710a4b789bca5ea17db2640f | 37014, 1113313, adfc67c9710a4b789bca5ea17db2640f | 0.3 |
| text_sanitization_log | identical | 47, 6170 | 47, 6170 | 9.3 |
| legislation_section | identical | 74484, 92326b7d4b26a9598692997749fc8ecd | 74484, 92326b7d4b26a9598692997749fc8ecd | 0.6 |
| legislation_act | identical | 1568, a578a9e1e5b233da5aa5a356d659ad04 | 1568, a578a9e1e5b233da5aa5a356d659ad04 | 0.0 |

## 4. Constraints, orphans and negative tests

| table | primary key | foreign key | unique | check | all validated |
|---|---|---|---|---|---|
| citation_mention | 1 | 2 |  |  | yes |
| cites_edge | 1 | 3 | 1 | 1 | yes |
| downloads | 1 |  | 1 | 2 | yes |
| field_conflicts | 1 | 1 | 1 | 1 | yes |
| judgment | 1 |  | 1 | 3 | yes |
| judgment_chunk | 1 | 2 | 1 |  | yes |
| judgment_field_provenance | 1 | 1 |  | 1 | yes |
| judgment_identifier |  | 1 | 1 | 1 | yes |
| judgment_judge | 1 | 1 |  | 1 | yes |
| judgment_language | 1 | 1 |  |  | yes |
| judgment_paragraph | 1 | 1 | 1 |  | yes |
| judgment_source_map | 1 | 3 | 1 | 2 | yes |
| judgment_statute | 1 | 4 |  |  | yes |
| judgment_text | 1 | 2 |  | 2 | yes |
| legislation_act | 1 |  |  |  | yes |
| legislation_section | 1 | 1 |  |  | yes |
| match_review_queue | 1 | 1 |  | 2 | yes |
| merge_report | 1 |  | 1 |  | yes |
| pipeline_runs | 1 |  |  | 1 | yes |
| review_audit | 1 |  |  |  | yes |
| source_vanga_raw | 1 |  | 1 |  | yes |
| source_vaquill_raw | 1 |  |  |  | yes |
| text_sanitization_log | 1 |  | 1 | 1 | yes |

Orphan check for every foreign key (child rows with no parent):

| foreign key | child | columns | parent | orphans |
|---|---|---|---|---|
| citation_mention_judgment_id_fkey | citation_mention | judgment_id | judgment | 0 |
| citation_mention_paragraph_id_fkey | citation_mention | paragraph_id | judgment_paragraph | 0 |
| cites_edge_from_judgment_id_fkey | cites_edge | from_judgment_id | judgment | 0 |
| cites_edge_mention_id_fkey | cites_edge | mention_id | citation_mention | 0 |
| cites_edge_to_judgment_id_fkey | cites_edge | to_judgment_id | judgment | 0 |
| field_conflicts_judgment_id_fkey | field_conflicts | judgment_id | judgment | 0 |
| judgment_chunk_judgment_id_fkey | judgment_chunk | judgment_id | judgment | 0 |
| judgment_chunk_vaquill_case_id_fkey | judgment_chunk | vaquill_case_id | source_vaquill_raw | 0 |
| judgment_field_provenance_judgment_id_fkey | judgment_field_provenance | judgment_id | judgment | 0 |
| judgment_identifier_judgment_id_fkey | judgment_identifier | judgment_id | judgment | 0 |
| judgment_judge_judgment_id_fkey | judgment_judge | judgment_id | judgment | 0 |
| judgment_language_judgment_id_fkey | judgment_language | judgment_id | judgment | 0 |
| judgment_paragraph_judgment_id_fkey | judgment_paragraph | judgment_id | judgment | 0 |
| judgment_source_map_judgment_id_fkey | judgment_source_map | judgment_id | judgment | 0 |
| judgment_source_map_vanga_path_fkey | judgment_source_map | vanga_path | judgment | 0 |
| judgment_source_map_vaquill_case_id_fkey | judgment_source_map | vaquill_case_id | source_vaquill_raw | 0 |
| judgment_statute_act_id_fkey | judgment_statute | act_id | legislation_act | 0 |
| judgment_statute_chunk_id_fkey | judgment_statute | chunk_id | legislation_section | 0 |
| judgment_statute_judgment_id_fkey | judgment_statute | judgment_id | judgment | 0 |
| judgment_statute_paragraph_id_fkey | judgment_statute | paragraph_id | judgment_paragraph | 0 |
| judgment_text_judgment_id_fkey | judgment_text | judgment_id | judgment | 0 |
| judgment_text_judgment_id_language_code_fkey | judgment_text | judgment_id, language_code | judgment_language | 0 |
| legislation_section_act_id_fkey | legislation_section | act_id | legislation_act | 0 |
| match_review_queue_vaquill_case_id_fkey | match_review_queue | vaquill_case_id | source_vaquill_raw | 0 |

Negative tests (each runs inside a transaction that is rolled back):

| write that must fail | result |
|---|---|
| duplicate primary key (judgment_judge) | rejected: UniqueViolation |
| orphan foreign key (judgment_chunk -> judgment) | rejected: ForeignKeyViolation |
| decision_year must equal year(decision_date) | rejected: CheckViolation |
| completeness flags must be mutually consistent | rejected: CheckViolation |
| second canonical copy of a Vanga path | rejected: UniqueViolation |
| a Vaquill case attached to two judgments | rejected: UniqueViolation |
| invalid text_status value | rejected: CheckViolation |
| duplicate vaquill_chunk_id | rejected: UniqueViolation |
| read-only role cannot write | rejected: ReadOnlySqlTransaction |

Logical integrity beyond foreign keys:

| check | violations |
|---|---|
| every judgment has exactly one judgment_source_map row | 0 |
| every judgment has all 12 tracked provenance fields | 0 |
| language rows with text_available have a judgment_text row, and vice versa | 0 |
| judgment_language.text_chunks equals the actual chunk rows | 0 |
| judgment_text.chunk_count equals the actual chunk rows; expected_chunks equals total_chunks | 0 |
| judgment_text.char_length equals length(text) | 0 |
| chunks_contiguous agrees with the chunk indexes actually stored | 0 |
| text_status agrees with judgment_text languages | 0 |
| bench_strength equals the number of judgment_judge rows | 0 |
| quality flag incomplete_english_text matches English completeness | 0 |
| match_status agrees with judgment_source_map | 0 |
| read-only role can read every table | 0 |

## 5. Language availability and text completeness, reconciled

Language availability (`judgment_language`, `text_status`) and text quality (`judgment_text`: completeness, overlap disagreement, offset drift) are stored and counted separately.

### 5.1 Text status

| text_status | match_status | judgments |
|---|---|---|
| english | matched | 35,596 |
| none | vanga_only | 1,357 |
| translation_only | matched | 1,418 |

### 5.2 Incomplete text sets: reconciling 277 and 276

**277 text sets are incomplete** (verified build and database output). The earlier figure of 276 counted only one of the two causes:

| measure | sets |
|---|---|
| incomplete (the source of truth) | 277 |
| with a text gap of more than 2 characters between chunks | 276 |
| with missing chunks (indexes not 0..n-1, or count differs from total_chunks) | 180 |
| both causes | 179 |
| text gap only | 97 |
| missing chunks only | 1 |
| check: gap + missing chunks - both = incomplete | yes |

So 276 (gap) + 1 (missing chunks without a gap) = 277. Breakdown by reason:

| incompleteness_reason | English | other languages | total |
|---|---|---|---|
| complete | 35573 | 99306 | 134879 |
| missing_chunks_and_text_gap | 5 | 174 | 179 |
| text_gap | 18 | 79 | 97 |
| missing_chunks | 0 | 1 | 1 |

### 5.3 Per language

| language | text sets | PDF listed | complete | missing chunks | text gap | both | texts with overlap disagreement | overlap events | texts with offset drift | drift chunks |
|---|---|---|---|---|---|---|---|---|---|---|
| pun | 36,127 | 36,982 | 36,110 | 0 | 11 | 6 | 61 | 96 | 75 | 110 |
| en | 35,596 | 37,213 | 35,573 | 0 | 18 | 5 | 80 | 106 | 107 | 149 |
| hin | 35,431 | 36,443 | 35,220 | 1 | 44 | 166 | 178 | 291 | 97 | 120 |
| ben | 4,973 | 5,957 | 4,968 | 0 | 4 | 1 | 2 | 6 | 2 | 3 |
| guj | 4,785 | 4,509 | 4,783 | 0 | 1 | 1 | 1 | 1 | 2 | 2 |
| mal | 3,739 | 3,781 | 3,729 | 0 | 10 | 0 | 14 | 37 | 19 | 62 |
| tam | 3,661 | 3,190 | 3,653 | 0 | 8 | 0 | 15 | 16 | 25 | 31 |
| mar | 3,097 | 3,077 | 3,097 | 0 | 0 | 0 | 1 | 1 | 2 | 2 |
| urd | 2,213 | 2,619 | 2,213 | 0 | 0 | 0 | 1 | 1 | 4 | 4 |
| tel | 2,198 | 2,546 | 2,198 | 0 | 0 | 0 | 2 | 2 | 5 | 5 |
| kan | 2,101 | 2,067 | 2,100 | 0 | 1 | 0 | 6 | 6 | 10 | 10 |
| ori | 662 | 698 | 662 | 0 | 0 | 0 | 1 | 2 | 1 | 3 |
| asm | 332 | 344 | 332 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nep | 171 | 171 | 171 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| san | 55 | 56 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| kok | 15 | 17 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gar | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| kas | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| kha | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### 5.4 English texts: quality dimensions are independent

| English texts | clean (complete, no overlap disagreement, no drift) | incomplete | with overlap disagreement | with offset drift | any issue |
|---|---|---|---|---|---|
| 35,596 | 35,484 | 23 | 80 | 107 | 112 |

### 5.5 What retrieval and evaluation code can see

`judgment_retrieval_status` has one row per judgment (38,371) with language availability and text quality side by side: English text available for 35,596, complete for 35,573, available but incomplete for 23, with overlap disagreement for 80, with offset drift for 107. A ranked hit can therefore be shown, filtered or excluded on these flags; nothing is repaired or hidden.

## 6. Database size

Whole database: **7.38 GB** (at verification time).

| table | rows (estimate) | heap MB | TOAST MB (large text) | indexes MB | total MB |
|---|---|---|---|---|---|
| judgment_chunk | 1,112,359 | 407.5 | 3,099.9 | 90.4 | 3,597.8 |
| judgment_text | 135,156 | 26.6 | 2,995.9 | 232.6 | 3,255.1 |
| source_vanga_raw | 43,552 | 6.3 | 175.6 | 4.1 | 186.0 |
| legislation_section | 74,484 | 104.3 | 0.7 | 3.4 | 108.4 |
| judgment_field_provenance | 460,452 | 50.4 | 0.0 | 21.8 | 72.3 |
| judgment | 38,371 | 24.6 | 0.0 | 20.4 | 45.1 |
| judgment_identifier | 191,599 | 14.8 | 0.0 | 14.4 | 29.2 |
| source_vaquill_raw | 37,014 | 26.4 | 0.0 | 1.2 | 27.6 |
| downloads | 43,786 | 12.2 | 0.0 | 6.0 | 18.2 |
| judgment_language | 141,924 | 8.9 | 0.0 | 5.8 | 14.7 |
| judgment_judge | 44,405 | 3.9 | 0.0 | 3.4 | 7.3 |
| judgment_source_map | 38,371 | 4.3 | 0.0 | 2.4 | 6.7 |
| legislation_act | 1,568 | 0.6 | 0.0 | 0.1 | 0.7 |
| merge_report | 230 | 0.0 | 0.0 | 0.0 | 0.1 |

## 7. Indexes, chosen by measurement

Rule: keep if an affected query is >=3x and >=5 ms faster at p50, or the index fixes a missed target. Timings are warm-cache (each query parameter is run twice, the second run is reported); first-run p95 is in the JSON. 30 parameters per query type, drawn from the real data (identifiers, party names with a typo, judge names, years, disposals).

### 7.1 Baseline: constraint indexes only

| query type | what | p50 ms | p95 ms | target ms | plan |
|---|---|---|---|---|---|
| ident_insc | citation-style lookup by INSC id | 0.1 | 0.17 | 50 | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| ident_scr | citation-style lookup by SCR citation | 0.09 | 0.14 | 50 | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| ident_cnr | lookup by CNR | 0.09 | 0.1 | 50 | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| ident_any_type | lookup by identifier value, type unknown | 4.9 | 8.65 | 50 | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| party_fuzzy | fuzzy petitioner search (one typo) | 156.61 | 189.83 | 300 | Seq Scan on judgment |
| respondent_fuzzy | fuzzy respondent search (one typo) | 159.15 | 200.35 | 300 | Seq Scan on judgment |
| title_fuzzy | fuzzy title search (one typo) | 391.79 | 431.0 | 300 | Seq Scan on judgment |
| party_substring | petitioner contains word | 23.58 | 32.65 | 300 | Seq Scan on judgment |
| title_substring | title contains word | 31.62 | 48.16 | 300 | Seq Scan on judgment |
| judge_fuzzy | fuzzy judge name | 73.21 | 103.05 | 300 | Seq Scan on judgment_judge |
| judge_exact_list | judgments of one judge | 3.03 | 3.83 |  | Seq Scan on judgment_judge; Index Scan using judgment_pkey on judgment |
| filter_date_disposal | date range + disposal | 5.73 | 6.31 |  | Seq Scan on judgment |
| filter_year_counts | judgments per year in a range | 5.63 | 6.51 |  | Seq Scan on judgment |
| filter_text_status | text status within years | 6.14 | 8.44 |  | Seq Scan on judgment |
| flag_array | quality flag filter | 8.94 | 16.24 |  | Seq Scan on judgment |
| language_array | languages listed filter | 12.7 | 18.53 |  | Seq Scan on judgment |
| chunk_list | chunk listing for one English text | 0.38 | 0.55 |  | Index Scan using judgment_chunk_pkey on judgment_chunk |
| english_text_fetch | fetch one assembled English text | 0.29 | 0.46 |  | Index Scan using judgment_text_pkey on judgment_text |
| page_load | full judgment page: 8 record queries + first chunks | 6.62 | 9.2 |  | Index Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier |
| meta_search | weighted metadata search (title A, parties B, citation C) | 409.02 | 456.06 |  | Seq Scan on judgment |

### 7.2 Candidate indexes

| candidate | build s | size MB | decision | evidence |
|---|---|---|---|---|
| identifier_by_judgment | 0.11 | 2.6 | KEEP | page_load: p50 6.62 -> 0.89 ms (7.4x, saves 5.7 ms) |
| identifier_by_value | 0.18 | 6.9 | drop | ident_any_type: p50 4.9 -> 0.08 ms (61.2x, saves 4.8 ms) |
| trgm_petitioner | 0.29 | 3.5 | KEEP | party_fuzzy: p50 156.61 -> 9.79 ms (16.0x, saves 146.8 ms); party_substring: p50 23.58 -> 0.28 ms (84.2x, saves 23.3 ms) |
| trgm_respondent | 0.26 | 3.4 | KEEP | respondent_fuzzy: p50 159.15 -> 22.25 ms (7.2x, saves 136.9 ms) |
| trgm_title | 0.59 | 6.1 | KEEP | title_fuzzy: p50 391.79 -> 169.93 ms (2.3x, saves 221.9 ms); title_substring: p50 31.62 -> 0.47 ms (67.3x, saves 31.2 ms) |
| trgm_judge | 0.14 | 1.6 | KEEP | judge_fuzzy: p50 73.21 -> 2.88 ms (25.4x, saves 70.3 ms) |
| btree_judge | 0.04 | 0.3 | drop | judge_exact_list: p50 3.03 -> 0.91 ms (3.3x, saves 2.1 ms) |
| btree_decision_date | 0.05 | 0.5 | drop | filter_date_disposal: p50 5.73 -> 1.92 ms (3.0x, saves 3.8 ms); filter_year_counts: p50 5.63 -> 1.54 ms (3.7x, saves 4.1 ms) |
| btree_disposal | 0.03 | 0.3 | drop | filter_date_disposal: p50 5.73 -> 1.25 ms (4.6x, saves 4.5 ms) |
| btree_decision_year | 0.03 | 0.3 | drop | filter_text_status: p50 6.14 -> 1.71 ms (3.6x, saves 4.4 ms) |
| gin_quality_flags | 0.02 | 0.1 | KEEP | flag_array: p50 8.94 -> 1.18 ms (7.6x, saves 7.8 ms) |
| gin_available_languages | 0.03 | 0.2 | KEEP | language_array: p50 12.7 -> 2.94 ms (4.3x, saves 9.8 ms) |
| meta_search_tsvector | 2.7 | 3.9 | KEEP | meta_search: p50 409.02 -> 1.37 ms |

**Borderline decisions** (saving within about 1.5 ms of the 5 ms threshold, so the outcome can flip on timing noise; the indexes are tiny, so they are cheap to add or drop if you disagree): `identifier_by_judgment` (page_load: saves 5.7 ms, kept); `identifier_by_value` (ident_any_type: saves 4.8 ms, dropped); `btree_decision_date` (filter_year_counts: saves 4.1 ms, dropped); `btree_disposal` (filter_date_disposal: saves 4.5 ms, dropped); `btree_decision_year` (filter_text_status: saves 4.4 ms, dropped). In an earlier identical run that crashed before saving its results, `identifier_by_judgment` saved 4.4 ms and was dropped.

### 7.3 Full-text search on the English texts: two designs

No index: {"term": "anticipatory bail", "count_ms": 82788, "matches": 304, "plan": ["Index Scan using judgment_text_pkey on judgment_text"]}

| design | build s | index MB | chosen |
|---|---|---|---|
| GIN on expression `to_tsvector('english', text)` (English rows) | 244.9 | 236.7 | no |
| stored `tsv_en` column + GIN | 460.7 (incl. 404.0 filling the column) | 227.1 | yes |

Decision: worst ranked top-20 query: expression index 163069.7 ms vs stored tsvector 369.4 ms; both return identical match counts.

Ranked top 20 by term frequency class (matches counted over all English texts):

| design | term class | queries | median matches | count p50 ms | ranked top-20 p50 ms | ranked top-20 max ms |
|---|---|---|---|---|---|---|
| expression index | common | 2 | 22949.5 | 9.4 | 123130.5 | 163069.7 |
| expression index | medium | 18 | 1,159.0 | 2.9 | 10568.7 | 35271.1 |
| expression index | rare | 4 | 117.0 | 0.9 | 1591.5 | 2403.5 |
| stored tsvector | common | 2 | 22949.5 | 6.7 | 269.6 | 369.4 |
| stored tsvector | medium | 18 | 1,159.0 | 2.6 | 29.1 | 165.9 |
| stored tsvector | rare | 4 | 117.0 | 0.9 | 4.5 | 7.3 |

Per term (stored tsvector design):

| term | matches | class | count ms | ranked top-20 ms |
|---|---|---|---|---|
| anticipatory bail | 304 | medium | 1.6 | 10.4 |
| specific performance of contract | 2,558 | medium | 3.7 | 74.9 |
| adverse possession | 2,413 | medium | 3.4 | 64.3 |
| natural justice | 10,305 | common | 6.2 | 169.9 |
| res judicata | 984 | medium | 2.4 | 22.5 |
| article 21 personal liberty | 2,640 | medium | 4.0 | 95.0 |
| limitation condonation of delay | 1,334 | medium | 3.1 | 35.7 |
| arbitration agreement | 1,762 | medium | 3.3 | 68.5 |
| habeas corpus | 637 | medium | 2.2 | 15.9 |
| income tax assessment | 3,270 | medium | 4.2 | 165.9 |
| compensation motor accident | 630 | medium | 2.2 | 19.0 |
| mens rea | 794 | medium | 2.1 | 21.3 |
| locus standi | 700 | medium | 1.8 | 17.8 |
| promissory estoppel | 283 | medium | 1.3 | 9.2 |
| sedition | 43 | rare | 0.6 | 2.8 |
| divorce cruelty | 196 | rare | 0.9 | 7.3 |
| land acquisition | 3,246 | medium | 2.8 | 84.8 |
| bank guarantee | 1,845 | medium | 2.8 | 50.5 |
| contempt of court | 1,709 | medium | 2.8 | 48.6 |
| court | 35,594 | common | 7.1 | 369.4 |
| ejusdem generis | 226 | medium | 1.3 | 11.8 |
| quantum meruit | 18 | rare | 1.0 | 1.0 |
| benami transaction | 191 | rare | 0.9 | 6.2 |
| zamindari abolition | 349 | medium | 1.1 | 8.9 |

### 7.4 Final query timings on the kept index set

| query type | what | p50 ms | p95 ms | max ms | target ms | target | plan |
|---|---|---|---|---|---|---|---|
| ident_insc | citation-style lookup by INSC id | 0.08 | 0.11 | 0.23 | 50 | met | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| ident_scr | citation-style lookup by SCR citation | 0.07 | 0.09 | 0.1 | 50 | met | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| ident_cnr | lookup by CNR | 0.08 | 0.1 | 0.14 | 50 | met | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| ident_any_type | lookup by identifier value, type unknown | 5.0 | 5.39 | 5.78 | 50 | met | Index Only Scan using judgment_identifier_identifier_type_value_judgment_id_key on judgment_identifier; Index Scan using judgment_pkey on judgment |
| party_fuzzy | fuzzy petitioner search (one typo) | 8.82 | 17.25 | 55.99 | 300 | met | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_petitioner_trgm_idx on ? |
| respondent_fuzzy | fuzzy respondent search (one typo) | 26.33 | 88.5 | 117.44 | 300 | met | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_respondent_trgm_idx on ? |
| title_fuzzy | fuzzy title search (one typo) | 197.38 | 325.98 | 373.32 | 300 | MISSED | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_title_trgm_idx on ? |
| party_substring | petitioner contains word | 0.42 | 2.74 | 3.07 | 300 | met | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_petitioner_trgm_idx on ? |
| title_substring | title contains word | 0.52 | 5.34 | 8.42 | 300 | met | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_title_trgm_idx on ? |
| judge_fuzzy | fuzzy judge name | 3.12 | 6.48 | 11.5 | 300 | met | Bitmap Heap Scan on judgment_judge; Bitmap Index Scan using judgment_judge_trgm_idx on ? |
| judge_exact_list | judgments of one judge | 1.19 | 2.15 | 3.0 |  |  | Bitmap Heap Scan on judgment_judge; Bitmap Index Scan using judgment_judge_trgm_idx on ? |
| filter_date_disposal | date range + disposal | 6.29 | 8.72 | 10.31 |  |  | Seq Scan on judgment |
| filter_year_counts | judgments per year in a range | 6.86 | 8.21 | 8.65 |  |  | Seq Scan on judgment |
| filter_text_status | text status within years | 7.12 | 8.05 | 8.7 |  |  | Seq Scan on judgment |
| flag_array | quality flag filter | 1.12 | 3.5 | 5.06 |  |  | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_quality_flags_idx on ? |
| language_array | languages listed filter | 3.65 | 10.64 | 11.27 |  |  | Seq Scan on judgment |
| chunk_list | chunk listing for one English text | 0.22 | 0.41 | 0.88 |  |  | Index Scan using judgment_chunk_pkey on judgment_chunk |
| english_text_fetch | fetch one assembled English text | 0.2 | 0.29 | 0.86 |  |  | Index Scan using judgment_text_pkey on judgment_text |
| page_load | full judgment page: 8 record queries + first chunks | 1.06 | 1.7 | 2.37 |  |  | Index Scan using judgment_identifier_judgment_idx on judgment_identifier |
| meta_search | weighted metadata search using stored tsvector + GIN | 1.36 | 5.91 | 6.15 |  |  | Bitmap Heap Scan on judgment; Bitmap Index Scan using judgment_search_tsv_idx on ? |
| fts_with_quality | ranked top 20 plus text-quality flags from judgment_retrieval_status | 37.96 | 158.3 | 311.25 | 2000 | met | Bitmap Heap Scan on judgment_text; Bitmap Index Scan using judgment_text_tsv_en_idx on ? |

**Targets missed in the final run:** `title_fuzzy`: p95 325.98 ms vs target 300 ms (p50 197.38 ms; baseline p95 431.0 ms; p95 314.07 ms in the run that built its index). The index roughly halves the latency but the query does not reach its target at p95, likely because similarity search over long `X versus Y` titles matches many candidate rows (not investigated further). The index is kept because it makes substring search on titles roughly 60 times faster at p50. Nothing was tuned to hide this; searching petitioner and respondent separately (both well inside the target) is the better path for fuzzy party search.

### 7.5 Rebuild time of the constraint-backed indexes

| table | REINDEX seconds | index MB |
|---|---|---|
| judgment_chunk | 2.33 | 90.4 |
| judgment_field_provenance | 0.14 | 21.8 |
| judgment_identifier | 0.26 | 14.4 |
| judgment_language | 0.06 | 5.8 |
| judgment_text | 57.61 | 232.6 |
| legislation_section | 0.05 | 3.4 |
| judgment_judge | 0.15 | 3.4 |
| downloads | 0.1 | 6.0 |
| source_vanga_raw | 0.57 | 4.1 |
| judgment_source_map | 0.11 | 2.4 |
| judgment | 1.66 | 20.4 |
| source_vaquill_raw | 0.05 | 1.2 |
| legislation_act | 0.01 | 0.1 |

### 7.6 Index sizes (largest)

| table | index | MB |
|---|---|---|
| judgment_text | judgment_text_tsv_en_idx | 227.1 |
| judgment_chunk | judgment_chunk_pkey | 45.2 |
| judgment_chunk | judgment_chunk_vaquill_chunk_id_key | 45.2 |
| judgment_field_provenance | judgment_field_provenance_pkey | 21.8 |
| judgment_identifier | judgment_identifier_identifier_type_value_judgment_id_key | 11.8 |
| judgment | judgment_title_trgm_idx | 6.4 |
| judgment_language | judgment_language_pkey | 5.8 |
| judgment_text | judgment_text_pkey | 5.5 |
| downloads | downloads_source_remote_path_key | 5.0 |
| judgment | judgment_search_tsv_idx | 3.9 |
| judgment | judgment_petitioner_trgm_idx | 3.7 |
| judgment | judgment_respondent_trgm_idx | 3.6 |
| legislation_section | legislation_section_pkey | 3.4 |
| judgment_identifier | judgment_identifier_judgment_idx | 2.6 |

Experiment duration: 1637.9 s. Kept: identifier_by_judgment, trgm_petitioner, trgm_respondent, trgm_title, trgm_judge, gin_quality_flags, gin_available_languages, meta_search_tsvector, fts_stored_tsvector. The DDL of the kept set is in `db/migrations/0007_indexes.sql`.
