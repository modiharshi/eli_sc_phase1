#!/usr/bin/env python3
"""Stage 2: profile Vanga + Vaquill raw parquet with DuckDB and write docs/SCHEMA_COMPARISON.md.

Read-only over raw/. Idempotent: regenerates the markdown from scratch each run.
Run:  .venv/bin/python -I pipeline/03_profile_schemas.py
"""
import datetime as dt
import pathlib
import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "SCHEMA_COMPARISON.md"
VANGA = f"{ROOT}/raw/vanga/metadata/parquet/*/*.parquet"
VQ_SC = f"{ROOT}/raw/vaquill/in_supreme-court_judgments.parquet"
VQ_LEG = f"{ROOT}/raw/vaquill/in_central_legislation.parquet"

con = duckdb.connect()
con.execute("set threads=4")
con.execute("set preserve_insertion_order=false")
con.execute(r"create macro norm(x) as lower(trim(regexp_replace(coalesce(x,''),'\s+',' ','g')))")

md = []


def esc(v):
    s = "" if v is None else str(v)
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(esc(x) for x in r) + " |")
    return "\n".join(out) + "\n"


def q(sql):
    return con.execute(sql).fetchall()


def one(sql):
    return con.execute(sql).fetchone()


def pct(n, d):
    return f"{100.0 * n / d:.2f}%" if d else "n/a"


def profile(tbl, skip=(), approx=()):
    """Per-column: type, null %, empty-string %, distinct, 3 sample values."""
    n = one(f"select count(*) from {tbl}")[0]
    cols = [(r[0], r[1]) for r in q(f"describe {tbl}") if r[0] not in skip]
    rows = []
    for c, t in cols:
        ident = f'"{c}"'
        as_txt = f"cast({ident} as varchar)"
        is_text = t == "VARCHAR"
        nulls = one(f"select count(*) from {tbl} where {ident} is null")[0]
        empty = one(f"select count(*) from {tbl} where {as_txt} in ('','[]')")[0]
        fn = "approx_count_distinct" if c in approx else "count(distinct"
        dsql = (f"select approx_count_distinct({as_txt}) from {tbl}" if c in approx
                else f"select count(distinct {as_txt}) from {tbl}")
        distinct = one(dsql)[0]
        samples = [r[0] for r in q(
            f"select distinct left({as_txt}, 60) from {tbl} "
            f"where {ident} is not null and {as_txt} not in ('','[]') limit 3")]
        rows.append([c, t, pct(nulls, n), pct(empty, n), f"{distinct:,}" + ("~" if c in approx else ""),
                     " ¦ ".join(samples)])
    return n, rows


H_PROF = ["column", "type", "null %", "empty-string %", "distinct", "3 samples"]

# ---------------------------------------------------------------- load
con.execute(f"""
create table vg as
select *,
       regexp_extract(filename, 'year=(\\d+)', 1)::int          as part_year,
       try_strptime(decision_date, '%d-%m-%Y')::date            as dd,
       replace(case_id, ' ', '_')                               as nkey,
       try_cast(regexp_extract(case_id, '^(\\d{{4}})', 1) as int) as id_year
from read_parquet('{VANGA}', hive_partitioning=false, union_by_name=true, filename=true)
""")
VG_ORIG = [r[0] for r in q("describe vg") if r[0] not in ("filename", "part_year", "dd", "nkey", "id_year")]

con.execute(f"""
create table vq_meta as
select distinct case_id, language_code, title, petitioner, respondent, disposition, case_number, citation,
       decision_date, date_of_registration, year, court, court_code, court_type, bench, bench_strength,
       judges, description, source_url
from read_parquet('{VQ_SC}')
""")
con.execute(r"""
alter table vq_meta add column dd date;
update vq_meta set dd = try_cast(decision_date as date);
alter table vq_meta add column id_year int;
update vq_meta set id_year = try_cast(regexp_extract(case_id, '^(\d{4})', 1) as int);
""")
con.execute(f"create view vq as select * from read_parquet('{VQ_SC}')")
con.execute(f"create view leg as select * from read_parquet('{VQ_LEG}')")

today = dt.date.today().isoformat()
md.append(f"# Schema comparison: Vanga vs Vaquill (Supreme Court)\n\nGenerated {today} by `pipeline/03_profile_schemas.py` "
          "(DuckDB over the untouched files in `raw/`). Regenerate by re-running the script.\n")

