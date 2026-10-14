#!/usr/bin/env bash
# Create (or start) the local ELI PostgreSQL 16 cluster. Idempotent. Run as root.
#  - listens on 127.0.0.1 only (not reachable from outside this machine)
#  - role eli_admin: owns the database, used by the pipeline
#  - role eli_readonly: SELECT only, read-only transactions, 15 s statement timeout (for the frontend / SQL console)
# Passwords are generated once into .env (git-ignored). Commit only .env.example.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN=/usr/lib/postgresql/16/bin
PGDATA="${ELI_PGDATA:-/var/lib/eli_pg/data}"
PORT="${PGPORT:-5433}"
ENVF="$ROOT/.env"

touch "$ENVF"; chmod 600 "$ENVF"
getenv() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2- || true; }
setenv() { grep -qE "^$1=" "$ENVF" || echo "$1=$2" >> "$ENVF"; }
setenv POSTGRES_ADMIN_PASSWORD "$(openssl rand -hex 16)"
setenv POSTGRES_READONLY_PASSWORD "$(openssl rand -hex 16)"
setenv PGHOST 127.0.0.1
setenv PGPORT "$PORT"
setenv PGDATABASE eli
ADMIN_PW="$(getenv POSTGRES_ADMIN_PASSWORD)"; RO_PW="$(getenv POSTGRES_READONLY_PASSWORD)"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  mkdir -p "$(dirname "$PGDATA")"; chown postgres:postgres "$(dirname "$PGDATA")"
  su postgres -c "$BIN/initdb -D $PGDATA -A trust -E UTF8 --locale=C.UTF-8 >/dev/null"
  cat >> "$PGDATA/postgresql.conf" <<CONF

# --- ELI settings (see docs/RUNBOOK.md) ---
listen_addresses = '127.0.0.1'
port = $PORT
shared_buffers = 3GB
effective_cache_size = 9GB
maintenance_work_mem = 2GB
work_mem = 32MB
max_parallel_maintenance_workers = 3
max_parallel_workers_per_gather = 2
wal_level = minimal            # lets the single-transaction bulk load skip WAL; backups use pg_dump
max_wal_senders = 0
wal_compression = on
max_wal_size = 6GB
min_wal_size = 512MB
checkpoint_timeout = 15min
random_page_cost = 1.1
jit = off
CONF
  # password auth for TCP, local socket only for the postgres OS user
  cat > "$PGDATA/pg_hba.conf" <<HBA
local all postgres peer
host  all all 127.0.0.1/32 scram-sha-256
HBA
fi

if ! su postgres -c "$BIN/pg_ctl -D $PGDATA status" >/dev/null 2>&1; then
  su postgres -c "$BIN/pg_ctl -D $PGDATA -l $PGDATA/../server.log start -w" >/dev/null
fi

PSQL="su postgres -c"
$PSQL "psql -p $PORT -Atq -d postgres" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eli_admin') THEN CREATE ROLE eli_admin LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eli_readonly') THEN CREATE ROLE eli_readonly LOGIN; END IF;
END \$\$;
ALTER ROLE eli_admin PASSWORD '$ADMIN_PW';
ALTER ROLE eli_readonly PASSWORD '$RO_PW';
ALTER ROLE eli_readonly SET default_transaction_read_only = on;
ALTER ROLE eli_readonly SET statement_timeout = '15s';
SQL
# limited write role for the web app (sessions, bookmarks, notes, reviews); see pipeline/11_derive.py
APP_PW=$(grep -s '^POSTGRES_APP_PASSWORD=' "$ENVF" | cut -d= -f2-)
if [ -z "$APP_PW" ]; then APP_PW=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))'); printf '\nPOSTGRES_APP_PASSWORD=%s\n' "$APP_PW" >> "$ENVF"; fi
$PSQL "psql -p $PORT -Atq -d postgres" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eli_app') THEN CREATE ROLE eli_app LOGIN; END IF;
END \$\$;
ALTER ROLE eli_app PASSWORD '$APP_PW';
SQL
su postgres -c "psql -p $PORT -Atq -d postgres -c \"SELECT 1 FROM pg_database WHERE datname='eli'\"" | grep -q 1 || \
  su postgres -c "psql -p $PORT -q -d postgres -c 'CREATE DATABASE eli OWNER eli_admin'"
su postgres -c "psql -p $PORT -q -d eli" <<SQL
REVOKE ALL ON DATABASE eli FROM PUBLIC;
GRANT CONNECT ON DATABASE eli TO eli_readonly, eli_admin, eli_app;
GRANT USAGE ON SCHEMA public TO eli_readonly;
ALTER SCHEMA public OWNER TO eli_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE eli_admin IN SCHEMA public GRANT SELECT ON TABLES TO eli_readonly;
SQL
echo "PostgreSQL ready on 127.0.0.1:$PORT (database eli). Credentials are in $ENVF"
