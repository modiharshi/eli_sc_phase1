# ELI: Indian Supreme Court data platform (beta, local)

Builds one canonical database of Supreme Court judgments from two open datasets and loads it into a local PostgreSQL.

* **Vanga** (Supreme Court metadata, public S3 bucket) is the canonical source for judgment records.
* **Vaquill** (Open India Law, Hugging Face) adds full text split into language-specific chunks, and a judges list.

Status: stages 1 to 6 done (download, profile, canonical merge, PostgreSQL load and indexes, web app, quick wins, REST API and MCP server). Not built: benchmark scorecard and advocate test (Stage 8), LLM features (Stage 9), original PDFs (Stage 10), HTTPS and public takedown form (the app is localhost-only). Start it with `bash infra/run_app.sh`, then open http://127.0.0.1:8000.

| read this | for |
|---|---|
| `docs/SCHEMA_COMPARISON.md` | what the two sources contain and how they differ |
| `docs/STAGE3_SCHEMA.md` | the canonical schema, merge rules and validation plan |
| `docs/STAGE3_VALIDATION.md` | results of the Stage 3 checks |
| `docs/STAGE4_REPORT.md` | load, constraints, language and completeness reconciliation, sizes, index experiment, timings |
| `docs/DECISIONS.md` | every choice and every place the data differed from the plan |
| `docs/STAGE5_6_REPORT.md` | what the web app and the nine quick wins do, test results, limits |
| `docs/V3_GAP_ANALYSIS.md` | gaps between the v3 brief and the Stage 4 build, and how they were closed |
| `docs/BENCH_ESTIMATE.md` | why bench size needed a header-based estimate, and how good it is |
| `docs/LICENCES.md`, `docs/SOURCE_PROFILE.md` | licence and attribution notes; source file and row counts |
| `docs/RUNBOOK.md` | how to rerun, run the app, back up, restore and tear down |

Layout: `pipeline/` numbered scripts, `db/migrations/` SQL, `api/` web app and REST API, `mcp/` MCP server, `tests/`, `infra/` PostgreSQL, app and backup scripts, `docs/`, `raw/` (untouched downloads, git-ignored), `build/` (generated tables, git-ignored). Credentials live in `.env` (git-ignored; see `.env.example`).