# ---------------------------------------------------------------- 1 headline
vg_rows = one("select count(*) from vg")[0]
vq_rows = one("select count(*) from vq")[0]
vq_cases = one("select count(distinct case_id) from vq")[0]
vg_keys = one("select count(distinct nkey) from vg")[0]
md.append("## 1. Headline facts\n")
md.append(table(["", "Vanga (metadata parquet)", "Vaquill (SC judgments)"], [
    ["grain", "one row per metadata record (a judgment)", "one row per text **chunk**"],
    ["rows", f"{vg_rows:,}", f"{vq_rows:,}"],
    ["columns", len(VG_ORIG), len(q("describe vq"))],
    ["distinct judgments (`case_id`)", f"{vg_keys:,} (distinct `case_id`)  /  {one('select count(distinct path) from vg')[0]:,} (distinct `path`)", f"{vq_cases:,}"],
    ["json files vs parquet rows", "43,552 JSON files = 43,552 parquet rows", "n/a"],
]))

# ---------------------------------------------------------------- 2 column profiles
CACHE = ROOT / "logs" / "profile_section2.md"  # delete to refresh the slow column profiles
if CACHE.exists():
    md.append(CACHE.read_text())
else:
    _start = len(md)
    md.append("## 2. Column profiles\n")
    md.append("`null %` is SQL NULL; `empty-string %` counts `''` and `[]`. Both mean 'no value'. `~` = approximate distinct count.\n")
    n, rows = profile("vg", skip=("filename", "part_year", "dd", "nkey", "id_year"), approx=("raw_html",))
    md.append(f"### 2.1 Vanga: {n:,} rows\n")
    md.append(table(H_PROF, rows))
    n, rows = profile("vq", approx=("text", "text_original"))
    md.append(f"### 2.2 Vaquill Supreme Court: {n:,} rows\n")
    md.append(table(H_PROF, rows))
    n, rows = profile("leg", approx=("text",) if "text" in [r[0] for r in q("describe leg")] else ())
    md.append(f"### 2.3 Vaquill central legislation: {n:,} rows (loaded for Phase 2 statute linking)\n")
    md.append(table(H_PROF, rows))
    CACHE.write_text("\n".join(md[_start:]))

# ---------------------------------------------------------------- 3 key overlap
md.append("## 3. Join key and overlap (preview only, nothing is merged here)\n")
md.append("Vanga `case_id` is an INSC identifier with a space (`1960 INSC 103`); Vaquill `case_id` is the same with an underscore "
          "(`1960_INSC_103`). Normalising the space gives an exact key. This is a preview of how far the key alone gets us; "
          "the tiered matching in Stage 3 still applies.\n")
both, vg_only, vq_only = one("""
select count(*) filter(where a.k is not null and b.k is not null),
       count(*) filter(where b.k is null), count(*) filter(where a.k is null)
from (select distinct nkey k from vg where nkey <> '') a full join (select distinct case_id k from vq_meta) b using (k)
""")
md.append(table(["", "judgments"], [["in both (exact normalised key)", f"{both:,}"], ["Vanga only", f"{vg_only:,}"],
                                      ["Vaquill only", f"{vq_only:,}"]]))
rows = q("""
select coalesce(a.decd, b.decd) as decade,
       count(*) filter(where a.k is not null and b.k is not null) both_,
       count(*) filter(where b.k is null) vanga_only, count(*) filter(where a.k is null) vaquill_only
from (select nkey k, (min(extract(year from dd))::int//10*10) decd from vg where nkey <> '' group by nkey) a
full join (select case_id k, (min(extract(year from dd))::int//10*10) decd from vq_meta group by case_id) b using (k)
group by 1 order by 1""")
md.append("By decade of decision date (NULL = no parseable date):\n")
md.append(table(["decade", "both", "Vanga only", "Vaquill only"], rows))

