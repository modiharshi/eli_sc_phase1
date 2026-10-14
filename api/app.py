"""ELI web app: FastAPI + server-rendered pages. Run with `bash infra/run_app.sh` (binds 127.0.0.1 only)."""
import csv
import io
import re
from html import escape

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db, exports, pages, rest, search
from .common import HERE, login_redirect, render

app = FastAPI(title="ELI", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
app.mount("/api/v1", rest.router)
app.include_router(pages.router)


@app.middleware("http")
async def guard(request: Request, call_next):
    """Login required everywhere except the login page, static files, health check and the key-authenticated REST API.
    POSTs must come from the same origin (the session cookie is also SameSite=Strict)."""
    p = request.url.path
    open_paths = p.startswith("/static") or p in ("/login", "/health", "/favicon.ico") or p.startswith("/api/v1") or False
    if request.method == "POST" and p != "/login" and not p.startswith("/api/v1"):
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
            return PlainTextResponse("cross-origin POST refused", status_code=403)
    if not open_paths and not auth.user_from_request(request):
        return login_redirect(request)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/v1"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    return render(request, "error.html", status_code=exc.status_code, code=exc.status_code, message=exc.detail)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    if request.url.path.startswith("/api/v1"):
        return JSONResponse({"error": "internal error", "detail": type(exc).__name__}, status_code=500)
    return render(request, "error.html", status_code=500, code=500, message=f"{type(exc).__name__}: {str(exc)[:300]}")


@app.get("/favicon.ico")
def favicon():
    return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="3" fill="#1f5fbf"/><text x="3" y="12" font-size="10" fill="#fff" font-family="sans-serif">E</text></svg>', media_type="image/svg+xml")


@app.get("/health")
def health():
    try:
        db.q1("select 1")
        return {"status": "ok", "db": "ok"}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "db": type(e).__name__}, status_code=503)


# ---- login -------------------------------------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/search"):
    return render(request, "login.html", next=next, error=None)


@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/search")):
    r = auth.login(username, password)
    if not r:
        return render(request, "login.html", status_code=401, next=next, error="Wrong username or password (or too many attempts; wait ten minutes).")
    token, _ = r
    resp = RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/search", status_code=303)
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", max_age=auth.SESSION_HOURS * 3600)
    return resp


@app.post("/logout")
def logout(request: Request):
    t = request.cookies.get(auth.COOKIE)
    if t:
        auth.logout(t)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/")
def home():
    return RedirectResponse("/search")


# ---- search ------------------------------------------------------------------------------------------------------
def _params(request: Request):
    p = {}
    for k in request.query_params.keys():
        vals = request.query_params.getlist(k)
        p[k] = vals if k in ("disposal", "bench", "judge_id", "lang", "source", "quality", "text_status") else vals[0]
    return p


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request):
    p = _params(request)
    res = search.run(p)
    types = [r["identifier_type"] for r in db.q("select distinct identifier_type from judgment_identifier order by 1")]
    return render(request, "search.html", p=p, res=res, scopes=search.SCOPES, id_types=types, sorts=list(search.SORTS))


@app.get("/search.csv")
def search_csv(request: Request):
    p = _params(request)
    p["_limit"] = 100000
    sql, args, *_ = search.build(p)
    with db.ro() as c:
        c.execute("select set_config('pg_trgm.similarity_threshold', '0.4', true)")
        ids = c.execute(sql, args).fetchone()["ids"]
        rows = c.execute("""select j.judgment_id, j.insc_id, j.title, j.petitioner, j.respondent, j.decision_date, j.decision_year, j.disposal, j.bench_strength,
                            j.citation, j.cnr, j.text_status, j.match_status from judgment_visible j where j.judgment_id = any(%s::uuid[]) order by j.decision_date""", [ids]).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    cols = ["judgment_id", "insc_id", "title", "petitioner", "respondent", "decision_date", "decision_year", "disposal", "bench_strength", "citation", "cnr", "text_status", "match_status"]
    w.writerow(cols + ["permalink"])
    base = str(request.base_url).rstrip("/")
    for r in rows:
        w.writerow([r[c] for c in cols] + [f"{base}/j/{r['judgment_id']}"])
    out.write(f"# {exports.NOTICE}\n")
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=eli_search.csv"})


