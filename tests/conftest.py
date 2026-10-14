import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT))
import pgconn  # noqa: E402

BASE = "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def client():
    pw = pgconn.env().get("ELI_ADMIN_PASSWORD") or __import__("os").environ["ELI_ADMIN_PASSWORD"]
    c = httpx.Client(base_url=BASE, follow_redirects=True, timeout=60)
    r = c.post("/login", data={"username": "admin", "password": pw})
    assert r.status_code == 200 and "Log out" in r.text, "login failed"
    return c


@pytest.fixture(scope="session")
def samples():
    """Five judgments from different eras (fixed rule, no randomness: the median-id judgment of each era)."""
    out = {}
    with pgconn.connect("admin") as c:
        for lo, hi in [(1950, 1959), (1970, 1979), (1990, 1999), (2010, 2019), (2020, 2025)]:
            r = c.execute("select judgment_id::text from judgment where decision_year between %s and %s and text_status = 'english' order by judgment_id offset 100 limit 1", (lo, hi)).fetchone()
            out[lo] = r[0]
    return out