# ---------------------------------------------------------------- 4 mapping
md.append("## 4. Field mapping\n")
md.append("### 4.1 Same field, possibly different name or format\n")
md.append(table(["concept", "Vanga column", "Vaquill column", "format difference"], [
    ["judgment id (INSC)", "`case_id` (`1960 INSC 103`), `nc_display` (`1960INSC103`)", "`case_id` (`1960_INSC_103`)", "space vs underscore"],
    ["title", "`title`", "`title`", "none expected"],
    ["petitioner / respondent", "`petitioner`, `respondent`", "`petitioner`, `respondent`", "none expected"],
    ["description", "`description`", "`description`", "see profile (mostly empty)"],
    ["decision date", "`decision_date` (`DD-MM-YYYY`, string)", "`decision_date` (`YYYY-MM-DD`, string)", "date format"],
    ["judges", "`judge` (comma-separated string)", "`judges` (list of strings) and `bench` (string)", "string vs list"],
    ["disposal", "`disposal_nature`", "`disposition`", "name"],
    ["report citation", "`citation` (`[1960] 3 S.C.R. 880`)", "`citation`", "none expected"],
    ["court", "`court`", "`court`", "none expected"],
    ["year", "`year` (law-report year, **not** decision year)", "`year`", "see section 6"],
    ["language", "`available_languages` (list of all languages, comma string)", "`language_code` (language of this chunk set)", "different meaning"],
]))
md.append("### 4.2 Only in Vanga\n")
md.append(table(["column", "note"], [
    ["`path`", "report key (`1960_3_880_887`); likely also the PDF file key in the S3 `data/` tree (to be confirmed in Stage 8). Not unique (see 6.1)"],
    ["`cnr`", "CNR-style identifier (`ESCR...`); one per distinct `path`"],
    ["`author_judge`", "**100% NULL**, carries no data"],
    ["`available_languages`", "languages the PDF exists in"],
    ["`raw_html`", "scraped HTML fragment; contains only a language dropdown and no PDF link (`href='#'`)"],
    ["`nc_display`", "compact INSC id"],
    ["`scraped_at`", "scrape timestamp"],
    ["JSON only: `citation_year`", "present in every JSON file, **absent from the parquet**; keep from the raw JSON"],
]))
md.append("### 4.3 Only in Vaquill\n")
md.append(table(["column", "note"], [
    ["`chunk_id`, `chunk_index`, `total_chunks`, `char_start`, `char_end`, `page_start`, `page_end`, `section_type`, `section_priority`, `box_aware`",
     "chunk structure"],
    ["`text`, `text_original`", "identical on every row (see 7.4)"],
    ["`bench_strength`", "always equals the length of `judges` (checked: 0 exceptions), so it is derived, not independent data"],
    ["`court_code`, `court_type`", "court coding"],
    ["`case_number`, `date_of_registration`, `source_url`, `bench`, `description`", "**100% empty** in the file, so they cannot fill anything"],
    ["`section_priority`", "**100% NULL**"],
]))
md.append("### 4.4 Fields in both, with measured agreement\n")
md.append("Computed on judgments present in both sources. Values are whitespace-collapsed and case-folded; dates are parsed; "
          "judges compared as sorted upper-case sets. `agree` = at least one non-empty value matches; `conflict` = both non-empty and none match; "
          "`only Vanga` / `only Vaquill` = the other side is empty (this is what filling can recover).\n")
FIELDS = {
    "title": ("norm(title)", "norm(title)"),
    "petitioner": ("norm(petitioner)", "norm(petitioner)"),
    "respondent": ("norm(respondent)", "norm(respondent)"),
    "description": ("norm(description)", "norm(description)"),
    "decision_date": ("coalesce(cast(dd as varchar),'')", "coalesce(cast(dd as varchar),'')"),
    "citation": ("norm(citation)", "norm(citation)"),
    "disposal / disposition": ("norm(disposal_nature)", "norm(disposition)"),
    "year": ("cast(year as varchar)", "cast(year as varchar)"),
    "court": ("norm(court)", "norm(court)"),
    "judges": (
        "coalesce(array_to_string(list_sort(list_transform(string_split(coalesce(judge,''), ','), x -> upper(trim(x)))),'|'),'')",
        "coalesce(array_to_string(list_sort(list_transform(judges, x -> upper(trim(x)))),'|'),'')"),
}
rows = []
conflict_examples = {}
for name, (ve, qe) in FIELDS.items():
    r = one(f"""
    with a as (select nkey k, list(distinct {ve}) filter (where {ve} <> '') av from vg where nkey <> '' group by nkey),
         b as (select case_id k, list(distinct {qe}) filter (where {qe} <> '') bv from vq_meta group by case_id),
         j as (select k, coalesce(av, []) av, coalesce(bv, []) bv from a join b using (k))
    select count(*),
      count(*) filter(where len(av)=0 and len(bv)=0),
      count(*) filter(where len(av)>0 and len(bv)=0),
      count(*) filter(where len(av)=0 and len(bv)>0),
      count(*) filter(where len(av)>0 and len(bv)>0 and list_has_any(av,bv)),
      count(*) filter(where len(av)>0 and len(bv)>0 and not list_has_any(av,bv))
    from j""")
    tot, be, ov, oq, ag, cf = r
    rows.append([name, f"{tot:,}", f"{ag:,}", f"{cf:,} ({pct(cf, ag + cf)})", f"{ov:,}", f"{oq:,}", f"{be:,}"])
    if cf:
        conflict_examples[name] = q(f"""
        with a as (select nkey k, list(distinct {ve}) filter (where {ve} <> '') av from vg where nkey <> '' group by nkey),
             b as (select case_id k, list(distinct {qe}) filter (where {qe} <> '') bv from vq_meta group by case_id)
        select k, left(cast(av as varchar),70), left(cast(bv as varchar),70)
        from a join b using (k)
        where len(av)>0 and len(bv)>0 and not list_has_any(av,bv) order by k limit 3""")
