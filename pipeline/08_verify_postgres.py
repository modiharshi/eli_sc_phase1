#!/usr/bin/env python3
"""Stage 4 verification of the loaded database. Writes build/verify_report.json (rendered by 10_stage4_report.py).

1. row counts: parquet vs database
2. content fingerprints: the same aggregate computed by DuckDB on the parquet and by PostgreSQL on the table
3. constraints: every PK/FK/unique/check present and validated; every FK checked for orphans
4. negative tests: writes that must be rejected, run inside rolled-back transactions
5. logical integrity beyond foreign keys
6. language availability vs text completeness reconciliation
7. sizes
Read-only on the data (negative tests roll back). Run:  .venv/bin/python -I pipeline/08_verify_postgres.py
"""
import json
import pathlib
import sys
import time

import duckdb
import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pgconn  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "build"
LEG = ROOT / "raw" / "vaquill" / "in_central_legislation.parquet"
R = "␀"  # NUL replacement used by the loader

duck = duckdb.connect()
duck.execute("set threads=4")
duck.execute("set memory_limit='5GB'")
pg = pgconn.connect("admin", autocommit=True)
out = {}
t0 = time.time()


def log(m):
    print(f"[{time.time() - t0:7.1f}s] {m}", flush=True)


def pq(sql, params=None):
    return pg.execute(sql, params).fetchall()


def dq(sql):
    return duck.execute(sql).fetchall()


P = lambda t: f"read_parquet('{B}/{t}.parquet')"

# ------------------------------------------------------------------ 1. row counts
load = json.loads((B / "load_report.json").read_text())
db_tables = [r[0] for r in pq("select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1")]
counts = []
for t in db_tables:
    n_db = pq(f'select count(*) from "{t}"')[0][0]
    exp = load["tables"].get(t, {}).get("rows_parquet")
    counts.append({"table": t, "rows_parquet": exp, "rows_database": n_db, "ok": (exp == n_db) if exp is not None else (n_db == 0 or t in ("pipeline_runs",)),
                   "note": "" if exp is not None else ("not loaded by design (empty)" if n_db == 0 else "written by the pipeline run log")})
out["counts"] = counts
log(f"counts: {sum(c['ok'] for c in counts)}/{len(counts)} tables match")

# ------------------------------------------------------------------ 2. fingerprints
O = lambda cols, key: f"order by {key}"
FP = []  # (name, duckdb sql, postgres sql)
FP.append(("judgment", f"""select count(*), sum(decision_year), count(distinct insc_id), md5(string_agg(judgment_id || '|' || coalesce(title,'') || '|' || coalesce(cast(decision_date as varchar),'') || '|' || coalesce(citation,''), ',' order by judgment_id)) from {P('judgment')}""",
           """select count(*), sum(decision_year), count(distinct insc_id), md5(string_agg(judgment_id::text || '|' || coalesce(title,'') || '|' || coalesce(decision_date::text,'') || '|' || coalesce(citation,''), ',' order by judgment_id::text collate "C")) from judgment"""))
FP.append(("judgment arrays and flags", f"""select md5(string_agg(coalesce(array_to_string(available_languages, ','), '~') || '/' || array_to_string(quality_flags, ',') || '/' || text_status || '/' || match_status, ';' order by judgment_id)) from {P('judgment')}""",
           """select md5(string_agg(coalesce(array_to_string(available_languages, ','), '~') || '/' || array_to_string(quality_flags, ',') || '/' || text_status || '/' || match_status, ';' order by judgment_id::text collate "C")) from judgment"""))
FP.append(("judgment_chunk", f"""select count(*), sum(char_start), sum(char_end), sum(total_chunks), count(text_original), count(distinct judgment_id), md5(string_agg(md5(replace(text, chr(0), '{R}')), '' order by judgment_id, language_code, chunk_index)) from {P('judgment_chunk')}""",
           """select count(*), sum(char_start), sum(char_end), sum(total_chunks), count(text_original), count(distinct judgment_id), md5(string_agg(md5(text), '' order by judgment_id::text collate "C", language_code collate "C", chunk_index)) from judgment_chunk"""))
