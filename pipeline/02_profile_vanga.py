"""Stage 1 verify + Stage 2 profile for Vanga.

Reads the raw parquet with DuckDB and writes:
  docs/manifests/vanga_downloads.csv   provenance of every downloaded object (sha256)
  docs/profile/vanga_columns.csv       per-column profile
  docs/profile/vanga_per_year.csv      files, bytes and rows per year partition
  docs/profile/vanga_checks.json       known-issue checks, quantified
Re-runnable: it only reads raw/ and overwrites its own outputs.
"""
import csv
import hashlib
import json
import os
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "vanga" / "metadata"
OUT = ROOT / "docs"
BUCKET = "s3://indian-supreme-court-judgments/metadata"

# Fields Vanga only exposes inside raw_html (the parsed parquet columns omit them).
HTML_FIELDS = {
    "html_case_no": r"Case No :</span><font color='green'>\s*([^<]*)",
    "html_bench": r"Bench :</span><font color='green'>\s*([^<]*)",
    "html_decision_date": r"Decision Date :</span><font color='green'>\s*([^<]*)",
    "html_disposal": r"Disposal Nature :</span><font color='green'>\s*([^<]*)",
    "html_coram": r"Coram :\s*(.*?)</strong>",
    "html_headnote": r"</strong><br>(.*?)<br><strong class='caseDetailsTD'",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_manifest():
    rows = []
    for p in sorted(RAW.glob("*/year=*/*")):
        if p.parent.parent.name == "json":
            continue  # json/ is unpacked from the tars; the tar sha covers it
        rel = p.relative_to(RAW)
        rows.append({
            "source": "vanga",
            "remote_path": f"{BUCKET}/{rel.as_posix()}",
            "local_path": p.relative_to(ROOT).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(p.stat().st_mtime)),
        })
    (OUT / "manifests").mkdir(parents=True, exist_ok=True)
    with open(OUT / "manifests" / "vanga_downloads.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main():
    n_manifest = write_manifest()
    c = duckdb.connect()
    c.sql(f"""create view v as select * from read_parquet('{RAW}/parquet/year=*/metadata.parquet',
              hive_partitioning=true, union_by_name=true)""")
    extra = ", ".join(f"nullif(trim(regexp_extract(raw_html, $${rx}$$, 1)), '') as {k}"
                      for k, rx in HTML_FIELDS.items())
    c.sql(f"create table t as select *, {extra}, try_strptime(decision_date, '%d-%m-%Y')::date as parsed_date from v")

    total = c.sql("select count(*) from t").fetchone()[0]
    cols = [r[0] for r in c.sql("describe t").fetchall()]
    types = dict(c.sql("select column_name, column_type from (describe t)").fetchall())
    prof = []
    for col in cols:
        nulls, empties, distinct = c.sql(
            f'select count(*) filter (where "{col}" is null), count(*) filter (where trim("{col}"::varchar) = \'\'), '
            f'count(distinct "{col}") from t').fetchone()
        samples = [r[0] for r in c.sql(
            f'select distinct left("{col}"::varchar, 80) from t where nullif(trim("{col}"::varchar), \'\') is not null '
            f'order by hash("{col}"::varchar) limit 3').fetchall()]
        prof.append({"column": col, "type": types[col], "origin": "raw_html" if col.startswith("html_") else
                     ("derived" if col == "parsed_date" else ("hive partition" if col == "year" else "parquet")),
                     "null_pct": round(100 * nulls / total, 2), "empty_pct": round(100 * empties / total, 2),
                     "distinct": distinct, "samples": " | ".join(s.replace("\n", " ") for s in samples)})
    (OUT / "profile").mkdir(parents=True, exist_ok=True)
    with open(OUT / "profile" / "vanga_columns.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(prof[0]))
        w.writeheader()
        w.writerows(prof)

    per_year = c.sql("select year, count(*) n_rows, count(distinct path) distinct_paths from t group by 1 order by 1").fetchall()
    with open(OUT / "profile" / "vanga_per_year.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "rows", "distinct_paths", "json_files", "json_bytes", "parquet_bytes", "tar_bytes"])
        for y, rows, dp in per_year:
            jd = RAW / "json" / f"year={y}"
            jf = [p for p in jd.glob("*.json")]
            w.writerow([y, rows, dp, len(jf), sum(p.stat().st_size for p in jf),
                        (RAW / "parquet" / f"year={y}" / "metadata.parquet").stat().st_size,
                        (RAW / "tar" / f"year={y}" / "metadata.tar").stat().st_size])

    one = lambda s: c.sql(s).fetchone()
    json_paths = {p.stem for p in (RAW / "json").glob("year=*/*.json")}
    pq_paths = {r[0] for r in c.sql("select distinct path from t").fetchall()}
    checks = {
        "rows": total,
        "distinct_path": len(pq_paths),
        "json_files": sum(1 for _ in (RAW / "json").glob("year=*/*.json")),
        "json_distinct_names": len(json_paths),
        "paths_only_in_parquet": len(pq_paths - json_paths),
        "paths_only_in_json": len(json_paths - pq_paths),
        "duplicate_rows_same_path": total - len(pq_paths),
        "duplicate_path_pattern": [dict(zip(["copies", "years", "decision_dates", "content_variants", "paths"], r)) for r in c.sql("""
            with d as (select path, count(*) n, count(distinct year) ys, count(distinct decision_date) dds,
                count(distinct md5(concat_ws('|', title, judge, citation, cnr, decision_date, disposal_nature))) v
              from t group by path having n > 1)
            select n, ys, dds, v, count(*) from d group by all order by 5 desc""").fetchall()],
        "duplicates_where_one_copy_is_decision_year": one("""
            select count(*) from (select path from t group by path having count(*) > 1
              and bool_or(year = year(parsed_date)) and bool_or(year <> year(parsed_date)))""")[0],
        "unparseable_decision_date": one("select count(*) from t where parsed_date is null")[0],
        "html_date_differs_from_column": one("select count(*) from t where html_decision_date <> decision_date")[0],
        "year_partition_ne_decision_year_rows": one("select count(*) from t where year <> year(parsed_date)")[0],
        "year_partition_ne_decision_year_distinct_paths": one(
            "select count(*) from (select path from t group by path having not bool_or(year = year(parsed_date)))")[0],
        "year_off_by_more_than_1_rows": one("select count(*) from t where abs(year - year(parsed_date)) > 1")[0],
        "decision_date_range": [str(x) for x in one("select min(parsed_date), max(parsed_date) from t")],
        "suspicious_dates_before_1950_or_future": one(
            "select count(distinct path) from t where parsed_date < date '1950-01-26' or parsed_date > current_date")[0],
        "same_nc_multiple_paths": one("""select count(*) from (select nc_display from t where nullif(nc_display,'') is not null
            group by 1 having count(distinct path) > 1)""")[0],
        "same_nc_multiple_decision_dates": one("""select count(*) from (select nc_display from t where nullif(nc_display,'') is not null
            group by 1 having count(distinct decision_date) > 1)""")[0],
        "same_case_no_multiple_decision_dates": one("""select count(*) from (select html_case_no from t where html_case_no is not null
            group by 1 having count(distinct decision_date) > 1)""")[0],
        "same_title_and_date_multiple_paths": one("""select count(*) from (select lower(title), decision_date from t
            group by all having count(distinct path) > 1)""")[0],
        "case_id_equals_nc_display": one("select count(*) from t where replace(case_id,' ','') = nc_display")[0],
        "path_prefix_S_supplementary": one("select count(distinct path) from t where path like 'S\\_%' escape '\\'")[0],
        "path_like_judis": one("select count(*) from t where raw_html ilike '%judis%' or path ilike '%judis%'")[0],
        "path_like_jonew": one("select count(*) from t where raw_html ilike '%jonew%'")[0],
        "author_marked_in_html": one("""select count(distinct path) from t where raw_html like '%data-tooltip="Author"%'""")[0],
        "author_judge_column_nonnull": one("select count(*) from t where author_judge is not null")[0],
        "citation_has_scr": one("select count(distinct path) from t where citation ilike '%S.C.R.%'")[0],
        "citation_has_scc_or_air": one("select count(distinct path) from t where citation ilike '%SCC%' or citation ilike '%AIR%'")[0],
        "bench_strength_distribution": dict(c.sql("""select html_bench, count(distinct path) from t group by 1 order by 2 desc limit 12""").fetchall()),
        "disposal_top": dict(c.sql("""select disposal_nature, count(distinct path) from t group by 1 order by 2 desc limit 15""").fetchall()),
        "languages_top": dict(c.sql("""select available_languages, count(distinct path) from t group by 1 order by 2 desc limit 8""").fetchall()),
        "manifest_objects": n_manifest,
    }
    with open(OUT / "profile" / "vanga_checks.json", "w") as f:
        json.dump(checks, f, indent=2, default=str)
    print(json.dumps(checks, indent=2, default=str))


if __name__ == "__main__":
    main()
