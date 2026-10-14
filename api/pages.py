"""Secondary pages: explorer, coverage, review, SQL console, judges, benches, analytics, benchmark, inventory, status, admin."""
import csv
import io
import re
import time

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from psycopg.types.json import Jsonb

from . import auth, db
from .common import render

router = APIRouter()
SECRET_TABLES = {"app_user", "app_session", "api_key"}


# ---- data explorer: reads the catalog, so new tables and columns appear automatically ---------------------------------
def _relations():
    return db.q("""select c.relname as name, case c.relkind when 'r' then 'table' when 'v' then 'view' when 'm' then 'materialized view' end as kind,
                          c.reltuples::bigint as est_rows, pg_size_pretty(pg_total_relation_size(c.oid)) as size,
                          (select count(*) from pg_attribute a where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped) as columns
                   from pg_class c join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'public' and c.relkind in ('r', 'v', 'm') and has_table_privilege(c.oid, 'select') order by c.relname""")


def _columns(table):
    cols = db.q("""select a.attname as name, format_type(a.atttypid, a.atttypmod) as type from pg_attribute a join pg_class c on c.oid = a.attrelid
                   join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relname = %s and a.attnum > 0 and not a.attisdropped order by a.attnum""", (table,))
    if not cols or table in SECRET_TABLES:
        raise HTTPException(404, f"No readable table or view called “{table}”.")
    return cols


def _explore_query(table, cols, p):
    names = [c["name"] for c in cols]
    sel = ", ".join(f'"{n}"' if "tsvector" not in c["type"] else f'left("{n}"::text, 120) as "{n}"' for n, c in zip(names, cols))
    where, args = [], []
    for n in names:
        v = (p.get(f"f_{n}") or "").strip()
        if v:
            where.append(f'"{n}"::text ilike %s')
            args.append(f"%{v}%")
    sql = f'select {sel} from "{table}"' + ((" where " + " and ".join(where)) if where else "")
    sort = p.get("sort")
    if sort in names:
        sql += f' order by "{sort}" {"desc" if p.get("dir") == "desc" else "asc"} nulls last'
    return sql, args, where


@router.get("/explorer")
def explorer(request: Request):
    return render(request, "explorer.html", rels=_relations(), secret=sorted(SECRET_TABLES))


@router.get("/explorer/{table}")
def explorer_table(request: Request, table: str, page: int = 1, full: int = 0):
    cols = _columns(table)
    p = dict(request.query_params)
    sql, args, where = _explore_query(table, cols, p)
    size = 50
    rows = db.q(sql + f" limit {size} offset {(max(page, 1) - 1) * size}", args)
    est = db.q1("select c.reltuples::bigint n from pg_class c where c.relname = %s and c.relnamespace = 'public'::regnamespace", (table,))["n"]
    total = db.q1(f'select count(*) n from "{table}"' + ((" where " + " and ".join(where)) if where else ""), args)["n"] if (where or est < 3_000_000) else est
    return render(request, "explorer_table.html", table=table, cols=cols, rows=rows, page=page, total=total, size=size, p=p, full=full, exact=bool(where or est < 3_000_000))


@router.get("/explorer/{table}.csv")
def explorer_csv(request: Request, table: str):
    cols = _columns(table)
    p = dict(request.query_params)
    sql, args, _ = _explore_query(table, cols, p)
    rows = db.q(sql + " limit 100000", args)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([c["name"] for c in cols])
    for r in rows:
        w.writerow([r[c["name"]] for c in cols])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={table}.csv"})


