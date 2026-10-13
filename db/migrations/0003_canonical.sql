-- 0003: canonical model. Vanga is the canonical source for judgment records and metadata;
-- Vaquill enriches with full text, judges list and language-specific chunks.

CREATE TABLE judgment (
    judgment_id        uuid     PRIMARY KEY,      -- uuid5 of the Vanga path: stable across rebuilds
    vanga_path         text     NOT NULL UNIQUE,
    insc_id            text,                      -- '1960 INSC 103'. NOT unique: 96 ids are shared by distinct reports
    title              text,
    petitioner         text,
    respondent         text,
    decision_date      date,
    decision_year      smallint,                  -- always derived from decision_date
    citation           text,                      -- report citation, e.g. [1960] 3 S.C.R. 880
    cnr                text,
    disposal           text,
    court              text,
    bench_strength     smallint,                  -- derived: number of judgment_judge rows
    case_number        text,                      -- no source in either dataset; always NULL for now
    diary_number       text,                      -- no source in either dataset; always NULL for now
    pdf_url            text,                      -- filled in Stage 8
    vanga_year_field   smallint,                  -- Vanga `year` as delivered (law-report year)
    vaquill_year_field smallint,                  -- Vaquill `year` as delivered
    vanga_year_folder  smallint,                  -- year=YYYY folder of the canonical copy
    available_languages text[],                   -- languages Vanga lists a PDF for (normalised codes)
    text_status        text     NOT NULL CHECK (text_status IN ('english', 'translation_only', 'none')),
    match_status       text     NOT NULL CHECK (match_status IN ('matched', 'vanga_only', 'in_review')),
    quality_flags      text[]   NOT NULL DEFAULT '{}',
    vanga_scraped_at   timestamptz,
    build_id           text     NOT NULL,
    CONSTRAINT decision_year_matches_date
        CHECK (decision_year IS NOT DISTINCT FROM EXTRACT(YEAR FROM decision_date)::smallint)
);

CREATE TABLE judgment_source_map (
    judgment_id      uuid PRIMARY KEY REFERENCES judgment,
    vanga_path       text NOT NULL REFERENCES judgment (vanga_path),
    vaquill_case_id  text REFERENCES source_vaquill_raw,
    match_method     text NOT NULL,   -- 'insc_id+citation' | 'none:empty_insc_id' | 'none:no_vaquill_candidate' | 'none:shared_insc_id_citation_differs' | 'review'
    match_confidence numeric(3,2) NOT NULL CHECK (match_confidence BETWEEN 0 AND 1),
    match_status     text NOT NULL CHECK (match_status IN ('matched', 'vanga_only', 'in_review')),
    UNIQUE (vaquill_case_id)          -- a Vaquill case is attached to at most one judgment
);

CREATE TABLE judgment_field_provenance (
    judgment_id   uuid NOT NULL REFERENCES judgment,
    field_name    text NOT NULL,
    chosen_source text NOT NULL CHECK (chosen_source IN ('vanga', 'vaquill', 'derived', 'none')),
    chosen_value  text,
    alt_value     text,               -- the other source's value when it differs; never overwritten
    reason        text NOT NULL,
    PRIMARY KEY (judgment_id, field_name)
);

-- Every disagreement between sources. Nothing is resolved silently.
CREATE TABLE field_conflicts (
    conflict_id   bigserial PRIMARY KEY,
    judgment_id   uuid NOT NULL REFERENCES judgment,
    field_name    text NOT NULL,
    vanga_value   text,
    vaquill_value text,
    resolution    text NOT NULL,
    status        text NOT NULL DEFAULT 'auto_resolved' CHECK (status IN ('auto_resolved', 'open', 'accepted', 'rejected')),
    UNIQUE (judgment_id, field_name)
);

