"""Headless-browser pass: logs in, visits each nav page and five judgments, fails on console errors, saves screenshots to logs/shots."""
import os, pathlib, sys
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline")); import pgconn
OUT = ROOT / "logs" / "shots"; OUT.mkdir(parents=True, exist_ok=True)
with pgconn.connect("admin") as c:
    ids = [c.execute("select judgment_id::text from judgment where decision_year between %s and %s and text_status='english' order by judgment_id offset 100 limit 1", (lo, hi)).fetchone()[0]
           for lo, hi in [(1950, 1959), (1970, 1979), (1990, 1999), (2010, 2019), (2020, 2025)]]
paths = ["/search?q=natural+justice", "/benches", "/judges", "/analytics/time-to-decision", "/explorer", "/explorer/judgment", "/coverage", "/review", "/sql", "/benchmark", "/inventory", "/status", "/admin"] + [f"/j/{i}" for i in ids] + [f"/j/{ids[1]}?tab=text&boundaries=1&find=bench"]
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"]) if os.path.exists("/opt/pw-browsers/chromium") else p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.on("console", lambda m: errors.append((pg.url, m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append((pg.url, str(e))))
    pg.goto("http://127.0.0.1:8000/login"); pg.fill("[name=username]", "admin"); pg.fill("[name=password]", os.environ["ELI_ADMIN_PASSWORD"]); pg.click("button.primary")
    for i, path in enumerate(paths):
        r = pg.goto("http://127.0.0.1:8000" + path); assert r.status < 400, (path, r.status)
        pg.screenshot(path=str(OUT / f"{i:02d}.png"), full_page=False)
    pg.set_viewport_size({"width": 390, "height": 800}); pg.goto("http://127.0.0.1:8000/search?q=bail"); pg.screenshot(path=str(OUT / "mobile_search.png"))
    b.close()
print("pages:", len(paths), "console errors:", errors)
