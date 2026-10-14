-- 0008: gaps between the v3 brief (Stages 3 to 9) and migrations 0001-0007.
-- DDL only and additive: no load is redone. Derived rows (judges, text quality, matviews)
-- are filled by pipeline/11_derive.py, which is idempotent.

-- ---- court (court-agnostic design) --------------------------------------------------------
create table if not exists court (
    court_id smallint generated always as identity primary key,
    name     text not null unique,
    code     text not null unique,
    type     text not null
);
insert into court (name, code, type) values ('Supreme Court of India', 'SC', 'supreme_court') on conflict do nothing;

-- default 1 = the only court loaded today; a load for another court must set court_id explicitly.
alter table judgment add column if not exists court_id smallint not null default 1 references court (court_id);
-- Fields in the brief that neither source contains. Always NULL, shown as "no source" in the UI.
alter table judgment add column if not exists date_of_registration date;
alter table judgment add column if not exists case_type text;
alter table judgment add column if not exists bench text;

-- ---- judges and aliases -------------------------------------------------------------------
create table if not exists judge (
    judge_id     integer generated always as identity primary key,
    canonical_name text not null unique,
    alias_key    text not null unique          -- upper-case, no spaces or full stops
);
create table if not exists judge_alias (
    alias_name text primary key,               -- a name exactly as it appears in judgment_judge.judge_name_norm
    judge_id   integer not null references judge (judge_id),
    method     text not null default 'punctuation_spacing'
);
alter table judgment_judge add column if not exists judge_id integer references judge (judge_id);
-- Neither source says who wrote the judgment. Stays NULL; judge pages mark it unavailable.
alter table judgment_judge add column if not exists is_author boolean;

-- ---- text quality -------------------------------------------------------------------------
create table if not exists judgment_text_quality (
    judgment_id        uuid not null references judgment (judgment_id),
    language_code      text not null,
    non_english_share  real,                   -- share of letters outside Latin script
    garbage_ratio      real,                   -- share of replacement, control and U+2400 characters
    chars_per_page     real,                   -- text length per page spanned by the chunks
    empty_chunks       integer,
    label              text not null check (label in ('clean', 'fair', 'noisy')),
    reasons            text[] not null default '{}',
    computed_at        timestamptz not null default now(),
    primary key (judgment_id, language_code)
);

-- ---- hide / takedown (admin action, audit kept) -------------------------------------------
create table if not exists judgment_hidden (
    judgment_id uuid primary key references judgment (judgment_id),
    hidden_by   text not null,
    reason      text not null,
    hidden_at   timestamptz not null default now()
);
create table if not exists takedown_request (
    request_id   bigint generated always as identity primary key,
    judgment_id  uuid references judgment (judgment_id),
    requester_name text,
    requester_contact text,
    reason       text not null,
    status       text not null default 'open' check (status in ('open', 'actioned', 'rejected')),
    created_at   timestamptz not null default now(),
    decided_by   text,
    decided_at   timestamptz
);

-- ---- application tables -------------------------------------------------------------------
create table if not exists app_user (
    user_id       integer generated always as identity primary key,
    username      text not null unique,
    password_hash text not null,
    role          text not null default 'viewer' check (role in ('admin', 'tester', 'viewer')),
    created_at    timestamptz not null default now(),
    last_login_at timestamptz,
    disabled      boolean not null default false
);
create table if not exists app_session (
    token_hash text primary key,
    user_id    integer not null references app_user (user_id) on delete cascade,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);
