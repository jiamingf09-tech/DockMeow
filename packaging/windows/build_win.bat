@echo off
:: DockMeow Windows build — pure CMD, no PowerShell required.
:: Usage: double-click  OR  from any CMD window at the repo root:
::
::   packaging\windows\build_win.bat
::
:: Prerequisites:
::   1. Python 3.11 (64-bit) — https://www.python.org/downloads/
::      Tick "Add Python to PATH" during installation.
::   2. Inno Setup 6 (optional, for the .exe installer)
::      https://jrsoftware.org/isdl.php

setlocal EnableDelayedExpansion

:: ── Locate repo root (two levels above this script) ──────────────────────────
pushd "%~dp0..\.."

echo.
echo ====================================================
echo   DockMeow Windows Build
echo ====================================================
echo.

:: ── 1. Verify Python ─────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.11 from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH".
    goto :fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo Using: %%v

:: ── 2. Create venv if needed ─────────────────────────────────────────────────
if not exist ".venv-build\Scripts\python.exe" (
    echo.
    echo Creating virtual environment .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 ( echo ERROR: venv creation failed. & goto :fail )
    echo   Created.
)

:: ── 3. Upgrade pip ───────────────────────────────────────────────────────────
echo.
echo Upgrading pip...
.venv-build\Scripts\python.exe -m pip install --quiet --upgrade pip

:: ── 4. Install Windows build dependencies ────────────────────────────────────
echo.
echo Installing dependencies from requirements-build-win.txt ...
.venv-build\Scripts\pip install --no-warn-script-location ^
    -r packaging\windows\requirements-build-win.txt
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed ^(see above^).
    echo Some packages may need Visual C++ Build Tools:
    echo   https://visualstudio.microsoft.com/visual-cpp-build-tools/
    goto :fail
)

:: ── 5. Install PyInstaller ───────────────────────────────────────────────────
echo.
echo Installing PyInstaller...
.venv-build\Scripts\pip install --quiet --no-warn-script-location pyinstaller
if errorlevel 1 ( echo ERROR: PyInstaller install failed. & goto :fail )

:: ── 6. Install vina (optional) ───────────────────────────────────────────────
echo.
echo Installing vina...
.venv-build\Scripts\pip install --quiet --no-warn-script-location vina
if errorlevel 1 (
    echo WARNING: vina not installed from PyPI.
    echo   x64 : check your internet connection.
    echo   ARM64: no PyPI wheel — copy from a conda env manually.
    echo Continuing without vina ^(docking will not work^).
)

:: ── 7. Read version ──────────────────────────────────────────────────────────
set PYTHONPATH=src
for /f "delims=" %%v in (
    '.venv-build\Scripts\python.exe -c "from dockmeow.version import __version__; print(__version__)" 2^>^&1'
) do set VERSION=%%v
if "!VERSION!"=="" (
    echo ERROR: Could not read version from src\dockmeow\version.py
    goto :fail
)
echo.
echo Building DockMeow !VERSION! ...

:: ── 8. PyInstaller ───────────────────────────────────────────────────────────
echo.
echo ^> Running PyInstaller...
set PYTHONPATH=src
.venv-build\Scripts\pyinstaller.exe packaging\dockmeow.spec --clean --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed. & goto :fail )

if not exist "dist\DockMeow\DockMeow.exe" (
    echo ERROR: dist\DockMeow\DockMeow.exe not found after build.
    goto :fail
)
echo   Built: dist\DockMeow\DockMeow.exe

:: ── 9. Find Inno Setup ───────────────────────────────────────────────────────
echo.
echo ^> Looking for Inno Setup (ISCC.exe)...
set "ISCC="
for %%p in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
) do if exist %%p set "ISCC=%%~p"
where iscc >nul 2>&1 && set "ISCC=iscc"

if "!ISCC!"=="" (
    echo   Not found — skipping installer.
    echo   Install from https://jrsoftware.org/isdl.php to build a Setup.exe
    echo   Raw build is ready at: dist\DockMeow\
    goto :done_no_installer
)
echo   Found: !ISCC!

:: ── 10. Create installer ─────────────────────────────────────────────────────
if not exist "dist\installers" mkdir "dist\installers"
"!ISCC!" /DMyAppVersion=!VERSION! packaging\windows\installer.iss
if errorlevel 1 ( echo ERROR: Inno Setup failed. & goto :fail )

echo.
echo ====================================================
echo   SUCCESS
echo   Installer: dist\installers\DockMeow-Setup-!VERSION!-x64.exe
echo ====================================================
goto :end

:done_no_installer
echo.
echo ====================================================
echo   SUCCESS ^(no installer — Inno Setup not found^)
echo   App folder: dist\DockMeow\
echo ====================================================
goto :end

:fail
echo.
echo Build FAILED. See errors above.
popd
pause
exit /b 1

:end
popd
pause
