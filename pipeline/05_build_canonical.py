#!/usr/bin/env python3
"""Stage 3: build the canonical tables from the immutable raw files.

Inputs  (read-only): raw/vanga/metadata/{parquet,json}, raw/vaquill/in_supreme-court_judgments.parquet
Outputs: build/*.parquet, one per table in db/migrations (judgment_id etc. as text; cast on load)

Vanga is canonical for judgment records. Vaquill enriches with judges, language-specific chunks and
assembled text. Deterministic: same raw files -> same judgment_ids and same table contents.
Run:  .venv/bin/python -I pipeline/05_build_canonical.py
"""
import datetime as dt
import collections
import hashlib
import json
import pathlib
import re
import shutil
import sys
import time
import uuid

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
BUILD = ROOT / "build"
TMP = ROOT / "build.tmp"
VQ = f"{RAW}/vaquill/in_supreme-court_judgments.parquet"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://eli.local/supreme-court-judgment")
HDR = re.compile(r"Case: [^\n]*\nSection: [^\n]*\n\n")
LANG_FIX = {"eng": "en"}  # Vanga uses ENG; Vaquill uses en. All other codes are the lower-cased Vanga token.

started = dt.datetime.now(dt.timezone.utc)
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)


if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir()
BUILD.mkdir(exist_ok=True)

manifest = (RAW / "MANIFEST.sha256")
BUILD_ID = "b" + hashlib.sha256(manifest.read_bytes()).hexdigest()[:12] if manifest.exists() else "b-nomanifest"

con = duckdb.connect(str(TMP / "work.duckdb"))
con.execute("set threads=4")
con.execute("set memory_limit='9GB'")
con.execute(f"set temp_directory='{TMP}/spill'")
con.execute("set preserve_insertion_order=false")
con.execute(r"create macro norm(x) as lower(trim(regexp_replace(coalesce(cast(x as varchar),''),'\s+',' ','g')))")
con.execute(r"create macro nz(x) as case when trim(coalesce(cast(x as varchar),'')) = '' then null else x end")
con.execute(r"create macro njudge(x) as upper(trim(regexp_replace(x,'\s+',' ','g')))")


def sql(s):
    return con.execute(s.replace("@RAW@", str(RAW)).replace("@BUILD_ID@", BUILD_ID))


def one(s):
    return sql(s).fetchone()


def out(table_sql, name):
    """Write a deterministic parquet file for one table."""
    sql(f"copy ({table_sql}) to '{TMP}/{name}.parquet' (format parquet, compression zstd, row_group_size 100000)")
    n = one(f"select count(*) from read_parquet('{TMP}/{name}.parquet')")[0]
    log(f"wrote {name}: {n:,} rows")
    return n


metrics = []  # (section, metric, dimension, numeric, text)


def metric(section, name, value, dimension=""):
    metrics.append((section, name, dimension, float(value) if isinstance(value, (int, float)) else None,
                    None if isinstance(value, (int, float)) else str(value)))


# ------------------------------------------------------------------ 1. Vanga raw (parquet + json)
log("loading Vanga parquet and json")
sql("""
create table vg_pq as
select title, petitioner, respondent, description, judge, author_judge, citation, case_id, cnr, decision_date,
       disposal_nature, court, available_languages, raw_html, path, nc_display, scraped_at, year as year_field,
       regexp_extract(filename, 'year=(\\d+)', 1)::int as year_folder
from read_parquet('@RAW@/vanga/metadata/parquet/*/*.parquet', hive_partitioning=false, union_by_name=true, filename=true)
""")
sql("""
create table vg_json as
select path, citation_year, nc_display, scraped_at, raw_html, regexp_extract(filename, 'year=(\\d+)', 1)::int as year_folder
from read_json('@RAW@/vanga/metadata/json/*/*.json', format='unstructured',
     columns={raw_html:'VARCHAR', path:'VARCHAR', citation_year:'VARCHAR', nc_display:'VARCHAR', scraped_at:'VARCHAR'}, filename=true)
""")
n_pq, n_js = one("select (select count(*) from vg_pq), (select count(*) from vg_json)")
jj = one("""select count(*), count(*) filter(where j.raw_html = p.raw_html and j.nc_display = p.nc_display and j.scraped_at = p.scraped_at),
            count(*) filter(where j.citation_year = cast(p.year_field as varchar))
            from vg_pq p join vg_json j using (year_folder, path)""")