# ---- coverage ----------------------------------------------------------------------------------------------------------
@router.get("/coverage")
def coverage(request: Request):
    by_year = db.q("select decision_year as year, match_status, count(*)::int n from judgment_visible group by 1, 2 order by 1")
    years = {}
    for r in by_year:
        years.setdefault(r["year"], {"year": r["year"], "matched": 0, "vanga_only": 0, "in_review": 0})[r["match_status"]] = r["n"]
    cols = [r["name"] for r in db.q("select a.attname as name from pg_attribute a where a.attrelid = 'judgment'::regclass and a.attnum > 0 and not a.attisdropped order by attnum") if r["name"] != "search_tsv"]
    nulls = db.q1("select count(*)::int total, " + ", ".join(f'count(*) filter (where "{c}" is null)::int as "{c}"' for c in cols) + " from judgment_visible")
    null_rows = [{"field": c, "nulls": nulls[c], "pct": round(100 * nulls[c] / nulls["total"], 1)} for c in cols]
    return render(request, "coverage.html", years=list(years.values()),
                  year_bars=[{"label": f"{y['year']} · both {y['matched']} / Vanga only {y['vanga_only']}", "n": y["matched"] + y["vanga_only"] + y["in_review"]} for y in years.values()], null_rows=null_rows, total=nulls["total"],
                  conflicts=db.q("select field_name, status, count(*)::int n from field_conflicts group by 1, 2 order by 3 desc"),
                  queue=db.q("select kind, status, count(*)::int n from match_review_queue group by 1, 2"),
                  text=db.q("select text_status, count(*)::int n from judgment_visible group by 1 order by 2 desc"),
                  quality=db.q("select (language_code = 'en') as english, label, count(*)::int n from judgment_text_quality group by 1, 2 order by 1 desc, 2"),
                  pdf=db.q1("select count(*)::int n from judgment_pdf")["n"])


# ---- review queues -----------------------------------------------------------------------------------------------------
@router.get("/review")
def review(request: Request):
    return render(request, "review.html",
                  matches=db.q("select * from match_review_queue order by status, review_id limit 200"),
                  conflicts=db.q("""select c.*, j.title from field_conflicts c join judgment j using (judgment_id) order by c.status, c.conflict_id limit 200"""),
                  reports=db.q("""select r.*, j.title from error_report r join judgment j using (judgment_id) order by (r.status = 'open') desc, r.report_id desc limit 200"""),
                  decisions=db.q("select * from review_decision order by decision_id desc limit 30"))


@router.post("/review/decide")
def review_decide(request: Request, queue: str = Form(...), item_key: str = Form(...), decision: str = Form(...), note: str = Form("")):
    u = auth.require(request, "admin")
    if queue not in ("match_review_queue", "field_conflicts", "error_report"):
        raise HTTPException(400, "unknown queue")
    with db.app() as c:
        before = c.execute(f"select to_jsonb(t) j from {queue} t where {'review_id' if queue == 'match_review_queue' else 'conflict_id' if queue == 'field_conflicts' else 'report_id'} = %s", (int(item_key),)).fetchone()
        if queue == "error_report":
            c.execute("update error_report set status = %s, decided_by = %s, decided_at = now() where report_id = %s", ("accepted" if decision == "accept" else "rejected", u["username"], int(item_key)))
        elif queue == "match_review_queue":
            c.execute("update match_review_queue set status = %s, decided_by = %s, decided_at = now(), decision_note = %s where review_id = %s", (decision, u["username"], note, int(item_key)))
        else:
            c.execute("update field_conflicts set status = %s where conflict_id = %s", (decision, int(item_key)))
        c.execute("insert into review_decision (queue, item_key, decision, decided_by, before_value, note) values (%s,%s,%s,%s,%s,%s)",
                  (queue, item_key, decision, u["username"], Jsonb(before["j"]) if before else None, note or None))
    return RedirectResponse("/review", status_code=303)


# ---- read-only SQL console ---------------------------------------------------------------------------------------------
WRITE_WORDS = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|call|do|set|reset|refresh|comment|lock|listen|notify)\b", re.I)


@router.get("/sql")
def sql_form(request: Request):
    return render(request, "sql.html", sql="select decision_year, count(*) from judgment group by 1 order by 1", result=None, error=None)


@router.post("/sql")
def sql_run(request: Request, sql: str = Form(...)):
    auth.require(request)
    s = sql.strip().rstrip(";")
    error, result, ms = None, None, None
    if ";" in s:
        error = "Only one statement is allowed."
    elif not re.match(r"^(select|with|explain)\b", s, re.I):
        error = "Only SELECT, WITH or EXPLAIN statements are allowed. This console is read-only."
    elif WRITE_WORDS.search(re.sub(r"'[^']*'", "''", s)):
        error = "The statement contains a keyword that changes data or settings; refused. (The database role is read-only as well.)"
    else:
        t = time.time()
        try:
            with db.ro() as c:
                c.execute("set local statement_timeout = '10s'")
                cur = c.execute(s)
                rows = cur.fetchmany(1001)
                names = [d.name for d in cur.description] if cur.description else []
                result = {"names": names, "rows": rows[:1000], "capped": len(rows) > 1000}
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
        ms = int((time.time() - t) * 1000)
    return render(request, "sql.html", sql=sql, result=result, error=error, ms=ms)


