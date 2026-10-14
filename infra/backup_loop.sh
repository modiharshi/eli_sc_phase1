#!/usr/bin/env bash
# Sandbox stand-in for a nightly job: sleeps until 02:15 local time, runs backup.sh, repeats. Stops if the container restarts.
# On a real machine use a systemd timer or cron instead:   15 2 * * *  bash /path/to/eli/infra/backup.sh
here="$(dirname "$0")"
while true; do
  now=$(date +%s); next=$(date -d "today 02:15" +%s); [ "$next" -le "$now" ] && next=$(date -d "tomorrow 02:15" +%s)
  sleep $((next - now)); bash "$here/backup.sh"
done
