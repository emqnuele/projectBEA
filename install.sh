#!/usr/bin/env bash
#
# ProjectBEA bootstrap — macOS and Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/emqnuele/projectBEA/main/install.sh | bash
#
# or, from a clone:  ./install.sh
#
# Installs uv if missing, syncs dependencies, builds the dashboard when Node is
# available, and hands over to the interactive wizard.

set -euo pipefail

BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
RED=$'\033[31m'; CYAN=$'\033[36m'; RESET=$'\033[0m'

step() { printf '\n%s==>%s %s%s%s\n' "$CYAN" "$RESET" "$BOLD" "$1" "$RESET"; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()  { printf '\n  %s✗%s %s\n\n' "$RED" "$RESET" "$1" >&2; exit 1; }

REPO_URL="https://github.com/emqnuele/projectBEA.git"
TARGET_DIR="${BEA_DIR:-projectBEA}"

printf '\n%sProjectBEA%s %s— an AI persona engine%s\n' "$BOLD" "$RESET" "$DIM" "$RESET"

# --- 1. the repository ------------------------------------------------------
# piping this script from curl means there is no clone yet; running it from one
# means there is. Handle both rather than documenting two commands.

if [ -f "pyproject.toml" ] && grep -q 'name = "projectbea"' pyproject.toml 2>/dev/null; then
  ok "already inside the repository"
else
  step "Downloading ProjectBEA"
  command -v git >/dev/null 2>&1 || die "git is required. Install it and run this again."
  [ -d "$TARGET_DIR" ] && die "$TARGET_DIR already exists. Remove it, or run ./install.sh from inside it."
  git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
  cd "$TARGET_DIR"
  ok "cloned into $(pwd)"
fi

# --- 2. uv ------------------------------------------------------------------

step "Checking uv"
if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version | awk '{print $2}')"
else
  warn "uv not found — installing from astral.sh"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # the installer edits the shell profile, which does not affect this process
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv installed but is not on PATH. Open a new terminal and run ./install.sh again."
  ok "uv installed"
fi

# --- 3. python dependencies -------------------------------------------------

step "Installing Python dependencies"
printf '  %sthis downloads a few hundred MB the first time%s\n' "$DIM" "$RESET"
uv sync
ok "dependencies ready"

# --- 4. the dashboard -------------------------------------------------------

step "Building the dashboard"
if command -v npm >/dev/null 2>&1; then
  (cd src/web/frontend && npm install --silent && npm run build >/dev/null)
  ok "dashboard built"
else
  warn "Node.js not found — skipping the dashboard."
  warn "Install Node 18+ from https://nodejs.org, then run: make frontend"
fi

# --- 5. configuration -------------------------------------------------------

step "Configuration"
uv run bea --setup