# ---- judgment ----------------------------------------------------------------------------------------------------
TABS = [("overview", "Overview"), ("text", "Full text"), ("chunks", "Chunks"), ("raw_vanga", "Raw: Vanga"), ("raw_vaquill", "Raw: Vaquill"),
        ("identifiers", "Identifiers"), ("judges", "Judges"), ("provenance", "Provenance and conflicts"), ("pdf", "Original PDF"), ("later", "Later phases")]
HIDE_COLS = {"search_tsv"}


def _get_judgment(jid):
    try:
        j = db.q1("select * from judgment_visible where judgment_id = %s::uuid", (jid,))
    except Exception:  # noqa: BLE001
        j = None
    if not j:
        raise HTTPException(404, "No such judgment (or it has been hidden).")
    return j


def _mark(text, term):
    """Escape, then highlight every case-insensitive occurrence of `term`. Returns (html, hits)."""
    esc = escape(text)
    if not term.strip():
        return esc, 0
    pat = re.compile(re.escape(escape(term.strip())), re.I)
    return pat.subn(lambda m: f"<mark>{m.group(0)}</mark>", esc)


@app.get("/j/{jid}", response_class=HTMLResponse)
def judgment(request: Request, jid: str, tab: str = "overview", lang: str = "en", find: str = "", boundaries: int = 0, page: int = 1):
    j = _get_judgment(jid)
    ctx = dict(j=j, tab=tab, tabs=TABS, lang=lang, find=find, boundaries=boundaries)
    langs = db.q("""select l.*, t.is_complete, t.char_length, t.incompleteness_reason, t.overlap_mismatches, t.offset_drift_chunks, q.label, q.reasons
                    from judgment_language l left join judgment_text t using (judgment_id, language_code)
                    left join judgment_text_quality q using (judgment_id, language_code) where judgment_id = %s order by language_code""", (jid,))
    en = next((r for r in langs if r["language_code"] == "en"), None)
    ctx["langs"] = langs
    ctx["en"] = en
    ctx["badge"] = en["label"] if en and en["label"] else None
    ctx["incomplete"] = bool(en and en["text_chunks"] and (not en["is_complete"] or en["overlap_mismatches"] or en["offset_drift_chunks"]))
    ctx["other_labels"] = [r for r in langs if r["language_code"] != "en" and r["label"] == "noisy"]
    if tab == "overview":
        prov = {r["field_name"]: r for r in db.q("select * from judgment_field_provenance where judgment_id = %s", (jid,))}
        conflicts = {r["field_name"]: r for r in db.q("select * from field_conflicts where judgment_id = %s", (jid,))}
        ctx.update(prov=prov, conflicts=conflicts, fields=[(k, v) for k, v in j.items() if k not in HIDE_COLS],
                   smap=db.q1("select * from judgment_source_map where judgment_id = %s", (jid,)))
    elif tab == "text":
        t = db.q1("select text, char_length, is_complete from judgment_text where judgment_id = %s and language_code = %s", (jid, lang))
        if t:
            text = t["text"]
            if boundaries:
                ch = db.q("select chunk_index, char_start, page_start from judgment_chunk where judgment_id = %s and language_code = %s order by chunk_index", (jid, lang))
                pieces, last = [], 0
                for c in ch:
                    s = max(c["char_start"] or 0, last)
                    pieces.append(escape(text[last:s]))
                    pieces.append(f'<span class="chunkmark">chunk {c["chunk_index"]} · page {c["page_start"]}</span>')
                    last = s
                pieces.append(escape(text[last:]))
                body, hits = "".join(pieces), None
                if find.strip():
                    body, hits = re.compile(re.escape(escape(find.strip())), re.I).subn(lambda m: f"<mark>{m.group(0)}</mark>", body)
            else:
                body, hits = _mark(text, find)
            ctx.update(body=body, hits=hits, t=t)
        else:
            ctx.update(body=None)
    elif tab == "chunks":
        n = db.q1("select count(*) n from judgment_chunk where judgment_id = %s and language_code = %s", (jid, lang))["n"]
        ctx.update(n=n, page=page, chunks=db.q("select * from judgment_chunk where judgment_id = %s and language_code = %s order by chunk_index limit 25 offset %s",
                                               (jid, lang, (page - 1) * 25)))
    elif tab == "raw_vanga":
        ctx["raws"] = db.q("select year_folder, is_canonical_copy, dedupe_reason, raw from source_vanga_raw where path = %s order by year_folder", (j["vanga_path"],))
    elif tab == "raw_vaquill":
        m = db.q1("select vaquill_case_id from judgment_source_map where judgment_id = %s", (jid,))
        ctx["raw_vq"] = db.q1("select * from source_vaquill_raw where vaquill_case_id = %s", (m["vaquill_case_id"],)) if m and m["vaquill_case_id"] else None
    elif tab == "identifiers":
        ctx["ids"] = db.q("select * from judgment_identifier where judgment_id = %s order by identifier_type, value", (jid,))
    elif tab == "judges":
        ctx["bench"] = db.q1("select * from judgment_bench_estimate where judgment_id = %s", (jid,))
        ctx["judges"] = db.q("select g.position, g.judge_name_raw, g.judge_name_norm, g.source, g.judge_id, g.is_author from judgment_judge g where judgment_id = %s order by position", (jid,))
    elif tab == "provenance":
        ctx.update(prov=db.q("select * from judgment_field_provenance where judgment_id = %s order by field_name", (jid,)),
                   conflicts=db.q("select * from field_conflicts where judgment_id = %s order by field_name", (jid,)))
    elif tab == "later":
        ctx["counts"] = {t: db.q1(f"select count(*) n from {t} where judgment_id = %s", (jid,))["n"] for t in ("judgment_paragraph", "judgment_statute")}
    return render(request, "judgment.html", **ctx)


