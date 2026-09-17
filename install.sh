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

git_hint() {
  case "$(uname -s)" in
    Darwin) printf '  brew install git   (or: xcode-select --install)' ;;
    *)      printf '  sudo apt install git   (or your distribution'\''s package manager)' ;;
  esac
}
TARGET_DIR="${BEA_DIR:-projectBEA}"

# the wordmark, in the one typeface a terminal has. `#` wherever the locale
# cannot promise the block character survives the trip to the screen
banner() {
  local ink='#'
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) ink='█' ;;
  esac
  printf '%s' "$BOLD"
  # 66 columns; anything narrower gets the name on one line instead
  if [ "${COLUMNS:-$(tput cols 2>/dev/null || echo 80)}" -ge 70 ]; then
    tr '#' "$ink" <<'ART'
  ####  ####   ###    ### #####  #### #####       ####  #####  ###
  #   # #   # #   #    #  #     #       #         #   # #     #   #
  ####  ####  #   #    #  ####  #       #         ####  ####  #####
  #     #  #  #   # #  #  #     #       #         #   # #     #   #
  #     #   #  ###   ##   #####  ####   #         ####  ##### #   #
ART
  else
    printf '  projectBEA\n'
  fi
  printf '%s  an AI persona engine%s\n' "$DIM" "$RESET"
}

banner

# --- 1. the repository ------------------------------------------------------
# piping this script from curl means there is no clone yet; running it from one
# means there is. Handle both rather than documenting two commands.

if [ -f "pyproject.toml" ] && grep -q 'name = "projectbea"' pyproject.toml 2>/dev/null; then
  ok "already inside the repository"
else
  step "Downloading ProjectBEA"
  # not installed for you on purpose: every package manager that can do it
  # wants root, and a script people pipe from curl should not be asking for it
  command -v git >/dev/null 2>&1 || die "git is required to download ProjectBEA.
    $(git_hint)
  Then run this again. You can also download the repository as a zip, but then
  \`uv run bea --update\` cannot keep your prompts across a new version."
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

# the dashboard is not the only javascript she has: her discord voice is a node
# program of its own, and installing only the dashboard left the skill switched
# on in the UI and dead in the process
step "Building the dashboard and the discord bot"
if command -v npm >/dev/null 2>&1; then
  uv run bea --install-node
  ok "dashboard and discord bot ready"
else
  warn "Node.js not found — skipping the dashboard and the discord bot."
  warn "Install Node 20+ from https://nodejs.org, then run: uv run bea --install-node"
fi

# --- 5. configuration -------------------------------------------------------

step "Configuration"

# Piped from curl, this script *is* this shell's standard input — so the wizard
# would read the rest of itself instead of an answer, and the arrow keys would
# have nowhere to come from. /dev/tty is the terminal the person is actually at.
if [ -t 0 ]; then
  uv run bea --setup
elif [ -r /dev/tty ]; then
  uv run bea --setup < /dev/tty
else
  warn "No terminal to ask questions on."
  warn "Run this yourself when you have one:  uv run bea --setup"
  exit 0
fi

printf '\n  %sShe is installed.%s  Next:\n\n' "$BOLD" "$RESET"
printf '    %suv run bea --web%s       the dashboard on http://127.0.0.1:8000\n' "$BOLD" "$RESET"
printf '    %suv run bea%s             the same engine, in the terminal\n' "$BOLD" "$RESET"
printf '    %suv run bea --doctor%s    checks this machine and says what to fix\n\n' "$BOLD" "$RESET"