FP.append(("judgment_text", f"""select count(*), sum(char_length), sum(chunk_count), sum(overlap_mismatches), sum(offset_drift_chunks), count(*) filter(where is_complete), md5(string_agg(md5(replace(text, chr(0), '{R}')) || incompleteness_reason, '' order by judgment_id, language_code)) from {P('judgment_text')}""",
           """select count(*), sum(char_length), sum(chunk_count), sum(overlap_mismatches), sum(offset_drift_chunks), count(*) filter(where is_complete), md5(string_agg(md5(text) || incompleteness_reason, '' order by judgment_id::text collate "C", language_code collate "C")) from judgment_text"""))
FP.append(("judgment_field_provenance", f"""select count(*), md5(string_agg(judgment_id || field_name || chosen_source || coalesce(chosen_value,'') || coalesce(alt_value,'') || reason, '|' order by judgment_id, field_name)) from {P('judgment_field_provenance')}""",
           """select count(*), md5(string_agg(judgment_id::text || field_name || chosen_source || coalesce(chosen_value,'') || coalesce(alt_value,'') || reason, '|' order by judgment_id::text collate "C", field_name collate "C")) from judgment_field_provenance"""))
FP.append(("judgment_identifier", f"""select count(*), md5(string_agg(judgment_id || identifier_type || value || source, '|' order by judgment_id, identifier_type, value)) from {P('judgment_identifier')}""",
           """select count(*), md5(string_agg(judgment_id::text || identifier_type || value || source, '|' order by judgment_id::text collate "C", identifier_type collate "C", value collate "C")) from judgment_identifier"""))
FP.append(("judgment_judge", f"""select count(*), md5(string_agg(judgment_id || cast(position as varchar) || judge_name_raw || judge_name_norm || source, '|' order by judgment_id, position)) from {P('judgment_judge')}""",
           """select count(*), md5(string_agg(judgment_id::text || position::text || judge_name_raw || judge_name_norm || source, '|' order by judgment_id::text collate "C", position)) from judgment_judge"""))
FP.append(("judgment_language", f"""select count(*), sum(text_chunks), count(*) filter(where pdf_listed), count(*) filter(where text_available), md5(string_agg(judgment_id || language_code || cast(coalesce(expected_chunks, -1) as varchar), '|' order by judgment_id, language_code)) from {P('judgment_language')}""",
           """select count(*), sum(text_chunks), count(*) filter(where pdf_listed), count(*) filter(where text_available), md5(string_agg(judgment_id::text || language_code || coalesce(expected_chunks, -1)::text, '|' order by judgment_id::text collate "C", language_code collate "C")) from judgment_language"""))
FP.append(("judgment_source_map", f"""select count(*), count(vaquill_case_id), md5(string_agg(judgment_id || vanga_path || coalesce(vaquill_case_id,'~') || match_method || match_status, '|' order by judgment_id)) from {P('judgment_source_map')}""",
           """select count(*), count(vaquill_case_id), md5(string_agg(judgment_id::text || vanga_path || coalesce(vaquill_case_id,'~') || match_method || match_status, '|' order by judgment_id::text collate "C")) from judgment_source_map"""))
FP.append(("source_vanga_raw (keys + JSON fields)", f"""select count(*), md5(string_agg(cast(source_row_id as varchar) || cast(year_folder as varchar) || path || cast(is_canonical_copy as varchar) || dedupe_reason || coalesce(json_extract_string(raw,'$.case_id'),'') || coalesce(json_extract_string(raw,'$.citation'),'') || coalesce(json_extract_string(raw,'$.scraped_at'),''), '|' order by source_row_id)) from {P('source_vanga_raw')}""",
           """select count(*), md5(string_agg(source_row_id::text || year_folder::text || path || is_canonical_copy::text || dedupe_reason || coalesce(raw->>'case_id','') || coalesce(raw->>'citation','') || coalesce(raw->>'scraped_at',''), '|' order by source_row_id)) from source_vanga_raw"""))
