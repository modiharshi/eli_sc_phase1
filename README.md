# ELI: Indian Supreme Court data platform (beta, local)

Builds one canonical database of Supreme Court judgments from two open datasets and loads it into a local PostgreSQL.

* **Vanga** (Supreme Court metadata, public S3 bucket) is the canonical source for judgment records.
* **Vaquill** (Open India Law, Hugging Face) adds full text split into language-specific chunks, and a judges list.

Status: stages 1 to 4 done (download, profile, canonical merge, PostgreSQL load and indexes). The frontend (stage 5), deployment, benchmark scorecard and PDFs are not built yet.

| read this | for |
|---|---|
| `docs/SCHEMA_COMPARISON.md` | what the two sources contain and how they differ |
| `docs/STAGE3_SCHEMA.md` | the canonical schema, merge rules and validation plan |
| `docs/STAGE3_VALIDATION.md` | results of the Stage 3 checks |
| `docs/STAGE4_REPORT.md` | load, constraints, language and completeness reconciliation, sizes, index experiment, timings |
| `docs/DECISIONS.md` | every choice and every place the data differed from the plan |
| `docs/RUNBOOK.md` | how to rerun, restore and tear down |

Layout: `pipeline/` numbered scripts, `db/migrations/` SQL, `infra/` PostgreSQL setup, `docs/`, `raw/` (untouched downloads, git-ignored), `build/` (generated tables, git-ignored). Credentials live in `.env` (git-ignored; see `.env.example`).
