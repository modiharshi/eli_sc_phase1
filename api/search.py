"""Search: one SQL statement per request returns the total, the requested page and all facet counts,
so every facet count describes exactly the current result set."""
from . import db

PAGE = 20
SORTS = {"relevance": "rank desc, j.decision_date desc nulls last", "date_desc": "j.decision_date desc nulls last",
         "date_asc": "j.decision_date asc nulls last", "title": "j.title asc nulls last"}
SCOPES = {"all": "Everything (metadata + English full text)", "title": "Title and parties (words)", "text": "English full text only",
          "parties": "Party names (contains)", "title_fuzzy": "Title (typo-tolerant)", "judge": "Judge name (contains)",
          "identifier": "Identifier (INSC, SCR, CNR…)"}
INCOMPLETE = "(t.judgment_id is not null and not (t.is_complete and t.overlap_mismatches = 0 and t.offset_drift_chunks = 0))"


def _as_list(v, cast=str):
    if v in (None, "", []):
        return []
    if not isinstance(v, list):
        v = [v]
    out = []
    for x in v:
        try:
            out.append(cast(x))
        except (TypeError, ValueError):
            pass
    return out


def build(p):
    """p: dict of query parameters (lists allowed). Returns (sql, args)."""
    where, args = [], []
    q = (p.get("q") or "").strip()
    scope = p.get("scope") if p.get("scope") in SCOPES else "all"
    tq = "websearch_to_tsquery('english', %s)"
    rank = "0::real"
    cte_args = []
    if q:
        if scope == "all":
            # two index scans combined with UNION; a plain OR across the joined tables took 21 s
            where.append(f"j.judgment_id in (select judgment_id from judgment where search_tsv @@ {tq} union select judgment_id from judgment_text where language_code = 'en' and tsv_en @@ {tq})"); args += [q, q]
            rank = f"(coalesce(ts_rank_cd(t.tsv_en, {tq}),0) + 2*coalesce(ts_rank_cd(j.search_tsv, {tq}),0))"; cte_args += [q, q]
        elif scope == "title":
            where.append(f"j.search_tsv @@ {tq}"); args.append(q); rank = f"ts_rank_cd(j.search_tsv, {tq})"; cte_args.append(q)
        elif scope == "text":
            where.append(f"t.tsv_en @@ {tq}"); args.append(q); rank = f"ts_rank_cd(t.tsv_en, {tq})"; cte_args.append(q)
        elif scope == "parties":
            where.append("(j.petitioner ilike %s or j.respondent ilike %s)"); args += [f"%{q}%"] * 2
        elif scope == "title_fuzzy":
            where.append("j.title %% %s"); args.append(q); rank = "similarity(j.title, %s)"; cte_args.append(q)
        elif scope == "judge":
            where.append("exists (select 1 from judgment_judge g where g.judgment_id = j.judgment_id and g.judge_name_norm ilike %s)"); args.append(f"%{q}%")
        elif scope == "identifier":
            where.append("(j.insc_id ilike %s or exists (select 1 from judgment_identifier i where i.judgment_id = j.judgment_id and i.value ilike %s))"); args += [f"{q}%"] * 2
    if q and scope in ("all", "title", "text") and rank != "0::real":
        # incomplete or inconsistent English texts stay visible but rank lower
        rank = f"({rank}) * case when {INCOMPLETE} then 0.5 else 1 end"
    within = (p.get("within") or "").strip()
    if within:   # "search within these results": a second full-text condition ANDed with everything else
        where.append(f"j.judgment_id in (select judgment_id from judgment where search_tsv @@ {tq} union select judgment_id from judgment_text where language_code = 'en' and tsv_en @@ {tq})"); args += [within, within]
    yf, yt = p.get("year_from"), p.get("year_to")
    if str(yf or "").isdigit():
        where.append("j.decision_year >= %s"); args.append(int(yf))
    if str(yt or "").isdigit():
        where.append("j.decision_year <= %s"); args.append(int(yt))
    for key, col in (("disposal", "j.disposal"), ("text_status", "j.text_status"), ("source", "j.match_status")):
        vals = _as_list(p.get(key))
        if vals:
            if key == "disposal" and "(none)" in vals:
                where.append(f"({col} = any(%s) or {col} is null)")
            else:
                where.append(f"{col} = any(%s)")
            args.append(vals)
    bench = _as_list(p.get("bench"), int)
    if bench:
        where.append("j.bench_strength = any(%s)"); args.append(bench)
    judges = _as_list(p.get("judge_id"), int)
    for jid in judges:
        where.append("exists (select 1 from judgment_judge g where g.judgment_id = j.judgment_id and g.judge_id = %s)"); args.append(jid)
    for key, col in (("petitioner", "j.petitioner"), ("respondent", "j.respondent"), ("case_number", "j.case_number")):
        if (p.get(key) or "").strip():
            where.append(f"{col} ilike %s"); args.append(f"%{p[key].strip()}%")
    if p.get("id_type") and p.get("id_value"):
        where.append("exists (select 1 from judgment_identifier i where i.judgment_id = j.judgment_id and i.identifier_type = %s and i.value ilike %s)"); args += [p["id_type"], f"{p['id_value'].strip()}%"]
    lang = [x.strip() for v in _as_list(p.get("lang")) for x in v.split(",") if x.strip()]
    if lang:
        where.append("j.available_languages && %s"); args.append(lang)
    quality = _as_list(p.get("quality"))
    if quality:
        where.append("tq.label = any(%s)"); args.append(quality)
    if p.get("incomplete") == "1":
        where.append(INCOMPLETE)

    sort = p.get("sort") if p.get("sort") in SORTS else ("relevance" if q and rank != "0::real" else "date_desc")
    try:
        page = max(1, int(p.get("page") or 1))
    except ValueError:
        page = 1
    LIMIT = int(p.get("_limit") or PAGE)
    wsql = ("where " + " and ".join(where)) if where else ""
    sql = f"""
with m as materialized (
  select j.judgment_id, j.decision_year, j.disposal, j.bench_strength, j.decision_date, j.title, {rank} as rank
  from judgment_visible j
  left join judgment_text t on t.judgment_id = j.judgment_id and t.language_code = 'en'
  left join judgment_text_quality tq on tq.judgment_id = j.judgment_id and tq.language_code = 'en'
  {wsql}
), ordered as (select judgment_id from m j order by {SORTS[sort].replace('j.rank', 'rank')} limit {LIMIT} offset {(page - 1) * LIMIT})
select (select count(*) from m) as total,
  (select coalesce(jsonb_agg(judgment_id), '[]') from ordered) as ids,
  (select coalesce(jsonb_agg(jsonb_build_object('v', decision_year, 'n', n) order by decision_year), '[]') from (select decision_year, count(*) n from m group by 1) x) as f_year,
  (select coalesce(jsonb_agg(jsonb_build_object('v', coalesce(disposal, '(none)'), 'n', n) order by n desc), '[]') from (select disposal, count(*) n from m group by 1) x) as f_disposal,
  (select coalesce(jsonb_agg(jsonb_build_object('v', bench_strength, 'n', n) order by bench_strength), '[]') from (select bench_strength, count(*) n from m group by 1) x) as f_bench,
  (select coalesce(jsonb_agg(jsonb_build_object('v', judge_id, 'label', name, 'n', n) order by n desc), '[]') from
     (select g.judge_id, jd.canonical_name as name, count(distinct g.judgment_id) n from m join judgment_judge g using (judgment_id) join judge jd using (judge_id) group by 1, 2 order by 3 desc limit 15) x) as f_judge
"""
    # args order: cte rank args come first in the select list of m, then where args
    return sql, cte_args + args, page, q, scope, sort


