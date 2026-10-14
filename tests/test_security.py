"""Roles, login and database privilege checks (needs the app running)."""
import secrets

import httpx
import psycopg
import pytest

import pgconn
from api import auth

BASE = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def viewer():
    name, pw = "pytest_viewer_" + secrets.token_hex(3), secrets.token_urlsafe(10)
    auth.create_user(name, pw, "viewer")
    c = httpx.Client(base_url=BASE, follow_redirects=True, timeout=60)
    assert "Log out" in c.post("/login", data={"username": name, "password": pw}).text
    yield c
    with pgconn.connect("admin") as a:
        a.execute("delete from app_session where user_id = (select user_id from app_user where username = %s)", (name,))
        a.execute("delete from app_user where username = %s", (name,)); a.commit()


def test_viewer_cannot_use_admin_actions(viewer):
    assert viewer.get("/admin").status_code == 403
    assert viewer.post("/review/decide", data={"queue": "error_report", "item_key": "1", "decision": "accept"}).status_code == 403
    assert viewer.post("/admin/hide", data={"judgment_id": "00000000-0000-0000-0000-000000000000", "reason": "x"}).status_code == 403
    assert viewer.get("/search?q=bail").status_code == 200


def test_wrong_password_and_lockout():
    c = httpx.Client(base_url=BASE, timeout=60)
    name = "lockout_" + secrets.token_hex(3)
    auth.create_user(name, "right-password-1", "viewer")
    try:
        for _ in range(5):
            assert c.post("/login", data={"username": name, "password": "wrong"}).status_code == 401
        assert c.post("/login", data={"username": name, "password": "right-password-1"}).status_code == 401, "locked out for the window"
    finally:
        with pgconn.connect("admin") as a:
            a.execute("delete from app_user where username = %s", (name,)); a.commit()


def test_cross_origin_post_refused(client):
    r = client.post("/sql", data={"sql": "select 1"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_session_cookie_flags():
    pw = pgconn.env()["ELI_ADMIN_PASSWORD"]
    r = httpx.post(BASE + "/login", data={"username": "admin", "password": pw}, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_logout_invalidates_session():
    pw = pgconn.env()["ELI_ADMIN_PASSWORD"]
    c = httpx.Client(base_url=BASE, follow_redirects=False, timeout=60)
    c.post("/login", data={"username": "admin", "password": pw})
    assert c.get("/search").status_code == 200
    c.post("/logout")
    r = httpx.get(BASE + "/search", follow_redirects=False, cookies={"eli_session": "stale"})
    assert r.status_code == 303


def _ro():
    e = pgconn.env()
    return psycopg.connect(host="127.0.0.1", port=int(e.get("PGPORT", 5433)), dbname="eli", user="eli_readonly", password=e["POSTGRES_READONLY_PASSWORD"])


@pytest.mark.parametrize("sql", ["insert into court (name, code, type) values ('x','x','x')", "delete from judgment", "update judgment set title = 'x'",
                                 "create table t_evil (a int)", "drop table judgment", "select * from app_user", "select * from api_key", "truncate judgment_chunk"])
def test_readonly_role_cannot_write_or_read_secrets(sql):
    with _ro() as c:
        with pytest.raises(psycopg.Error):
            c.execute(sql)


def test_app_role_cannot_touch_judgment_data():
    e = pgconn.env()
    with psycopg.connect(host="127.0.0.1", port=int(e.get("PGPORT", 5433)), dbname="eli", user="eli_app", password=e["POSTGRES_APP_PASSWORD"]) as c:
        for sql in ["delete from judgment", "update judgment set title = 'x'", "drop table judgment", "insert into judgment_text (judgment_id) values (gen_random_uuid())"]:
            with pytest.raises(psycopg.Error):
                c.execute(sql)
            c.rollback()


def test_postgres_and_app_listen_on_localhost_only():
    """Reads /proc/net/tcp{,6}: every LISTEN socket on port 5433 (Postgres) or 8000 (app) must be 127.0.0.1 (or ::1)."""
    found = []
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = open(f).read().splitlines()[1:]
        except OSError:
            continue
        for ln in lines:
            parts = ln.split()
            addr, state = parts[1], parts[3]
            ip, port = addr.split(":")
            if state == "0A" and int(port, 16) in (5433, 8000):
                found.append((int(port, 16), ip))
                assert ip in ("0100007F", "00000000000000000000000001000000"), (int(port, 16), ip)
    assert {p for p, _ in found} == {5433, 8000}, found
