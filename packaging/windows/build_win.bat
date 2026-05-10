@echo off
:: DockMeow Windows build launcher — works from CMD (no PowerShell needed).
:: Usage: double-click, or from any CMD window at the repo root:
::
::   packaging\windows\build_win.bat
::
:: Optional arguments are forwarded to build_win.ps1, e.g.:
::   packaging\windows\build_win.bat -SkipInstaller
::   packaging\windows\build_win.bat -Sign "THUMBPRINT_HERE"
::
:: Prerequisites:
::   1. Python 3.11 (64-bit) in PATH  — https://www.python.org/downloads/
::   2. Inno Setup 6 (for installer)  — https://jrsoftware.org/isdl.php
::      (skip with -SkipInstaller if you only want DockMeow.exe)

setlocal EnableDelayedExpansion

:: ── Move to repo root (two levels above this script) ─────────────────────────
cd /d "%~dp0..\.."

echo.
echo ===================================================
echo   DockMeow Windows Build
echo ===================================================
echo.

:: ── 1. Verify Python is available ────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.11 ^(64-bit^) from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH" during installation.
    goto :fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo Using: %%v

:: ── 2. Create virtual environment if it doesn't exist ────────────────────────
if not exist ".venv-build\Scripts\python.exe" (
    echo.
    echo Creating virtual environment .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        goto :fail
    )
    echo   Done.
)

:: ── 3. Upgrade pip inside the venv ───────────────────────────────────────────
echo.
echo Upgrading pip...
.venv-build\Scripts\python.exe -m pip install --quiet --upgrade pip

:: ── 4. Install Windows build dependencies ────────────────────────────────────
echo.
echo Installing build dependencies (requirements-build-win.txt)...
.venv-build\Scripts\pip install --quiet --no-warn-script-location ^
    -r packaging\windows\requirements-build-win.txt
if errorlevel 1 (
    echo ERROR: Failed to install build dependencies.
    echo Check the error above; some packages may need Visual C++ Build Tools.
    goto :fail
)

:: ── 5. Install PyInstaller ───────────────────────────────────────────────────
.venv-build\Scripts\pip install --quiet --no-warn-script-location pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    goto :fail
)

:: ── 6. Install vina (Windows x64 PyPI wheel; ARM64: install via conda) ────────
echo.
echo Installing vina...
.venv-build\Scripts\pip install --quiet --no-warn-script-location vina
if errorlevel 1 (
    echo WARNING: vina could not be installed from PyPI.
    echo   x64:  This should not happen — check your internet connection.
    echo   ARM64: No PyPI wheel exists; install via conda in .venv-build or
    echo          copy the vina package from a conda env manually.
    echo   The build will continue but docking will not work without vina.
)

:: ── 7. Launch the PowerShell build script ────────────────────────────────────
echo.
echo Launching build via PowerShell...
echo.
powershell.exe -NoLogo -ExecutionPolicy Bypass ^
    -File "packaging\windows\build_win.ps1" %*
if errorlevel 1 (
    echo.
    echo Build FAILED. See errors above.
    goto :fail
)

echo.
echo Build complete.
goto :end

:fail
echo.
pause
exit /b 1

:end
pause