# ---- judges --------------------------------------------------------------------------------------------------------------
@router.get("/judges")
def judges(request: Request, q: str = ""):
    rows = db.q("""select j.judge_id, j.canonical_name, f.n, (select min(decision_year) from judgment_judge g join judgment_visible v using (judgment_id) where g.judge_id = j.judge_id) first_year,
                          (select max(decision_year) from judgment_judge g join judgment_visible v using (judgment_id) where g.judge_id = j.judge_id) last_year
                   from judge j join facet_judge f using (judge_id) where (%s = '' or exists (select 1 from judge_alias a where a.judge_id = j.judge_id and a.alias_name ilike %s))
                   order by f.n desc""", (q, f"%{q}%"))
    return render(request, "judges.html", rows=rows, q=q)


@router.get("/judge/{judge_id}")
def judge_page(request: Request, judge_id: int, page: int = 1):
    jd = db.q1("select * from judge where judge_id = %s", (judge_id,))
    if not jd:
        raise HTTPException(404, "No such judge.")
    size = 25
    return render(request, "judge.html", jd=jd, page=page, size=size,
                  aliases=[r["alias_name"] for r in db.q("select alias_name from judge_alias where judge_id = %s", (judge_id,))],
                  total=db.q1("select count(distinct judgment_id) n from judgment_judge g join judgment_visible using (judgment_id) where g.judge_id = %s", (judge_id,))["n"],
                  rows=db.q("""select j.judgment_id, j.title, j.decision_date, j.bench_strength, j.disposal from judgment_judge g join judgment_visible j using (judgment_id)
                               where g.judge_id = %s order by j.decision_date desc limit %s offset %s""", (judge_id, size, (page - 1) * size)),
                  years=db.q("""select decision_year as label, count(*)::int n from judgment_judge g join judgment_visible j using (judgment_id) where g.judge_id = %s group by 1 order by 1""", (judge_id,)),
                  outcomes=db.q("""select coalesce(disposal, '(none)') as label, count(*)::int n from judgment_judge g join judgment_visible j using (judgment_id) where g.judge_id = %s group by 1 order by 2 desc""", (judge_id,)),
                  companions=db.q("""select o.judge_id, d.canonical_name as label, count(*)::int n from judgment_judge g join judgment_judge o on o.judgment_id = g.judgment_id and o.judge_id <> g.judge_id
                                     join judge d on d.judge_id = o.judge_id join judgment_visible v on v.judgment_id = g.judgment_id where g.judge_id = %s group by 1, 2 order by 3 desc limit 12""", (judge_id,)),
                  authored=db.q1("select count(*) filter (where is_author) n from judgment_judge where judge_id = %s", (judge_id,))["n"])


# ---- Constitution Benches ------------------------------------------------------------------------------------------------
@router.get("/benches")
def benches(request: Request, min_size: int = 5, year_from: int = 0, year_to: int = 3000, page: int = 1, basis: str = "effective"):
    """basis: effective (larger of source list and text-header estimate), listed (source judges list only)."""
    size = 50
    col = "b.bench_listed" if basis == "listed" else "b.bench_effective"
    frm = "judgment_bench b join judgment_visible j using (judgment_id)"
    where = f"{col} >= %s and j.decision_year between %s and %s"
    args = (min_size, year_from, year_to)
    total = db.q1(f"select count(*) n from {frm} where {where}", args)["n"]
    rows = db.q(f"select j.judgment_id, j.title, j.decision_date, b.bench_listed, b.bench_header, b.bench_effective, b.bench_basis, j.disposal, j.citation from {frm} where {where} order by j.decision_date, j.title limit %s offset %s", args + (size, (page - 1) * size))
    by_year = db.q(f"select j.decision_year::text as label, count(*)::int n from {frm} where {where} group by 1 order by 1", args)
    stats = db.q1("""select count(*)::int total, count(bench_listed)::int with_listed, count(*) filter (where bench_listed is null)::int null_listed,
                            count(*) filter (where bench_listed = 1)::int one_judge, count(bench_header)::int with_header,
                            count(*) filter (where bench_effective is null)::int not_derivable from judgment_bench""")
    return render(request, "benches.html", rows=rows, total=total, by_year=by_year, min_size=min_size, year_from=year_from, year_to=year_to, page=page, size=size, stats=stats, basis=basis)


