# Runbook (local, Stages 1 to 6)

Everything runs on this machine. Nothing is exposed beyond `127.0.0.1`. `raw/`, `build/`, `logs/` and `.env` are git-ignored.

## Order of stages

| step | command | what it does | rerun safe |
|---|---|---|---|
| 1a | `pipeline/01_download_vanga.sh` | anonymous `aws s3 sync` of Vanga metadata into `raw/vanga/` | yes, resumes |
| 1b | `pipeline/02_download_vaquill.sh` | resumable download of the Supreme Court file and central legislation into `raw/vaquill/` | yes, resumes |
| 2 | `.venv/bin/python -I pipeline/03_profile_schemas.py` | writes `docs/SCHEMA_COMPARISON.md` | yes |
| 3a | `.venv/bin/python -I pipeline/04_manifest.py` | checksums all raw files; the first run records `raw/MANIFEST.sha256`, later runs fail if anything changed | yes |
| 3b | `.venv/bin/python -I pipeline/05_build_canonical.py` | builds `build/*.parquet` (about 4 minutes); reports whether two builds are identical | yes, deterministic |
| 3c | `.venv/bin/python -I pipeline/06_validate_stage3.py` | independent checks, writes `docs/STAGE3_VALIDATION.md` (about 25 minutes) | yes |
| 4a | `bash infra/pg_setup.sh` | creates or starts the PostgreSQL 16 cluster, roles and database | yes |
| 4b | `.venv/bin/python -I pipeline/07_load_postgres.py [--rebuild]` | single-transaction load (about 10 minutes). Refuses to touch a loaded database without `--rebuild` | yes with `--rebuild` |
| 4c | `.venv/bin/python -I pipeline/08_verify_postgres.py` | counts, content fingerprints, constraints, orphans, negative tests | yes |
| 4d | `.venv/bin/python -I pipeline/09_index_benchmark.py --apply` | applies the kept indexes from `db/migrations/0007_indexes.sql` (about 15 minutes, mostly the full-text column) | run once after a load |
| 4e | `.venv/bin/python -I pipeline/09_index_benchmark.py` | the full index experiment (about 40 minutes); needs an un-indexed database, so run it right after `07 --rebuild` | after a rebuild |
| 4f | `.venv/bin/python -I pipeline/10_stage4_report.py` | writes `docs/STAGE4_REPORT.md` from the measurement files | yes |
| 5a | `.venv/bin/python -I pipeline/11_derive.py` | applies migration 0008+, creates role `eli_app`, builds judges and aliases, text quality (about 4 minutes), refreshes facet views | yes |
| 5b | `.venv/bin/python -I pipeline/13_bench_estimate.py` | bench size from text headers into `judgment_bench_estimate` (needs migration 0009 applied by hand: `psql -f db/migrations/0009_bench_estimate.sql`) | yes |
| 5c | `.venv/bin/python -I pipeline/12_title_fuzzy_check.py` | the `title_fuzzy` threshold measurement | yes |

After `07 --rebuild`, run `09 --apply`, then `11_derive.py`, then apply 0009 and run `13_bench_estimate.py`, to get back to the current state.

Long jobs: start them with `setsid nohup ... > logs/NAME.log 2>&1 < /dev/null &` so closing the session does not stop them, and read the log.

## Setting up from nothing

```bash
uv venv .venv && uv pip install --python .venv/bin/python duckdb pyarrow "psycopg[binary]"
pipeline/01_download_vanga.sh && pipeline/02_download_vaquill.sh
.venv/bin/python -I pipeline/04_manifest.py
.venv/bin/python -I pipeline/05_build_canonical.py
bash infra/pg_setup.sh                       # as root; writes .env with generated passwords
.venv/bin/python -I pipeline/07_load_postgres.py
.venv/bin/python -I pipeline/09_index_benchmark.py --apply
.venv/bin/python -I pipeline/08_verify_postgres.py
```

## PostgreSQL

