"""Database access for the web app. Reads use the read-only role; app writes use the limited eli_app role."""
import pathlib
import sys

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pipeline"))
import pgconn  # noqa: E402


def _conninfo(user, pw):
    e = pgconn.env()
    return f"host={e.get('PGHOST', '127.0.0.1')} port={e.get('PGPORT', 5433)} dbname={e.get('PGDATABASE', 'eli')} user={user} password={pw}"


_pools = {}


def _pool(kind):
    if kind not in _pools:
        e = pgconn.env()
        user, pw = {"ro": ("eli_readonly", e["POSTGRES_READONLY_PASSWORD"]),
                    "app": ("eli_app", e["POSTGRES_APP_PASSWORD"]),
                    "admin": ("eli_admin", e["POSTGRES_ADMIN_PASSWORD"])}[kind]
        _pools[kind] = ConnectionPool(_conninfo(user, pw), min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)
    return _pools[kind]


def ro():
    """Read-only connection (context manager). Role default: read-only transactions, 15 s statement timeout."""
    return _pool("ro").connection()


def app():
    """Write connection for app tables only (sessions, bookmarks, notes, reviews, reports)."""
    return _pool("app").connection()


def admin():  # CLI only (api/manage.py)
    """Used only for admin actions that no restricted role may do (creating users, API keys)."""
    return _pool("admin").connection()


def q(sql, params=None, kind="ro"):
    with _pool(kind).connection() as c:
        return c.execute(sql, params).fetchall()


def q1(sql, params=None, kind="ro"):
    rows = q(sql, params, kind)
    return rows[0] if rows else None
