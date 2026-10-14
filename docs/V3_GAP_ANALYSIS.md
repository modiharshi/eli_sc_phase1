# Gaps between the v3 brief (Stages 3 and 4) and what was built, and how each was closed

Compared on 2026-10-14 against migrations 0001 to 0007. Closed by new migrations 0008 and 0009 and `pipeline/11_derive.py` without redoing any load.

## Stage 3
| v3 brief item | Status at Stage 4 | Action |
|---|---|---|
| `court` table, `court_id` on `judgment` | missing (`judgment.court` text only) | 0008: `court` (Supreme Court only), `judgment.court_id` (default 1, FK) |
| `bench` column | missing | 0008: `judgment.bench` (NULL: no source) |
| `year_decided` | exists as `decision_year` | kept (rename would touch every query; documented) |
| `date_of_registration`, `case_type` | missing | 0008: NULL columns, shown as “no source” (absent from both sources) |
| `disposition` | exists as `disposal` | kept |
| `language` on `judgment` | `available_languages` plus `judgment_language` | kept; richer than one value |
| `judge` and raw-name alias table | missing (`judgment_judge` only) | 0008: `judge`, `judge_alias`, `judgment_judge.judge_id`; 279 names resolved to 279 judges by spacing and punctuation only |
| author flag on `judgment_judge` | missing | 0008: `is_author` (NULL: not in sources) |
| `judgment_text_quality` | missing | 0008 + `11_derive.py`: 135,156 rows (English: 35,479 clean, 117 fair, 0 noisy; other languages: 84,757 clean, 7,661 fair, 7,142 noisy) |
| application tables (`app_user` … `api_usage`) | missing | 0008: all of them, plus `app_session`, `judgment_hidden`, `judgment_pdf` (Stage 10 stub) |
| `review_decision` | `review_audit` existed | both kept: `review_audit` is the pipeline/admin audit, `review_decision` records review-queue decisions |
| tiered matching on diary number etc. | not possible: sources have no diary number or PDF path | `DECISIONS.md` D9 |
| Phase 2 stubs | present | no change |

## Stage 4
| v3 brief item | Status | Action |
|---|---|---|
| facet materialised views (year, disposition, bench, judge, case type) | missing | 0008: `facet_*` and `analytics_bench_by_year`; refreshed by `11_derive.py refresh`. Each reads in about 1 ms |
| B-tree on decision_date, year, disposition, case_number, bench_strength, case_type | measured and not kept (`DECISIONS.md` S18) | unchanged: no measured query needed them; case_number and case_type are always NULL |
| unique and B-tree on every identifier and foreign key | unique keys exist; FK columns not all indexed | unchanged; no measured query needed them |
| GIN tsvector for full text, weighted tsvector over title and parties, trigram on parties, title, judges | kept | none |
| `pg_trgm`, `unaccent`, `btree_gin` | installed | none |
| `pgvector` column design | not present | deliberately not added; Stage 9, needs your approval |
| timings: id lookup < 50 ms, party fuzzy < 300 ms, full text < 2 s, facets < 500 ms | all met except `title_fuzzy` | `title_fuzzy` re-measured with similarity threshold 0.4: p95 197 ms (0.3: 357 ms in the same run); recall of the original title 100/100 (`DECISIONS.md` S25) |

## Found while building Stage 6
* Bench size: the sources list one judge for 91% of judgments (`BENCH_ESTIMATE.md`); migration 0009 adds a labelled header-based estimate.
* `docs/LICENCES.md` and `docs/SOURCE_PROFILE.md` (Stage 1 deliverables) had not been written; both are now.