* Cluster: `/var/lib/eli_pg/data`, port **5433**, database `eli`, listening on 127.0.0.1 only. Start or create it with `bash infra/pg_setup.sh` (safe to rerun). Log: `/var/lib/eli_pg/server.log`.
* Roles: `eli_admin` (owns the database; used by the pipeline) and `eli_readonly` (SELECT only, read-only transactions, 15 s statement timeout; for the frontend and SQL console). Passwords are in `.env`; commit only `.env.example`.
* `wal_level = minimal`: the load skips WAL, so there is no replication or point-in-time recovery. Back up with `pg_dump -Fc` (see below).
* Connect: `PGPASSWORD=$(grep POSTGRES_ADMIN_PASSWORD .env | cut -d= -f2) psql -h 127.0.0.1 -p 5433 -U eli_admin eli`.

## The web app (Stages 5 and 6)

```bash
bash infra/pg_setup.sh                                   # makes sure PostgreSQL and the roles exist
(nohup bash infra/run_app.sh >/dev/null 2>&1 &)          # http://127.0.0.1:8000 , log in logs/app.log
python -m api.manage create-user NAME admin|tester|viewer      # asks for a password
python -m api.manage create-api-key LABEL                       # key is shown once; REST: /api/v1/*, header X-API-Key
python -m api.manage hide JUDGMENT_ID "reason"                  # or unhide; also on the Admin page
.venv/bin/python mcp/server.py                                  # MCP server on stdio; add as a command in an MCP client
ELI_ADMIN_PASSWORD=... .venv/bin/python -m pytest tests -q      # 47 tests against the running app
ELI_ADMIN_PASSWORD=... .venv/bin/python tests/shots.py          # headless browser pass, screenshots in logs/shots
```
Python changes need an app restart (kill the `uvicorn api.app` process and start it again); template changes do not. Run python with `python -m ...` from the repo root so `api` imports resolve. `ELI_ADMIN_PASSWORD` in `.env` is the dev login used by the tests; replace the `admin` password and delete that line for real use.

Reset a password: `UPDATE app_user SET password_hash = ... WHERE username = ...` with an argon2 hash from `python -c "from argon2 import PasswordHasher as P; print(P().hash('NEW'))"`.

## Backup and restore

`bash infra/backup.sh` writes a compressed custom-format dump to `/var/backups/eli` (outside the repo), refuses to start with under 4 GB free, checks the archive can be listed, and keeps the newest 2. `bash infra/backup_loop.sh` repeats it nightly at 02:15; this sandbox has no cron or systemd, so the loop dies if the container restarts. On a normal host use cron (`15 2 * * *`) or a systemd timer.

**Restore from a dump** into a scratch database (needs the `postgres` OS user because `eli_admin` cannot create databases):
```bash
su postgres -c "createdb -p 5433 eli_restore_test"
su postgres -c "pg_restore -p 5433 --no-owner -d eli_restore_test /var/backups/eli/eli_YYYYMMDDTHHMMSSZ.dump"
```
A full restore needs about 11 GB of free disk (the data plus rebuilding the indexes); on this machine only about 10 GB was free, so the restore test was done on the small tables only (see `STAGE5_6_REPORT.md`).

Older manual form:

```bash
pg_dump -h 127.0.0.1 -p 5433 -U eli_admin -Fc eli > /path/outside/repo/eli_$(date +%F).dump
createdb ... eli_scratch && pg_restore -d eli_scratch /path/outside/repo/eli_YYYY-MM-DD.dump   # test restores into a scratch database
```

The database is fully reproducible from `raw/` (stages 3 and 4), so a dump is a convenience, not the only copy.

## Adding or changing data

Raw files are never edited. To refresh Vanga (it updates about twice a month): rerun `01`, then `04` (it will list the new files as ADDED and exit non-zero; after reviewing, delete `raw/MANIFEST.sha256` to record the new baseline), then `05`, `06`, `07 --rebuild`, `09 --apply`, `08`.

## Tearing down

`su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/eli_pg/data stop"`; remove `/var/lib/eli_pg` to delete the database. Nothing else is running.