@app.get("/insc/{insc}")
def by_insc(insc: str):
    key = insc.replace("-", " ").replace("_", " ")
    rows = db.q("select judgment_id, title, decision_date, citation from judgment_visible where insc_id = %s", (key,))
    if len(rows) == 1:
        return RedirectResponse(f"/j/{rows[0]['judgment_id']}")
    if not rows:
        raise HTTPException(404, f"No judgment with INSC id “{key}”.")
    items = "".join(f'<li><a href="/j/{r["judgment_id"]}">{escape(r["title"] or "")}</a> {r["decision_date"]} {escape(r["citation"] or "")}</li>' for r in rows)
    return HTMLResponse(f"<p>Several reports share INSC id {escape(key)}:</p><ul>{items}</ul>")


@app.post("/j/{jid}/report")
def report_error(request: Request, jid: str, field_name: str = Form(...), suggested_value: str = Form(""), comment: str = Form("")):
    u = auth.require(request)
    j = _get_judgment(jid)
    cur_val = j.get(field_name)
    with db.app() as c:
        c.execute("insert into error_report (user_id, judgment_id, field_name, current_value, suggested_value, comment) values (%s,%s,%s,%s,%s,%s)",
                  (u["user_id"], jid, field_name, None if cur_val is None else str(cur_val), suggested_value or None, comment or None))
    return RedirectResponse(f"/j/{jid}?tab=overview&reported={field_name}", status_code=303)


@app.get("/j/{jid}/export.{fmt}")
def export_one(jid: str, fmt: str, lang: str = "en"):
    return exports.single(_get_judgment(jid), fmt, lang)


@app.get("/export/bundle.{fmt}")
def export_bundle(fmt: str, ids: str):
    js = [_get_judgment(i) for i in ids.split(",")[:25]]
    return exports.bundle(js, fmt)