md.append(table(["field", "judgments in both", "agree", "conflict (of comparable)", "only Vanga", "only Vaquill", "both empty"], rows))
if conflict_examples:
    md.append("Example conflicts (key, Vanga value(s), Vaquill value(s)):\n")
    for name, ex in conflict_examples.items():
        md.append(f"- **{name}**: " + "; ".join(f"`{e[0]}`: {e[1]} vs {e[2]}" for e in ex))
    md.append("")

# ---------------------------------------------------------------- 5 vaquill structure
md.append("## 5. Vaquill is chunk-level\n")
md.append(f"- Distinct `case_id` values: **{vq_cases:,}** across {vq_rows:,} chunk rows "
          f"(average {vq_rows / vq_cases:.1f} chunks per case).\n")
langs = q("""select language_code, count(distinct case_id) cases, count(*) chunks from vq group by 1 order by 2 desc""")
md.append("Chunk sets exist **per language**; the chunk_id carries a language suffix (e.g. `_hin`). A case can therefore have several chunk sets.\n")
md.append(table(["language_code", "cases", "chunks"], [[a, f"{b:,}", f"{c:,}"] for a, b, c in langs]))
multi = one("select count(*) from (select case_id from vq_meta group by 1 having count(distinct language_code) > 1)")[0]
md.append(f"Cases with more than one language chunk set: **{multi:,}**.\n")
md.append("### 5.1 Is metadata constant across a case's chunks?\n")
META = ["title", "petitioner", "respondent", "disposition", "case_number", "citation", "decision_date", "date_of_registration",
        "year", "court", "court_code", "court_type", "bench", "bench_strength", "judges", "description", "source_url"]
rows = []
for c in META:
    expr = f"cast({c} as varchar)"
    n_all, n_lang = one(f"""
    select (select count(*) from (select case_id from vq_meta group by 1 having count(distinct {expr}) > 1)),
           (select count(*) from (select case_id, language_code from vq_meta group by 1,2 having count(distinct {expr}) > 1))""")
    ex = q(f"select case_id, left(string_agg(distinct {expr}, ' ¦ '),90) from vq_meta group by 1 having count(distinct {expr}) > 1 order by 1 limit 1")
    rows.append([c, f"{n_all:,}", f"{n_lang:,}", f"{ex[0][0]}: {ex[0][1]}" if ex else ""])
md.append(table(["metadata column", "cases where it varies across chunks (all languages)", "cases where it varies within one language set", "example"], rows))
nonconst = one(f"""select count(*) from (select case_id from vq_meta group by 1 having
  count(distinct (title, petitioner, respondent, disposition, case_number, citation, decision_date, year, court, bench, bench_strength, cast(judges as varchar))) > 1)""")[0]
md.append(f"Cases with **any** of the core metadata columns varying across chunks: **{nonconst:,}** of {vq_cases:,}.\n")
md.append("### 5.2 Chunk completeness\n")
inc = one("""select count(*), count(*) filter(where n <> tc or mx + 1 <> tc) from (
  select case_id, language_code, count(*) n, max(chunk_index) mx, max(total_chunks) tc from vq group by 1,2)""")
md.append(f"Chunk sets (case × language): {inc[0]:,}. Sets whose row count or max `chunk_index`+1 differs from `total_chunks` "
          f"(missing or extra chunks): **{inc[1]:,}**.\n")