metric("raw", "vanga_parquet_rows", n_pq)
metric("raw", "vanga_json_rows", n_js)
metric("raw", "vanga_json_parquet_joined", jj[0])
metric("raw", "vanga_json_parquet_identical_fields", jj[1])
metric("raw", "vanga_json_citation_year_equals_year", jj[2])

sql("""
create table vg_all as
select row_number() over (order by year_folder, path) as source_row_id, p.*, j.citation_year,
       try_strptime(decision_date, '%d-%m-%Y')::date as dd,
       replace(case_id, ' ', '_') as nkey,
       count(*) over (partition by path) as n_path
from vg_pq p left join vg_json j using (year_folder, path)
""")
sql("""
alter table vg_all add column dedupe_reason varchar;
update vg_all set dedupe_reason = case
    when n_path = 1 then 'unique_path'
    when extract(year from dd) = year_folder then 'folder_year_matches_decision_year'
    else 'misfiled_copy' end;
""")
sql("create table vg as select * from vg_all where dedupe_reason <> 'misfiled_copy'")
metric("dedupe", "vanga_rows", one("select count(*) from vg_all")[0])
metric("dedupe", "canonical_rows", one("select count(*) from vg")[0])
metric("dedupe", "misfiled_copies_excluded", one("select count(*) from vg_all where dedupe_reason='misfiled_copy'")[0])
metric("dedupe", "paths_with_zero_or_multiple_canonical_copies",
       one("select count(*) from (select path from vg_all group by 1 having count(*) filter(where dedupe_reason <> 'misfiled_copy') <> 1)")[0])

# stable internal ids: uuid5 of the Vanga path
paths = [r[0] for r in sql("select path from vg order by path").fetchall()]
jid = pa.table({"path": paths, "judgment_id": [str(uuid.uuid5(NS, "vanga-path:" + p)) for p in paths]})
con.register("jid_arrow", jid)
sql("create table jid as select * from jid_arrow")
assert one("select count(*), count(distinct judgment_id) from jid")[0] == one("select count(distinct judgment_id) from jid")[0]

VG_COLS = ["title", "petitioner", "respondent", "description", "judge", "author_judge", "citation", "case_id", "cnr",
           "decision_date", "disposal_nature", "court", "available_languages", "raw_html", "path", "nc_display", "scraped_at"]
struct = ", ".join(f"{c} := {c}" for c in VG_COLS) + ", year := year_field, citation_year := citation_year"
out(f"""select source_row_id, year_folder::smallint as year_folder, path, (dedupe_reason <> 'misfiled_copy') as is_canonical_copy,
               dedupe_reason, cast(to_json(struct_pack({struct})) as varchar) as raw
        from vg_all order by source_row_id""", "source_vanga_raw")

# ------------------------------------------------------------------ 2. Vaquill case level
log("reading Vaquill case-level metadata")
sql(f"""
create table vq_meta as
select distinct case_id, title, petitioner, respondent, disposition, case_number, citation, decision_date, date_of_registration,
       year as year_field, court, court_code, court_type, bench, bench_strength, judges, description, source_url
from read_parquet('{VQ}')
""")
sql(f"""
create table vq_chunkinfo as
select case_id, count(*) as chunk_row_count, list_sort(list(distinct language_code)) as languages
from read_parquet('{VQ}') group by case_id
""")
metric("vaquill", "case_ids", one("select count(distinct case_id) from vq_meta")[0])
metric("vaquill", "cases_with_varying_metadata", one("select count(*) from (select case_id from vq_meta group by 1 having count(*) > 1)")[0])
sql("""
create table vq_case as
select m.*, try_cast(m.decision_date as date) as qdd, c.chunk_row_count, c.languages
from vq_meta m join vq_chunkinfo c using (case_id)
qualify row_number() over (partition by m.case_id order by m.title, m.citation, m.decision_date) = 1
""")
vstruct = ", ".join(f"{c} := {c}" for c in ["case_id", "title", "petitioner", "respondent", "disposition", "case_number", "citation",
                                            "decision_date", "date_of_registration", "court", "court_code", "court_type", "bench",
                                            "bench_strength", "judges", "description", "source_url"]) + ", year := year_field"
out(f"""select case_id as vaquill_case_id, cast(to_json(struct_pack({vstruct})) as varchar) as raw,
               chunk_row_count::integer as chunk_row_count, languages
        from vq_case order by case_id""", "source_vaquill_raw")

