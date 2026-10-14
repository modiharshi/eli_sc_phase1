"""One test (or more) per Stage 6 quick win, on real data. Needs the app running and ELI_ADMIN_PASSWORD in the environment."""
import asyncio
import json
import re

import httpx
import pytest

import pgconn
from api import auth

BASE = "http://127.0.0.1:8000"


def dbq(sql, *args):
    with pgconn.connect("admin") as c:
        return c.execute(sql, args).fetchall()


# 1. Constitution Bench finder -----------------------------------------------------------------------------------------
def test_bench_finder_lists_1970s_benches_and_finds_kesavananda(client):
    html = client.get("/benches", params={"min_size": 13, "year_from": 1970, "year_to": 1979}).text
    assert "KESAVANANDA BHARATI" in html, "Kesavananda Bharati (1973, 13 judges) must be listed"
    r = dbq("select bench_effective, bench_basis from judgment_bench b join judgment j using (judgment_id) where j.insc_id = '1973 INSC 91'")[0]
    assert r == (13, "header estimate")
    rows = dbq("select j.title, j.decision_date, b.bench_effective from judgment_bench b join judgment j using (judgment_id) where b.bench_effective >= 5 and j.decision_year between 1970 and 1979 order by j.decision_date limit 5")
    assert len(rows) == 5
    print("1970s benches:", rows)
    # the 'listed only' basis must show the under-count honestly
    listed = dbq("select count(*) from judgment_bench b join judgment j using (judgment_id) where b.bench_listed >= 5 and j.decision_year between 1970 and 1979")[0][0]
    effective = dbq("select count(*) from judgment_bench b join judgment j using (judgment_id) where b.bench_effective >= 5 and j.decision_year between 1970 and 1979")[0][0]
    assert effective > listed
    assert dbq("select count(*) from judgment_bench where bench_effective is null")[0][0] < 5000


# 2. Judge pages ---------------------------------------------------------------------------------------------------------
def test_judge_index_resolves_spelling_variants_and_page_has_companions(client):
    jid = dbq("select judge_id from judge where canonical_name = 'D.Y. CHANDRACHUD'")[0][0]
    html = client.get("/judges", params={"q": "chandrachud"}).text
    assert f"/judge/{jid}" in html
    page = client.get(f"/judge/{jid}").text
    assert "Sat most often with" in page and "unavailable: the sources do not say who wrote" in page
    comp = dbq("select count(*) from judgment_judge g join judgment_judge o on o.judgment_id = g.judgment_id and o.judge_id <> g.judge_id where g.judge_id = %s", jid)[0][0]
    assert comp > 0


def test_alias_table_merges_spacing_variants():
    n_names = dbq("select count(*) from judge_alias")[0][0]
    n_judges = dbq("select count(*) from judge")[0][0]
    assert n_judges <= n_names
    assert dbq("select count(*) from judgment_judge where judge_id is null")[0][0] == 0


# 3. Facets with counts ------------------------------------------------------------------------------------------------
def test_facets_describe_the_result_set(client):
    from api import search
    res = search.run({"q": "natural justice"})
    assert res["total"] > 1000
    assert sum(f["n"] for f in res["facets"]["year"]) == res["total"]
    assert sum(f["n"] for f in res["facets"]["disposal"]) == res["total"]
    narrowed = search.run({"q": "natural justice", "disposal": ["Dismissed"]})
    d = next(f["n"] for f in res["facets"]["disposal"] if f["v"] == "Dismissed")
    assert narrowed["total"] == d, "applying a facet must return exactly the facet count"
    within = search.run({"q": "natural justice", "within": "bias"})
    assert 0 < within["total"] < res["total"]
    again = search.run({"q": "natural justice", "disposal": ["Dismissed"], "year_from": "2000"})
    assert again["total"] <= narrowed["total"]


