#!/usr/bin/env python3
"""Stage 4: load the validated Stage 3 outputs (build/*.parquet) into PostgreSQL.

One transaction: migrations 0001..0006, then COPY of every table in foreign-key order, then sequences.
Any error rolls everything back, so the database is either empty or fully loaded. Re-running on a loaded
database refuses unless --rebuild is given (which drops the public schema first).
Raw files are never touched. Legislation is read from raw/vaquill/in_central_legislation.parquet.

Run:  .venv/bin/python -I pipeline/07_load_postgres.py [--rebuild]
"""
import datetime as dt
import io
import json
import pathlib
import sys
import time

import duckdb
import pyarrow.csv as pacsv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pgconn  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "build"
LEG = ROOT / "raw" / "vaquill" / "in_central_legislation.parquet"
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("*.sql"))
REBUILD = "--rebuild" in sys.argv
t_start = time.time()


def log(msg):
    print(f"[{time.time() - t_start:7.1f}s] {msg}", flush=True)


# Load order respects foreign keys. (table, parquet path or None, optional custom SELECT)
ORDER = [
    "source_vanga_raw", "source_vaquill_raw", "judgment", "judgment_source_map", "judgment_field_provenance",
    "field_conflicts", "match_review_queue", "judgment_judge", "judgment_identifier", "judgment_language",
    "judgment_text", "judgment_chunk", "downloads", "merge_report",
]

duck = duckdb.connect()
duck.execute("set threads=4")
duck.execute("set memory_limit='4GB'")


def pg_array(col):
    """DuckDB list column -> PostgreSQL array literal text."""
    return ("case when {c} is null then null else '{{' || array_to_string(list_transform({c}, x -> '\"' || replace(replace(x, '\\', '\\\\'), '\"', '\\\"') || '\"'), ',') || '}}' end"
            .format(c=f'"{col}"'))


NUL_FIX = {"judgment_chunk": ["text"], "judgment_text": ["text"]}  # columns where NUL (U+0000) is replaced by U+2400
REPL = "\u2400"


def select_for(src, fix=()):
    """SELECT from a parquet file with list columns rendered as array literals. Returns (sql, columns)."""
    cols = duck.execute(f"describe select * from read_parquet('{src}')").fetchall()
    exprs, names = [], []
    for name, typ, *_ in cols:
        names.append(name)
        if typ.endswith("[]"):
            exprs.append(f"{pg_array(name)} as \"{name}\"")
        elif name in fix:
            exprs.append(f"replace(\"{name}\", chr(0), '{REPL}') as \"{name}\"")
        else:
            exprs.append(f'"{name}"')
    return f"select {', '.join(exprs)} from read_parquet('{src}')", names


def copy_table(cur, table, select_sql, columns):
    t0 = time.time()
    reader = duck.execute(select_sql).fetch_record_batch(20000)
    opts = pacsv.WriteOptions(include_header=False, quoting_style="all_valid")
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(chr(34) + c + chr(34) for c in columns)}) FROM STDIN WITH (FORMAT csv)") as cp:
        for batch in reader:
            buf = io.BytesIO()
            pacsv.write_csv(batch, buf, write_options=opts)
            cp.write(buf.getvalue())
            n += batch.num_rows
    dt_ = time.time() - t0
    log(f"loaded {table}: {n:,} rows in {dt_:.1f}s ({n / max(dt_, 1e-9):,.0f} rows/s)")
    return n, dt_


