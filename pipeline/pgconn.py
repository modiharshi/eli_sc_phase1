"""Connection helper: credentials come from the git-ignored .env file or the environment."""
import os
import pathlib

import psycopg

ROOT = pathlib.Path(__file__).resolve().parent.parent


def env():
    values = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    values.update({k: v for k, v in os.environ.items() if k in ("PGHOST", "PGPORT", "PGDATABASE", "POSTGRES_ADMIN_PASSWORD", "POSTGRES_READONLY_PASSWORD")})
    return values


def connect(role="admin", **kw):
    e = env()
    user, pw = ("eli_admin", e["POSTGRES_ADMIN_PASSWORD"]) if role == "admin" else ("eli_readonly", e["POSTGRES_READONLY_PASSWORD"])
    return psycopg.connect(host=e.get("PGHOST", "127.0.0.1"), port=int(e.get("PGPORT", 5433)), dbname=e.get("PGDATABASE", "eli"),
                           user=user, password=pw, **kw)