create table if not exists saved_search (
    search_id  bigint generated always as identity primary key,
    user_id    integer not null references app_user (user_id) on delete cascade,
    name       text not null,
    query      jsonb not null,
    alert_weekly boolean not null default false,
    created_at timestamptz not null default now()
);
create table if not exists bookmark (
    user_id     integer not null references app_user (user_id) on delete cascade,
    judgment_id uuid not null references judgment (judgment_id),
    created_at  timestamptz not null default now(),
    primary key (user_id, judgment_id)
);
create table if not exists note (
    note_id     bigint generated always as identity primary key,
    user_id     integer not null references app_user (user_id) on delete cascade,
    judgment_id uuid not null references judgment (judgment_id),
    body        text not null,
    created_at  timestamptz not null default now()
);
create table if not exists highlight (
    highlight_id bigint generated always as identity primary key,
    user_id      integer not null references app_user (user_id) on delete cascade,
    judgment_id  uuid not null references judgment (judgment_id),
    language_code text not null default 'en',
    char_start   integer not null,
    char_end     integer not null check (char_end > char_start),
    colour       text,
    created_at   timestamptz not null default now()
);
create table if not exists error_report (
    report_id   bigint generated always as identity primary key,
    user_id     integer references app_user (user_id),
    judgment_id uuid not null references judgment (judgment_id),
    field_name  text not null,
    current_value text,
    suggested_value text,
    comment     text,
    status      text not null default 'open' check (status in ('open', 'accepted', 'rejected')),
    created_at  timestamptz not null default now(),
    decided_by  text,
    decided_at  timestamptz
);
create table if not exists review_decision (
    decision_id bigint generated always as identity primary key,
    queue       text not null,                 -- match_review_queue / field_conflicts / error_report
    item_key    text not null,
    decision    text not null,
    decided_by  text not null,
    decided_at  timestamptz not null default now(),
    before_value jsonb,
    after_value  jsonb,
    note        text
);
create table if not exists api_key (
    key_id      integer generated always as identity primary key,
    user_id     integer references app_user (user_id),
    key_hash    text not null unique,
    label       text,
    rate_limit_per_min integer not null default 60,
    created_at  timestamptz not null default now(),
    revoked_at  timestamptz
);
create table if not exists api_usage (
    usage_id bigint generated always as identity primary key,
    key_id   integer references api_key (key_id),
    endpoint text not null,
    status   smallint not null,
    ms       integer,
    at       timestamptz not null default now()
);
create table if not exists benchmark_query (
    query_id  integer generated always as identity primary key,
    kind      text not null,                   -- findability / search_quality / advocate_task
    text      text not null,
    expected  jsonb,
    proposed  boolean not null default true    -- proposed by Claude until the owner confirms
);
create table if not exists benchmark_result (
    result_id bigint generated always as identity primary key,
    query_id  integer not null references benchmark_query (query_id),
    run_at    timestamptz not null default now(),
    tester    text,
    system    text not null default 'eli',     -- eli / indian_kanoon
    outcome   jsonb not null,
    seconds   real,
    rating    smallint
);
create table if not exists ai_case_brief (
    judgment_id uuid not null references judgment (judgment_id),
    language_code text not null default 'en',
    prompt_version text not null,
    model       text not null,
    brief       jsonb not null,
    cost_usd    numeric(10, 6) not null default 0,
    created_at  timestamptz not null default now(),
    feedback    smallint,
    primary key (judgment_id, language_code, prompt_version)
);
create table if not exists ai_question_log (
    log_id      bigint generated always as identity primary key,
    user_id     integer references app_user (user_id),
    judgment_id uuid not null references judgment (judgment_id),
    question    text not null,
    answer      jsonb,
    model       text,
    cost_usd    numeric(10, 6) not null default 0,
    created_at  timestamptz not null default now()
);

-- Stage 10 stub, empty.
create table if not exists judgment_pdf (
    judgment_id uuid not null references judgment (judgment_id),
    language_code text not null,
    vanga_id    text,
    object_key  text not null,
    bytes       bigint,
    sha256      text,
    primary key (judgment_id, language_code)
);

-- ---- facet and analytics materialised views (refreshed by pipeline/11_derive.py) -----------
-- Hidden judgments are excluded everywhere.
create or replace view judgment_visible as
    select j.* from judgment j where not exists (select 1 from judgment_hidden h where h.judgment_id = j.judgment_id);

drop materialized view if exists facet_year, facet_disposition, facet_bench, facet_judge, facet_case_type, analytics_bench_by_year;
create materialized view facet_year as
    select decision_year as value, count(*)::int n from judgment_visible group by 1;
create materialized view facet_disposition as
    select coalesce(disposal, '(none)') as value, count(*)::int n from judgment_visible group by 1;
create materialized view facet_bench as
    select bench_strength as value, count(*)::int n from judgment_visible group by 1;
create materialized view facet_judge as
    select g.judge_id, g.judge_name_norm as value, count(distinct g.judgment_id)::int n
    from judgment_judge g join judgment_visible j using (judgment_id) group by 1, 2;
create materialized view facet_case_type as
    select coalesce(case_type, '(no source)') as value, count(*)::int n from judgment_visible group by 1;
create materialized view analytics_bench_by_year as
    select decision_year, bench_strength, count(*)::int n from judgment_visible group by 1, 2;
create unique index on facet_year (value);
create unique index on facet_disposition (value);
create unique index on facet_bench (value);
create unique index on facet_judge (judge_id, value);
create unique index on facet_case_type (value);
create unique index on analytics_bench_by_year (decision_year, bench_strength);

-- the read-only role may read everything new except credentials and sessions
grant select on all tables in schema public to eli_readonly;
revoke select on app_user, app_session, api_key from eli_readonly;