def main():
    report = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "tables": {}}
    # ---- pre-checks on the data about to be loaded
    log("pre-checks")
    for t in ORDER:
        if not (B / f"{t}.parquet").exists():
            sys.exit(f"missing build/{t}.parquet; run pipeline/05_build_canonical.py first")
    for t in ORDER:  # NUL is only tolerated (and replaced) in the known text columns; anywhere else it aborts the load
        vcols = [r[0] for r in duck.execute(f"describe select * from read_parquet('{B}/{t}.parquet')").fetchall() if r[1] == "VARCHAR"]
        for c in vcols:
            if c in NUL_FIX.get(t, []):
                continue
            n_nul = duck.execute(f"select count(*) from read_parquet('{B}/{t}.parquet') where \"{c}\" like '%' || chr(0) || '%'").fetchone()[0]
            if n_nul:
                sys.exit(f"NUL characters in {t}.{c} ({n_nul} rows): not handled; stop and decide")
    for t, cs in NUL_FIX.items():
        for c in cs:  # the replacement symbol must be unused so that the substitution stays reversible
            if duck.execute(f"select count(*) from read_parquet('{B}/{t}.parquet') where \"{c}\" like '%{REPL}%'").fetchone()[0]:
                sys.exit(f"{REPL} already occurs in {t}.{c}; choose another replacement")
    parquet_counts = {t: duck.execute(f"select count(*) from read_parquet('{B}/{t}.parquet')").fetchone()[0] for t in ORDER}

    with pgconn.connect("admin", autocommit=False) as conn:
        cur = conn.cursor()
        existing = cur.execute("select count(*) from information_schema.tables where table_schema = 'public'").fetchone()[0]
        if existing and not REBUILD:
            sys.exit(f"database already has {existing} tables; use --rebuild to drop and reload")
        cur.execute("set local synchronous_commit = off")
        cur.execute("set local maintenance_work_mem = '2GB'")
        cur.execute("set local timezone = 'UTC'")
        t_ddl = time.time()
        if REBUILD:
            log("dropping schema public")
            cur.execute("drop schema public cascade")
            cur.execute("create schema public authorization eli_admin")
            cur.execute("grant usage on schema public to eli_readonly")
        for m in MIGRATIONS:
            cur.execute(m.read_text())
            log(f"applied {m.name}")
        report["migrations_seconds"] = round(time.time() - t_ddl, 2)

        t_load = time.time()
        for t in ORDER:
            sql_, cols = select_for(f"{B}/{t}.parquet", NUL_FIX.get(t, []))
            n, secs = copy_table(cur, t, sql_, cols)
            report["tables"][t] = {"rows_parquet": parquet_counts[t], "rows_loaded": n, "seconds": round(secs, 2)}

        # ---- log of every text value that was changed because PostgreSQL cannot store NUL
        log_rows = f"""
            select 'judgment_chunk' as table_name, vaquill_chunk_id as row_key, 'text' as column_name,
                   (length(text) - length(replace(text, chr(0), '')))::integer as nul_count, '{REPL}' as replacement,
                   'NUL replaced one-for-one in the database copy; raw parquet unchanged' as note
            from read_parquet('{B}/judgment_chunk.parquet') where text like '%' || chr(0) || '%'
            union all
            select 'judgment_text', judgment_id || '/' || language_code, 'text', (length(text) - length(replace(text, chr(0), '')))::integer, '{REPL}',
                   'NUL replaced one-for-one in the database copy; raw parquet unchanged'
            from read_parquet('{B}/judgment_text.parquet') where text like '%' || chr(0) || '%'
            order by 1, 2"""
        n, secs = copy_table(cur, "text_sanitization_log", log_rows, ["table_name", "row_key", "column_name", "nul_count", "replacement", "note"])
        report["tables"]["text_sanitization_log"] = {"rows_parquet": n, "rows_loaded": n, "seconds": round(secs, 2)}

        # ---- legislation (small), with a constancy check so act-level columns are lossless
        log("legislation")
        act_cols = ["title", "year", "jurisdiction", "state", "instrument_type", "doc_type", "act_status", "in_force", "source_url", "mirror_url",
                    "source_publisher", "language_code"]
        for c in act_cols:
            bad = duck.execute(f"select count(*) from (select act_id from read_parquet('{LEG}') group by 1 having count(distinct {c}) > 1)").fetchone()[0]
            if bad:
                raise SystemExit(f"legislation column {c} is not constant per act ({bad} acts); act-level storage would lose data")
        act_sql = (f"select act_id, any_value(title) as title, any_value(try_cast(year as smallint)) as year, any_value(jurisdiction) as jurisdiction, "
                   f"any_value(state) as state, any_value(instrument_type) as instrument_type, any_value(doc_type) as doc_type, "
                   f"any_value(act_status) as act_status, any_value(in_force) as in_force, any_value(source_url) as source_url, "
                   f"any_value(mirror_url) as mirror_url, any_value(source_publisher) as source_publisher, any_value(language_code) as language_code "
                   f"from read_parquet('{LEG}') group by act_id order by act_id")
        duck.execute(f"create temp table leg_act as {act_sql}")
        a_sql, a_cols = ("select * from leg_act", [r[0] for r in duck.execute("describe leg_act").fetchall()])
        n, secs = copy_table(cur, "legislation_act", a_sql, a_cols)
        report["tables"]["legislation_act"] = {"rows_parquet": n, "rows_loaded": n, "seconds": round(secs, 2)}
        sec_cols = ["chunk_id", "act_id", "chapter", "section_number", "section_title", "text", "section_type", "provision_type", "legal_subject",
                    "has_proviso", "has_non_obstante", "delegation_type", "department", "regulatory_body", "acts_referenced", "defined_terms",
                    "amendment_count", "source_url"]
        types = {r[0]: r[1] for r in duck.execute(f"describe select * from read_parquet('{LEG}')").fetchall()}
        exprs = [f"{pg_array(c)} as \"{c}\"" if types[c].endswith("[]") else f'"{c}"' for c in sec_cols]
        n_leg = duck.execute(f"select count(*) from read_parquet('{LEG}')").fetchone()[0]
        n, secs = copy_table(cur, "legislation_section", f"select {', '.join(exprs)} from read_parquet('{LEG}') order by chunk_id", sec_cols)
        report["tables"]["legislation_section"] = {"rows_parquet": n_leg, "rows_loaded": n, "seconds": round(secs, 2)}

        # ---- sequences for tables loaded with explicit ids, grants for the read-only role, run log
        for tbl, col in (("field_conflicts", "conflict_id"), ("match_review_queue", "review_id")):
            cur.execute(f"select setval(pg_get_serial_sequence('{tbl}', '{col}'), coalesce(max({col}), 1), max({col}) is not null) from {tbl}")
        cur.execute("grant select on all tables in schema public to eli_readonly")
        cur.execute("alter default privileges for role eli_admin in schema public grant select on tables to eli_readonly")
        for line in (B / "pipeline_runs.jsonl").read_text().splitlines():
            r = json.loads(line)
            cur.execute("insert into pipeline_runs (stage, started_at, finished_at, status, row_counts) values (%s,%s,%s,%s,%s)",
                        (r["stage"], r["started_at"], r["finished_at"], r["status"], json.dumps(r["row_counts"])))
        report["load_seconds"] = round(time.time() - t_load, 2)
        report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        cur.execute("insert into pipeline_runs (stage, started_at, finished_at, status, row_counts) values (%s,%s,%s,%s,%s)",
                    ("07_load_postgres", report["started_at"], report["finished_at"], "succeeded",
                     json.dumps({t: v["rows_loaded"] for t, v in report["tables"].items()})))
        log("committing")
        t_c = time.time()
        conn.commit()
        report["commit_seconds"] = round(time.time() - t_c, 2)
        log(f"committed in {report['commit_seconds']}s")

    # ---- statistics (outside the transaction)
    with pgconn.connect("admin", autocommit=True) as conn:
        t0 = time.time()
        conn.execute("analyze")
        report["analyze_seconds"] = round(time.time() - t0, 2)
        log(f"analyze done in {report['analyze_seconds']}s")
    report["total_seconds"] = round(time.time() - t_start, 2)
    (B / "load_report.json").write_text(json.dumps(report, indent=1))
    log(f"done: {sum(v['rows_loaded'] for v in report['tables'].values()):,} rows in {report['total_seconds']}s")


if __name__ == "__main__":
    main()
