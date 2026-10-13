-- 0001: extensions and operational tables.
-- Extensions are enabled now; their indexes are created in the Stage 4 migration.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS btree_gin;

CREATE TABLE pipeline_runs (
    run_id       bigserial PRIMARY KEY,
    stage        text        NOT NULL,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    status       text        NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    row_counts   jsonb,
    detail       text
);

-- Every raw file kept under raw/, with its checksum. Raw files are never modified.
CREATE TABLE downloads (
    download_id   bigserial PRIMARY KEY,
    source        text        NOT NULL CHECK (source IN ('vanga', 'vaquill')),
    remote_path   text        NOT NULL,
    local_path    text        NOT NULL,
    bytes         bigint      NOT NULL CHECK (bytes >= 0),
    sha256        char(64)    NOT NULL,
    downloaded_at timestamptz NOT NULL,
    UNIQUE (source, remote_path)
);

-- Key/value metrics written by each build, so reports can be regenerated from the database.
CREATE TABLE merge_report (
    report_id     bigserial PRIMARY KEY,
    build_id      text        NOT NULL,
    section       text        NOT NULL,
    metric        text        NOT NULL,
    dimension     text        NOT NULL DEFAULT '',
    value_numeric numeric,
    value_text    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (build_id, section, metric, dimension)
);
