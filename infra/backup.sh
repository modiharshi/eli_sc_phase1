#!/usr/bin/env bash
# Logical backup of the ELI database to a folder outside the repo. Safe to run any time; keeps the newest $KEEP dumps.
#   bash infra/backup.sh                      one dump now
#   bash infra/backup_loop.sh                 dump every night at 02:15 local time (no cron or systemd in the sandbox)
# Restore: see docs/RUNBOOK.md ("Restore from a dump").
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${ELI_BACKUP_DIR:-/var/backups/eli}"; KEEP="${KEEP:-2}"; MIN_FREE_GB="${MIN_FREE_GB:-4}"
mkdir -p "$DIR" "$ROOT/logs"
set -a; . "$ROOT/.env"; set +a
export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"
free_gb=$(df -P "$DIR" | awk 'NR==2{print int($4/1048576)}')
if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then echo "$(date -u +%FT%TZ) ABORT only ${free_gb} GB free (< $MIN_FREE_GB)" | tee -a "$ROOT/logs/backup.log"; exit 1; fi
out="$DIR/eli_$(date -u +%Y%m%dT%H%M%SZ).dump"
echo "$(date -u +%FT%TZ) start $out" >> "$ROOT/logs/backup.log"
if pg_dump -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5433}" -U eli_admin -d "${PGDATABASE:-eli}" -Fc -Z 6 -f "$out.part"; then
  # the archive must be listable end to end before it counts as a backup
  n=$(pg_restore --list "$out.part" | grep -c ' TABLE DATA ')
  mv "$out.part" "$out"
  echo "$(date -u +%FT%TZ) done $(du -h "$out" | cut -f1) ${n} table-data entries" | tee -a "$ROOT/logs/backup.log"
  ls -1t "$DIR"/eli_*.dump | tail -n +$((KEEP + 1)) | xargs -r rm -f
else
  rm -f "$out.part"; echo "$(date -u +%FT%TZ) FAILED" | tee -a "$ROOT/logs/backup.log"; exit 1
fi