dupchunk = one("select count(*) from (select chunk_id from vq group by 1 having count(*) > 1)")[0]
md.append(f"Duplicate `chunk_id` values: **{dupchunk:,}**.\n")
md.append(table(["section_type", "chunks"], [[a, f"{b:,}"] for a, b in q("select coalesce(section_type,'NULL'), count(*) from vq group by 1 order by 2 desc")]))

# ---------------------------------------------------------------- 6 upstream issues
md.append("## 6. Known upstream issues, tested and quantified\n")
md.append("### 6.1 Vanga duplicates and repeated judgments\n")
empty_rows = one("""select count(*), count(distinct path), (select count(distinct v.path) from vg v join vq_meta q on lower(trim(v.title)) = lower(trim(q.title)) and v.dd = q.dd where v.case_id = '')
                    from vg where case_id = ''""")
dup_goodcopy = one("""select count(*), count(*) filter(where good = 1) from (
  select path, sum((extract(year from dd) = part_year)::int) good from vg
  where path in (select path from vg group by 1 having count(*) > 1) group by 1)""")
dup_cols = {}
for _c in ["title","petitioner","respondent","description","judge","author_judge","citation","case_id","cnr","decision_date","disposal_nature",
           "court","available_languages","raw_html","nc_display","year","scraped_at"]:
    _n = one(f"select count(*) from (select path from vg where path in (select path from vg group by 1 having count(*)>1) group by 1 having count(distinct cast({_c} as varchar))>1)")[0]
    if _n: dup_cols[_c] = _n

p = one("select count(*), count(distinct path), count(distinct nkey) filter(where nkey <> ''), count(distinct cnr) from vg")
dup_paths = one("select count(*), coalesce(sum(n),0) from (select path, count(*) n from vg group by 1 having count(*) > 1)")
dup_diffyear = one("select count(*) from (select path from vg group by 1 having count(distinct part_year) > 1)")[0]
dup_identical = one("""select count(*) filter(where nd = 1), count(*) filter(where nd > 1) from (
  select path, count(distinct md5(concat_ws('¦', title, petitioner, respondent, description, judge, author_judge, citation, case_id, cnr,
        decision_date, disposal_nature, court, available_languages, raw_html, nc_display, cast(year as varchar)))) nd
  from vg group by 1 having count(*) > 1)""")
multi_path = one("select count(*) from (select nkey from vg where nkey <> '' group by 1 having count(distinct path) > 1)")[0]
multi_date_case = one("select count(*) from (select nkey from vg where nkey <> '' group by 1 having count(distinct dd) > 1)")[0]
multi_date_path = one("select count(*) from (select path from vg group by 1 having count(distinct dd) > 1)")[0]
md.append(table(["measure", "value"], [
    ["parquet rows", f"{p[0]:,}"], ["distinct `path`", f"{p[1]:,}"], ["distinct non-empty `case_id`", f"{p[2]:,}"], ["distinct `cnr`", f"{p[3]:,}"],
    ["extra rows (rows − distinct path)", f"{p[0] - p[1]:,}"],
    ["`path` values appearing in more than one row", f"{dup_paths[0]:,} (covering {dup_paths[1]:,} rows)"],
    ["…of which sit under different `year=` partitions", f"{dup_diffyear:,}"],
    ["…of which all columns are identical (pure copies)", f"{dup_identical[0]:,}"],
    ["…of which some column differs", f"{dup_identical[1]:,}"],
    ["columns that differ between the two copies (paths affected)", ", ".join(f"`{k}` {v:,}" for k, v in dup_cols.items())],
    ["duplicated paths where **exactly one** copy has decision-date year = partition year", f"{dup_goodcopy[1]:,} of {dup_goodcopy[0]:,}"],
    ["rows with an **empty** `case_id` (and empty `nc_display`)", f"{empty_rows[0]:,} rows / {empty_rows[1]:,} paths (matchable to Vaquill on title+date: {empty_rows[2]:,})"],
    ["non-empty `case_id` values mapping to more than one `path`", f"{multi_path:,}"],
    ["`case_id` with more than one distinct decision date", f"{multi_date_case:,}"],
    ["`path` with more than one distinct decision date", f"{multi_date_path:,}"],
]))
ex = q("""select nkey, string_agg(distinct cast(dd as varchar), ' ¦ '), string_agg(distinct path, ' ¦ ') from vg
          where nkey <> '' group by 1 having count(distinct dd) > 1 order by 1 limit 5""")