-- Matches that were NOT merged: ambiguous, conflicting or orphaned.
CREATE TABLE match_review_queue (
    review_id       bigserial PRIMARY KEY,
    kind            text NOT NULL CHECK (kind IN ('ambiguous_match', 'citation_conflict', 'date_conflict', 'vaquill_orphan')),
    vaquill_case_id text NOT NULL REFERENCES source_vaquill_raw,
    candidate_paths text[] NOT NULL DEFAULT '{}',
    detail          jsonb,
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'rejected')),
    decided_by      text,
    decided_at      timestamptz,
    decision_note   text
);

CREATE TABLE judgment_judge (
    judgment_id     uuid     NOT NULL REFERENCES judgment,
    position        smallint NOT NULL,            -- 1-based order on the bench
    judge_name_raw  text     NOT NULL,
    judge_name_norm text     NOT NULL,            -- upper-case, whitespace collapsed
    source          text     NOT NULL CHECK (source IN ('vanga', 'vaquill')),
    PRIMARY KEY (judgment_id, position)
);

CREATE TABLE judgment_identifier (
    judgment_id     uuid NOT NULL REFERENCES judgment,
    identifier_type text NOT NULL,                -- INSC | SCR | CNR | VANGA_PATH | NC_DISPLAY (SCC, AIR, DIARY_NO: no source yet)
    value           text NOT NULL,
    source          text NOT NULL CHECK (source IN ('vanga', 'vaquill', 'both')),
    UNIQUE (identifier_type, value, judgment_id)
);

-- Which languages exist for a judgment, and in what form. "No English text" is distinguishable
-- from "no text at all": the former has rows here with text_chunks > 0 for other languages.
CREATE TABLE judgment_language (
    judgment_id     uuid    NOT NULL REFERENCES judgment,
    language_code   text    NOT NULL,
    pdf_listed      boolean NOT NULL,             -- Vanga lists a PDF in this language
    text_available  boolean NOT NULL,             -- Vaquill has chunks in this language
    text_chunks     integer NOT NULL DEFAULT 0,
    expected_chunks integer,
    PRIMARY KEY (judgment_id, language_code)
);

-- Vaquill chunks, verbatim apart from two lossless storage choices:
--  * case-level metadata (title, judges, ...) is stored once in source_vaquill_raw (constant per case);
--  * text_original is NULL when it equals text (true for every row at build time, asserted).
CREATE TABLE judgment_chunk (
    judgment_id      uuid     NOT NULL REFERENCES judgment,
    language_code    text     NOT NULL,
    chunk_index      integer  NOT NULL,
    vaquill_chunk_id text     NOT NULL UNIQUE,
    vaquill_case_id  text     NOT NULL REFERENCES source_vaquill_raw,
    total_chunks     integer  NOT NULL,
    text             text     NOT NULL,           -- raw, including the "Case: ... Section: ..." header
    text_original    text,
    char_start       integer  NOT NULL,
    char_end         integer  NOT NULL,
    page_start       integer,
    page_end         integer,
    section_type     text,
    section_priority integer,
    box_aware        boolean,
    PRIMARY KEY (judgment_id, language_code, chunk_index)
);

-- Assembled full text, one row per judgment and language. Built from judgment_chunk with the
-- header stripped and overlapping chunk windows de-duplicated using char offsets.
CREATE TABLE judgment_text (
    judgment_id        uuid    NOT NULL REFERENCES judgment,
    language_code      text    NOT NULL,
    text               text    NOT NULL,
    text_source        text    NOT NULL DEFAULT 'vaquill',
    chunk_count        integer NOT NULL,
    expected_chunks    integer NOT NULL,
    char_length        integer NOT NULL,
    is_complete        boolean NOT NULL,          -- all chunks present and no gap larger than 2 characters
    small_gap_count    integer NOT NULL,          -- gaps of 1-2 characters (whitespace between chunks), filled with newlines
    large_gap_count    integer NOT NULL,          -- missing text; marks the set incomplete
    overlap_mismatches integer NOT NULL,          -- overlap region differing from the text already assembled
    PRIMARY KEY (judgment_id, language_code),
    FOREIGN KEY (judgment_id, language_code) REFERENCES judgment_language
);
