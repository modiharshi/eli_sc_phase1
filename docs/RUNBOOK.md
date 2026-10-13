# Runbook (local, Stages 1 to 4)

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

## Backup and restore (manual for now; no schedule yet)

```bash
pg_dump -h 127.0.0.1 -p 5433 -U eli_admin -Fc eli > /path/outside/repo/eli_$(date +%F).dump
createdb ... eli_scratch && pg_restore -d eli_scratch /path/outside/repo/eli_YYYY-MM-DD.dump   # test restores into a scratch database
```

The database is fully reproducible from `raw/` (stages 3 and 4), so a dump is a convenience, not the only copy.

## Adding or changing data

Raw files are never edited. To refresh Vanga (it updates about twice a month): rerun `01`, then `04` (it will list the new files as ADDED and exit non-zero; after reviewing, delete `raw/MANIFEST.sha256` to record the new baseline), then `05`, `06`, `07 --rebuild`, `09 --apply`, `08`.

## Tearing down

`su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/eli_pg/data stop"`; remove `/var/lib/eli_pg` to delete the database. Nothing else is running.
