"""HTTP checks against the running app (python -m pytest tests -q). Start the app first: bash infra/run_app.sh"""
import re

import pytest

PAGES = ["/search", "/search?q=natural+justice", "/benches", "/judges", "/analytics/time-to-decision", "/explorer", "/explorer/judgment",
         "/coverage", "/review", "/sql", "/benchmark", "/inventory", "/status", "/admin"]


def test_login_required(client):
    import httpx
    r = httpx.get("http://127.0.0.1:8000/search", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]


@pytest.mark.parametrize("path", PAGES)
def test_nav_pages_load(client, path):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])
    assert "Traceback" not in r.text and "not the official record" in r.text.lower()


def test_judgment_tabs_and_fields(client, samples):
    from api import db  # noqa: F401
    import sys, pathlib
    for era, jid in samples.items():
        ov = client.get(f"/j/{jid}")
        assert ov.status_code == 200, era
        cols = [r[0] for r in __import__("psycopg").connect(**{}).execute("select 1").fetchall()] if False else None
        for tab in ["overview", "text", "chunks", "raw_vanga", "raw_vaquill", "identifiers", "judges", "provenance", "pdf", "later"]:
            r = client.get(f"/j/{jid}?tab={tab}")
            assert r.status_code == 200, (era, tab, r.status_code, r.text[:200])


def test_overview_shows_every_judgment_column(client, samples):
    import pgconn
    with pgconn.connect("admin") as c:
        cols = [r[0] for r in c.execute("select column_name from information_schema.columns where table_name='judgment' and column_name <> 'search_tsv' order by ordinal_position").fetchall()]
    for jid in samples.values():
        html = client.get(f"/j/{jid}").text
        missing = [c for c in cols if f"<code>{c}</code>" not in html]
        assert not missing, missing


def test_explorer_lists_every_table(client):
    import pgconn
    with pgconn.connect("admin") as c:
        names = {r[0] for r in c.execute("select tablename from pg_tables where schemaname='public'").fetchall()} - {"app_user", "app_session", "api_key"}
    html = client.get("/explorer").text
    missing = [n for n in names if f'href="/explorer/{n}"' not in html]
    assert not missing, missing


def test_sql_console_rejects_writes(client):
    for stmt in ["delete from judgment", "select 1; select 2", "drop table judgment", "update judgment set title = 'x'", "select * from judgment where false; --"]:
        r = client.post("/sql", data={"sql": stmt})
        assert r.status_code == 200
        assert "refused" in r.text or "Only" in r.text, stmt
    ok = client.post("/sql", data={"sql": "select count(*) as n from judgment"})
    assert "38371" in ok.text or "38,371" in ok.text