FP.append(("source_vaquill_raw (keys + JSON fields)", f"""select count(*), sum(chunk_row_count), md5(string_agg(vaquill_case_id || array_to_string(languages, ',') || coalesce(json_extract_string(raw,'$.citation'),'') || coalesce(json_extract_string(raw,'$.decision_date'),''), '|' order by vaquill_case_id)) from {P('source_vaquill_raw')}""",
           """select count(*), sum(chunk_row_count), md5(string_agg(vaquill_case_id || array_to_string(languages, ',') || coalesce(raw->>'citation','') || coalesce(raw->>'decision_date',''), '|' order by vaquill_case_id collate "C")) from source_vaquill_raw"""))
FP.append(("text_sanitization_log", f"""select count(*), sum(nul_count) from (select (length(text) - length(replace(text, chr(0), '')))::int as nul_count from {P('judgment_chunk')} where text like '%' || chr(0) || '%' union all select (length(text) - length(replace(text, chr(0), '')))::int from {P('judgment_text')} where text like '%' || chr(0) || '%')""",
           """select count(*), sum(nul_count) from text_sanitization_log"""))
FP.append(("legislation_section", f"""select count(*), md5(string_agg(chunk_id || act_id || coalesce(section_number,'') || coalesce(section_type,'') || cast(length(text) as varchar), '|' order by chunk_id)) from read_parquet('{LEG}')""",
           """select count(*), md5(string_agg(chunk_id || act_id || coalesce(section_number,'') || coalesce(section_type,'') || length(text)::text, '|' order by chunk_id collate "C")) from legislation_section"""))
FP.append(("legislation_act", f"""select count(distinct act_id), md5(string_agg(act_id || any_t, '|' order by act_id)) from (select act_id, any_value(title) as any_t from read_parquet('{LEG}') group by 1)""",
           """select count(*), md5(string_agg(act_id || title, '|' order by act_id collate "C")) from legislation_act"""))
fps = []
for name, dsql, psql in FP:
    t1 = time.time()
    d = [str(x) for x in dq(dsql)[0]]
    t2 = time.time()
    p = [str(x) for x in pq(psql)[0]]
    ok = d == p
    fps.append({"name": name, "parquet": d, "database": p, "ok": ok, "seconds": round(time.time() - t1, 1)})
    log(f"fingerprint {name}: {'MATCH' if ok else 'DIFFERENT'} ({time.time() - t1:.1f}s)")
out["fingerprints"] = fps

# ------------------------------------------------------------------ 3. constraints and orphans
cons = pq("""select conrelid::regclass::text, contype, count(*), bool_and(convalidated) from pg_constraint
             where connamespace = 'public'::regnamespace and contype in ('p','f','u','c') group by 1, 2 order by 1, 2""")
out["constraints"] = [{"table": a, "type": {"p": "primary key", "f": "foreign key", "u": "unique", "c": "check"}[b], "count": c, "validated": v} for a, b, c, v in cons]
fks = pq("""select c.conname, c.conrelid::regclass::text, c.confrelid::regclass::text,
                   (select array_agg(a.attname order by k.ord) from unnest(c.conkey) with ordinality k(attnum, ord) join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum),
                   (select array_agg(a.attname order by k.ord) from unnest(c.confkey) with ordinality k(attnum, ord) join pg_attribute a on a.attrelid = c.confrelid and a.attnum = k.attnum)
            from pg_constraint c where c.contype = 'f' and c.connamespace = 'public'::regnamespace order by 2, 1""")
orphans = []
for name, child, parent, ccols, pcols in fks:
    cond = " and ".join(f'c."{a}" = p."{b}"' for a, b in zip(ccols, pcols))
    notnull = " and ".join(f'c."{a}" is not null' for a in ccols)
    n_orph = pq(f"select count(*) from {child} c where {notnull} and not exists (select 1 from {parent} p where {cond})")[0][0]
    orphans.append({"constraint": name, "child": child, "columns": ccols, "parent": parent, "orphans": n_orph})