@router.get("/analytics/time-to-decision")
def time_to_decision(request: Request):
    return render(request, "unavailable.html", title="Time to decision",
                  reason="date_of_registration is not in the Supreme Court data. The check: it is absent from Vanga and 100% empty in Vaquill (see docs/SCHEMA_COMPARISON.md and DECISIONS.md D4). "
                         "Registration-to-decision times need the registration date; none can be computed without inventing it.",
                  have=db.q1("select count(date_of_registration)::int n from judgment")["n"])


# ---- benchmark (stored query lists and results; the scorecard itself is Stage 8) ----------------------------------------
@router.get("/benchmark")
def benchmark(request: Request):
    return render(request, "benchmark.html", queries=db.q("select * from benchmark_query order by kind, query_id"),
                  results=db.q("select r.*, q.text from benchmark_result r join benchmark_query q using (query_id) order by result_id desc limit 100"))


@router.post("/benchmark/query")
def benchmark_add(request: Request, kind: str = Form(...), text: str = Form(...)):
    auth.require(request, "admin")
    with db.app() as c:
        c.execute("insert into benchmark_query (kind, text) values (%s,%s)", (kind, text))
    return RedirectResponse("/benchmark", status_code=303)


@router.post("/benchmark/result")
def benchmark_result(request: Request, query_id: int = Form(...), system: str = Form("eli"), seconds: float = Form(0), rating: int = Form(0), outcome: str = Form("")):
    u = auth.require(request)
    with db.app() as c:
        c.execute("insert into benchmark_result (query_id, tester, system, seconds, rating, outcome) values (%s,%s,%s,%s,%s,%s::jsonb)",
                  (query_id, u["username"], system, seconds or None, rating or None, '{"note": ' + __import__("json").dumps(outcome) + "}"))
    return RedirectResponse("/benchmark", status_code=303)


# ---- feature inventory and status ----------------------------------------------------------------------------------------
FEATURES = [
    ("Stage 1-4", "Downloads, checksums, canonical merge, Postgres load, measured indexes", "built", "/status"),
    ("Search", "Full text (English), field-scoped, typo-tolerant title, filters, facets, sorting, snippets", "built", "/search"),
    ("Judgment page", "Overview, full text, chunks, raw Vanga, raw Vaquill, identifiers, judges, provenance", "built", "/search"),
    ("Data explorer", "Every table, view and column from the catalog, sort, filter, CSV", "built", "/explorer"),
    ("Coverage dashboard", "Per year per source, null rates, conflicts, queues, text status, quality", "built", "/coverage"),
    ("Review queues", "Match queue, field conflicts, user error reports with audit trail", "built", "/review"),
    ("SQL console", "SELECT only, 10 s timeout, 1000 rows", "built", "/sql"),
    ("Benchmark page", "Stored queries and results; scorecard run is Stage 8", "partial", "/benchmark"),
    ("Constitution Bench finder", "Bench size = larger of source judges list and an estimate read from the text header (labelled); 12% of judgments have neither", "built", "/benches"),
    ("Judge pages", "Alias-aware index, judgments, years, companions, outcomes. Author of judgment: not in source data", "partial", "/judges"),
    ("Facet filters with counts", "Year, disposition, bench size, judge. Case type: not in source data", "partial", "/search"),
    ("Time-to-decision analytics", "unavailable: date_of_registration not in source data", "unavailable", "/analytics/time-to-decision"),
    ("Permalinks and citation copy", "By id and INSC id; INSC and SCR strings copy as stored; no SCC/AIR invented", "built", "/search"),
    ("Report an error", "Per field on the judgment page, into error_report and the review queue", "built", "/review"),
    ("Data-quality badge", "clean / fair / noisy on results and judgment page, with filter", "built", "/search"),
    ("Export", "CSV of results; txt, docx, pdf of one judgment or a bundle", "built", "/search"),
    ("REST API and API keys", "/api/v1, key auth, rate limit, usage log", "built", "/admin"),
    ("MCP server", "mcp/server.py, same read-only operations", "built", "/admin"),
    ("Attribution, banner, hide-judgment, nightly dump", "Stage 7 parts that need no public server", "built", "/status"),
    ("HTTPS, S3 backups, public takedown form", "Deferred: the app is localhost-only", "not built", ""),
    ("Language-neutral full-text index", "Only English has a full-text index; non-English shows 'no English text'", "not built", ""),
    ("Paragraphs, citations made / cited by, statutes", "Later-phase tables exist and are empty; shown as not built", "not built", ""),
    ("Good-law labels, citation graph, High Courts", "Out of scope by instruction", "not built", ""),
    ("AI case brief, ask-this-judgment, more-like-this, compare, saved searches, alerts", "Stage 9", "not built", ""),
    ("Original PDFs", "Stage 10, needs your approval; targeted PDFs for metadata-only judgments planned after Stage 6", "not built", ""),
]


