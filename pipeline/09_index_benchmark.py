#!/usr/bin/env python3
"""Stage 4 indexes, chosen by measurement instead of guesswork.

Phase 0  baseline: run the representative workload with only the constraint-backed indexes (PK / unique).
Phase 1  one candidate index at a time: build it (timed, sized), re-run the queries it could help, decide.
         KEEP if an affected query gets >= 3x faster AND >= 5 ms faster at p50, or if it fixes a missed target.
         Otherwise DROP it, and the numbers stay in the report.
Phase 2  re-run everything on the final set, write db/migrations/0007_indexes.sql with the kept DDL,
         time REINDEX of the constraint indexes, and write build/index_report.json.

Modes:  (default) full experiment   |   --apply  apply the saved 0007_indexes.sql to a freshly loaded database (timed)
Run:    .venv/bin/python -I pipeline/09_index_benchmark.py [--apply]
"""
import json
import pathlib
import random
import re
import statistics
import sys
import time

import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pgconn  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "build"
MIG = ROOT / "db" / "migrations" / "0007_indexes.sql"
T0 = time.time()
N_PARAMS = 30


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", flush=True)


conn = pgconn.connect("admin", autocommit=True)
conn.execute("set jit = off")


def q(sql, params=None):
    return conn.execute(sql, params).fetchall()


def save_partial(report):
    (B / "index_report.partial.json").write_text(json.dumps(report, indent=1, default=str))


def mb(n):
    return round(n / 1e6, 1)


# ------------------------------------------------------------------ apply-only mode
if "--apply" in sys.argv:
    t = time.time()
    for stmt_name, stmt in re.findall(r"-- step: (.+?)\n(.*?)(?=\n-- step:|\Z)", MIG.read_text(), flags=re.S):
        t1 = time.time()
        conn.execute(stmt)
        log(f"{stmt_name}: {time.time() - t1:.1f}s")
    conn.execute("analyze")
    log(f"applied {MIG.name} in {time.time() - t:.1f}s")
    sys.exit(0)

# ------------------------------------------------------------------ parameter pools drawn from the real data
random.seed(20261013)


def typo(s):
    words = [w for w in re.findall(r"[A-Za-z]{5,}", s)]
    if not words:
        return s
    w = random.choice(words)
    i = random.randint(1, len(w) - 2)
    return s.replace(w, w[:i] + w[i + 1:], 1)


def pool(sql, n=N_PARAMS):
    return [r[0] for r in q(sql + f" limit {n}")]


insc = pool("select value from judgment_identifier where identifier_type = 'INSC' order by md5(value)")
scr = pool("select value from judgment_identifier where identifier_type = 'SCR' order by md5(value)")
cnr = pool("select value from judgment_identifier where identifier_type = 'CNR' order by md5(value)")
parties = pool("select petitioner from judgment where petitioner is not null order by md5(judgment_id::text)")
respondents = pool("select respondent from judgment where respondent is not null order by md5(judgment_id::text || 'r')")
titles = pool("select title from judgment where title is not null order by md5(judgment_id::text || 't')")
words = [random.choice(re.findall(r"[A-Za-z]{7,}", t) or ["COMMISSIONER"]) for t in titles]
judges = pool("select judge_name_norm from (select distinct judge_name_norm from judgment_judge) x order by md5(judge_name_norm)")
page_ids = pool("select judgment_id::text from judgment where text_status = 'english' order by md5(judgment_id::text || 'p')")
disposals = [r[0] for r in q("select disposal from judgment where disposal is not null group by 1 order by count(*) desc limit 8")]
windows = []
for _ in range(N_PARAMS):
    y = random.randint(1951, 2020)
    windows.append((f"{y}-01-01", f"{y + random.randint(1, 5)}-12-31"))