out["orphans"] = orphans
log(f"foreign keys checked: {len(orphans)}, total orphans {sum(o['orphans'] for o in orphans)}")

# ------------------------------------------------------------------ 4. negative tests (all rolled back)
class Rollback(Exception):
    pass


NEG = [
    ("duplicate primary key (judgment_judge)", "insert into judgment_judge select * from judgment_judge limit 1", psycopg.errors.UniqueViolation),
    ("orphan foreign key (judgment_chunk -> judgment)", "insert into judgment_chunk (judgment_id, language_code, chunk_index, vaquill_chunk_id, vaquill_case_id, total_chunks, text, char_start, char_end) "
     "select gen_random_uuid(), 'en', 0, 'x', vaquill_case_id, 1, 't', 0, 1 from source_vaquill_raw limit 1", psycopg.errors.ForeignKeyViolation),
    ("decision_year must equal year(decision_date)", "update judgment set decision_year = 1900 where judgment_id = (select judgment_id from judgment limit 1)", psycopg.errors.CheckViolation),
    ("completeness flags must be mutually consistent", "update judgment_text set is_complete = not is_complete where (judgment_id, language_code) = (select judgment_id, language_code from judgment_text limit 1)", psycopg.errors.CheckViolation),
    ("second canonical copy of a Vanga path", "insert into source_vanga_raw select source_row_id + 100000000, 1900, path, true, 'unique_path', raw from source_vanga_raw where is_canonical_copy limit 1", psycopg.errors.UniqueViolation),
    ("a Vaquill case attached to two judgments", "update judgment_source_map set vaquill_case_id = (select vaquill_case_id from judgment_source_map where vaquill_case_id is not null limit 1) where vaquill_case_id is null and judgment_id = (select judgment_id from judgment_source_map where vaquill_case_id is null limit 1)", psycopg.errors.UniqueViolation),
    ("invalid text_status value", "update judgment set text_status = 'maybe' where judgment_id = (select judgment_id from judgment limit 1)", psycopg.errors.CheckViolation),
    ("duplicate vaquill_chunk_id", "insert into judgment_chunk select judgment_id, language_code, chunk_index + 1000000, vaquill_chunk_id, vaquill_case_id, total_chunks, text, text_original, char_start, char_end, page_start, page_end, section_type, section_priority, box_aware from judgment_chunk limit 1", psycopg.errors.UniqueViolation),
    ("read-only role cannot write", None, psycopg.errors.ReadOnlySqlTransaction),
]
neg = []
for title, sql_, expected in NEG:
    try:
        if sql_ is None:
            with pgconn.connect("readonly", autocommit=True) as ro:
                ro.execute("update judgment set title = title")
        else:
            with pg.transaction():
                pg.execute(sql_)
                raise Rollback()
        res = ("ACCEPTED (bad)", False)
    except Rollback:
        res = ("ACCEPTED (bad)", False)
    except expected as e:
        res = (f"rejected: {type(e).__name__}", True)
    except Exception as e:  # noqa
        res = (f"rejected with a different error: {type(e).__name__}: {str(e).splitlines()[0][:90]}", False)
    neg.append({"test": title, "result": res[0], "ok": res[1]})
out["negative_tests"] = neg
log(f"negative tests: {sum(n['ok'] for n in neg)}/{len(neg)} rejected as expected")