@router.get("/inventory")
def inventory(request: Request):
    rels = _relations()
    return render(request, "inventory.html", features=FEATURES, rels=rels,
                  exts=db.q("select extname, extversion from pg_extension order by 1"),
                  idx=db.q("select tablename, indexname, pg_size_pretty(pg_relation_size(format('%I.%I', schemaname, indexname)::regclass)) size from pg_indexes where schemaname = 'public' and indexname not like '%%pkey' order by 1, 2"),
                  runs=db.q("select distinct stage from pipeline_runs order by 1"))


@router.get("/status")
def status(request: Request):
    import os
    import pathlib
    bdir = pathlib.Path(os.environ.get("ELI_BACKUP_DIR", "/var/backups/eli"))
    dumps = sorted(bdir.glob("*.dump"), key=lambda p: p.stat().st_mtime) if bdir.exists() else []
    return render(request, "status.html", runs=db.q("select * from pipeline_runs order by run_id desc limit 30"),
                  size=db.q1("select pg_size_pretty(pg_database_size(current_database())) s")["s"],
                  counts=db.q("select relname as name, reltuples::bigint as n from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r' order by 2 desc"),
                  idx=db.q("select indexname, pg_size_pretty(pg_relation_size(format('%I.%I', schemaname, indexname)::regclass)) size from pg_indexes where schemaname = 'public' order by pg_relation_size(format('%I.%I', schemaname, indexname)::regclass) desc limit 12"),
                  backup=(time.strftime("%Y-%m-%d %H:%M", time.localtime(dumps[-1].stat().st_mtime)), dumps[-1].name, round(dumps[-1].stat().st_size / 1e6)) if dumps else None,
                  spend=0.0, cap=25.0, host=os.uname().nodename)


# ---- admin: hide judgments, API keys, users -------------------------------------------------------------------------------
@router.get("/admin")
def admin(request: Request):
    u = auth.user_from_request(request)
    if not u or u["role"] != "admin":
        raise HTTPException(403, "Admin only.")
    return render(request, "admin.html", hidden=db.q("select h.*, j.title from judgment_hidden h join judgment j using (judgment_id) order by hidden_at desc"),
                  keys=db.q("select key_id, label, rate_limit_per_min, created_at, revoked_at from api_key order by key_id", kind="app"),
                  users=db.q("select user_id, username, role, last_login_at, disabled from app_user order by user_id", kind="app"),
                  usage=db.q("select endpoint, count(*)::int n, round(avg(ms))::int ms from api_usage group by 1 order by 2 desc", kind="app"),
                  takedowns=db.q("select * from takedown_request order by request_id desc limit 20"), new_key=request.query_params.get("new_key"))


@router.post("/admin/hide")
def admin_hide(request: Request, judgment_id: str = Form(...), reason: str = Form(...), action: str = Form("hide")):
    u = auth.require(request, "admin")
    with db.app() as c:
        if action == "hide":
            c.execute("insert into judgment_hidden (judgment_id, hidden_by, reason) values (%s::uuid,%s,%s) on conflict do nothing", (judgment_id.strip(), u["username"], reason))
        else:
            c.execute("delete from judgment_hidden where judgment_id = %s::uuid", (judgment_id.strip(),))
        c.execute("insert into review_audit (actor, target_table, target_key, action, after_value) values (%s,'judgment',%s,%s,jsonb_build_object('reason', %s::text))",
                  (u["username"], judgment_id.strip(), action, reason))
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/key")
def admin_key(request: Request, label: str = Form(...), revoke: int = Form(0)):
    u = auth.require(request, "admin")
    if revoke:
        with db.app() as c:
            c.execute("update api_key set revoked_at = now() where key_id = %s", (revoke,))
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/admin?new_key=" + auth.create_api_key(label, u["user_id"]), status_code=303)
