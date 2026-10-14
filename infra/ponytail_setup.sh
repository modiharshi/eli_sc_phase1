#!/usr/bin/env bash
# Ponytail v5.2.0: disabled-by-default install and offline verification.
#
#   ponytail_setup.sh          install (user scope), disable, verify    [Cloud Setup script]
#   ponytail_setup.sh verify   verify only; never installs or enables
#
# Safety model: the plugin is DISABLED before anything is verified, and this script never
# enables it. Verification reads files and hashes them; it executes no plugin code.
# Activation is a separate, explicit step (docs/PONYTAIL.md). Always exits 0 so a failure
# here never blocks the Cloud session; the result is in $LOG and the final status line.
set +u
PIN=2961b52fc1fe6a5a87c7a959a79512e5c2f3ffe5
SRC='DietrichGebert/ponytail#v5.2.0'
ID='ponytail@ponytail'
LOG=${PONYTAIL_LOG:-/var/tmp/ponytail_setup.log}
MODE=${1:-setup}

log() { echo "$*" | tee -a "$LOG"; }
done_() { log "STATUS: $1"; exit 0; }

: > "$LOG"
log "ponytail_setup mode=$MODE $(date -u +%FT%TZ)"

command -v claude >/dev/null 2>&1 && command -v git >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 \
  || done_ "SKIPPED claude, git or python3 missing; plugin not installed (fail-open)"

if [ "$MODE" = setup ]; then
  # Second default-off route, read by the plugin's hooks if it is ever enabled.
  mkdir -p "$HOME/.config/ponytail"
  [ -e "$HOME/.config/ponytail/config.json" ] \
    || printf '{"defaultMode":"off"}\n' > "$HOME/.config/ponytail/config.json"

  if ! claude plugin list 2>/dev/null | grep -q 'ponytail@ponytail'; then
    claude plugin marketplace add "$SRC" --scope user >>"$LOG" 2>&1 \
      || done_ "SKIPPED marketplace add failed; plugin not installed (fail-open)"
    claude plugin install "$ID" --scope user >>"$LOG" 2>&1 \
      || done_ "SKIPPED install failed; plugin not installed (fail-open)"
  fi
  # Disable first, verify second. install enables by default; nothing runs between
  # install and this line because no Claude session exists yet.
  claude plugin disable "$ID" --scope user >>"$LOG" 2>&1 \
    || { claude plugin uninstall "$ID" --scope user >>"$LOG" 2>&1
         done_ "REMOVED could not disable after install; uninstalled (fail-closed)"; }
fi

# ---- verification (no plugin code is executed) ----
INFO=$(python3 -I - <<'PY'
import json, os
try:
    d = json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))
except Exception:
    raise SystemExit
for k, v in d.get('plugins', {}).items():
    if k.startswith('ponytail@'):
        e = v[0] if isinstance(v, list) else v
        print(e.get('gitCommitSha') or '-', e.get('installPath') or '-')
PY
)
GOT=${INFO%% *}; IPATH=${INFO#* }
[ -n "$INFO" ] && [ "$GOT" != "-" ] && [ -d "$IPATH" ] \
  || done_ "UNVERIFIED install record not found or incomplete; plugin stays disabled; do not activate"

remove() {
  claude plugin uninstall "$ID" --scope user >>"$LOG" 2>&1
  claude plugin marketplace remove ponytail >>"$LOG" 2>&1
  done_ "REMOVED $1 (fail-closed)"
}

[ "$GOT" = "$PIN" ] || remove "commit mismatch got=$GOT want=$PIN"

MP="$HOME/.claude/plugins/marketplaces/ponytail"
git -C "$MP" cat-file -e "$PIN^{commit}" 2>/dev/null \
  || done_ "UNVERIFIED pinned commit not present in marketplace clone; hashes not checked; do not activate"

# Every file the pinned commit ships must exist in the install with identical content,
# and the install must contain no executable file the commit does not ship.
bad=0; n=0
while IFS= read -r f; do
  want=$(git -C "$MP" show "$PIN:$f" 2>/dev/null | sha256sum | cut -d' ' -f1)
  have=$( [ -f "$IPATH/$f" ] && sha256sum < "$IPATH/$f" | cut -d' ' -f1 || echo MISSING )
  n=$((n+1))
  [ "$want" = "$have" ] || { log "HASH MISMATCH $f"; bad=1; }
done < <(git -C "$MP" ls-tree -r --name-only "$PIN")
while IFS= read -r f; do
  git -C "$MP" cat-file -e "$PIN:${f#./}" 2>/dev/null || { log "EXTRA FILE $f"; bad=1; }
done < <(cd "$IPATH" && find . -type f -not -path './.git/*' | sed 's#^\./##')
[ "$bad" = 0 ] || remove "file hash mismatch"

done_ "VERIFIED commit=$PIN files=$n; plugin installed but DISABLED. Activate only by explicit action (docs/PONYTAIL.md)"