FTS_TERMS = ["anticipatory bail", "specific performance of contract", "adverse possession", "natural justice", "res judicata",
             "article 21 personal liberty", "limitation condonation of delay", "arbitration agreement", "habeas corpus", "income tax assessment",
             "compensation motor accident", "mens rea", "locus standi", "promissory estoppel", "sedition", "divorce cruelty", "land acquisition",
             "bank guarantee", "contempt of court", "court", "ejusdem generis", "quantum meruit", "benami transaction", "zamindari abolition"]

# ------------------------------------------------------------------ workload definitions
# name -> (sql, list of params, target_ms or None, description)
W = {
    "ident_insc": ("select j.judgment_id, j.title, j.decision_date from judgment_identifier i join judgment j using (judgment_id) where i.identifier_type = 'INSC' and i.value = %s",
                   [(v,) for v in insc], 50, "citation-style lookup by INSC id"),
    "ident_scr": ("select j.judgment_id, j.title, j.decision_date from judgment_identifier i join judgment j using (judgment_id) where i.identifier_type = 'SCR' and i.value = %s",
                  [(v,) for v in scr], 50, "citation-style lookup by SCR citation"),
    "ident_cnr": ("select j.judgment_id, j.title, j.decision_date from judgment_identifier i join judgment j using (judgment_id) where i.identifier_type = 'CNR' and i.value = %s",
                  [(v,) for v in cnr], 50, "lookup by CNR"),
    "ident_any_type": ("select j.judgment_id, j.title from judgment_identifier i join judgment j using (judgment_id) where i.value = %s",
                       [(v,) for v in scr], 50, "lookup by identifier value, type unknown"),
    "party_fuzzy": ("select judgment_id, petitioner, similarity(petitioner, %s) s from judgment where petitioner %% %s order by s desc limit 20",
                    [(typo(p), typo(p)) for p in parties], 300, "fuzzy petitioner search (one typo)"),
    "respondent_fuzzy": ("select judgment_id, respondent, similarity(respondent, %s) s from judgment where respondent %% %s order by s desc limit 20",
                         [(typo(p), typo(p)) for p in respondents], 300, "fuzzy respondent search (one typo)"),
    "title_fuzzy": ("select judgment_id, title, similarity(title, %s) s from judgment where title %% %s order by s desc limit 20",
                    [(typo(p), typo(p)) for p in titles], 300, "fuzzy title search (one typo)"),
    "party_substring": ("select judgment_id, title from judgment where petitioner ilike %s order by decision_date desc limit 50",
                        [(f"%{w}%",) for w in words], 300, "petitioner contains word"),
    "title_substring": ("select judgment_id, title from judgment where title ilike %s order by decision_date desc limit 50",
                        [(f"%{w}%",) for w in words], 300, "title contains word"),
    "judge_fuzzy": ("select judge_name_norm, count(*) from judgment_judge where judge_name_norm %% %s group by 1 order by max(similarity(judge_name_norm, %s)) desc limit 10",
                    [(typo(j), typo(j)) for j in judges], 300, "fuzzy judge name"),
    "judge_exact_list": ("select j.judgment_id, j.title, j.decision_date from judgment_judge g join judgment j using (judgment_id) where g.judge_name_norm = %s order by j.decision_date desc limit 50",
                         [(j,) for j in judges], None, "judgments of one judge"),
    "filter_date_disposal": ("select judgment_id, title, decision_date from judgment where decision_date between %s and %s and disposal = %s order by decision_date desc limit 50",
                             [(a, b, random.choice(disposals)) for a, b in windows], None, "date range + disposal"),
    "filter_year_counts": ("select decision_year, count(*) from judgment where decision_date between %s and %s group by 1 order by 1",
                           [(a, b) for a, b in windows], None, "judgments per year in a range"),
    "filter_text_status": ("select count(*) from judgment where text_status = %s and decision_year between %s and %s",
                           [(random.choice(["english", "translation_only", "none"]), int(a[:4]), int(b[:4])) for a, b in windows], None, "text status within years"),
    "flag_array": ("select count(*) from judgment where quality_flags @> %s::text[]",
                   [(random.choice([["no_english_text"], ["insc_id_shared"], ["not_in_vaquill"], ["incomplete_english_text"], ["report_year_differs_from_decision_year"]]),) for _ in range(N_PARAMS)],
                   None, "quality flag filter"),
    "language_array": ("select count(*) from judgment where available_languages @> %s::text[]",
                       [(random.choice([["pun"], ["hin", "en"], ["ben"], ["tam", "en"], ["guj"]]),) for _ in range(N_PARAMS)], None, "languages listed filter"),
    "chunk_list": ("select chunk_index, page_start, section_type, length(text) from judgment_chunk where judgment_id = %s and language_code = 'en' order by chunk_index",
                   [(p,) for p in page_ids], None, "chunk listing for one English text"),
    "english_text_fetch": ("select text, is_complete, overlap_mismatches from judgment_text where judgment_id = %s and language_code = 'en'",
                           [(p,) for p in page_ids], None, "fetch one assembled English text"),
}
PAGE_QUERIES = [  # one judgment page = several small queries
    "select * from judgment where judgment_id = %s", "select * from judgment_field_provenance where judgment_id = %s",
    "select * from judgment_judge where judgment_id = %s order by position", "select * from judgment_identifier where judgment_id = %s",
    "select * from judgment_language where judgment_id = %s", "select * from field_conflicts where judgment_id = %s",
    "select * from judgment_retrieval_status where judgment_id = %s", "select * from judgment_source_map where judgment_id = %s"]


