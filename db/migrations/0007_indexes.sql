-- 0007: secondary indexes, kept by measurement (see docs/STAGE4_REPORT.md). Apply AFTER loading data:
--   .venv/bin/python -I pipeline/09_index_benchmark.py --apply
-- Constraint-backed indexes (PK / unique) are created with the tables in 0001-0006.

-- step: identifier_by_judgment
create index judgment_identifier_judgment_idx on judgment_identifier (judgment_id);

-- step: trgm_petitioner
create index judgment_petitioner_trgm_idx on judgment using gin (petitioner gin_trgm_ops);

-- step: trgm_respondent
create index judgment_respondent_trgm_idx on judgment using gin (respondent gin_trgm_ops);

-- step: trgm_title
create index judgment_title_trgm_idx on judgment using gin (title gin_trgm_ops);

-- step: trgm_judge
create index judgment_judge_trgm_idx on judgment_judge using gin (judge_name_norm gin_trgm_ops);

-- step: gin_quality_flags
create index judgment_quality_flags_idx on judgment using gin (quality_flags);

-- step: gin_available_languages
create index judgment_languages_idx on judgment using gin (available_languages);

-- step: meta_search_tsvector_1
alter table judgment add column search_tsv tsvector generated always as (
  setweight(to_tsvector('english', coalesce(title,'')), 'A') || setweight(to_tsvector('english', coalesce(petitioner,'') || ' ' || coalesce(respondent,'')), 'B')
  || setweight(to_tsvector('simple', coalesce(citation,'') || ' ' || coalesce(insc_id,'')), 'C')) stored;

-- step: meta_search_tsvector_2
create index judgment_search_tsv_idx on judgment using gin (search_tsv);

-- step: fts_stored_tsvector_column
alter table judgment_text add column tsv_en tsvector;

-- step: fts_stored_tsvector_fill
update judgment_text set tsv_en = to_tsvector('english', text) where language_code = 'en';

-- step: fts_stored_tsvector_index
create index judgment_text_tsv_en_idx on judgment_text using gin (tsv_en);
