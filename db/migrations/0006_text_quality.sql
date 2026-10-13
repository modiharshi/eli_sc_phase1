-- 0006: per-text quality tracking, kept separate from language availability (judgment_language).
-- Additive: the Stage 3 tables are unchanged apart from these columns and one view.
ALTER TABLE judgment_text
    ADD COLUMN chunks_contiguous     boolean NOT NULL,   -- chunk indexes are exactly 0..n-1 and n = expected chunks
    ADD COLUMN offset_drift_chunks   integer NOT NULL,   -- chunks whose body length differs from their char window
    ADD COLUMN incompleteness_reason text    NOT NULL
        CHECK (incompleteness_reason IN ('complete', 'missing_chunks', 'text_gap', 'missing_chunks_and_text_gap')),
    ADD CONSTRAINT text_completeness_consistent
        CHECK (is_complete = (incompleteness_reason = 'complete')
               AND chunks_contiguous = (incompleteness_reason IN ('complete', 'text_gap'))
               AND (large_gap_count > 0) = (incompleteness_reason IN ('text_gap', 'missing_chunks_and_text_gap')));

COMMENT ON COLUMN judgment_text.is_complete IS 'false when chunks are missing or text is missing between chunks; the text is kept as delivered, never repaired';
COMMENT ON COLUMN judgment_text.overlap_mismatches IS 'overlap regions where two chunks disagree; earlier chunk kept. Independent of completeness';
COMMENT ON COLUMN judgment_text.offset_drift_chunks IS 'chunks whose length differs from char_end - char_start. Independent of completeness';

-- One row per judgment for retrieval and evaluation code: language availability and text quality side by side,
-- so a ranked hit on an incomplete or inconsistent text can be shown, filtered or excluded explicitly.
CREATE VIEW judgment_retrieval_status AS
SELECT j.judgment_id, j.vanga_path, j.insc_id, j.title, j.decision_date, j.decision_year,
       j.text_status, j.match_status,
       (en.judgment_id IS NOT NULL)                          AS english_text_available,
       en.is_complete                                        AS english_text_complete,
       en.incompleteness_reason                              AS english_incompleteness_reason,
       en.overlap_mismatches                                 AS english_overlap_mismatches,
       en.offset_drift_chunks                                AS english_offset_drift_chunks,
       en.chunk_count                                        AS english_chunk_count,
       en.expected_chunks                                    AS english_expected_chunks,
       COALESCE(l.text_languages, '{}')                      AS languages_with_text,
       COALESCE(l.pdf_languages, '{}')                       AS languages_pdf_listed
FROM judgment j
LEFT JOIN judgment_text en ON en.judgment_id = j.judgment_id AND en.language_code = 'en'
LEFT JOIN (SELECT judgment_id,
                  array_agg(language_code ORDER BY language_code) FILTER (WHERE text_available) AS text_languages,
                  array_agg(language_code ORDER BY language_code) FILTER (WHERE pdf_listed)     AS pdf_languages
           FROM judgment_language GROUP BY judgment_id) l ON l.judgment_id = j.judgment_id;

-- PostgreSQL text cannot hold U+0000. The raw Vaquill data contains NUL in a few garbled chunks (Hindi, Malayalam).
-- In the database copy each NUL is replaced one-for-one by U+2400 (symbol for null), so lengths and offsets are unchanged.
-- Every affected row is listed here; the raw Parquet files are never modified, so the substitution is fully reversible.
CREATE TABLE text_sanitization_log (
    log_id      bigserial PRIMARY KEY,
    table_name  text    NOT NULL,
    row_key     text    NOT NULL,          -- vaquill_chunk_id for judgment_chunk; judgment_id/language for judgment_text
    column_name text    NOT NULL,
    nul_count   integer NOT NULL CHECK (nul_count > 0),
    replacement text    NOT NULL,
    note        text    NOT NULL,
    UNIQUE (table_name, row_key, column_name)
);