def run(p):
    sql, args, page, q, scope, sort = build(p)
    with db.ro() as c:
        c.execute("select set_config('pg_trgm.similarity_threshold', '0.4', true)")
        res = c.execute(sql, args).fetchone()
        ids = res["ids"]
        rows = []
        if ids:
            tq = "websearch_to_tsquery('english', %s)"
            snippet = (f"case when %s <> '' and t.text is not null and %s in ('all','text') then ts_headline('english', t.text, {tq}, 'StartSel=⟦,StopSel=⟧,MaxFragments=2,MaxWords=28,MinWords=8,FragmentDelimiter= … ') end")
            rows = c.execute(f"""
              select j.judgment_id, j.title, j.petitioner, j.respondent, j.decision_date, j.decision_year, j.disposal, j.bench_strength,
                     j.insc_id, j.citation, j.text_status, j.match_status, j.available_languages, tq.label as quality, tq.reasons as quality_reasons,
                     (t.judgment_id is not null and not (t.is_complete and t.overlap_mismatches = 0 and t.offset_drift_chunks = 0)) as incomplete,
                     {snippet} as snippet
              from judgment_visible j
              left join judgment_text t on t.judgment_id = j.judgment_id and t.language_code = 'en'
              left join judgment_text_quality tq on tq.judgment_id = j.judgment_id and tq.language_code = 'en'
              where j.judgment_id = any(%s::uuid[])""", [q, scope, q, ids]).fetchall()
            from html import escape
            for r in rows:
                if r["snippet"]:
                    r["snippet"] = escape(r["snippet"]).replace("⟦", "<mark>").replace("⟧", "</mark>")
            order = {i: n for n, i in enumerate(ids)}
            rows.sort(key=lambda r: order[str(r["judgment_id"])])
    return dict(total=res["total"], rows=rows, page=page, pages=max(1, -(-res["total"] // PAGE)), q=q, scope=scope, sort=sort,
                facets=dict(year=res["f_year"], disposal=res["f_disposal"], bench=res["f_bench"], judge=res["f_judge"]))