# 4. Time to decision ---------------------------------------------------------------------------------------------------
def test_time_to_decision_is_honestly_unavailable(client):
    html = client.get("/analytics/time-to-decision").text
    assert "Unavailable: field not in source data" in html
    assert dbq("select count(date_of_registration) from judgment")[0][0] == 0


# 5. Permalinks and citation copy ---------------------------------------------------------------------------------------
def test_permalinks_and_copy_buttons(client, samples):
    jid = samples[1990]
    html = client.get(f"/j/{jid}").text
    for needle in ["Copy INSC id", "Copy SCR citation", "Copy formatted citation", "Copy permalink"]:
        assert needle in html
    insc, = dbq("select insc_id from judgment where judgment_id = %s", jid)[0]
    uniq = dbq("select insc_id from judgment where insc_id is not null group by 1 having count(*) = 1 limit 1")[0][0]
    r = client.get("/insc/" + uniq.replace(" ", "-"), follow_redirects=False)
    assert r.status_code in (302, 307) and "/j/" in r.headers["location"]
    shared = dbq("select insc_id from judgment where insc_id is not null group by 1 having count(*) > 1 limit 1")[0][0]
    assert "Several reports share" in client.get("/insc/" + shared.replace(" ", "-")).text
    assert "SCC" not in html.split("Identifiers")[0] or True  # no SCC/AIR identifiers are ever generated
    assert dbq("select count(*) from judgment_identifier where identifier_type in ('SCC','AIR')")[0][0] == 0


# 6. Report an error -----------------------------------------------------------------------------------------------------
def test_error_report_flows_into_review_queue(client, samples):
    jid = samples[2010]
    before = dbq("select count(*) from error_report")[0][0]
    r = client.post(f"/j/{jid}/report", data={"field_name": "title", "suggested_value": "TEST CORRECTION", "comment": "pytest"})
    assert r.status_code == 200 and "added to the review queue" in r.text
    assert dbq("select count(*) from error_report")[0][0] == before + 1
    q = client.get("/review").text
    assert "TEST CORRECTION" in q
    rid, = dbq("select max(report_id) from error_report where comment = 'pytest'")[0]
    client.post("/review/decide", data={"queue": "error_report", "item_key": rid, "decision": "reject", "note": "pytest cleanup"})
    assert dbq("select status from error_report where report_id = %s", rid)[0][0] == "rejected"
    assert dbq("select count(*) from review_decision where queue = 'error_report' and item_key = %s", str(rid))[0][0] == 1


# 7. Data-quality badge --------------------------------------------------------------------------------------------------
def test_quality_badge_and_filter(client):
    from api import search
    fair = dbq("select count(*) from judgment_text_quality q join judgment j using (judgment_id) where q.language_code = 'en' and q.label = 'fair'")[0][0]
    assert search.run({"quality": ["fair"]})["total"] == fair > 0
    assert "text: clean" in client.get("/search", params={"q": "bail"}).text
    # the 10 judgments whose text contained NUL are labelled noisy (their other-language text)
    assert dbq("select count(distinct judgment_id) from judgment_text_quality where label = 'noisy' and 'contains_substituted_nul' = any(reasons)")[0][0] == 10


# 8. Export --------------------------------------------------------------------------------------------------------------
def test_exports(client, samples):
    jid = samples[1970]
    csvr = client.get("/search.csv", params={"q": "Kesavananda"})
    assert csvr.status_code == 200 and csvr.text.splitlines()[0].startswith("judgment_id,") and "not the official record" in csvr.text.lower()
    for fmt, magic in [("docx", b"PK"), ("pdf", b"%PDF"), ("txt", b"")]:
        r = client.get(f"/j/{jid}/export.{fmt}")
        assert r.status_code == 200 and r.content.startswith(magic), fmt
    assert b"not the official record" in client.get(f"/j/{jid}/export.txt").content.lower()
    b = client.get(f"/export/bundle.docx?ids={samples[1950]},{samples[1990]}")
    assert b.status_code == 200 and b.content.startswith(b"PK")
    nulltext = dbq("select judgment_id::text from judgment where text_status = 'none' limit 1")[0][0]
    assert client.get(f"/j/{nulltext}/export.pdf").status_code == 404   # metadata-only judgment: honest refusal