# ------------------------------------------------------------------ 3. Matching: normalised INSC id + citation
log("matching")
sql("""
create table qm as
select q.case_id, q.qdd, q.citation as qcit,
       coalesce(list(v.path order by v.path) filter (where v.path is not null), []) as cand_paths,
       coalesce(list(v.path order by v.path) filter (where v.path is not null and norm(v.citation) = norm(q.citation)), []) as cit_paths
from vq_case q left join vg v on v.nkey = q.case_id and v.nkey <> ''
group by q.case_id, q.qdd, q.citation
""")
sql("""
create table qdecision as
select qm.*, v.dd as vdd,
  case
    when len(cand_paths) = 0 then 'vaquill_orphan'
    when len(cit_paths) = 1 and v.dd = qm.qdd then 'matched'
    when len(cit_paths) = 1 then 'date_conflict'
    when len(cit_paths) > 1 then 'ambiguous_match'
    else 'citation_conflict' end as outcome
from qm left join vg v on len(qm.cit_paths) = 1 and v.path = qm.cit_paths[1]
""")
for outcome, n in sql("select outcome, count(*) from qdecision group by 1 order by 1").fetchall():
    metric("match", "vaquill_cases", n, outcome)
sql("create table matched as select case_id, cit_paths[1] as path from qdecision where outcome = 'matched'")
sql("""
create table in_review as
select case_id, outcome as kind, cand_paths from qdecision where outcome <> 'matched'
""")
sql("""
create table review_paths as select distinct unnest(cand_paths) as path from in_review
""")
metric("match", "unique_vaquill_case_per_path", one("select count(*) - count(distinct path) from matched")[0])

out("""select row_number() over (order by case_id)::bigint as review_id, kind, case_id as vaquill_case_id, cand_paths as candidate_paths,
              cast(to_json(struct_pack(kind := kind, candidates := cand_paths)) as varchar) as detail, 'open' as status
       from in_review order by case_id""", "match_review_queue")

# ------------------------------------------------------------------ 4. Chunks (language-specific, key = judgment + language + index)
log("building chunk table (large)")
sql(f"""
copy (
  select jid.judgment_id, q.language_code, q.chunk_index::integer as chunk_index, q.chunk_id as vaquill_chunk_id, q.case_id as vaquill_case_id,
         q.total_chunks::integer as total_chunks, q.text, case when q.text_original = q.text then null else q.text_original end as text_original,
         q.char_start::integer as char_start, q.char_end::integer as char_end, q.page_start::integer as page_start,
         q.page_end::integer as page_end, q.section_type, q.section_priority::integer as section_priority, q.box_aware
  from read_parquet('{VQ}') q join matched m on m.case_id = q.case_id join jid on jid.path = m.path
  order by jid.judgment_id, q.language_code, q.chunk_index
) to '{TMP}/judgment_chunk.parquet' (format parquet, compression zstd, row_group_size 50000)
""")
log("judgment_chunk written")
sql(f"""
create table chunk_stats as
select jid.judgment_id, q.language_code, count(*)::integer as text_chunks, max(q.total_chunks)::integer as expected_chunks
from read_parquet('{VQ}') q join matched m on m.case_id = q.case_id join jid on jid.path = m.path
group by 1, 2
""")
metric("chunks", "vaquill_chunk_rows", one(f"select count(*) from read_parquet('{VQ}')")[0])
metric("chunks", "chunks_attached", one("select sum(text_chunks) from chunk_stats")[0])
metric("chunks", "text_original_differs_from_text", one(f"select count(*) from read_parquet('{VQ}') where text_original <> text")[0])

# ------------------------------------------------------------------ 5. Text assembly (offset-aware)
log("assembling text")


def assemble(chunks):
    """chunks: list of (idx, start, end, raw_text, total) sorted by idx. Returns (text, stats).

    Each chunk body (header stripped) is the slice text[start:end] of the full text. Neighbouring windows
    overlap (tens of characters) or leave a 1-2 character gap (whitespace trimmed at chunk ends), so chunks
    are placed by offset instead of concatenated. `cur` is the offset just past the text assembled so far.
    """
    pieces, tail = [], ""
    cur = 0
    st = dict(small=0, large=0, mismatch=0, mismatch_ws=0, drift=0, nohdr=0, gap_sizes=[], drift_abs=[], overlap_sizes=[])
    for _, s, e, raw, _tot in chunks:
        m = HDR.match(raw)
        body = raw[m.end():] if m else raw
        if not m:
            st["nohdr"] += 1
        if len(body) != e - s:
            st["drift"] += 1
            st["drift_abs"].append(abs(len(body) - (e - s)))
        if s > cur:  # gap before this chunk
            gap = s - cur
            st["gap_sizes"].append(gap)
            st["small" if gap <= 2 else "large"] += 1
            fill = "\n" * min(gap, 2)
            pieces.append(fill)
            tail = (tail + fill)[-4000:]
            cur = s
        ov = cur - s  # characters this chunk shares with the text already assembled
        if ov > 0:
            k = min(ov, len(body))
            if k <= len(tail) and body[:k] != tail[-k:]:
                st["mismatch"] += 1
                st["overlap_sizes"].append(k)
                if "".join(body[:k].split()) == "".join(tail[-k:].split()):
                    st["mismatch_ws"] += 1  # differs only in whitespace
            body = body[ov:]
        if body:
            pieces.append(body)
            tail = (tail + body)[-4000:]
            cur += len(body)
    return "".join(pieces), st