def run(name, passes=2):
    sql, params, target, desc = W[name]
    res = {"description": desc, "target_ms": target, "runs": len(params)}
    times = [[] for _ in range(passes)]
    rows = []
    with conn.cursor() as cur:
        for ps in range(passes):
            for p in params:
                t = time.perf_counter()
                cur.execute(sql, p)
                r = cur.fetchall()
                times[ps].append((time.perf_counter() - t) * 1000)
                if ps == passes - 1:
                    rows.append(len(r))
    warm = times[-1]
    res.update({"p50_ms": round(statistics.median(warm), 2), "p95_ms": round(sorted(warm)[int(len(warm) * 0.95) - 1], 2), "max_ms": round(max(warm), 2),
                "first_pass_p95_ms": round(sorted(times[0])[int(len(times[0]) * 0.95) - 1], 2), "median_rows": statistics.median(rows)})
    res["plan"] = plan(sql, params[0])
    return res


def plan(sql, p):
    try:
        j = conn.execute("explain (format json) " + sql, p).fetchone()[0][0]["Plan"]
    except Exception as e:  # noqa
        return [f"plan unavailable: {type(e).__name__}"]
    out = []

    def walk(n):
        t = n["Node Type"]
        if "Scan" in t:
            out.append(f"{t}" + (f" using {n['Index Name']}" if "Index Name" in n else "") + f" on {n.get('Relation Name', '?')}")
        for c in n.get("Plans", []):
            walk(c)
    walk(j)
    return out


def run_page_load():
    times = []
    with conn.cursor() as cur:
        for ps in range(2):
            ts = []
            for pid in page_ids:
                t = time.perf_counter()
                for s in PAGE_QUERIES:
                    cur.execute(s, (pid,))
                    cur.fetchall()
                cur.execute("select chunk_index, page_start, length(text) from judgment_chunk where judgment_id = %s and language_code = 'en' order by chunk_index limit 5", (pid,))
                cur.fetchall()
                ts.append((time.perf_counter() - t) * 1000)
            times = ts
    return {"description": "full judgment page: 8 record queries + first chunks", "target_ms": None, "runs": len(page_ids),
            "p50_ms": round(statistics.median(times), 2), "p95_ms": round(sorted(times)[int(len(times) * 0.95) - 1], 2), "max_ms": round(max(times), 2),
            "first_pass_p95_ms": None, "median_rows": None, "plan": plan(PAGE_QUERIES[3], (page_ids[0],))}


