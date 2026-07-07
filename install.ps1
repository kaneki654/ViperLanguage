# install.ps1 — Viper installer for Windows
# Usage:  powershell -ExecutionPolicy Bypass -File install.ps1
# Does everything: installs the viper command, puts it on your PATH
# automatically, and adds the editor extension to VS Code and Cursor.

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

Write-Host "=== Viper installer ===" -ForegroundColor Cyan

# --- helpers -------------------------------------------------------------
function Add-ToUserPath([string]$dir) {
    if (-not $dir -or -not (Test-Path $dir)) { return }
    # persist to the *user* PATH (no admin needed); .NET broadcasts the
    # change so newly opened terminals pick it up without a reboot
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $current) { $current = "" }
    $parts = $current -split ";" | Where-Object { $_ }
    if ($parts -notcontains $dir) {
        [Environment]::SetEnvironmentVariable("Path", (($parts + $dir) -join ";"), "User")
        Write-Host "added to PATH: $dir" -ForegroundColor Green
    }
    # also patch THIS session so 'viper' works right away
    if (($env:Path -split ";") -notcontains $dir) {
        $env:Path = "$env:Path;$dir"
    }
}

# --- 1. find a suitable Python (3.10+) -----------------------------------
$python = $null
foreach ($cand in @("python", "py")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        try {
            $v = & $cand -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))" 2>$null
            if ($v -and ([version]$v -ge [version]"3.10")) { $python = $cand; break }
        } catch {}
    }
}
if (-not $python) {
    Write-Host "error: Python 3.10+ not found. Install it from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "       (check 'Add python.exe to PATH' in the installer!)" -ForegroundColor Red
    exit 1
}
Write-Host "using $python ($(& $python --version))"

# --- 2. install viper: pipx if available, else pip --user -----------------
if (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "installing with pipx..."
    pipx install --force $repo
    pipx ensurepath *> $null
    # pipx's shim directory, so this session works immediately too
    try { $pipxBin = pipx environment --value PIPX_BIN_DIR 2>$null } catch { $pipxBin = $null }
    if (-not $pipxBin) { $pipxBin = Join-Path $env:USERPROFILE ".local\bin" }
    Add-ToUserPath $pipxBin
} else {
    Write-Host "pipx not found - installing with pip --user..."
    & $python -m pip install --user $repo
    $scripts = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"
    Add-ToUserPath $scripts
}

# --- 3. editor extension: VS Code + Cursor --------------------------------
$ext = Join-Path $repo "editor\vscode\viper"
$targets = @(
    (Join-Path $env:USERPROFILE ".vscode\extensions"),
    (Join-Path $env:USERPROFILE ".cursor\extensions")
)
foreach ($dir in $targets) {
    if (Test-Path (Split-Path $dir)) {
        $dest = Join-Path $dir "viper-lang.viper-1.0.0"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Recurse -Force "$ext\*" $dest
        Write-Host "editor extension installed -> $dest" -ForegroundColor Green
    }
}
Write-Host "(restart VS Code / Cursor to activate .vp highlighting)"

# --- 4. verify -------------------------------------------------------------
Write-Host ""
if (Get-Command viper -ErrorAction SilentlyContinue) {
    viper --version
    Write-Host ""
    Write-Host "Viper is ready to use RIGHT NOW in this window. Try:  viper repl" -ForegroundColor Cyan
    Write-Host "(other terminals that are already open need to be reopened once)"
} else {
    Write-Host "Installed, but 'viper' was not found - close this terminal, open a new one," -ForegroundColor Yellow
    Write-Host "and run 'viper --version'. If it still fails, tell me the output of:" -ForegroundColor Yellow
    Write-Host "  $python -m pip show viper-lang" -ForegroundColor Yellow
}