schema = pa.schema([
    ("judgment_id", pa.string()), ("language_code", pa.string()), ("text", pa.string()), ("text_source", pa.string()),
    ("chunk_count", pa.int32()), ("expected_chunks", pa.int32()), ("char_length", pa.int32()), ("is_complete", pa.bool_()),
    ("small_gap_count", pa.int32()), ("large_gap_count", pa.int32()), ("overlap_mismatches", pa.int32()),
])
writer = pq.ParquetWriter(str(TMP / "judgment_text.parquet"), schema, compression="zstd")
pf = pq.ParquetFile(str(TMP / "judgment_chunk.parquet"))
buf, cur_key, cur_chunks = [], None, []
totals = dict(sets=0, small=0, large=0, mismatch=0, mismatch_ws=0, drift=0, nohdr=0, incomplete=0)
by_lang = collections.defaultdict(lambda: collections.Counter())
drift_all, gap_big = [], []


def flush_group():
    global cur_key, cur_chunks
    if cur_key is None:
        return
    chunks = sorted(cur_chunks, key=lambda c: c[0])
    text, st = assemble(chunks)
    expected = max(c[4] for c in chunks)
    idxs = [c[0] for c in chunks]
    contiguous = idxs == list(range(len(idxs))) and len(idxs) == expected
    complete = contiguous and st["large"] == 0
    lang = cur_key[1]
    buf.append((cur_key[0], lang, text, "vaquill", len(chunks), expected, len(text), complete, st["small"], st["large"], st["mismatch"]))
    totals["sets"] += 1
    for k in ("small", "large", "mismatch", "mismatch_ws", "drift", "nohdr"):
        totals[k] += st[k]
    totals["incomplete"] += 0 if complete else 1
    for g in st["gap_sizes"]:
        by_lang[lang]["gap_1" if g == 1 else "gap_2" if g == 2 else "gap_3_to_24" if g <= 24 else "gap_over_24"] += 1
    by_lang[lang]["mismatch_events"] += st["mismatch"]
    by_lang[lang]["texts_with_mismatch"] += 1 if st["mismatch"] else 0
    by_lang[lang]["drift_chunks"] += st["drift"]
    by_lang[lang]["sets"] += 1
    by_lang[lang]["incomplete_sets"] += 0 if complete else 1
    by_lang[lang]["non_contiguous_sets"] += 0 if contiguous else 1
    drift_all.extend(st["drift_abs"])
    cur_key, cur_chunks = None, []


def write_buf():
    global buf
    if buf:
        cols = list(zip(*buf))
        writer.write_table(pa.table({f.name: pa.array(cols[i], type=f.type) for i, f in enumerate(schema)}, schema=schema))
        buf = []


for batch in pf.iter_batches(batch_size=40000, columns=["judgment_id", "language_code", "chunk_index", "char_start", "char_end", "total_chunks", "text"]):
    d = batch.to_pydict()
    for jid_, lang, idx, s, e, tot, txt in zip(d["judgment_id"], d["language_code"], d["chunk_index"], d["char_start"], d["char_end"], d["total_chunks"], d["text"]):
        key = (jid_, lang)
        if key != cur_key:
            flush_group()
            cur_key = key
        cur_chunks.append((idx, s, e, txt, tot))
    if len(buf) > 3000:
        write_buf()
flush_group()
write_buf()
writer.close()
for k, v in totals.items():
    metric("text", k, v)
for lang, cnt in sorted(by_lang.items()):
    for k, v in sorted(cnt.items()):
        metric("text_by_language", k, v, lang)
