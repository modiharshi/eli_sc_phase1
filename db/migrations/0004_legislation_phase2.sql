-- 0004: legislation (loaded from in_central_legislation.parquet in Stage 4) and the Phase 2 stubs.
-- The stubs are created empty with their foreign keys so Phase 2 plugs in without a rewrite.

CREATE TABLE legislation_act (
    act_id           text PRIMARY KEY,
    title            text NOT NULL,
    year             smallint,
    jurisdiction     text,
    state            text,
    instrument_type  text,
    doc_type         text,
    act_status       text,
    in_force         boolean,
    source_url       text,
    mirror_url       text,
    source_publisher text,
    language_code    text
);

CREATE TABLE legislation_section (
    chunk_id          text PRIMARY KEY,
    act_id            text NOT NULL REFERENCES legislation_act,
    chapter           text,
    section_number    text,
    section_title     text,
    text              text NOT NULL,
    section_type      text,
    provision_type    text,
    legal_subject     text,              -- stringified list in the source, kept as delivered
    has_proviso       boolean,
    has_non_obstante  boolean,
    delegation_type   text,
    department        text,
    regulatory_body   integer,
    acts_referenced   text[],
    defined_terms     text[],
    amendment_count   integer,
    source_url        text
);

CREATE TABLE judgment_paragraph (
    paragraph_id  bigserial PRIMARY KEY,
    judgment_id   uuid     NOT NULL REFERENCES judgment,
    language_code text     NOT NULL DEFAULT 'en',
    ordinal       integer  NOT NULL,
    para_label    text,
    text          text     NOT NULL,
    char_start    integer  NOT NULL,
    char_end      integer  NOT NULL,
    method        text     NOT NULL,
    UNIQUE (judgment_id, language_code, ordinal)
);

CREATE TABLE citation_mention (
    mention_id       bigserial PRIMARY KEY,
    judgment_id      uuid    NOT NULL REFERENCES judgment,
    paragraph_id     bigint  REFERENCES judgment_paragraph,
    raw_text         text    NOT NULL,
    char_start       integer NOT NULL,
    char_end         integer NOT NULL,
    citation_type    text,
    normalized_value text,
    method           text    NOT NULL
);

-- Edges only for unique or human-confirmed matches.
CREATE TABLE cites_edge (
    edge_id           bigserial PRIMARY KEY,
    from_judgment_id  uuid   NOT NULL REFERENCES judgment,
    to_judgment_id    uuid   NOT NULL REFERENCES judgment,
    mention_id        bigint NOT NULL REFERENCES citation_mention,
    match_status      text   NOT NULL CHECK (match_status IN ('unique', 'human_confirmed')),
    confirmed_by      text,
    UNIQUE (from_judgment_id, to_judgment_id, mention_id)
);

CREATE TABLE judgment_statute (
    link_id        bigserial PRIMARY KEY,
    judgment_id    uuid   NOT NULL REFERENCES judgment,
    paragraph_id   bigint REFERENCES judgment_paragraph,
    act_id         text   NOT NULL REFERENCES legislation_act,
    chunk_id       text   REFERENCES legislation_section,
    mention_text   text,
    method         text   NOT NULL
);