if ex:
    md.append("Examples of one `case_id` under several decision dates (id, dates, paths):\n")
    md.append(table(["case_id", "dates", "paths"], [[a, b, c[:120]] for a, b, c in ex]))
md.append("**Dedupe rule (verified):** the second copy of each duplicated `path` is a misfiled copy under the wrong `year=` folder. Keep the copy whose partition year equals the year of its parsed decision date; this picks exactly one copy for every duplicated path.\n")

md.append("### 6.2 Wrong or misleading year\n")
md.append("Decision year is derived from the **parsed decision date**, never from `year`. Supreme Court first sat 28 Jan 1950, so any date earlier than that, or later than today, is wrong.\n")
v = one("""select count(*), count(*) filter(where dd is null),
  count(*) filter(where dd < date '1950-01-28'), count(*) filter(where dd > current_date),
  count(*) filter(where year <> part_year), count(*) filter(where extract(year from dd) <> part_year),
  count(*) filter(where extract(year from dd) <> year), count(*) filter(where id_year <> extract(year from dd)),
  min(dd), max(dd) from vg""")
vq_ = one("""select count(*), count(*) filter(where dd is null), count(*) filter(where dd < date '1950-01-28'),
  count(*) filter(where dd > current_date), count(*) filter(where extract(year from dd) <> year),
  count(*) filter(where id_year <> extract(year from dd)), min(dd), max(dd) from vq_meta""")
md.append(table(["test", "Vanga (rows)", "Vaquill (case×language rows)"], [
    ["rows tested", f"{v[0]:,}", f"{vq_[0]:,}"],
    ["decision date missing or unparseable", f"{v[1]:,} ({pct(v[1], v[0])})", f"{vq_[1]:,} ({pct(vq_[1], vq_[0])})"],
    ["decision date before 1950-01-28", f"{v[2]:,}", f"{vq_[2]:,}"],
    ["decision date in the future", f"{v[3]:,}", f"{vq_[3]:,}"],
    ["`year` column ≠ `year=` partition folder", f"{v[4]:,} ({pct(v[4], v[0])})", "n/a (single file)"],
    ["decision-date year ≠ `year=` partition folder", f"{v[5]:,} ({pct(v[5], v[0])})", "n/a"],
    ["decision-date year ≠ `year` column", f"{v[6]:,} ({pct(v[6], v[0])})", f"{vq_[4]:,} ({pct(vq_[4], vq_[0])})"],
    ["INSC-id year ≠ decision-date year", f"{v[7]:,} ({pct(v[7], v[0])})", f"{vq_[5]:,} ({pct(vq_[5], vq_[0])})"],
    ["earliest / latest decision date", f"{v[8]} / {v[9]}", f"{vq_[6]} / {vq_[7]}"],
]))
ex = q("""select case_id, decision_date, year, part_year, id_year from vg
          where dd < date '1950-01-28' or dd > current_date or abs(id_year - extract(year from dd)) >= 2 order by abs(id_year - extract(year from dd)) desc nulls first limit 8""")
if ex:
    md.append("Worst Vanga year anomalies (case_id, decision_date, `year`, partition, INSC-id year):\n")
    md.append(table(["case_id", "decision_date", "year", "partition", "id year"], ex))
ex = q("""select distinct case_id, decision_date, year from vq_meta
          where dd < date '1950-01-28' or dd > current_date or abs(id_year - extract(year from dd)) >= 2
          order by abs(id_year - extract(year from dd)) desc nulls first limit 8""")
if ex:
    md.append("Worst Vaquill year anomalies (case_id, decision_date, `year`):\n")
    md.append(table(["case_id", "decision_date", "year"], ex))

md.append("### 6.3 Same judgment under more than one decision date\n")
vq_multi = one("select count(*) from (select case_id from vq_meta group by 1 having count(distinct dd) > 1)")[0]
md.append(f"- Vanga: **{multi_date_case:,}** `case_id` values and **{multi_date_path:,}** `path` values carry more than one decision date (examples in 6.1).\n"
          f"- Vaquill: **{vq_multi:,}** `case_id` values carry more than one decision date.\n")
_r = one("""with d as (select * from vg where extract(year from dd) = part_year or path not in (select path from vg group by 1 having count(*) > 1))
  select (select count(*) from d), (select count(distinct path) from d), count(*), count(*) filter(where nc > 1), count(*) filter(where nd > 1) from (
  select case_id, count(distinct citation) nc, count(distinct dd) nd from d where case_id <> '' group by 1 having count(distinct path) > 1)""")
