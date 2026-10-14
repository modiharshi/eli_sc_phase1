"""Local username/password login, server-side sessions, API keys. Bound to 127.0.0.1 only."""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request

from . import db

ph = PasswordHasher()
COOKIE = "eli_session"
SESSION_HOURS = 12
_login_failures = {}


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username, password, role="viewer"):
    with db.app() as c:
        c.execute("insert into app_user (username, password_hash, role) values (%s, %s, %s)", (username, ph.hash(password), role))


def login(username, password, ip="local"):
    """Returns (token, user) or None. Five failures per username in ten minutes lock the account briefly."""
    now = time.time()
    fails = [t for t in _login_failures.get(username, []) if now - t < 600]
    if len(fails) >= 5:
        return None
    u = db.q1("select * from app_user where username=%s and not disabled", (username,), kind="app")
    try:
        if not u:
            ph.hash(password)  # equalise timing
            raise VerifyMismatchError()
        ph.verify(u["password_hash"], password)
    except VerifyMismatchError:
        _login_failures[username] = fails + [now]
        return None
    token = secrets.token_urlsafe(32)
    with db.app() as c:
        c.execute("insert into app_session (token_hash, user_id, expires_at) values (%s, %s, %s)",
                  (_h(token), u["user_id"], datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)))
        c.execute("update app_user set last_login_at = now() where user_id = %s", (u["user_id"],))
    return token, u


def logout(token):
    with db.app() as c:
        c.execute("delete from app_session where token_hash = %s", (_h(token),))


def user_from_request(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return _session_user(token)


def _session_user(token):
    with db.app() as c:   # app_user/app_session are not readable by the read-only role
        r = c.execute("""select u.user_id, u.username, u.role from app_session s join app_user u using (user_id)
                         where s.token_hash = %s and s.expires_at > now() and not u.disabled""", (_h(token),)).fetchone()
    return r


def require(request: Request, role=None):
    u = user_from_request(request)
    if not u:
        raise HTTPException(status_code=401, detail="login required")
    if role == "admin" and u["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return u


# ---- API keys -------------------------------------------------------------------------------------------------------
_rate = {}


def create_api_key(label, user_id=None, rate=60):
    key = "eli_" + secrets.token_urlsafe(30)
    with db.app() as c:
        c.execute("insert into api_key (user_id, key_hash, label, rate_limit_per_min) values (%s, %s, %s, %s)", (user_id, _h(key), label, rate))
    return key


def api_key_from_request(request: Request):
    key = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if not key:
        raise HTTPException(status_code=401, detail="missing API key (send header X-API-Key)")
    with db.app() as c:
        r = c.execute("select key_id, rate_limit_per_min from api_key where key_hash = %s and revoked_at is null", (_h(key),)).fetchone()
    if not r:
        raise HTTPException(status_code=401, detail="invalid or revoked API key")
    now = time.time()
    window = [t for t in _rate.get(r["key_id"], []) if now - t < 60]
    if len(window) >= r["rate_limit_per_min"]:
        raise HTTPException(status_code=429, detail=f"rate limit {r['rate_limit_per_min']}/min exceeded")
    _rate[r["key_id"]] = window + [now]
    return r
