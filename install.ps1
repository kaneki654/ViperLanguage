# install.ps1 — Viper installer for Windows
# Usage:  powershell -ExecutionPolicy Bypass -File install.ps1
# Installs the viper command, then adds the editor extension to VS Code and Cursor.

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

Write-Host "=== Viper installer ===" -ForegroundColor Cyan

# --- 1. find a suitable Python (3.10+) ---------------------------------
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

# --- 2. install viper: pipx if available, else pip --user ---------------
$installed = $false
if (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "installing with pipx..."
    pipx install --force $repo
    $installed = $true
} else {
    Write-Host "pipx not found - installing with pip --user..."
    & $python -m pip install --user $repo
    $installed = $true
    # warn if the user Scripts dir is not on PATH
    $scripts = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"
    if ($env:Path -notlike "*$scripts*") {
        Write-Host ""
        Write-Host "note: '$scripts' is not on your PATH." -ForegroundColor Yellow
        Write-Host "      Add it (Settings > System > About > Advanced system settings" -ForegroundColor Yellow
        Write-Host "      > Environment Variables) so the 'viper' command works everywhere." -ForegroundColor Yellow
    }
}

# --- 3. editor extension: VS Code + Cursor ------------------------------
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

# --- 4. verify -----------------------------------------------------------
Write-Host ""
if (Get-Command viper -ErrorAction SilentlyContinue) {
    viper --version
    Write-Host "Viper is ready. Try:  viper repl" -ForegroundColor Cyan
} else {
    Write-Host "Installed, but 'viper' is not on PATH yet - open a NEW terminal and try 'viper --version'." -ForegroundColor Yellow
}
