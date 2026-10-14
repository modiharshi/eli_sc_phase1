"""ELI MCP server (read-only). Same operations as the REST API: search, get judgment, get judge, Constitution Benches.
Run:  .venv/bin/python mcp/server.py        (stdio transport; add to an MCP client as a command)
It reads the database directly through the read-only role, so it needs the same .env as the web app.
Note: this directory has no __init__.py on purpose, so it cannot shadow the installed `mcp` package."""
import json
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))  # append, not insert: keep the real `mcp` package first

from mcp.server.mcpserver import MCPServer  # noqa: E402

from api import db, search  # noqa: E402
from api.common import ATTRIBUTION, NOT_OFFICIAL, json_default  # noqa: E402

mcp = MCPServer("eli-supreme-court")


def _out(payload):
    return json.dumps({"data": payload, "attribution": ATTRIBUTION, "notice": NOT_OFFICIAL}, default=json_default, ensure_ascii=False)


@mcp.tool()
def search_judgments(query: str, scope: str = "all", year_from: int | None = None, year_to: int | None = None, page: int = 1) -> str:
    """Search Supreme Court of India judgments. scope: all, title, text, parties, title_fuzzy, judge, identifier. Returns 20 results per page with facets."""
    p = {"q": query, "scope": scope, "page": str(page)}
    if year_from:
        p["year_from"] = str(year_from)
    if year_to:
        p["year_to"] = str(year_to)
    res = search.run(p)
    keep = ("judgment_id", "title", "decision_date", "disposal", "bench_strength", "insc_id", "citation", "text_status", "quality", "incomplete", "snippet")
    return _out({"total": res["total"], "page": res["page"], "pages": res["pages"], "results": [{k: r[k] for k in keep} for r in res["rows"]]})


@mcp.tool()
def get_judgment(judgment_id: str, include_text: bool = False) -> str:
    """Get one judgment's canonical record, judges and identifiers; optionally the English full text."""
    j = db.q1("select * from judgment_visible where judgment_id = %s::uuid", (judgment_id,))
    if not j:
        return _out({"error": "no such judgment"})
    j.pop("search_tsv", None)
    j["judges"] = db.q("select position, judge_name_norm, judge_id from judgment_judge where judgment_id = %s order by position", (judgment_id,))
    j["identifiers"] = db.q("select identifier_type, value from judgment_identifier where judgment_id = %s", (judgment_id,))
    if include_text:
        t = db.q1("select text from judgment_text where judgment_id = %s and language_code = 'en'", (judgment_id,))
        j["text_en"] = t["text"] if t else None
    return _out(j)


@mcp.tool()
def get_judge(judge_id: int) -> str:
    """Get a judge (all spelling variants resolved to one person) and their most recent judgments."""
    jd = db.q1("select * from judge where judge_id = %s", (judge_id,))
    if not jd:
        return _out({"error": "no such judge"})
    jd["judgments"] = db.q("""select j.judgment_id, j.title, j.decision_date, j.bench_strength from judgment_judge g join judgment_visible j using (judgment_id)
                              where g.judge_id = %s order by j.decision_date desc limit 100""", (judge_id,))
    return _out(jd)


@mcp.tool()
def list_constitution_benches(min_judges: int = 5, year_from: int = 0, year_to: int = 3000) -> str:
    """List judgments with at least min_judges judges on the bench. bench_effective is the larger of the source's judges list and an estimate read from the judgment text header (bench_basis says which); ~12% of judgments have no header estimate."""
    return _out(db.q("""select j.judgment_id, j.title, j.decision_date, b.bench_listed, b.bench_header, b.bench_effective, b.bench_basis, j.citation
                        from judgment_bench b join judgment_visible j using (judgment_id)
                        where b.bench_effective >= %s and j.decision_year between %s and %s order by j.decision_date limit 500""", (min_judges, year_from, year_to)))


if __name__ == "__main__":
    mcp.run()
