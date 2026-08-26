# ProjectBEA bootstrap — Windows.
#
#   irm https://raw.githubusercontent.com/emqnuele/projectBEA/main/install.ps1 | iex
#
# or, from a clone:  .\install.ps1
#
# Installs uv if missing, syncs dependencies, builds the dashboard when Node is
# available, and hands over to the interactive wizard.

$ErrorActionPreference = "Stop"

function Step($text) { Write-Host "`n==> " -ForegroundColor Cyan -NoNewline; Write-Host $text -ForegroundColor White }
function Ok($text)   { Write-Host "  " -NoNewline; Write-Host "OK " -ForegroundColor Green -NoNewline; Write-Host $text }
function Warn($text) { Write-Host "  " -NoNewline; Write-Host "!  " -ForegroundColor Yellow -NoNewline; Write-Host $text }
function Die($text)  { Write-Host "`n  " -NoNewline; Write-Host "x  $text`n" -ForegroundColor Red; exit 1 }

$RepoUrl   = "https://github.com/emqnuele/projectBEA.git"
$TargetDir = if ($env:BEA_DIR) { $env:BEA_DIR } else { "projectBEA" }

Write-Host "`nProjectBEA " -ForegroundColor White -NoNewline
Write-Host "- an AI persona engine" -ForegroundColor DarkGray

# --- 1. the repository ------------------------------------------------------
# piped from irm there is no clone yet; run from one there is. Handle both.

if ((Test-Path "pyproject.toml") -and (Select-String -Path "pyproject.toml" -Pattern 'name = "projectbea"' -Quiet)) {
    Ok "already inside the repository"
} else {
    Step "Downloading ProjectBEA"
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die "git is required. Install it and run this again." }
    if (Test-Path $TargetDir) { Die "$TargetDir already exists. Remove it, or run .\install.ps1 from inside it." }
    git clone --depth 1 $RepoUrl $TargetDir
    Set-Location $TargetDir
    Ok "cloned into $(Get-Location)"
}

# --- 2. uv ------------------------------------------------------------------

Step "Checking uv"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Ok "uv $((uv --version) -split ' ' | Select-Object -Last 1)"
} else {
    Warn "uv not found - installing from astral.sh"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    # the installer edits the user PATH, which this process does not inherit
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Die "uv installed but is not on PATH. Open a new terminal and run .\install.ps1 again."
    }
    Ok "uv installed"
}

# --- 3. python dependencies -------------------------------------------------

Step "Installing Python dependencies"
Write-Host "  this downloads a few hundred MB the first time" -ForegroundColor DarkGray
uv sync
Ok "dependencies ready"

# --- 4. the dashboard -------------------------------------------------------

Step "Building the dashboard"
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location src\web\frontend
    npm install --silent
    npm run build | Out-Null
    Pop-Location
    Ok "dashboard built"
} else {
    Warn "Node.js not found - skipping the dashboard."
    Warn "Install Node 18+ from https://nodejs.org, then run: make frontend"
}

# --- 5. configuration -------------------------------------------------------

Step "Configuration"
uv run bea --setup