SPECIAL = ("meta_search", "meta_search_idx", "fts_with_quality")  # added later and only valid for some index outcomes


def run_all(names=None):
    res = {}
    for n in (names or [k for k in W if k not in SPECIAL]):
        res[n] = run(n)
    if names is None or "page_load" in names:
        res["page_load"] = run_page_load()
    return res


# ------------------------------------------------------------------ full-text search workloads (depend on the index variant)
FTS = {
    "expr": {"rank": "select t.judgment_id, ts_rank(to_tsvector('english', t.text), q) r from judgment_text t, websearch_to_tsquery('english', %s) q "
                     "where t.language_code = 'en' and to_tsvector('english', t.text) @@ q order by r desc limit 20",
             "count": "select count(*) from judgment_text t where t.language_code = 'en' and to_tsvector('english', t.text) @@ websearch_to_tsquery('english', %s)"},
    "col": {"rank": "select t.judgment_id, ts_rank(t.tsv_en, q) r from judgment_text t, websearch_to_tsquery('english', %s) q where t.tsv_en @@ q order by r desc limit 20",
            "count": "select count(*) from judgment_text t where t.tsv_en @@ websearch_to_tsquery('english', %s)"},
}


def fts_run(variant, passes=1, terms=FTS_TERMS):
    out = {}
    with conn.cursor() as cur:
        for term in terms:
            rec = {}
            for kind in ("count", "rank"):
                ts = []
                for _ in range(passes):
                    t = time.perf_counter()
                    cur.execute(FTS[variant][kind], (term,))
                    rows = cur.fetchall()
                    ts.append((time.perf_counter() - t) * 1000)
                rec[kind + "_ms"] = round(ts[-1], 1)
                if kind == "count":
                    rec["matches"] = rows[0][0]
            out[term] = rec
    return out


def classify(f):
    for t, r in f.items():
        r["class"] = "rare" if r["matches"] < 200 else "medium" if r["matches"] < 5000 else "common"
    return f


def fts_summary(f):
    by = {}
    for t, r in f.items():
        by.setdefault(r["class"], []).append(r)
    s = {}
    for c, rs in by.items():
        rk = sorted(r["rank_ms"] for r in rs)
        s[c] = {"queries": len(rs), "rank_p50_ms": statistics.median(rk), "rank_max_ms": rk[-1], "count_p50_ms": statistics.median(r["count_ms"] for r in rs),
                "matches_median": statistics.median(r["matches"] for r in rs)}
    return s


# ------------------------------------------------------------------ candidates
CANDS = [  # (id, [steps (name, sql)], affected workloads, drop sql)
    ("identifier_by_judgment", [("identifier_by_judgment", "create index judgment_identifier_judgment_idx on judgment_identifier (judgment_id)")], ["page_load"], "drop index judgment_identifier_judgment_idx"),
    ("identifier_by_value", [("identifier_by_value", "create index judgment_identifier_value_idx on judgment_identifier (value)")], ["ident_any_type"], "drop index judgment_identifier_value_idx"),
    ("trgm_petitioner", [("trgm_petitioner", "create index judgment_petitioner_trgm_idx on judgment using gin (petitioner gin_trgm_ops)")], ["party_fuzzy", "party_substring"], "drop index judgment_petitioner_trgm_idx"),
    ("trgm_respondent", [("trgm_respondent", "create index judgment_respondent_trgm_idx on judgment using gin (respondent gin_trgm_ops)")], ["respondent_fuzzy"], "drop index judgment_respondent_trgm_idx"),
    ("trgm_title", [("trgm_title", "create index judgment_title_trgm_idx on judgment using gin (title gin_trgm_ops)")], ["title_fuzzy", "title_substring"], "drop index judgment_title_trgm_idx"),
    ("trgm_judge", [("trgm_judge", "create index judgment_judge_trgm_idx on judgment_judge using gin (judge_name_norm gin_trgm_ops)")], ["judge_fuzzy"], "drop index judgment_judge_trgm_idx"),
    ("btree_judge", [("btree_judge", "create index judgment_judge_name_idx on judgment_judge (judge_name_norm)")], ["judge_exact_list"], "drop index judgment_judge_name_idx"),
    ("btree_decision_date", [("btree_decision_date", "create index judgment_decision_date_idx on judgment (decision_date)")], ["filter_date_disposal", "filter_year_counts"], "drop index judgment_decision_date_idx"),
    ("btree_disposal", [("btree_disposal", "create index judgment_disposal_idx on judgment (disposal)")], ["filter_date_disposal"], "drop index judgment_disposal_idx"),
    ("btree_decision_year", [("btree_decision_year", "create index judgment_decision_year_idx on judgment (decision_year)")], ["filter_text_status"], "drop index judgment_decision_year_idx"),
    ("gin_quality_flags", [("gin_quality_flags", "create index judgment_quality_flags_idx on judgment using gin (quality_flags)")], ["flag_array"], "drop index judgment_quality_flags_idx"),
    ("gin_available_languages", [("gin_available_languages", "create index judgment_languages_idx on judgment using gin (available_languages)")], ["language_array"], "drop index judgment_languages_idx"),
]