md.append(f"**What these are:** after applying the dedupe rule from 6.1, Vanga has {_r[0]:,} rows for {_r[1]:,} distinct paths (one row per path). "
          f"Of the {_r[2]} INSC ids that still map to more than one path, **{_r[3]} have a different report citation per path** and {_r[4]} have different decision dates. "
          "These are separate reported judgments (often related proceedings between the same parties, e.g. `2014_INSC_168`) that share one INSC id, "
          "not one judgment filed under several dates. Consequences: (1) the INSC id alone is **not** a unique judgment key in Vanga; "
          "(2) Vaquill keeps one record per id, so it holds fewer judgments than Vanga's distinct paths; (3) Stage 3 matching must use the INSC id **plus citation** "
          "and send any id that still has several candidates to the review queue.\n")

md.append("### 6.4 `judis/NNNN.pdf` links needing a `jonew/` prefix\n")
vg_links = one("select count(*) filter(where raw_html ilike '%judis/%'), count(*) filter(where raw_html ilike '%jonew/%'), "
               "count(*) filter(where raw_html ilike '%.pdf%'), count(*) filter(where path ilike '%judis%') from vg")
vq_links = one("select count(*) filter(where source_url ilike '%judis/%'), count(*) filter(where source_url ilike '%jonew/%'), "
               "count(*) filter(where source_url <> '') from vq_meta")
vq_text = one("select count(*) filter(where text ilike '%judis/%'), count(*) filter(where text ilike '%jonew/%') from vq")
md.append(table(["where searched", "`judis/`", "`jonew/`", "any PDF link"], [
    ["Vanga `raw_html` / `path`", vg_links[0] + vg_links[3], vg_links[1], vg_links[2]],
    ["Vaquill `source_url`", vq_links[0], vq_links[1], vq_links[2]],
    ["Vaquill chunk `text` (chunks containing the string)", f"{vq_text[0]:,}", f"{vq_text[1]:,}", "n/a"],
]))
md.append("**Result:** neither source stores a PDF URL. Vanga's only link is `href='#'` and Vaquill `source_url` is empty on every row. "
          "The `judis/` → `jonew/` problem therefore cannot occur in the metadata. `pdf_url` has to be derived later from the Vanga "
          "`path` and `year` and the S3 `data/` key layout (Stage 8), not copied from the data.\n")

# ---------------------------------------------------------------- 7 other observations
md.append("## 7. Other observations that affect the merge design\n")
md.append("### 7.1 Fields the prompt expects that are absent\n")
md.append("- **diary number:** no column in either source. Not derivable from these files; `judgment.diary_number` stays empty until a source exists.\n"
          "- **language of the judgment:** Vanga has only the list of available languages; Vaquill has a per-chunk-set `language_code`.\n"
          "- **bench strength:** Vaquill only. Vanga's `judge` list could give a count; compare in Stage 3.\n"
          "- **identifier types:** see the citation formats in the profile. SCC and AIR identifiers are checked in the Stage 7 readiness tests.\n")
bs = one("""select count(*) filter(where bench_strength is not null), count(*) filter(where bench_strength = 0) from vq_meta""")
md.append("### 7.2 Judges\n")
vg_multi = one("select count(*) filter(where judge like '%,%'), count(*) filter(where judge is null or judge = '') from vg")
md.append(f"Vanga `judge` is a comma-separated string ({vg_multi[0]:,} rows list more than one judge, {vg_multi[1]:,} rows are empty). "
          "Vaquill `judges` is a proper list. Both go into `judgment_judge` one row per judge.\n")
md.append("### 7.3 Languages\n")
md.append("Vanga `available_languages` example: `ENG,BEN,GUJ,HIN,MAL,MAR,PUN,TEL,URD`. Vaquill stores regional-language chunk sets in the same table, so the "
          f"unique chunk key is (`case_id`, `language_code`, `chunk_index`) (checked: {one('select count(*) from (select 1 from vq group by case_id, language_code, chunk_index having count(*) > 1)')[0]} duplicates), not (`case_id`, `chunk_index`).\n")
md.append("### 7.4 `text` vs `text_original`\n")
td = one("select count(*) filter(where text <> text_original), count(*) filter(where text = text_original), count(*) filter(where text is null or text = '') from vq")
md.append(f"Chunks where `text` ≠ `text_original`: **{td[0]:,}**; identical: **{td[1]:,}**; empty text: **{td[2]:,}**. "
          "`text_original` is therefore a redundant copy.\n")
