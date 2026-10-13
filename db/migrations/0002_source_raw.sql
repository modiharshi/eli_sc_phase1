-- 0002: verbatim source records (staging). Nothing here is cleaned or merged.

-- One row per Vanga parquet row (43,552), including the misfiled duplicate copies.
-- `raw` holds all 18 parquet columns plus citation_year, which only exists in the JSON files.
CREATE TABLE source_vanga_raw (
    source_row_id     bigint   PRIMARY KEY,
    year_folder       smallint NOT NULL,          -- the year=YYYY folder the file sat in
    path              text     NOT NULL,          -- Vanga report key, e.g. 1960_3_880_887
    is_canonical_copy boolean  NOT NULL,
    dedupe_reason     text     NOT NULL,          -- 'unique_path' | 'folder_year_matches_decision_year' | 'misfiled_copy'
    raw               jsonb    NOT NULL,
    UNIQUE (year_folder, path)
);
-- Exactly one canonical copy per path.
CREATE UNIQUE INDEX source_vanga_raw_one_canonical ON source_vanga_raw (path) WHERE is_canonical_copy;

-- One row per Vaquill case. All case-level metadata is constant across a case's chunks
-- (verified: 0 exceptions), so it is stored once here; chunk-specific columns live in judgment_chunk.
CREATE TABLE source_vaquill_raw (
    vaquill_case_id text   PRIMARY KEY,           -- e.g. 1960_INSC_103
    raw             jsonb  NOT NULL,
    chunk_row_count integer NOT NULL,
    languages       text[] NOT NULL
);