def size_of(index_name):
    return q("select pg_relation_size(%s::regclass)", (index_name,))[0][0]


def decide(before, after, affected):
    reasons = []
    keep = False
    for w in affected:
        b, a = before[w], after[w]
        speedup = b["p50_ms"] / max(a["p50_ms"], 0.01)
        saved = b["p50_ms"] - a["p50_ms"]
        missed = b["target_ms"] is not None and b["p95_ms"] > b["target_ms"] and a["p95_ms"] <= b["target_ms"]
        ok = (speedup >= 3 and saved >= 5) or missed
        keep = keep or ok
        reasons.append(f"{w}: p50 {b['p50_ms']} -> {a['p50_ms']} ms ({speedup:.1f}x, saves {saved:.1f} ms)" + ("; fixes a missed target" if missed else ""))
    return keep, reasons


def main():
    report = {"started": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "rule": "keep if an affected query is >=3x and >=5 ms faster at p50, or the index fixes a missed target"}
    conn.execute("analyze")
    report["size_before_indexes"] = q("select pg_database_size(current_database())")[0][0]
    log("phase 0: baseline with constraint indexes only")
    baseline = run_all()
    report["baseline"] = baseline
    for n, r in baseline.items():
        log(f"  baseline {n}: p50 {r['p50_ms']} ms, p95 {r['p95_ms']} ms, plan {r['plan'][:2]}")

    # metadata search and its weighted tsvector (on-the-fly baseline first)
    meta_expr = ("select judgment_id, ts_rank(v, q) r from (select judgment_id, setweight(to_tsvector('english', coalesce(title,'')), 'A') || "
                 "setweight(to_tsvector('english', coalesce(petitioner,'') || ' ' || coalesce(respondent,'')), 'B') || setweight(to_tsvector('simple', coalesce(citation,'') || ' ' || coalesce(insc_id,'')), 'C') as v from judgment) j, "
                 "websearch_to_tsquery('english', %s) q where v @@ q order by r desc limit 20")
    W["meta_search"] = (meta_expr, [(t,) for t in ["commissioner of income tax", "state of kerala", "union of india", "bank", "sushil ansal", "land acquisition", "municipal corporation", "mohan lal"] * 4][:N_PARAMS], None,
                        "weighted metadata search (title A, parties B, citation C)")
    baseline["meta_search"] = run("meta_search")
    log(f"  baseline meta_search (computed on the fly): p50 {baseline['meta_search']['p50_ms']} ms")
    report["baseline_initial"] = json.loads(json.dumps(baseline))  # frozen copy: `baseline` is updated as indexes are kept

    save_partial(report)
    log("phase 1: candidate indexes, one at a time")
    kept = []
    cand_reports = []
    for cid, steps, affected, drop_sql in CANDS:
        t = time.time()
        for _, s in steps:
            conn.execute(s)
        secs = round(time.time() - t, 2)
        tbl = re.search(r"create index (\w+) on (\w+)", steps[0][1])
        iname, tname = tbl.group(1), tbl.group(2)
        conn.execute(f"analyze {tname}")
        sz = size_of(iname)
        after = run_all(affected) if "page_load" not in affected else {**run_all([w for w in affected if w != "page_load"]), "page_load": run_page_load()}
        keep, reasons = decide(baseline, after, affected)
        used = {w: any(iname in p for p in after[w]["plan"]) for w in affected}
        cand_reports.append({"id": cid, "index": iname, "table": tname, "build_seconds": secs, "bytes": sz, "kept": keep, "reasons": reasons, "used_by_planner": used,
                             "before": {w: {k: baseline[w][k] for k in ("p50_ms", "p95_ms")} for w in affected},
                             "after": {w: {k: after[w][k] for k in ("p50_ms", "p95_ms")} for w in affected}, "ddl": [s for _, s in steps]})
        log(f"  {cid}: built in {secs}s, {mb(sz)} MB -> {'KEEP' if keep else 'DROP'}; " + "; ".join(reasons))
        if keep:
            kept.append(cid)
            baseline.update({w: after[w] for w in affected})  # later candidates compare against the improved state
        else:
            conn.execute(drop_sql)
    report["candidates"] = cand_reports
    save_partial(report)

    # weighted metadata tsvector
    t = time.time()
    conn.execute("""alter table judgment add column search_tsv tsvector generated always as (
        setweight(to_tsvector('english', coalesce(title,'')), 'A') || setweight(to_tsvector('english', coalesce(petitioner,'') || ' ' || coalesce(respondent,'')), 'B')
        || setweight(to_tsvector('simple', coalesce(citation,'') || ' ' || coalesce(insc_id,'')), 'C')) stored""")
    conn.execute("create index judgment_search_tsv_idx on judgment using gin (search_tsv)")
    conn.execute("analyze judgment")
    secs = round(time.time() - t, 2)
    W["meta_search_idx"] = ("select judgment_id, ts_rank(search_tsv, q) r from judgment, websearch_to_tsquery('english', %s) q where search_tsv @@ q order by r desc limit 20",
                            W["meta_search"][1], None, "weighted metadata search using stored tsvector + GIN")
    after = run("meta_search_idx")
    b, a = baseline["meta_search"], after
    keep_meta = (b["p50_ms"] / max(a["p50_ms"], 0.01) >= 3 and b["p50_ms"] - a["p50_ms"] >= 5)
    sz = size_of("judgment_search_tsv_idx")
    cand_reports.append({"id": "meta_search_tsvector", "index": "judgment_search_tsv_idx", "table": "judgment", "build_seconds": secs, "bytes": sz, "kept": keep_meta,
                         "reasons": [f"meta_search: p50 {b['p50_ms']} -> {a['p50_ms']} ms"], "used_by_planner": {"meta_search": any("judgment_search_tsv_idx" in p for p in a["plan"])},
                         "before": {"meta_search": {"p50_ms": b["p50_ms"], "p95_ms": b["p95_ms"]}}, "after": {"meta_search": {"p50_ms": a["p50_ms"], "p95_ms": a["p95_ms"]}},
                         "ddl": ["alter table judgment add column search_tsv ... generated always as (...) stored", "create index judgment_search_tsv_idx on judgment using gin (search_tsv)"]})
    log(f"  meta_search tsvector: {secs}s, {mb(sz)} MB -> {'KEEP' if keep_meta else 'DROP'} (p50 {b['p50_ms']} -> {a['p50_ms']} ms)")
    if keep_meta:
        kept.append("meta_search_tsvector")
        baseline["meta_search_idx"] = after
    else:
        conn.execute("drop index judgment_search_tsv_idx")
        conn.execute("alter table judgment drop column search_tsv")

    # ---- full-text search: two designs on the English texts
    log("full text search: no index (one count query only, 5 minute limit)")
    conn.execute("set statement_timeout = '300s'")
    t = time.time()
    try:
        n = conn.execute(FTS["expr"]["count"], ("anticipatory bail",)).fetchone()[0]
        report["fts_no_index"] = {"term": "anticipatory bail", "count_ms": round((time.time() - t) * 1000), "matches": n, "plan": plan(FTS["expr"]["count"], ("anticipatory bail",))}
    except Exception as e:  # noqa
        report["fts_no_index"] = {"term": "anticipatory bail", "error": type(e).__name__, "after_seconds": round(time.time() - t)}
    conn.execute("set statement_timeout = 0")
    log(f"  no index: {report['fts_no_index']}")

    log("FTS design 1: GIN on the expression to_tsvector('english', text), English rows only")
    t = time.time()
    conn.execute("create index judgment_text_fts_expr_idx on judgment_text using gin (to_tsvector('english', text)) where language_code = 'en'")
    secs1 = round(time.time() - t, 1)
    sz1 = size_of("judgment_text_fts_expr_idx")
    conn.execute("analyze judgment_text")
    log(f"  built in {secs1}s, {mb(sz1)} MB; running queries")
    f1 = classify(fts_run("expr"))
    # classes come from design 1's counts; both designs must return the same counts
    log("FTS design 2: stored tsvector column + GIN")
    t = time.time()
    conn.execute("alter table judgment_text add column tsv_en tsvector")
    conn.execute("update judgment_text set tsv_en = to_tsvector('english', text) where language_code = 'en'")
    secs_fill = round(time.time() - t, 1)
    conn.execute("create index judgment_text_tsv_en_idx on judgment_text using gin (tsv_en)")
    secs2 = round(time.time() - t, 1)
    conn.execute("vacuum analyze judgment_text")
    sz2 = size_of("judgment_text_tsv_en_idx")
    col_bytes = q("select pg_total_relation_size('judgment_text') - pg_total_relation_size('judgment_text_tsv_en_idx')")[0][0]
    log(f"  column filled in {secs_fill}s, index done at {secs2}s, index {mb(sz2)} MB; running queries")
    f2 = fts_run("col")
    for term in f1:
        f2[term]["class"] = f1[term]["class"]
        assert f1[term]["matches"] == f2[term]["matches"], f"designs disagree on '{term}'"
    s1, s2 = fts_summary(f1), fts_summary(f2)
    log(f"  design 1 summary: {s1}")
    log(f"  design 2 summary: {s2}")
    worst1 = max(r["rank_ms"] for r in f1.values())
    worst2 = max(r["rank_ms"] for r in f2.values())
    pick = "col" if worst2 < worst1 else "expr"
    report["fts"] = {"design_expr": {"build_seconds": secs1, "index_bytes": sz1, "per_term": f1, "summary": s1},
                     "design_column": {"fill_seconds": secs_fill, "build_seconds_incl_fill": secs2, "index_bytes": sz2, "per_term": f2, "summary": s2},
                     "chosen": pick, "reason": f"worst ranked top-20 query: expression index {worst1} ms vs stored tsvector {worst2} ms; both return identical match counts"}
    if pick == "col":
        conn.execute("drop index judgment_text_fts_expr_idx")
        kept += ["fts_stored_tsvector"]
    else:
        conn.execute("drop index judgment_text_tsv_en_idx")
        conn.execute("alter table judgment_text drop column tsv_en")
        kept += ["fts_expression"]
    log(f"  chosen FTS design: {pick}")
    save_partial(report)

    # ---- retrieval with text-quality visibility
    W["fts_with_quality"] = ("select x.judgment_id, x.r, v.english_text_complete, v.english_overlap_mismatches, v.english_offset_drift_chunks from (select t.judgment_id, ts_rank(t.tsv_en, q) r "
                             "from judgment_text t, websearch_to_tsquery('english', %s) q where t.tsv_en @@ q order by r desc limit 20) x join judgment_retrieval_status v using (judgment_id) order by x.r desc",
                             [(t,) for t in FTS_TERMS[:20]], 2000, "ranked top 20 plus text-quality flags from judgment_retrieval_status")
    if pick == "col":
        report["fts_with_quality"] = run("fts_with_quality", passes=1)
    log("phase 2: final run on the kept index set")
    final = run_all()
    if "meta_search_tsvector" in kept:
        final["meta_search"] = run("meta_search_idx")
    if pick == "col":
        final["fts_with_quality"] = run("fts_with_quality", passes=2)
    report["final"] = final
    report["kept"] = kept

    # ---- constraint-index rebuild timing (proxy for their build cost, which happened inside the load transaction)
    reindex = []
    for (tbl,) in q("select relname from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r' and reltuples > 1000 order by reltuples desc"):
        t = time.time()
        conn.execute(f'reindex table "{tbl}"')
        reindex.append({"table": tbl, "seconds": round(time.time() - t, 2), "index_bytes": q("select pg_indexes_size(%s::regclass)", (tbl,))[0][0]})
    report["reindex"] = reindex
    conn.execute("analyze")
    report["size_after_indexes"] = q("select pg_database_size(current_database())")[0][0]
    report["index_sizes"] = q("select c.relname, i.relname, pg_relation_size(i.oid) from pg_index x join pg_class c on c.oid = x.indrelid join pg_class i on i.oid = x.indexrelid "
                              "where c.relnamespace = 'public'::regnamespace order by 3 desc")

    # ---- write the kept DDL as a migration (the file is applied with --apply on a freshly loaded database)
    parts = ["-- 0007: secondary indexes, kept by measurement (see docs/STAGE4_REPORT.md). Apply AFTER loading data:",
             "--   .venv/bin/python -I pipeline/09_index_benchmark.py --apply", "-- Constraint-backed indexes (PK / unique) are created with the tables in 0001-0006."]
    for c in cand_reports:
        if c["kept"]:
            for i, d in enumerate(c["ddl"]):
                parts.append(f"\n-- step: {c['id']}{'' if len(c['ddl']) == 1 else '_' + str(i + 1)}\n" + (d if not d.startswith("alter table judgment add column search_tsv ...") else
                    "alter table judgment add column search_tsv tsvector generated always as (\n  setweight(to_tsvector('english', coalesce(title,'')), 'A') || setweight(to_tsvector('english', coalesce(petitioner,'') || ' ' || coalesce(respondent,'')), 'B')\n  || setweight(to_tsvector('simple', coalesce(citation,'') || ' ' || coalesce(insc_id,'')), 'C')) stored") + ";")
    if pick == "col":
        parts.append("\n-- step: fts_stored_tsvector_column\nalter table judgment_text add column tsv_en tsvector;")
        parts.append("\n-- step: fts_stored_tsvector_fill\nupdate judgment_text set tsv_en = to_tsvector('english', text) where language_code = 'en';")
        parts.append("\n-- step: fts_stored_tsvector_index\ncreate index judgment_text_tsv_en_idx on judgment_text using gin (tsv_en);")
    else:
        parts.append("\n-- step: fts_expression_index\ncreate index judgment_text_fts_expr_idx on judgment_text using gin (to_tsvector('english', text)) where language_code = 'en';")
    MIG.write_text("\n".join(parts) + "\n")
    report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    report["total_seconds"] = round(time.time() - T0, 1)
    (B / "index_report.json").write_text(json.dumps(report, indent=1, default=str))
    log(f"done; kept {kept}")


if __name__ == "__main__":
    main()
