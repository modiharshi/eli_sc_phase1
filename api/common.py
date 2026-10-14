import json
import pathlib
import re
from datetime import date, datetime
from html import escape as _esc
from uuid import UUID

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth

HERE = pathlib.Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

ATTRIBUTION = ("Judgment data: Vanga / Dattam Labs, Indian Supreme Court Judgments (CC BY 4.0), and Vaquill, Open India Law (CC BY 4.0). "
               "Underlying judgments are Government of India works from the Supreme Court of India / eCourts.")
NOT_OFFICIAL = "Not the official record; verify against the court's own copy."

QUALITY_HELP = {
    "clean": "No problems found by the automatic checks.",
    "fair": "Minor issues: some odd characters, a lot of non-Latin script, thin pages, or the text has gaps or inconsistent overlaps.",
    "noisy": "Likely OCR or extraction damage: many odd characters, mostly non-Latin text, near-empty pages, empty chunks, or characters we had to substitute.",
}


def json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, UUID):
        return str(o)
    return str(o)


def pretty(o):
    return json.dumps(o, indent=2, ensure_ascii=False, default=json_default)


def fmt(v):
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return ", ".join(map(str, v))
    return str(v)


templates.env.filters["pretty"] = pretty
templates.env.filters["fmt"] = fmt
templates.env.globals.update(ATTRIBUTION=ATTRIBUTION, NOT_OFFICIAL=NOT_OFFICIAL, QUALITY_HELP=QUALITY_HELP)

NAV = [("Search", "/search"), ("Constitution Benches", "/benches"), ("Judges", "/judges"), ("Time to decision", "/analytics/time-to-decision"),
       ("Data explorer", "/explorer"), ("Coverage", "/coverage"), ("Review queues", "/review"), ("SQL console", "/sql"),
       ("Benchmark", "/benchmark"), ("Feature inventory", "/inventory"), ("Status", "/status"), ("Admin", "/admin")]


def render(request: Request, name: str, status_code=200, **ctx):
    user = auth.user_from_request(request)
    ctx.update(request=request, user=user, nav=NAV, path=request.url.path)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def login_redirect(request: Request):
    nxt = request.url.path + (("?" + request.url.query) if request.url.query else "")
    return RedirectResponse("/login?next=" + re.sub(r"[^A-Za-z0-9/_.?=&%-]", "", nxt), status_code=303)


def bars(rows, label_key="label", value_key="n", width=560, bar_h=14):
    """Tiny server-side horizontal bar chart (inline SVG, no JS)."""
    if not rows:
        return ""
    top = max(r[value_key] for r in rows) or 1
    h = len(rows) * (bar_h + 4)
    parts = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" class="bars">']
    for i, r in enumerate(rows):
        y = i * (bar_h + 4)
        w = int((width - 230) * r[value_key] / top)
        parts.append(f'<text x="0" y="{y + bar_h - 3}" class="bl">{_esc(str(r[label_key])[:34])}</text>'
                     f'<rect x="170" y="{y}" width="{max(w, 1)}" height="{bar_h}" class="bb"/>'
                     f'<text x="{175 + w}" y="{y + bar_h - 3}" class="bl">{r[value_key]:,}</text>')
    parts.append("</svg>")
    return "".join(parts)


templates.env.globals["bars"] = bars
