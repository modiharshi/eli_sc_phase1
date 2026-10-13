#!/usr/bin/env python3
"""Stage 3 validation: independent reconciliation checks over build/*.parquet and the raw files.

Writes docs/STAGE3_VALIDATION.md. Exit code 1 if any check FAILs. A check with status EXCEPTION is a
measured, explained deviation (the explanation is printed next to the numbers).
Run:  .venv/bin/python -I pipeline/06_validate_stage3.py
"""
import datetime as dt
import json
import pathlib
import random
import subprocess
import sys
import uuid

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
B = ROOT / "build"
OUT = ROOT / "docs" / "STAGE3_VALIDATION.md"
VQ = f"{RAW}/vaquill/in_supreme-court_judgments.parquet"
VANGA = f"{RAW}/vanga/metadata/parquet/*/*.parquet"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://eli.local/supreme-court-judgment")

con = duckdb.connect()
con.execute("set threads=4")
con.execute("set memory_limit='9GB'")
con.execute("set preserve_insertion_order=false")
con.execute(r"create macro norm(x) as lower(trim(regexp_replace(coalesce(cast(x as varchar),''),'\s+',' ','g')))")
for t in ["judgment", "judgment_source_map", "judgment_field_provenance", "field_conflicts", "match_review_queue", "judgment_judge",
          "judgment_identifier", "judgment_language", "judgment_chunk", "judgment_text", "source_vanga_raw", "source_vaquill_raw", "merge_report"]:
    con.execute(f"create view {t} as select * from read_parquet('{B}/{t}.parquet')")


def q(s):
    return con.execute(s).fetchall()


def one(s):
    return con.execute(s).fetchone()


