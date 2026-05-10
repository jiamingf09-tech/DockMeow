@echo off
:: DockMeow Windows build - pure CMD, no PowerShell required.
:: Usage: double-click, or run from any CMD window at the repo root:
::   packaging\windows\build_win.bat
::
:: Prerequisites:
::   1. Python 3.11 (64-bit) - https://www.python.org/downloads/
::      Tick "Add Python to PATH" during installation.
::   2. Inno Setup 6 (optional, for the Setup.exe installer)
::      https://jrsoftware.org/isdl.php

setlocal EnableDelayedExpansion

pushd "%~dp0..\.."

echo.
echo ================================================
echo   DockMeow Windows Build
echo ================================================
echo.

:: --- 1. Verify Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.11 from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH".
    goto :fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo Using: %%v

:: --- 2. Create venv ---
if not exist ".venv-build\Scripts\python.exe" (
    echo.
    echo Creating virtual environment .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 ( echo ERROR: venv creation failed. & goto :fail )
    echo   Created.
)

:: --- 3. Upgrade pip ---
echo.
echo Upgrading pip...
.venv-build\Scripts\python.exe -m pip install --quiet --upgrade pip

:: --- 4. Install build dependencies ---
echo.
echo Installing dependencies (requirements-build-win.txt)...
.venv-build\Scripts\pip install --no-warn-script-location -r packaging\windows\requirements-build-win.txt
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed (see output above).
    goto :fail
)

:: --- 5. Install PyInstaller ---
echo.
echo Installing PyInstaller...
.venv-build\Scripts\pip install --quiet --no-warn-script-location pyinstaller
if errorlevel 1 ( echo ERROR: PyInstaller install failed. & goto :fail )

:: --- 6. Install vina (optional) ---
echo.
echo Installing vina...
.venv-build\Scripts\pip install --quiet --no-warn-script-location vina
if errorlevel 1 (
    echo WARNING: vina not installed from PyPI.
    echo   If you are on ARM64, copy vina from a conda env manually.
    echo   Build continues - docking will not work without vina.
)

:: --- 7. Read version (via temp file to avoid quoting issues) ---
set PYTHONPATH=src
.venv-build\Scripts\python.exe -c "from dockmeow.version import __version__; print(__version__)" > .ver.tmp 2>&1
set /p VERSION=<.ver.tmp
del .ver.tmp
if "!VERSION!"=="" (
    echo ERROR: Could not read version from src\dockmeow\version.py
    goto :fail
)
echo.
echo Building DockMeow !VERSION! ...

:: --- 8. Run PyInstaller ---
echo.
echo Running PyInstaller...
set PYTHONPATH=src
.venv-build\Scripts\pyinstaller.exe packaging\dockmeow.spec --clean --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed. & goto :fail )

if not exist "dist\DockMeow\DockMeow.exe" (
    echo ERROR: dist\DockMeow\DockMeow.exe not found after build.
    goto :fail
)
echo   Built: dist\DockMeow\DockMeow.exe

:: --- 9. Find Inno Setup ---
echo.
echo Looking for Inno Setup (ISCC.exe)...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"       set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"  set "ISCC=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
where iscc >nul 2>&1
if not errorlevel 1 set ISCC=iscc

if "!ISCC!"=="" (
    echo   Not found - skipping installer creation.
    echo   Get Inno Setup 6 from https://jrsoftware.org/isdl.php
    echo   Raw app folder is ready at: dist\DockMeow\
    goto :done
)
echo   Found: !ISCC!

:: --- 10. Build installer ---
if not exist "dist\installers" mkdir "dist\installers"
"!ISCC!" /DMyAppVersion=!VERSION! packaging\windows\installer.iss
if errorlevel 1 ( echo ERROR: Inno Setup failed. & goto :fail )
echo   Installer: dist\installers\DockMeow-Setup-!VERSION!-x64.exe

:done
echo.
echo ================================================
echo   Build complete!
echo ================================================
popd
pause
exit /b 0

:fail
echo.
echo Build FAILED. See errors above.
popd
pause
exit /b 1
