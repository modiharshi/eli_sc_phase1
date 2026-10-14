-- 0009: bench size recovered from the judgment text header (a labelled estimate; judgment.bench_strength is unchanged).
-- The sources list only the judges named in their record, usually one, so bench_strength under-counts real benches.
create table if not exists judgment_bench_estimate (
    judgment_id      uuid primary key references judgment (judgment_id),
    judges_in_header smallint not null check (judges_in_header between 1 and 15),
    header           text not null,          -- the matched header text, kept so every estimate can be checked by eye
    method           text not null default 'header_regex_v1',
    computed_at      timestamptz not null default now()
);
create index if not exists judgment_bench_estimate_n_idx on judgment_bench_estimate (judges_in_header);
grant select on judgment_bench_estimate to eli_readonly, eli_app;

-- listed = judges named by the sources; header = estimate above; effective = the larger of the two (never smaller than what a source lists)
create or replace view judgment_bench as
    select j.judgment_id, j.bench_strength as bench_listed, e.judges_in_header as bench_header,
           greatest(j.bench_strength, e.judges_in_header) as bench_effective,
           case when e.judges_in_header is not null and e.judges_in_header > coalesce(j.bench_strength, 0) then 'header estimate'
                when j.bench_strength is not null then 'source judges list' end as bench_basis
    from judgment_visible j left join judgment_bench_estimate e using (judgment_id);
grant select on judgment_bench to eli_readonly, eli_app;