# ------------------------------------------------------------------ 5. logical integrity
LI = [
    ("every judgment has exactly one judgment_source_map row", "select count(*) from judgment j left join judgment_source_map m using (judgment_id) where m.judgment_id is null"),
    ("every judgment has all 12 tracked provenance fields", "select count(*) from (select judgment_id from judgment_field_provenance group by 1 having count(*) <> 12) x union all select count(*) from judgment j where not exists (select 1 from judgment_field_provenance p where p.judgment_id = j.judgment_id)"),
    ("language rows with text_available have a judgment_text row, and vice versa", """select (select count(*) from judgment_language l where text_available and not exists (select 1 from judgment_text t where t.judgment_id = l.judgment_id and t.language_code = l.language_code))
        + (select count(*) from judgment_text t where not exists (select 1 from judgment_language l where l.judgment_id = t.judgment_id and l.language_code = t.language_code and l.text_available))"""),
    ("judgment_language.text_chunks equals the actual chunk rows", """select count(*) from judgment_language l left join (select judgment_id, language_code, count(*) n from judgment_chunk group by 1, 2) c using (judgment_id, language_code) where l.text_chunks <> coalesce(c.n, 0)"""),
    ("judgment_text.chunk_count equals the actual chunk rows; expected_chunks equals total_chunks", """select count(*) from judgment_text t join (select judgment_id, language_code, count(*) n, max(total_chunks) tc from judgment_chunk group by 1, 2) c using (judgment_id, language_code) where t.chunk_count <> c.n or t.expected_chunks <> c.tc"""),
    ("judgment_text.char_length equals length(text)", "select count(*) from judgment_text where char_length <> length(text)"),
    ("chunks_contiguous agrees with the chunk indexes actually stored", """select count(*) from judgment_text t join (select judgment_id, language_code, count(*) n, min(chunk_index) mn, max(chunk_index) mx from judgment_chunk group by 1, 2) c using (judgment_id, language_code)
        where t.chunks_contiguous <> (c.mn = 0 and c.mx + 1 = c.n and c.n = t.expected_chunks)"""),
    ("text_status agrees with judgment_text languages", """select count(*) from judgment j where text_status <> case when exists (select 1 from judgment_text t where t.judgment_id = j.judgment_id and t.language_code = 'en') then 'english'
        when exists (select 1 from judgment_text t where t.judgment_id = j.judgment_id) then 'translation_only' else 'none' end"""),
    ("bench_strength equals the number of judgment_judge rows", "select count(*) from judgment j left join (select judgment_id, count(*) n from judgment_judge group by 1) g using (judgment_id) where coalesce(j.bench_strength, 0) <> coalesce(g.n, 0)"),
    ("quality flag incomplete_english_text matches English completeness", """select count(*) from judgment j left join judgment_text t on t.judgment_id = j.judgment_id and t.language_code = 'en'
        where ('incomplete_english_text' = any(j.quality_flags)) <> (t.judgment_id is not null and not t.is_complete)"""),
    ("match_status agrees with judgment_source_map", "select count(*) from judgment j join judgment_source_map m using (judgment_id) where j.match_status <> m.match_status or (m.vaquill_case_id is not null) <> (j.match_status = 'matched')"),
    ("read-only role can read every table", None),
]
li = []
for title, sql_ in LI:
    if sql_ is None:
        with pgconn.connect("readonly", autocommit=True) as ro:
            bad = 0
            for t in db_tables:
                try:
                    ro.execute(f'select count(*) from "{t}"').fetchone()
                except Exception:
                    bad += 1
    else:
        bad = sum(r[0] for r in pq(sql_))
    li.append({"check": title, "violations": bad, "ok": bad == 0})
out["logical"] = li
log(f"logical integrity: {sum(x['ok'] for x in li)}/{len(li)} clean")

# ------------------------------------------------------------------ 6. language and completeness reconciliation
rec = {}
rec["status"] = pq("select text_status, match_status, count(*) from judgment group by 1, 2 order by 1, 2")
rec["reasons"] = pq("""select incompleteness_reason, count(*) filter(where language_code = 'en'), count(*) filter(where language_code <> 'en'), count(*) from judgment_text group by 1 order by 4 desc""")
tot_inc = pq("select count(*) from judgment_text where not is_complete")[0][0]
gap = pq("select count(*) from judgment_text where large_gap_count > 0")[0][0]
noncontig = pq("select count(*) from judgment_text where not chunks_contiguous")[0][0]
both = pq("select count(*) from judgment_text where large_gap_count > 0 and not chunks_contiguous")[0][0]
rec["incomplete_reconciliation"] = {"incomplete_total": tot_inc, "with_text_gap": gap, "non_contiguous": noncontig, "both": both,
                                    "text_gap_only": gap - both, "missing_chunks_only": noncontig - both,
                                    "check_total_equals_union": tot_inc == (gap + noncontig - both)}