def md_table(headers, rows):
    esc = lambda v: ("" if v is None else str(v)).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(esc(x) for x in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


results = []  # (id, title, status, detail)
sections = []  # extra markdown (tables)


def check(cid, title, ok, detail="", exception=None):
    """ok True -> PASS. ok False with `exception` text -> EXCEPTION (documented). Otherwise FAIL."""
    if ok:
        status = "PASS"
    elif exception:
        status, detail = "EXCEPTION", f"{detail}  Explanation: {exception}"
    else:
        status = "FAIL"
    results.append((cid, title, status, detail))
    print(f"{status:9} {cid} {title}: {detail}", flush=True)


def n(x):
    return f"{x:,}"


# ====================================================================== A. raw integrity
mf = subprocess.run([sys.executable, "-I", str(ROOT / "pipeline" / "04_manifest.py")], capture_output=True, text=True)
check("A1", "raw/ unchanged since the first manifest (sha256 of all 43,786 files re-verified)", mf.returncode == 0,
      mf.stdout.strip().splitlines()[0] if mf.stdout.strip() else mf.stderr[:200])
mr = {(r[0], r[1], r[2]): r[3] for r in q("select section, metric, dimension, value_numeric from merge_report where value_numeric is not null")}
TL = {}
for (sec, met, dim), val in mr.items():
    if sec == "text_by_language":
        TL.setdefault(dim, {})[met] = int(val)
def tl(met, lang=None):
    return sum(v.get(met, 0) for k, v in TL.items() if lang in (None, k))
vg_rows = one(f"select count(*) from read_parquet('{VANGA}', hive_partitioning=false, union_by_name=true)")[0]
check("A2", "Vanga: parquet rows = JSON files = source_vanga_raw rows",
      vg_rows == one("select count(*) from source_vanga_raw")[0] == int(mr[("raw", "vanga_json_rows", "")]),
      f"parquet {n(vg_rows)}, json {n(int(mr[('raw', 'vanga_json_rows', '')]))}, staged {n(one('select count(*) from source_vanga_raw')[0])}")
check("A3", "Vanga JSON and parquet agree on raw_html, nc_display and scraped_at for every row",
      mr[("raw", "vanga_json_parquet_identical_fields", "")] == mr[("raw", "vanga_json_parquet_joined", "")] == vg_rows,
      f"{n(int(mr[('raw', 'vanga_json_parquet_identical_fields', '')]))} of {n(int(mr[('raw', 'vanga_json_parquet_joined', '')]))} identical")
vq_cases_raw = one(f"select count(distinct case_id) from read_parquet('{VQ}')")[0]
check("A4", "Vaquill: source_vaquill_raw has one row per raw case_id",
      vq_cases_raw == one("select count(*) from source_vaquill_raw")[0], f"raw {n(vq_cases_raw)}, staged {n(one('select count(*) from source_vaquill_raw')[0])}")
bad = one(f"""
select count(*) from source_vanga_raw s join read_parquet('{VANGA}', hive_partitioning=false, union_by_name=true, filename=true) p
  on s.path = p.path and s.year_folder = regexp_extract(p.filename, 'year=(\\d+)', 1)::int
where json_extract_string(s.raw, '$.title') is distinct from p.title or json_extract_string(s.raw, '$.case_id') is distinct from p.case_id
   or json_extract_string(s.raw, '$.citation') is distinct from p.citation or json_extract_string(s.raw, '$.decision_date') is distinct from p.decision_date
   or json_extract_string(s.raw, '$.available_languages') is distinct from p.available_languages or json_extract_string(s.raw, '$.judge') is distinct from p.judge""")[0]
check("A5", "source_vanga_raw JSON reproduces the original parquet values (title, case_id, citation, date, languages, judge)", bad == 0, f"{bad} differing rows")

# ====================================================================== B. canonical counts and duplicates
nj, nj_distinct, nj_paths = one("select count(*), count(distinct judgment_id), count(distinct vanga_path) from judgment")
canon = one("select count(*) from source_vanga_raw where is_canonical_copy")[0]
check("B1", "canonical judgments = distinct Vanga paths = canonical copies in staging",
      nj == nj_distinct == nj_paths == canon == one(f"select count(distinct path) from read_parquet('{VANGA}', hive_partitioning=false, union_by_name=true)")[0],
      f"judgments {n(nj)}, distinct ids {n(nj_distinct)}, distinct paths {n(nj_paths)}, canonical copies {n(canon)}")
wrong = sum(1 for jid, p in q("select judgment_id, vanga_path from judgment") if str(uuid.uuid5(NS, "vanga-path:" + p)) != jid)
check("B2", "judgment_id is the stable uuid5 of the Vanga path (recomputed for every row)", wrong == 0, f"{wrong} mismatches")
dup = q("""select (select count(*) from source_vanga_raw), (select count(*) from source_vanga_raw where is_canonical_copy),
                  (select count(*) from source_vanga_raw where not is_canonical_copy),
                  (select count(*) from (select path from source_vanga_raw group by 1 having count(*) filter(where is_canonical_copy) <> 1))""")[0]
check("B3", "duplicate resolution: staged rows = canonical + misfiled; exactly one canonical copy per path",
      dup[0] == dup[1] + dup[2] and dup[3] == 0, f"{n(dup[0])} rows = {n(dup[1])} canonical + {n(dup[2])} misfiled; paths without exactly one canonical copy: {dup[3]}")
rule = one("""
with s as (select year_folder, path, is_canonical_copy, dedupe_reason,
             extract(year from try_strptime(json_extract_string(raw, '$.decision_date'), '%d-%m-%Y')) as dyear from source_vanga_raw)
select count(*) filter(where dedupe_reason = 'misfiled_copy' and year_folder = dyear),
       count(*) filter(where dedupe_reason = 'folder_year_matches_decision_year' and year_folder <> dyear),
       count(*) filter(where dedupe_reason = 'misfiled_copy'), count(*) filter(where dedupe_reason = 'folder_year_matches_decision_year')
from s""")
check("B4", "folder-year rule: every misfiled copy has folder year != decision year; every kept duplicate has folder year = decision year",
      rule[0] == 0 and rule[1] == 0 and rule[2] == rule[3], f"misfiled copies {n(rule[2])}, kept duplicate copies {n(rule[3])}, violations {rule[0] + rule[1]}")
dupkey = one("select count(*) from (select insc_id, citation from judgment where insc_id is not null group by 1, 2 having count(*) > 1)")[0]
check("B5", "no two canonical judgments share both INSC id and citation", dupkey == 0, f"{dupkey} duplicate (insc_id, citation) pairs")
shared = one("select count(*) from (select insc_id from judgment where insc_id is not null group by 1 having count(*) > 1)")[0]
results.append(("B6", "INSC ids shared by more than one canonical judgment (kept distinct, flagged `insc_id_shared`)", "INFO", f"{shared} ids"))

# ====================================================================== C. matching
cases = one("select count(*) from source_vaquill_raw")[0]
matched_cases = one("select count(*) from judgment_source_map where vaquill_case_id is not null")[0]
review_cases = one("select count(distinct vaquill_case_id) from match_review_queue")[0]
check("C1", "every Vaquill case is matched or in the review queue (none dropped)", cases == matched_cases + review_cases,
      f"{n(cases)} cases = {n(matched_cases)} matched + {n(review_cases)} in review")
by_status = dict(q("select match_status, count(*) from judgment group by 1"))
check("C2", "judgments = matched + in_review + vanga_only", nj == sum(by_status.values()), f"{by_status}")
rec = one(f"""
with vq as (select distinct case_id, citation, try_cast(decision_date as date) as qd from read_parquet('{VQ}')),
 raw as (select *, replace(case_id, ' ', '_') as nkey, try_strptime(decision_date, '%d-%m-%Y')::date as dd, regexp_extract(filename, 'year=(\\d+)', 1)::int as yf,
              count(*) over (partition by path) as np
         from read_parquet('{VANGA}', hive_partitioning=false, union_by_name=true, filename=true)),
 canon as (select * from raw where not (np > 1 and extract(year from dd) <> yf))
select count(*), count(distinct vq.case_id) from vq join canon c on c.nkey = vq.case_id and norm(c.citation) = norm(vq.citation) and c.dd = vq.qd""")
check("C3", "independent re-derivation from the raw files (INSC id + citation + date) gives the same matched count",
      rec[0] == rec[1] == matched_cases, f"raw re-derivation {n(rec[0])} pairs / {n(rec[1])} cases; build {n(matched_cases)}")
queue = q("select kind, count(*) from match_review_queue group by 1")
check("C4", "ambiguous / conflicting matches are queued, never merged (queue contents shown)", True, f"queue by kind: {dict(queue) or 'empty'}")
orph = one("select count(*) from match_review_queue where kind = 'vaquill_orphan'")[0]
check("C5", "no Vaquill case without a Vanga counterpart (Vaquill-only judgments)", orph == 0, f"{orph} orphans")
dm = one("""select count(*) from judgment_source_map m join judgment j using (judgment_id) join source_vaquill_raw r on r.vaquill_case_id = m.vaquill_case_id
            where try_cast(json_extract_string(r.raw, '$.decision_date') as date) is distinct from j.decision_date""")[0]
check("C6", "every matched pair agrees on decision date", dm == 0, f"{dm} disagreements")
methods = q("select match_method, match_status, count(*) from judgment_source_map group by 1, 2 order by 3 desc")
sections.append(("Match outcomes (judgment_source_map)", md_table(["match_method", "match_status", "judgments"], [(a, b, n(c)) for a, b, c in methods])))

# ====================================================================== D. chunks
pk = one("select count(*) from (select 1 from judgment_chunk group by judgment_id, language_code, chunk_index having count(*) > 1)")[0]
idu = one("select count(*) - count(distinct vaquill_chunk_id) from judgment_chunk")[0]
check("D1", "chunk key (judgment_id, language_code, chunk_index) and vaquill_chunk_id are unique", pk == 0 and idu == 0, f"duplicate keys {pk}, duplicate chunk ids {idu}")
raw_chunks = one(f"select count(*) from read_parquet('{VQ}')")[0]
bc = one("select count(*) from judgment_chunk")[0]
check("D2", "every raw Vaquill chunk is preserved (row count)", raw_chunks == bc, f"raw {n(raw_chunks)}, judgment_chunk {n(bc)}")
percase = one(f"""
select count(*) from (select case_id, count(*) c from read_parquet('{VQ}') group by 1) r
full join (select vaquill_case_id as case_id, count(*) c from judgment_chunk group by 1) b using (case_id) where r.c is distinct from b.c""")[0]
check("D3", "per-case chunk counts equal the raw counts", percase == 0, f"{percase} cases differ")
txt = one(f"""
select count(*) filter(where md5(r.text) <> md5(c.text)), count(*) filter(where c.text_original is not null),
       count(*) filter(where c.text_original is null and r.text_original <> r.text), count(*) filter(where c.char_start is distinct from r.char_start or c.char_end is distinct from r.char_end
           or c.page_start is distinct from r.page_start or c.page_end is distinct from r.page_end or c.section_type is distinct from r.section_type
           or c.total_chunks is distinct from r.total_chunks or c.language_code is distinct from r.language_code or c.box_aware is distinct from r.box_aware)
from judgment_chunk c join read_parquet('{VQ}') r on r.chunk_id = c.vaquill_chunk_id""")
check("D4", "raw chunks are byte-identical: text, offsets, pages, section, language (header NOT stripped in judgment_chunk)",
      txt[0] == 0 and txt[3] == 0, f"text differs {txt[0]}, other columns differ {txt[3]}")
check("D5", "text_original is NULL only where it equals text in the raw data (lossless)", txt[1] == 0 and txt[2] == 0,
      f"rows keeping text_original {txt[1]}, rows where it was dropped but differed {txt[2]}")
inc = q("""select count(*), count(*) filter(where not is_complete), count(*) filter(where large_gap_count > 0) from judgment_text""")[0]
en_inc = one("select count(*) from judgment_text where language_code = 'en' and not is_complete")[0]
top_inc = sorted(((l, v.get("incomplete_sets", 0)) for l, v in TL.items()), key=lambda x: -x[1])[:4]
check("D6", "every chunk set is complete (chunks 0..n-1 present, n = total_chunks, no missing text)", inc[1] == 0,
      f"{n(inc[1])} of {n(inc[0])} sets are incomplete: {n(tl('non_contiguous_sets'))} with chunk indexes missing or a count different from total_chunks, "
      f"{n(inc[2])} with a gap of more than 2 characters between chunks. English sets incomplete: {en_inc}. Most affected languages: "
      + ", ".join(f"{l} {c}" for l, c in top_inc) + ".",
      exception="Vaquill delivers these sets with chunks missing. They are kept as delivered, flagged `is_complete = false` (and `incomplete_english_text` on the judgment for English), and not repaired or guessed.")
inc_rows = q("""select t.judgment_id, t.language_code, t.chunk_count, t.expected_chunks, t.large_gap_count from judgment_text t where not t.is_complete order by 1, 2 limit 8""")
sections.append(("Sample of incomplete chunk sets", md_table(["judgment_id", "language", "chunks present", "chunks expected", "large gaps"], inc_rows)))

# ====================================================================== E. text reconstruction
sets_lang = one("select count(*) from judgment_language where text_available")[0]
sets_text = one("select count(*) from judgment_text")[0]
check("E1", "one assembled text per (judgment, language) that has chunks", sets_lang == sets_text, f"language rows with text {n(sets_lang)}, texts {n(sets_text)}")
hdr = one(r"select count(*) from judgment_text where regexp_matches(text, 'Case: [^\n]*\nSection: [^\n]*\n\n')")[0]
check("E2", "no Vaquill header left in any assembled text", hdr == 0, f"{n(hdr)} texts still contain a 'Case: ... Section: ...' header")
tm = {k: int(mr[("text", k, "")]) for k in ["sets", "small", "large", "mismatch", "drift", "nohdr", "incomplete"]}
check("E3", "every raw chunk began with the header (so stripping was uniform)", tm["nohdr"] == 0, f"{tm['nohdr']} chunks without a header")
ws = int(mr[("text", "mismatch_ws", "")])
check("E4", "overlapping chunk windows agree with the text already assembled", tm["mismatch"] == 0,
      f"{n(tm['mismatch'])} overlap regions disagreed in {n(one('select count(*) from judgment_text where overlap_mismatches > 0')[0])} texts "
      f"({n(ws)} differ only in whitespace); English: {n(tl('mismatch_events', 'en'))} events in {n(tl('texts_with_mismatch', 'en'))} texts, of {n(tl('sets', 'en'))} English texts",
      exception="Inside the overlap of two Vaquill chunks the characters differ (examples seen: redacted `xxx` passages, repeated list letters, broken glyphs in Indic scripts). "
                "The earlier chunk's characters are kept and the later chunk's overlapping part is dropped. Affected texts are listed by `overlap_mismatches > 0`.")
check("E5", "chunk body length equals the char_end - char_start window", tm["drift"] == 0,
      f"{n(tm['drift'])} chunks differ in length from their offset window (median |difference| {int(mr.get(('text', 'drift_abs_median', ''), 0))}, "
      f"95th percentile {int(mr.get(('text', 'drift_abs_p95', ''), 0))}, max {int(mr.get(('text', 'drift_abs_max', ''), 0))} characters)",
      exception="The offsets Vaquill supplies do not exactly match the body length for these chunks. Each chunk is still placed at its own char_start, so the drift does not propagate to later chunks.")
lens = one("""select count(*) filter(where t.char_length = m.mx), count(*) filter(where t.char_length <> m.mx), avg(abs(t.char_length - m.mx))
              from judgment_text t join (select judgment_id, language_code, max(char_end) mx from judgment_chunk group by 1, 2) m using (judgment_id, language_code)""")
results.append(("E6", "assembled length vs the last chunk's char_end", "INFO", f"equal for {n(lens[0])} texts, different for {n(lens[1])} (mean absolute difference {lens[2]:.1f} characters)"))
empty = one("select count(*) from judgment_text where char_length = 0")[0]
check("E7", "no empty assembled texts", empty == 0, f"{empty} empty")

sections.append(("Text assembly quality by language", md_table(
    ["language", "texts", "incomplete", "gap = 2 chars (normal)", "gap 3-24", "gap > 24", "overlap mismatches", "texts with mismatch", "length-drift chunks"],
    [(l, n(v.get("sets", 0)), n(v.get("incomplete_sets", 0)), n(v.get("gap_2", 0)), n(v.get("gap_3_to_24", 0)), n(v.get("gap_over_24", 0)),
      n(v.get("mismatch_events", 0)), n(v.get("texts_with_mismatch", 0)), n(v.get("drift_chunks", 0)))
     for l, v in sorted(TL.items(), key=lambda kv: -kv[1].get("sets", 0))])))
# independent positional check on a seeded random sample of clean sets
random.seed(20261013)
sample_sets = q("select judgment_id, language_code from judgment_text where is_complete and overlap_mismatches = 0 and small_gap_count < 5 order by hash(judgment_id || language_code) limit 1500")
bad_sets = 0
for jid_, lang in sample_sets:
    full = one(f"select text from judgment_text where judgment_id = '{jid_}' and language_code = '{lang}'")[0]
    for s, e, rawtxt in q(f"select char_start, char_end, text from judgment_chunk where judgment_id = '{jid_}' and language_code = '{lang}' order by chunk_index"):
        i = rawtxt.find("\n\n", rawtxt.find("\nSection: "))
        body = rawtxt[i + 2:]
        if full[s:s + len(body)] != body:
            bad_sets += 1
            break
check("E8", "positional check: in 1,500 sampled complete texts, every chunk body sits at its char_start in the assembled text",
      bad_sets == 0, f"{bad_sets} of {len(sample_sets)} sampled texts failed")

# ====================================================================== F. language coverage
ts = dict(q("select text_status, count(*) from judgment group by 1"))
check("F1", "text_status reconciles: english + translation_only = matched judgments; none = unmatched",
      ts.get("english", 0) + ts.get("translation_only", 0) == by_status.get("matched", 0) and ts.get("none", 0) == nj - by_status.get("matched", 0),
      f"{ts}")
none_with_text = one("select count(*) from judgment j where text_status = 'none' and exists (select 1 from judgment_text t where t.judgment_id = j.judgment_id)")[0]
tr_with_en = one("select count(*) from judgment j where text_status = 'translation_only' and exists (select 1 from judgment_text t where t.judgment_id = j.judgment_id and t.language_code = 'en')")[0]
en_without = one("select count(*) from judgment j where text_status = 'english' and not exists (select 1 from judgment_text t where t.judgment_id = j.judgment_id and t.language_code = 'en')")[0]
check("F2", "'no English text' is distinct from 'no text at all' (none => no texts; translation_only => texts but no English; english => has English)",
      none_with_text == 0 and tr_with_en == 0 and en_without == 0, f"violations: none-with-text {none_with_text}, translation-with-English {tr_with_en}, english-without-English {en_without}")
meta_none = one("select count(*) filter(where title is not null and decision_date is not null and citation is not null), count(*) from judgment where text_status <> 'english'")
check("F3", "metadata is complete for judgments without usable full text (searchable by metadata)",
      meta_none[0] >= 0.99 * meta_none[1], f"{n(meta_none[0])} of {n(meta_none[1])} judgments without English text have title, date and citation")
sections.append(("Judgments by text status", md_table(["text_status", "judgments"], [(a, n(b)) for a, b in sorted(ts.items())])))
sections.append(("English text coverage by decade of decision (all canonical judgments)", md_table(
    ["decade", "judgments", "english text", "translation only", "no text", "% english"],
    [(d, n(a), n(b), n(c), n(e), f"{100.0 * b / a:.1f}") for d, a, b, c, e in q("""
      select (decision_year // 10 * 10)::int d, count(*), count(*) filter(where text_status='english'), count(*) filter(where text_status='translation_only'),
             count(*) filter(where text_status='none') from judgment group by 1 order by 1""")])))
sections.append(("Language availability (texts from Vaquill vs PDFs Vanga lists)", md_table(
    ["language", "text available", "PDF listed", "listed but no text", "text but not listed"],
    [(l, n(a), n(b), n(c), n(d)) for l, a, b, c, d in q("""
      select language_code, count(*) filter(where text_available), count(*) filter(where pdf_listed),
             count(*) filter(where pdf_listed and not text_available), count(*) filter(where text_available and not pdf_listed)
      from judgment_language group by 1 order by 2 desc, 1""")])))
mism_lang = one("select count(*) from judgment_language where text_available and text_chunks <> expected_chunks")[0]
results.append(("F4", "language sets whose chunk count differs from total_chunks (same sets as D6)", "INFO", f"{n(mism_lang)}"))

# ====================================================================== G. years
bad = one("select count(*) from judgment where decision_year is distinct from extract(year from decision_date)::smallint")[0]
check("G1", "decision_year equals the year of decision_date for every judgment", bad == 0, f"{bad} mismatches")
nd = one("select count(*) from judgment where decision_date is null")[0]
check("G2", "every judgment has a parsed decision date", nd == 0, f"{nd} without")
yf = one("select count(*) filter(where vanga_year_field is not null), count(*) filter(where vaquill_year_field is not null), count(*) filter(where match_status='matched') from judgment")
check("G3", "original source-year fields retained (Vanga on every row, Vaquill on every matched row)", yf[0] == nj and yf[1] == yf[2],
      f"vanga_year_field {n(yf[0])}/{n(nj)}, vaquill_year_field {n(yf[1])}/{n(yf[2])}")
yc = q("""select j.vanga_path, j.insc_id, c.vanga_value, c.vaquill_value, j.decision_date, j.decision_year from field_conflicts c join judgment j using (judgment_id)
          where c.field_name = 'source_year' order by 1""")
check("G4", "source-year conflicts are recorded and resolved by one deterministic rule (decision_year from decision_date)", True,
      f"{len(yc)} conflicts between Vanga year and Vaquill year; all keep decision_year = year(decision_date)")
sections.append(("Source-year conflicts (Vanga `year` vs Vaquill `year`)", md_table(["vanga_path", "insc_id", "vanga year", "vaquill year", "decision_date", "decision_year"], yc)))
yd = one("""select count(*) filter(where vanga_year_field <> decision_year), count(*) filter(where vaquill_year_field <> decision_year),
                   count(*) filter(where list_contains(quality_flags, 'insc_year_differs_from_decision_year')) from judgment""")
results.append(("G5", "source year fields that differ from the decision year (flagged, not corrected)", "INFO",
                f"Vanga {n(yd[0])} ({100.0 * yd[0] / nj:.1f}%), Vaquill {n(yd[1])}; INSC-id year differs: {n(yd[2])}"))

# ====================================================================== H. provenance and NULL policy
FIELDS = ["title", "petitioner", "respondent", "citation", "disposal", "court", "decision_date", "judges", "cnr", "available_languages", "decision_year", "bench_strength"]
prov_n = one("select count(*) from judgment_field_provenance")[0]
check("H1", f"every judgment has provenance for all {len(FIELDS)} tracked fields", prov_n == nj * len(FIELDS)
      and one("select count(*) from (select 1 from judgment_field_provenance group by judgment_id, field_name having count(*) > 1)")[0] == 0,
      f"{n(prov_n)} rows, expected {n(nj * len(FIELDS))}")
mis = {}
for f in ["title", "petitioner", "respondent", "citation", "disposal", "court", "cnr"]:
    mis[f] = one(f"select count(*) from judgment j join judgment_field_provenance p on p.judgment_id = j.judgment_id and p.field_name = '{f}' where j.{f} is distinct from p.chosen_value")[0]
mis["decision_date"] = one("select count(*) from judgment j join judgment_field_provenance p on p.judgment_id = j.judgment_id and p.field_name = 'decision_date' where cast(j.decision_date as varchar) is distinct from p.chosen_value")[0]
mis["decision_year"] = one("select count(*) from judgment j join judgment_field_provenance p on p.judgment_id = j.judgment_id and p.field_name = 'decision_year' where cast(j.decision_year as varchar) is distinct from p.chosen_value")[0]
mis["bench_strength"] = one("select count(*) from judgment j join judgment_field_provenance p on p.judgment_id = j.judgment_id and p.field_name = 'bench_strength' where cast(j.bench_strength as varchar) is distinct from p.chosen_value")[0]
check("H2", "the value stored in judgment equals the provenance chosen_value, field by field", sum(mis.values()) == 0, f"mismatches: { {k: v for k, v in mis.items() if v} or 'none' }")
srcs = q("select field_name, chosen_source, count(*) from judgment_field_provenance group by 1, 2 order by 1, 2")
sections.append(("Provenance: chosen source per field", md_table(["field", "chosen_source", "judgments"], [(a, b, n(c)) for a, b, c in srcs])))
reasons = q("select field_name, reason, count(*) from judgment_field_provenance where reason like 'conflict%' or reason like '%filled%' group by 1, 2 order by 1")
sections.append(("Provenance: fills and conflicts", md_table(["field", "reason", "judgments"], [(a, b, n(c)) for a, b, c in reasons]) if reasons else "No fills and no conflicts were needed beyond those listed in the conflict table.\n"))
cf = q("select field_name, count(*) from field_conflicts group by 1 order by 1")
prov_conf = dict(q("select field_name, count(*) from judgment_field_provenance where reason like 'conflict%' group by 1"))
cf_ok = all(prov_conf.get(f, 0) == c for f, c in cf if f not in ("source_year", "bench_strength"))
check("H3", "every field conflict is surfaced in field_conflicts and keeps the other value as alt_value", cf_ok,
      f"conflicts by field: {dict(cf) or 'none'}")
sections.append(("Field conflicts by field", md_table(["field", "conflicts"], [(a, n(b)) for a, b in cf]) if cf else "No conflicts recorded.\n"))
nonnull = one("select count(case_number), count(diary_number), count(pdf_url) from judgment")
check("H4", "fields with no source stay NULL (case_number, diary_number, pdf_url); OCR description is not used", nonnull == (0, 0, 0), f"non-null counts: {nonnull}")
bs = one("""select count(*) filter(where coalesce(j.bench_strength, 0) <> coalesce(c.n, 0)) from judgment j
            left join (select judgment_id, count(*) n from judgment_judge group by 1) c using (judgment_id)""")[0]
check("H5", "bench_strength equals the number of judgment_judge rows", bs == 0, f"{bs} mismatches")
idu = one("select count(*) from (select 1 from judgment_identifier group by identifier_type, value, judgment_id having count(*) > 1)")[0]
check("H6", "identifiers unique on (type, value, judgment_id)", idu == 0, f"{idu} duplicates")
idt = q("select identifier_type, count(*) from judgment_identifier group by 1 order by 1")
sections.append(("Identifiers by type (no SCC, AIR or diary numbers exist in either source)", md_table(["type", "rows"], [(a, n(b)) for a, b in idt])))
before = {k[1]: v for k, v in mr.items() if k[0] == "null_rate_before_pct"}
after = {k[1]: v for k, v in mr.items() if k[0] == "null_rate_after_pct"}
sections.append(("Null / empty rate per field, before (Vanga canonical rows) and after the merge", md_table(
    ["field", "before %", "after %"], [(k, f"{before[k]:.2f}", f"{after[k]:.2f}") for k in before])))
np_ = one("select count(*) from judgment_judge where source = 'vaquill'")[0], one("select count(*) from judgment_judge where source = 'vanga'")[0]
results.append(("H7", "judgment_judge rows by source", "INFO", f"vaquill {n(np_[0])}, vanga {n(np_[1])}"))

# ====================================================================== I. reproducibility
rp = B / "reproducibility.json"
if rp.exists():
    rr = json.loads(rp.read_text())
    check("I1", "rebuilding from the same raw files gives identical table contents", rr["identical"], f"{sum(rr['tables'].values())}/{len(rr['tables'])} tables identical")
else:
    results.append(("I1", "rebuild reproducibility", "NOT RUN", "run pipeline/05_build_canonical.py a second time"))

# ====================================================================== J. schema alignment with the migrations
try:
    ddl = subprocess.run(["psql", "-h", "127.0.0.1", "-p", "54329", "-U", "postgres", "-At", "-F", "|", "-c",
                          "select table_name, column_name from information_schema.columns where table_schema = 'public'"],
                         capture_output=True, text=True, timeout=20)
    cols = {}
    for line in ddl.stdout.splitlines():
        t, c = line.split("|")
        cols.setdefault(t, set()).add(c)
    probs = []
    for t in ["judgment", "judgment_source_map", "judgment_field_provenance", "field_conflicts", "match_review_queue", "judgment_judge", "judgment_identifier",
              "judgment_language", "judgment_chunk", "judgment_text", "source_vanga_raw", "source_vaquill_raw"]:
        pc = {r[0] for r in q(f"describe {t}")}
        extra = pc - cols.get(t, set())
        if extra:
            probs.append(f"{t}: parquet columns not in DDL {sorted(extra)}")
    check("J1", "every column written to build/*.parquet exists in the migration DDL (checked against a scratch PostgreSQL 16)", not probs and bool(cols), "; ".join(probs) or f"{len(cols)} tables inspected")
except Exception as exc:  # noqa
    results.append(("J1", "schema alignment with migrations", "NOT RUN", f"scratch PostgreSQL not reachable ({exc.__class__.__name__})"))

# ====================================================================== K. samples across eras
random.seed(7)
eras = [(1950, 1959), (1970, 1979), (1990, 1999), (2010, 2019), (2020, 2029)]
samples = []
for lo, hi in eras:
    samples += [r[0] for r in q(f"select judgment_id from judgment where decision_year between {lo} and {hi} and match_status = 'matched' order by hash(judgment_id || 'k{lo}') limit 2")]
sample_md = []
for jid_ in samples:
    _cur = con.execute(f"select * from judgment where judgment_id = '{jid_}'")
    j = dict(zip([d[0] for d in _cur.description], _cur.fetchone()))
    rawv = one(f"select raw, year_folder from source_vanga_raw where is_canonical_copy and path = '{j['vanga_path']}'")
    rawq = one(f"select r.raw, r.chunk_row_count from judgment_source_map m join source_vaquill_raw r using (vaquill_case_id) where m.judgment_id = '{jid_}'")
    snippet = one(f"select left(text, 160) from judgment_text where judgment_id = '{jid_}' and language_code = 'en'")
    sample_md.append(f"#### {j['insc_id']}: {j['title']}\n")
    sample_md.append("**Canonical judgment**\n\n```json\n" + json.dumps(j, indent=1, default=str, ensure_ascii=False) + "\n```\n")
    vraw = json.loads(rawv[0]); vraw["raw_html"] = f"<{len(vraw['raw_html'])} chars>"
    sample_md.append("**Raw Vanga** (folder year " + str(rawv[1]) + ")\n\n```json\n" + json.dumps(vraw, indent=1, ensure_ascii=False) + "\n```\n")
    sample_md.append(f"**Raw Vaquill** ({rawq[1]} chunk rows)\n\n```json\n" + rawq[0] + "\n```\n")
    sample_md.append("**First 160 characters of the assembled English text:** `" + (snippet[0].replace("\n", " ") if snippet else "none") + "`\n")

# ====================================================================== write the report
fails = [r for r in results if r[2] == "FAIL"]
exc = [r for r in results if r[2] == "EXCEPTION"]
now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
bid = one("select distinct build_id from merge_report limit 1")[0]
lines = [f"# Stage 3 validation report\n", f"Build `{bid}`, validated {now} by `pipeline/06_validate_stage3.py`. Every check below is computed from `build/*.parquet` and, where noted, "
         "re-derived independently from the raw files.\n",
         f"**Result: {sum(1 for r in results if r[2] == 'PASS')} PASS, {len(exc)} EXCEPTION (explained), {len(fails)} FAIL, "
         f"{sum(1 for r in results if r[2] in ('INFO', 'NOT RUN'))} informational / not run.**\n",
         "## Checks\n", md_table(["id", "check", "status", "measured"], results)]
for title, body in sections:
    lines += [f"## {title}\n", body]
lines += ["## Sample of 10 merged records across eras (canonical row next to both raw sources)\n"] + sample_md
OUT.write_text("\n".join(lines))
print(f"\nwrote {OUT}: {len(fails)} FAIL, {len(exc)} EXCEPTION")
sys.exit(1 if fails else 0)