if drift_all:
    drift_all.sort()
    metric("text", "drift_abs_median", drift_all[len(drift_all) // 2])
    metric("text", "drift_abs_p95", drift_all[int(len(drift_all) * 0.95)])
    metric("text", "drift_abs_max", drift_all[-1])
log(f"assembled {totals['sets']:,} text sets; {totals}")

# ------------------------------------------------------------------ 6. Fields, provenance, conflicts
log("canonical fields")

sql("""
create table fv as
select jid.judgment_id, v.path, v.nkey, v.case_id as vcase_id, v.dd, v.year_folder, v.cnr, v.nc_display, v.scraped_at, v.judge, v.available_languages,
       v.year_field as v_year, v.title as v_title, v.petitioner as v_petitioner, v.respondent as v_respondent,
       v.citation as v_citation, v.disposal_nature as v_disposal, v.court as v_court,
       (mt.case_id is not null) as is_matched, mt.case_id as q_case_id,
       q.title as q_title, q.petitioner as q_petitioner, q.respondent as q_respondent, q.citation as q_citation,
       q.disposition as q_disposal, q.court as q_court, q.qdd, q.year_field as q_year, q.judges as q_judges, q.bench_strength as q_bench
from vg v
join jid on jid.path = v.path
left join matched mt on mt.path = v.path
left join vq_case q on q.case_id = mt.case_id
""")
FIELDS = [  # (canonical field, vanga expr, vaquill expr)
    ("title", "nz(v_title)", "nz(q_title)"),
    ("petitioner", "nz(v_petitioner)", "nz(q_petitioner)"),
    ("respondent", "nz(v_respondent)", "nz(q_respondent)"),
    ("citation", "nz(v_citation)", "nz(q_citation)"),
    ("disposal", "nz(v_disposal)", "nz(q_disposal)"),
    ("court", "nz(v_court)", "nz(q_court)"),
    ("decision_date", "cast(dd as varchar)", "cast(qdd as varchar)"),
]
prov_parts, conf_parts = [], []
for f, a, b in FIELDS:
    prov_parts.append(f"""
    select judgment_id, '{f}' as field_name,
      case when {a} is not null then 'vanga' when {b} is not null then 'vaquill' else 'none' end as chosen_source,
      coalesce(cast({a} as varchar), cast({b} as varchar)) as chosen_value,
      case when {a} is not null and {b} is not null and norm({a}) <> norm({b}) then cast({b} as varchar) end as alt_value,
      case when {a} is not null and {b} is not null and norm({a}) <> norm({b}) then 'conflict: vanga value kept, vaquill value preserved'
           when {a} is not null then 'vanga canonical value'
           when {b} is not null then 'vanga empty: filled from vaquill'
           else 'no value in either source' end as reason
    from fv""")
    conf_parts.append(f"""
    select judgment_id, '{f}' as field_name, cast({a} as varchar) as vanga_value, cast({b} as varchar) as vaquill_value,
           'vanga value kept in judgment; vaquill value preserved in field_provenance.alt_value and source_vaquill_raw' as resolution
    from fv where {a} is not null and {b} is not null and norm({a}) <> norm({b})""")

# judges: Vaquill structured list preferred when matched and non-empty, else Vanga comma list
sql("""
create table judges as
select judgment_id, is_matched,
  list_filter(list_transform(string_split(coalesce(judge, ''), ','), x -> trim(x)), x -> x <> '') as vlist,
  list_filter(list_transform(coalesce(q_judges, []), x -> trim(x)), x -> x <> '') as qlist
from fv
""")
sql("""
create table judges_chosen as
select judgment_id, is_matched, vlist, qlist,
  case when len(qlist) > 0 then qlist else vlist end as chosen,
  case when len(qlist) > 0 then 'vaquill' when len(vlist) > 0 then 'vanga' else 'none' end as chosen_source
from judges
""")
prov_parts.append("""
    select judgment_id, 'judges' as field_name, chosen_source,
      case when len(chosen) > 0 then array_to_string(chosen, ' | ') end as chosen_value,
      case when len(qlist) > 0 and len(vlist) > 0 and list_sort(list_distinct(list_transform(qlist, x -> njudge(x)))) <> list_sort(list_distinct(list_transform(vlist, x -> njudge(x))))
           then array_to_string(vlist, ' | ') end as alt_value,
      case when len(qlist) > 0 and len(vlist) > 0 and list_sort(list_distinct(list_transform(qlist, x -> njudge(x)))) <> list_sort(list_distinct(list_transform(vlist, x -> njudge(x))))
           then 'conflict: vaquill structured list used, vanga list preserved'
           when len(qlist) > 0 then 'vaquill structured judges list'
           when len(vlist) > 0 then 'vanga comma-separated judge string'
           else 'no value in either source' end as reason
    from judges_chosen""")
conf_parts.append("""
    select judgment_id, 'judges' as field_name, array_to_string(vlist, ' | ') as vanga_value, array_to_string(qlist, ' | ') as vaquill_value,
           'vaquill structured list used in judgment_judge; vanga list preserved in field_provenance.alt_value' as resolution
    from judges_chosen
    where len(qlist) > 0 and len(vlist) > 0 and list_sort(list_distinct(list_transform(qlist, x -> njudge(x)))) <> list_sort(list_distinct(list_transform(vlist, x -> njudge(x))))""")
# bench strength: derived from the chosen judges list
conf_parts.append("""
    select j.judgment_id, 'bench_strength' as field_name, cast(len(j.chosen) as varchar) as vanga_value, cast(f.q_bench as varchar) as vaquill_value,
           'derived count from judges list kept; vaquill bench_strength preserved in source_vaquill_raw' as resolution
    from judges_chosen j join fv f using (judgment_id)
    where f.is_matched and f.q_bench is not null and f.q_bench <> len(j.chosen)""")
# source year fields: both kept verbatim; canonical decision_year derives from decision_date
conf_parts.append("""
    select judgment_id, 'source_year' as field_name, cast(v_year as varchar) as vanga_value, cast(q_year as varchar) as vaquill_value,
           'rule: decision_year derived from decision_date; both source year fields kept as delivered (vanga_year_field, vaquill_year_field)' as resolution
    from fv where is_matched and try_cast(v_year as integer) is not null and q_year is not null and try_cast(v_year as integer) <> q_year""")
prov_parts.append("""
    select judgment_id, 'cnr' as field_name, case when nz(cnr) is not null then 'vanga' else 'none' end,
           nz(cnr), null, case when nz(cnr) is not null then 'vanga only field' else 'no value in either source' end from fv""")
prov_parts.append("""
    select judgment_id, 'available_languages' as field_name, case when nz(available_languages) is not null then 'vanga' else 'none' end,
           nz(available_languages), null, case when nz(available_languages) is not null then 'vanga only field' else 'vanga list empty' end from fv""")
prov_parts.append("""
    select f.judgment_id, 'decision_year', case when coalesce(f.dd, f.qdd) is not null then 'derived' else 'none' end,
           cast(extract(year from coalesce(f.dd, f.qdd)) as varchar), null,
           case when coalesce(f.dd, f.qdd) is not null then 'year(decision_date)' else 'no decision date' end from fv f""")
prov_parts.append("""
    select judgment_id, 'bench_strength', case when len(chosen) > 0 then 'derived' else 'none' end,
           case when len(chosen) > 0 then cast(len(chosen) as varchar) end, null,
           case when len(chosen) > 0 then 'count of judges on the chosen list' else 'no judges in either source' end from judges_chosen""")

out("select * from (" + " union all ".join(prov_parts) + ") order by judgment_id, field_name", "judgment_field_provenance")
out("select row_number() over (order by judgment_id, field_name)::bigint as conflict_id, *, 'auto_resolved' as status from ("
    + " union all ".join(conf_parts) + ") order by judgment_id, field_name", "field_conflicts")
for f, n in sql(f"select field_name, count(*) from read_parquet('{TMP}/field_conflicts.parquet') group by 1 order by 1").fetchall():
    metric("conflicts", "field_conflicts", n, f)

out("""select judgment_id, (pos)::smallint as position, nm as judge_name_raw, njudge(nm) as judge_name_norm, chosen_source as source
       from (select judgment_id, chosen_source, unnest(range(1, len(chosen) + 1)) as pos, unnest(chosen) as nm from judges_chosen)
       order by judgment_id, pos""", "judgment_judge")

# ------------------------------------------------------------------ 7. Languages
sql("""
create table lang_pdf as
select judgment_id, lower(trim(tok)) as tok
from (select judgment_id, unnest(string_split(coalesce(available_languages, ''), ',')) as tok from fv)
where trim(tok) <> ''
""")
sql("""
create table lang_pdf2 as
select distinct judgment_id, case when tok = 'eng' then 'en' else tok end as language_code from lang_pdf
""")
out("""
select coalesce(p.judgment_id, s.judgment_id) as judgment_id, coalesce(p.language_code, s.language_code) as language_code,
       (p.judgment_id is not null) as pdf_listed, (s.judgment_id is not null) as text_available,
       coalesce(s.text_chunks, 0)::integer as text_chunks, s.expected_chunks
from lang_pdf2 p full outer join chunk_stats s on s.judgment_id = p.judgment_id and s.language_code = p.language_code
order by 1, 2""", "judgment_language")

# ------------------------------------------------------------------ 8. Canonical judgment
log("judgment")
sql(f"""
create table text_flags as
select judgment_id,
  max(case when language_code = 'en' then 1 else 0 end) as has_en,
  count(*) as n_sets,
  max(case when language_code = 'en' and not is_complete then 1 else 0 end) as en_incomplete
from read_parquet('{TMP}/judgment_text.parquet') group by 1
""")
sql("""
create table judgment_final as
select f.judgment_id, f.path as vanga_path,
  nz(f.vcase_id) as insc_id,
  coalesce(nz(f.v_title), nz(f.q_title)) as title,
  coalesce(nz(f.v_petitioner), nz(f.q_petitioner)) as petitioner,
  coalesce(nz(f.v_respondent), nz(f.q_respondent)) as respondent,
  coalesce(f.dd, f.qdd) as decision_date,
  extract(year from coalesce(f.dd, f.qdd))::smallint as decision_year,
  coalesce(nz(f.v_citation), nz(f.q_citation)) as citation,
  nz(f.cnr) as cnr,
  coalesce(nz(f.v_disposal), nz(f.q_disposal)) as disposal,
  coalesce(nz(f.v_court), nz(f.q_court)) as court,
  case when len(j.chosen) > 0 then len(j.chosen)::smallint end as bench_strength,
  cast(null as varchar) as case_number, cast(null as varchar) as diary_number, cast(null as varchar) as pdf_url,
  try_cast(f.v_year as smallint) as vanga_year_field, f.q_year::smallint as vaquill_year_field, f.year_folder::smallint as vanga_year_folder,
  case when len(la.langs) > 0 then la.langs end as available_languages,
  case when coalesce(t.has_en, 0) = 1 then 'english' when coalesce(t.n_sets, 0) > 0 then 'translation_only' else 'none' end as text_status,
  case when f.is_matched then 'matched' when rp.path is not null then 'in_review' else 'vanga_only' end as match_status,
  list_filter([
    case when nz(f.vcase_id) is null then 'empty_insc_id' end,
    case when nz(f.vcase_id) is not null and sh.n > 1 then 'insc_id_shared' end,
    case when try_cast(substr(f.vcase_id, 1, 4) as integer) <> extract(year from coalesce(f.dd, f.qdd)) then 'insc_year_differs_from_decision_year' end,
    case when try_cast(f.v_year as integer) <> extract(year from coalesce(f.dd, f.qdd)) then 'report_year_differs_from_decision_year' end,
    case when not f.is_matched then 'not_in_vaquill' end,
    case when coalesce(t.has_en, 0) = 0 and coalesce(t.n_sets, 0) > 0 then 'no_english_text' end,
    case when coalesce(t.n_sets, 0) = 0 then 'no_text' end,
    case when coalesce(t.en_incomplete, 0) = 1 then 'incomplete_english_text' end
  ], x -> x is not null) as quality_flags,
  try_cast(f.scraped_at as timestamp) as vanga_scraped_at,
  '@BUILD_ID@' as build_id
from fv f
join judges_chosen j using (judgment_id)
left join (select judgment_id, list(language_code order by language_code) as langs from lang_pdf2 group by 1) la using (judgment_id)
left join text_flags t using (judgment_id)
left join review_paths rp on rp.path = f.path
left join (select nkey, count(*) as n from vg where nkey <> '' group by 1) sh on sh.nkey = f.nkey
""")
out("select * from judgment_final order by judgment_id", "judgment")

out("""
select jf.judgment_id, jf.vanga_path, f.q_case_id as vaquill_case_id,
  case when f.is_matched then 'insc_id+citation'
       when rp.path is not null then 'review'
       when nz(f.vcase_id) is null then 'none:empty_insc_id'
       when exists (select 1 from vq_case q where q.case_id = f.nkey) then 'none:shared_insc_id_citation_differs'
       else 'none:no_vaquill_candidate' end as match_method,
  case when f.is_matched then 1.00 else 0.00 end::decimal(3,2) as match_confidence,
  jf.match_status
from judgment_final jf join fv f using (judgment_id) left join review_paths rp on rp.path = f.path
order by jf.judgment_id""", "judgment_source_map")

# ------------------------------------------------------------------ 9. Identifiers
out("""
select judgment_id, identifier_type, value, source from (
  select f.judgment_id, 'INSC' as identifier_type, f.vcase_id as value, case when f.is_matched then 'both' else 'vanga' end as source from fv f where nz(f.vcase_id) is not null
  union all
  select f.judgment_id, case when f.v_citation like '%S.C.R.%' then 'SCR' else 'CITATION' end, f.v_citation, case when f.is_matched then 'both' else 'vanga' end from fv f where nz(f.v_citation) is not null
  union all
  select f.judgment_id, 'CNR', f.cnr, 'vanga' from fv f where nz(f.cnr) is not null
  union all
  select f.judgment_id, 'VANGA_PATH', f.path, 'vanga' from fv f
  union all
  select f.judgment_id, 'NC_DISPLAY', f.nc_display, 'vanga' from fv f where nz(f.nc_display) is not null
) order by judgment_id, identifier_type, value""", "judgment_identifier")

# ------------------------------------------------------------------ 10. Merge report: null rates before/after, counts
for name, vexpr, after in [
    ("title", "nz(title)", "title"), ("petitioner", "nz(petitioner)", "petitioner"), ("respondent", "nz(respondent)", "respondent"),
    ("citation", "nz(citation)", "citation"), ("disposal", "nz(disposal_nature)", "disposal"), ("court", "nz(court)", "court"),
    ("decision_date", "dd", "decision_date"), ("cnr", "nz(cnr)", "cnr"), ("judges", "nz(judge)", None),
    ("available_languages", "nz(available_languages)", "available_languages"),
]:
    before = one(f"select 100.0 * count(*) filter(where {vexpr} is null) / count(*) from vg")[0]
    if after is None:
        after_v = one("select 100.0 * count(*) filter(where len(chosen) = 0) / count(*) from judges_chosen")[0]
    else:
        after_v = one(f"select 100.0 * count(*) filter(where {after} is null) / count(*) from judgment_final")[0]
    metric("null_rate_before_pct", name, before)
    metric("null_rate_after_pct", name, after_v)
for status, n in sql("select match_status, count(*) from judgment_final group by 1 order by 1").fetchall():
    metric("judgments", "by_match_status", n, status)
for status, n in sql("select text_status, count(*) from judgment_final group by 1 order by 1").fetchall():
    metric("judgments", "by_text_status", n, status)
metric("judgments", "canonical_judgments", one("select count(*) from judgment_final")[0])

mrows = [(BUILD_ID, s, m, d, n, t) for s, m, d, n, t in metrics]
con.execute("create table merge_report (build_id varchar, section varchar, metric varchar, dimension varchar, value_numeric double, value_text varchar)")
con.executemany("insert into merge_report values (?,?,?,?,?,?)", mrows)
out("select * from merge_report order by section, metric, dimension", "merge_report")

# ------------------------------------------------------------------ 11. Content digests (reproducibility) and publish
log("digests")
digests = {}
for p in sorted(TMP.glob("*.parquet")):
    d = con.execute(f"select sum(hash(t)::hugeint)::varchar from read_parquet('{p}') t").fetchone()[0]
    digests[p.stem] = d
con.close()
previous = None
if (BUILD / "digests.json").exists():
    previous = json.loads((BUILD / "digests.json").read_text())
(TMP / "digests.json").write_text(json.dumps(digests, indent=1, sort_keys=True))
if previous is not None:
    same = {k: previous.get(k) == v for k, v in digests.items() if k != "merge_report"}
    log("reproducibility vs previous build: " + ("IDENTICAL" if all(same.values()) else "DIFFERS: " + ", ".join(k for k, v in same.items() if not v)))
    (TMP / "reproducibility.json").write_text(json.dumps({"identical": all(same.values()), "tables": same}, indent=1))

shutil.rmtree(TMP / "spill", ignore_errors=True)
(TMP / "work.duckdb").unlink(missing_ok=True)
for p in sorted(TMP.iterdir()):
    dest = BUILD / p.name
    if dest.exists():
        dest.unlink()
    shutil.move(str(p), str(dest))
shutil.rmtree(TMP, ignore_errors=True)

finished = dt.datetime.now(dt.timezone.utc)
n_judg = next(m[3] for m in metrics if m[1] == "canonical_judgments")
with open(BUILD / "pipeline_runs.jsonl", "a") as f:
    f.write(json.dumps({"stage": "05_build_canonical", "build_id": BUILD_ID, "started_at": started.isoformat(),
                        "finished_at": finished.isoformat(), "status": "succeeded", "row_counts": {"judgment": n_judg}}) + "\n")
log(f"done, build_id={BUILD_ID}")