rec["by_language"] = pq("""
select l.language_code, count(*) filter(where l.text_available) as text_sets, count(*) filter(where l.pdf_listed) as pdf_listed,
       count(*) filter(where t.is_complete) as complete, count(*) filter(where t.incompleteness_reason = 'missing_chunks') as missing_chunks,
       count(*) filter(where t.incompleteness_reason = 'text_gap') as text_gap, count(*) filter(where t.incompleteness_reason = 'missing_chunks_and_text_gap') as both_,
       count(*) filter(where t.overlap_mismatches > 0) as overlap_texts, coalesce(sum(t.overlap_mismatches), 0) as overlap_events,
       count(*) filter(where t.offset_drift_chunks > 0) as drift_texts, coalesce(sum(t.offset_drift_chunks), 0) as drift_chunks
from judgment_language l left join judgment_text t using (judgment_id, language_code)
group by 1 order by 2 desc, 1""")
rec["english_quality"] = pq("""
select count(*) as english_texts,
       count(*) filter(where is_complete and overlap_mismatches = 0 and offset_drift_chunks = 0) as clean,
       count(*) filter(where not is_complete) as incomplete,
       count(*) filter(where overlap_mismatches > 0) as with_overlap_disagreement,
       count(*) filter(where offset_drift_chunks > 0) as with_offset_drift,
       count(*) filter(where not is_complete or overlap_mismatches > 0 or offset_drift_chunks > 0) as any_issue
from judgment_text where language_code = 'en'""")[0]
rec["retrieval_view"] = pq("""
select count(*), count(*) filter(where english_text_available), count(*) filter(where english_text_complete),
       count(*) filter(where english_text_available and not english_text_complete),
       count(*) filter(where english_overlap_mismatches > 0), count(*) filter(where english_offset_drift_chunks > 0) from judgment_retrieval_status""")[0]
out["reconciliation"] = rec

# ------------------------------------------------------------------ 7. sizes
out["database_bytes"] = pq("select pg_database_size(current_database())")[0][0]
out["table_sizes"] = pq("""
select c.relname, c.reltuples::bigint, pg_table_size(c.oid) - coalesce(pg_total_relation_size(c.reltoastrelid), 0) as heap,
       coalesce(pg_total_relation_size(c.reltoastrelid), 0) as toast, pg_indexes_size(c.oid) as indexes, pg_total_relation_size(c.oid) as total
from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' order by total desc""")
out["index_sizes"] = pq("""select c.relname as table, i.relname as index, pg_relation_size(i.oid) from pg_index x join pg_class c on c.oid = x.indrelid join pg_class i on i.oid = x.indexrelid
                           where c.relnamespace = 'public'::regnamespace order by 3 desc""")
out["sanitization"] = pq("""select table_name, lang, count(*), sum(nul_count) from (
    select s.table_name, c.language_code as lang, s.nul_count from text_sanitization_log s join judgment_chunk c on s.table_name = 'judgment_chunk' and c.vaquill_chunk_id = s.row_key
    union all select table_name, split_part(row_key, '/', 2), nul_count from text_sanitization_log where table_name = 'judgment_text') x group by 1, 2 order by 1, 2""")
out["verified_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
(B / "verify_report.json").write_text(json.dumps(out, indent=1, default=str))
bad_total = (sum(not c["ok"] for c in counts) + sum(not f["ok"] for f in fps) + sum(o["orphans"] for o in orphans)
             + sum(not n["ok"] for n in neg) + sum(not x["ok"] for x in li) + sum(not c["validated"] for c in out["constraints"]))
log(f"done; problems found: {bad_total}")
sys.exit(1 if bad_total else 0)