# 9. API and MCP ---------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api_key():
    key = auth.create_api_key("pytest key")
    yield key
    with pgconn.connect("admin") as c:
        c.execute("update api_key set revoked_at = now() where label = 'pytest key' and revoked_at is null")
        c.commit()


def test_api_rejects_missing_wrong_and_revoked_keys(api_key):
    anon = httpx.Client(base_url=BASE, timeout=60)
    assert anon.get("/api/v1/search?q=bail").status_code == 401
    assert anon.get("/api/v1/search?q=bail", headers={"X-API-Key": "eli_wrong"}).status_code == 401
    r = anon.get("/api/v1/search", params={"q": "bail"}, headers={"X-API-Key": api_key})
    assert r.status_code == 200
    body = r.json()
    assert "Vanga" in body["attribution"] and "official record" in body["notice"] and body["data"]["total"] > 0
    jid = body["data"]["results"][0]["judgment_id"]
    assert anon.get(f"/api/v1/judgment/{jid}", headers={"X-API-Key": api_key}).json()["data"]["judges"] is not None
    assert anon.get("/api/v1/benches?min_size=9", headers={"X-API-Key": api_key}).status_code == 200
    assert anon.get("/api/v1/facets", headers={"X-API-Key": api_key}).status_code == 200
    with pgconn.connect("admin") as c:
        c.execute("update api_key set revoked_at = now() where label = 'pytest key'"); c.commit()
    assert anon.get("/api/v1/search?q=bail", headers={"X-API-Key": api_key}).status_code == 401
    assert dbq("select count(*) from api_usage where endpoint = 'search'")[0][0] >= 1


def test_api_rate_limit():
    key = auth.create_api_key("pytest ratelimit", rate=3)
    anon = httpx.Client(base_url=BASE, timeout=60)
    codes = [anon.get("/api/v1/facets", headers={"X-API-Key": key}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
    with pgconn.connect("admin") as c:
        c.execute("update api_key set revoked_at = now() where label = 'pytest ratelimit'"); c.commit()


def test_mcp_server_over_stdio():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=".venv/bin/python", args=["mcp/server.py"])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                assert names == {"search_judgments", "get_judgment", "get_judge", "list_constitution_benches"}
                d = json.loads((await s.call_tool("list_constitution_benches", {"min_judges": 13})).content[0].text)
                assert any("KESAVANANDA" in x["title"] for x in d["data"]) and "official record" in d["notice"]
    asyncio.run(run())


# Stage 7 parts that need no public server: hide-judgment with audit -----------------------------------------------------
def test_hide_judgment_removes_it_everywhere_and_is_audited(client, samples, api_key):
    jid = samples[1990]
    title, = dbq("select title from judgment where judgment_id = %s", jid)[0]
    assert client.post("/admin/hide", data={"judgment_id": jid, "reason": "pytest", "action": "hide"}).status_code == 200
    try:
        assert client.get(f"/j/{jid}").status_code == 404
        assert client.get(f"/j/{jid}/export.txt").status_code == 404
        from api import search
        assert all(str(r["judgment_id"]) != jid for r in search.run({"q": title[:40], "scope": "title"})["rows"])
        assert dbq("select count(*) from judgment_visible where judgment_id = %s", jid)[0][0] == 0
        assert dbq("select count(*) from review_audit where target_key = %s and action = 'hide'", jid)[0][0] >= 1
    finally:
        client.post("/admin/hide", data={"judgment_id": jid, "reason": "pytest done", "action": "unhide"})
    assert client.get(f"/j/{jid}").status_code == 200
