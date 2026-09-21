#!/usr/bin/env bash
set -euo pipefail

# Sync the repository's canonical SHURA identity/context into Hermes.
# This script backs up the current live Hermes files before replacing them.
# It intentionally does not touch ~/.hermes/config.yaml or secrets.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$HERMES_HOME/shura-backups/$STAMP"

mkdir -p "$BACKUP_DIR" "$HERMES_HOME/skills/shura"

backup_if_present() {
  local src="$1"
  local dst_name="$2"
  if [[ -f "$src" ]]; then
    cp -p "$src" "$BACKUP_DIR/$dst_name"
  fi
}

backup_if_present "$HERMES_HOME/SOUL.md" "SOUL.md"
backup_if_present "$HERMES_HOME/skills/shura/SKILL.md" "SKILL.md"

install -m 600 "$REPO_ROOT/docs/shura/SOUL.md" "$HERMES_HOME/SOUL.md"
install -m 600 "$REPO_ROOT/docs/shura/SHURA_SKILL.md" "$HERMES_HOME/skills/shura/SKILL.md"

cat > "$BACKUP_DIR/MANIFEST.txt" <<EOF
SHURA Hermes context sync
Timestamp: $STAMP
Repository: $REPO_ROOT
Hermes home: $HERMES_HOME
Installed:
  docs/shura/SOUL.md -> ~/.hermes/SOUL.md
  docs/shura/SHURA_SKILL.md -> ~/.hermes/skills/shura/SKILL.md
Backup: $BACKUP_DIR

Not modified:
  ~/.hermes/config.yaml
  ~/.hermes/.env
  ~/.hermes/auth.json
  ~/.hermes/memories/*
EOF

printf '\nSHURA context synced.\nBackup: %s\n' "$BACKUP_DIR"
printf '\nNext verification commands:\n'
printf '  hermes doctor\n'
printf '  hermes config show\n'
printf '  hermes prompt-size\n'
printf '  hermes -z "Respond with exactly: SHURA CONTEXT SYNC PASSED"\n'
printf '\nThe final smoke test is intentionally identity-focused; inspect the output before treating the sync as complete.\n'
