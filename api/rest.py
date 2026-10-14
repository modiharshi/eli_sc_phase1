"""Read-only REST API v1 (API-key auth, per-key rate limit, usage log). Every response carries attribution and the caveat."""
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from . import auth, db, search
from .common import ATTRIBUTION, NOT_OFFICIAL, json_default

# A sub-application mounted at /api/v1 so it has its own OpenAPI document and docs page (/api/v1/docs).
router = FastAPI(title="ELI API (Supreme Court of India, beta)", version="1",
                 description=f"Read-only. Send your key in the X-API-Key header. {ATTRIBUTION} {NOT_OFFICIAL}")
_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@router.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


def key(request: Request, _k=Depends(_key_header)):
    return auth.api_key_from_request(request)


def respond(request, k, endpoint, payload, t0, status=200):
    body = {"data": payload, "attribution": ATTRIBUTION, "notice": NOT_OFFICIAL}
    try:
        with db.app() as c:
            c.execute("insert into api_usage (key_id, endpoint, status, ms) values (%s,%s,%s,%s)", (k["key_id"], endpoint, status, int((time.time() - t0) * 1000)))
    except Exception:  # noqa: BLE001
        pass
    import json
    return JSONResponse(json.loads(json.dumps(body, default=json_default)), status_code=status)


@router.get("/search")
def api_search(request: Request, k=Depends(key)):
    t0 = time.time()
    p = {kk: (request.query_params.getlist(kk) if kk in ("disposal", "bench", "judge_id", "lang", "source", "quality") else request.query_params[kk]) for kk in request.query_params}
    p.pop("api_key", None)
    res = search.run(p)
    rows = [{c: r[c] for c in ("judgment_id", "title", "decision_date", "disposal", "bench_strength", "insc_id", "citation", "text_status", "quality", "incomplete", "snippet")} for r in res["rows"]]
    return respond(request, k, "search", {"total": res["total"], "page": res["page"], "pages": res["pages"], "results": rows, "facets": res["facets"]}, t0)


@router.get("/judgment/{jid}")
def api_judgment(request: Request, jid: str, include_text: bool = False, k=Depends(key)):
    t0 = time.time()
    try:
        j = db.q1("select * from judgment_visible where judgment_id = %s::uuid", (jid,))
    except Exception:  # noqa: BLE001
        j = None
    if not j:
        raise HTTPException(404, "no such judgment")
    j.pop("search_tsv", None)
    j["judges"] = db.q("select position, judge_name_norm, judge_id from judgment_judge where judgment_id = %s order by position", (jid,))
    j["identifiers"] = db.q("select identifier_type, value, source from judgment_identifier where judgment_id = %s", (jid,))
    if include_text:
        t = db.q1("select text from judgment_text where judgment_id = %s and language_code = 'en'", (jid,))
        j["text_en"] = t["text"] if t else None
    return respond(request, k, "judgment", j, t0)


@router.get("/judge/{judge_id}")
def api_judge(request: Request, judge_id: int, k=Depends(key)):
    t0 = time.time()
    jd = db.q1("select * from judge where judge_id = %s", (judge_id,))
    if not jd:
        raise HTTPException(404, "no such judge")
    jd["aliases"] = [r["alias_name"] for r in db.q("select alias_name from judge_alias where judge_id = %s", (judge_id,))]
    jd["judgments"] = db.q("""select j.judgment_id, j.title, j.decision_date, j.bench_strength, j.disposal from judgment_judge g join judgment_visible j using (judgment_id)
                              where g.judge_id = %s order by j.decision_date desc limit 200""", (judge_id,))
    return respond(request, k, "judge", jd, t0)


@router.get("/benches")
def api_benches(request: Request, min_size: int = 5, year_from: int = 0, year_to: int = 3000, k=Depends(key)):
    t0 = time.time()
    rows = db.q("""select j.judgment_id, j.title, j.decision_date, b.bench_listed, b.bench_header, b.bench_effective, b.bench_basis, j.disposal, j.citation
                   from judgment_bench b join judgment_visible j using (judgment_id)
                   where b.bench_effective >= %s and j.decision_year between %s and %s order by j.decision_date limit 1000""", (min_size, year_from, year_to))
    return respond(request, k, "benches", rows, t0)


@router.get("/facets")
def api_facets(request: Request, k=Depends(key)):
    t0 = time.time()
    out = {n: db.q(f"select * from facet_{n}") for n in ("year", "disposition", "bench", "case_type")}
    out["judge"] = db.q("select judge_id, value, n from facet_judge order by n desc limit 100")
    return respond(request, k, "facets", out, t0)
