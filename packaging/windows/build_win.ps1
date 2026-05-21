# DockMeow Windows build script
#
# Recommended: run via the CMD launcher (no PowerShell setup needed)
#   Double-click  packaging\windows\build_win.bat
#   or from any CMD window at the repo root:
#   packaging\windows\build_win.bat
#
# Advanced: run directly from PowerShell
#   cd C:\path\to\DockMeow
#   python -m venv .venv-build-win-x64
#   .venv-build-win-x64\Scripts\pip install -r packaging\windows\requirements-build-win.txt pyinstaller
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_win.ps1
#
# Optional flags:
#   -Sign "thumbprint"   Code-sign DockMeow.exe with the given cert thumbprint
#   -SkipInstaller       Only run PyInstaller, skip Inno Setup
#
# Prerequisites on the Windows build machine:
#   1. Python 3.11 (64-bit) - https://www.python.org/downloads/
#      Tick "Add Python to PATH" during installation.
#   2. Inno Setup 6 - https://jrsoftware.org/isdl.php
#      Default install location is detected automatically; or add iscc to PATH.
#   Note: Windows ARM users should run the x64 installer under Windows emulation.
#         Native ARM64 wheels are not available for every scientific dependency.
#         Docking on Windows uses the bundled Vina executable fallback.

param(
    [string]$Sign          = "",
    [switch]$SkipInstaller = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Locate repo root (two levels up from this script)
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ROOT

# Version
$env:PYTHONPATH = "src"
$VENV_DIR = if ($env:DOCKMEOW_WIN_VENV) { $env:DOCKMEOW_WIN_VENV } else { ".venv-build-win-x64" }
$PYTHON   = Join-Path $VENV_DIR "Scripts\python.exe"
$PYI      = Join-Path $VENV_DIR "Scripts\pyinstaller.exe"

if (-not (Test-Path $PYTHON)) {
    throw "Python venv not found at $VENV_DIR. Create it with:`n  python -m venv $VENV_DIR`n  $VENV_DIR\Scripts\pip install -r packaging\windows\requirements-build-win.txt pyinstaller"
}

$PY_ARCH = & $PYTHON -c "import platform; print(platform.machine())"
if ($PY_ARCH -ne "AMD64") {
    throw "Windows x64 build requires AMD64 Python, but $VENV_DIR is $PY_ARCH. Recreate $VENV_DIR with Python 3.11 x64."
}

$VERSION  = & $PYTHON -c "from dockmeow.version import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0) { throw "Could not read version from src/dockmeow/version.py" }

$ARCH          = "x64"
$DIST_BASE     = "dist\windows-$ARCH"
$DIST_DIR      = "$DIST_BASE\DockMeow"
$DIST_EXE      = "$DIST_DIR\DockMeow.exe"
$INSTALLER_OUT = "dist\installers\DockMeow-Setup-$VERSION-$ARCH.exe"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  DockMeow $VERSION  Windows $ARCH build" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Step 1: PyInstaller
Write-Host "`nRunning PyInstaller..." -ForegroundColor Yellow

$env:PYTHONPATH = "src"
& $PYI packaging\dockmeow.spec --clean --noconfirm --distpath $DIST_BASE
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

if (-not (Test-Path $DIST_EXE)) {
    throw "ERROR: $DIST_EXE not found after PyInstaller run."
}

$SIZE_MB = [math]::Round(
    (Get-ChildItem $DIST_DIR -Recurse -ErrorAction SilentlyContinue |
     Measure-Object -Property Length -Sum).Sum / 1MB
)
Write-Host "  App directory: $DIST_DIR  ($SIZE_MB MB)" -ForegroundColor Gray

# Step 2: Verify QtWebEngineProcess.exe is present
Write-Host "`nChecking QtWebEngineProcess.exe..." -ForegroundColor Yellow
$webengine_proc = @(
    "$DIST_DIR\PySide6\Qt\bin\QtWebEngineProcess.exe",
    "$DIST_DIR\PySide6\QtWebEngineProcess.exe",
    "$DIST_DIR\_internal\PySide6\QtWebEngineProcess.exe",
    "$DIST_DIR\QtWebEngineProcess.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($webengine_proc) {
    Write-Host "  Found: $webengine_proc" -ForegroundColor Gray
} else {
    Write-Warning "QtWebEngineProcess.exe not found - 3D viewer may not work."
    Write-Warning "Check that PySide6.QtWebEngineWidgets is installed in the venv."
}

# Step 3: Code sign (optional)
if ($Sign) {
    Write-Host "`nCode signing DockMeow.exe (thumbprint: $Sign)..." -ForegroundColor Yellow
    $signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if (-not $signtool) {
        # Try Windows SDK default paths
        $sdk_paths = @(
            "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
            "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
        )
        $signtool = $sdk_paths | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $signtool) { Write-Warning "signtool.exe not found - skipping code signing." }
    } else {
        $signtool = $signtool.Source
    }

    if ($signtool) {
        & $signtool sign /sha1 $Sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /v $DIST_EXE
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Code signing failed (non-fatal - app will show SmartScreen warning)"
        } else {
            Write-Host "  Signed" -ForegroundColor Green
        }
    }
} else {
    Write-Host "`n  (skipping code signing - pass -Sign <thumbprint> to enable)" -ForegroundColor DarkGray
    Write-Host "  Users will see a Windows SmartScreen / UAC warning on first run." -ForegroundColor DarkGray
}

# Step 4: Inno Setup installer
if ($SkipInstaller) {
    Write-Host "`n  (skipping Inno Setup - -SkipInstaller was set)" -ForegroundColor DarkGray
    Write-Host "`nPyInstaller output ready: $DIST_DIR" -ForegroundColor Green
    exit 0
}

Write-Host "`nCreating installer with Inno Setup..." -ForegroundColor Yellow

# Locate ISCC.exe
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    $iscc = $iscc.Source
} else {
    $iscc_candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    )
    $iscc = $iscc_candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $iscc) {
    throw "Inno Setup (ISCC.exe) not found.`nInstall from https://jrsoftware.org/isdl.php`nor add ISCC.exe to PATH."
}

Write-Host "  ISCC: $iscc" -ForegroundColor Gray
New-Item -ItemType Directory -Force -Path "dist\installers" | Out-Null

# Pass version as a define so installer.iss doesn't need to be edited per release
& $iscc `
    "/DMyAppVersion=$VERSION" `
    "/DMyAppSourceDir=..\..\$DIST_DIR" `
    "packaging\windows\installer.iss"

if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed (exit $LASTEXITCODE)" }

if (Test-Path $INSTALLER_OUT) {
    $INST_MB = [math]::Round((Get-Item $INSTALLER_OUT).Length / 1MB)
    Write-Host ""
    Write-Host "Installer ready: $INSTALLER_OUT  ($INST_MB MB)" -ForegroundColor Green
} else {
    # Inno Setup may use a slightly different filename; find it
    $found = Get-ChildItem "dist\installers" -Filter "DockMeow-Setup*.exe" |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($found) {
        Write-Host ""
        Write-Host "Installer ready: $($found.FullName)  ($([math]::Round($found.Length/1MB)) MB)" -ForegroundColor Green
    } else {
        Write-Warning "Expected installer not found at $INSTALLER_OUT"
    }
}