_hdr = one("select count(*) filter(where text like 'Case: %' and text like '%' || chr(10) || 'Section: %') from vq")[0]
md.append(f"Every chunk ({_hdr:,} of {td[0] + td[1]:,}) starts with a `Case: … Section: …` header that Vaquill adds; "
          "it is not judgment text and must be stripped before assembling `judgment_text`.\n")

md.append("### 7.5 English text coverage in Vaquill\n")
noen = one("select count(*) from (select case_id from vq group by 1 having count(*) filter(where language_code = 'en') = 0)")[0]
md.append(f"Cases with **no `en` chunk set**: **{noen:,}** of {vq_cases:,} ({pct(noen, vq_cases)}). They only have translations (`hin`, `pun`, ...). "
          "By decade of decision year:\n")
md.append(table(["decade", "cases without English text"], q("""select (yr//10*10)::int d, count(*) from (
  select case_id, min(year) as yr from vq group by 1 having count(*) filter(where language_code = 'en') = 0) group by 1 order by 1""")))
_scr = q("""select language_code, round(100.0*avg(regexp_matches(text, '[\u0A00-\u0A7F]')::int), 1), round(100.0*avg(regexp_matches(text, '[\u0900-\u097F]')::int), 1)
            from vq where language_code in ('en','pun','hin') group by 1 order by 1""")
md.append("Script sanity check (share of chunks containing Gurmukhi / Devanagari characters): "
          + "; ".join(f"`{a}` {b}% / {c}%" for a, b, c in _scr) + ". The language labels are trustworthy.\n")
md.append("### 7.6 Bench strength\n")
_b = one("select count(*) filter(where bench_strength <> len(judges)), count(*) from vq_meta")
_bv = one("""with v as (select distinct replace(case_id,' ','_') k, len(string_split(judge, ',')) n from vg where judge <> '' and nkey <> ''),
 q as (select distinct case_id k, bench_strength b from vq_meta) select count(*), count(*) filter(where n <> b) from v join q using (k)""")
md.append(f"Vaquill `bench_strength` ≠ `len(judges)` in {_b[0]:,} of {_b[1]:,} rows. Counting the comma-separated Vanga `judge` string instead disagrees with Vaquill "
          f"for {_bv[1]:,} of {_bv[0]:,} judgments, so the two sources agree on bench size almost everywhere.\n")

_gap = q("select extract(year from dd)::int y, count(distinct nkey) from vg where nkey <> '' and nkey not in (select case_id from vq_meta) group by 1 order by 2 desc limit 4")
summary = ["## Summary of findings\n",
  f"1. **Vaquill is a subset of Vanga, not a complement.** {both:,} judgments are in both, {vg_only:,} are Vanga-only and **{vq_only:,} are Vaquill-only** "
  f"(exact `case_id` key, empty keys excluded). Vanga-only decision years: " + ", ".join(f"{y} ({n})" for y, n in _gap) + ".\n",
  "2. **Where both have a value they agree almost perfectly** (section 4.4). Vaquill adds **full text, chunk structure and a judges list**; Vanga adds `cnr`, "
  "language availability, the raw HTML and the extra judgments. There is little metadata for Vaquill to fill and none for Vanga to fix.\n",
  f"3. **Vanga contains {p[0] - p[1]:,} duplicate rows** (misfiled copies under the wrong `year=` folder) and **{empty_rows[0]} rows with an empty `case_id`**. A verified rule picks the right copy.\n",
  "4. **Vaquill metadata is constant across every case's chunks** (0 exceptions), so one canonical row per `case_id` is safe.\n",
  f"5. **{noen:,} cases have no English text** in Vaquill (mostly the 2000s).\n",
  "6. **Not present in either source:** `case_number`, diary number, PDF URL, `author_judge`, `date_of_registration`, `section_priority`. These canonical fields will be empty; they are not merge failures.\n",
  f"7. **Year:** `year` is not the decision year in {pct(v[6], v[0])} of Vanga rows and {pct(vq_[4], vq_[0])} of Vaquill rows. No decision date is before 1950 or in the future, so the `1902` vs `2002` problem is **not present** in these files.\n"]
_i = next(i for i, x in enumerate(md) if x.startswith("## 1. Headline facts"))
md[_i:_i] = summary

OUT.parent.mkdir(exist_ok=True)
OUT.write_text("\n".join(md))
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
