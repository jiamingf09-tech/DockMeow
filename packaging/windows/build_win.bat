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
set "PYTHON_CMD=python"
py -V:3.11 -c "import platform, sys; sys.exit(0 if platform.machine() == 'AMD64' else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -V:3.11"

%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11 x64 not found.
    echo Install Python 3.11 x64 from https://www.python.org/downloads/
    echo Make sure it is available via "py -V:3.11" or python in PATH.
    goto :fail
)
for /f "delims=" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo Using: %%v
for /f "delims=" %%a in ('%PYTHON_CMD% -c "import platform; print(platform.machine())" 2^>^&1') do set "PY_ARCH=%%a"
if /I not "!PY_ARCH!"=="AMD64" (
    echo ERROR: Windows x64 build requires AMD64 Python, found !PY_ARCH!.
    echo Install/use Python 3.11 x64, then recreate .venv-build.
    goto :fail
)

:: --- 2. Create venv ---
if "%DOCKMEOW_WIN_VENV%"=="" set "DOCKMEOW_WIN_VENV=.venv-build-win-x64"
if not exist "%DOCKMEOW_WIN_VENV%\Scripts\python.exe" (
    echo.
    echo Creating virtual environment %DOCKMEOW_WIN_VENV% ...
    %PYTHON_CMD% -m venv "%DOCKMEOW_WIN_VENV%"
    if errorlevel 1 ( echo ERROR: venv creation failed. & goto :fail )
    echo   Created.
)

for /f "delims=" %%a in ('"%DOCKMEOW_WIN_VENV%\Scripts\python.exe" -c "import platform; print(platform.machine())" 2^>^&1') do set "VENV_ARCH=%%a"
if /I not "!VENV_ARCH!"=="AMD64" (
    echo ERROR: Existing %DOCKMEOW_WIN_VENV% is !VENV_ARCH!, but this script builds Windows x64.
    echo Delete/recreate %DOCKMEOW_WIN_VENV% with Python 3.11 x64 before running again.
    goto :fail
)

:: --- 3. Upgrade pip ---
echo.
echo Upgrading pip...
"%DOCKMEOW_WIN_VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip

:: --- 4. Install build dependencies ---
echo.
echo Installing dependencies (requirements-build-win.txt)...
"%DOCKMEOW_WIN_VENV%\Scripts\pip.exe" install --no-warn-script-location -r packaging\windows\requirements-build-win.txt
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed (see output above).
    goto :fail
)

:: --- 5. Install PyInstaller ---
echo.
echo Installing PyInstaller...
"%DOCKMEOW_WIN_VENV%\Scripts\pip.exe" install --quiet --no-warn-script-location pyinstaller
if errorlevel 1 ( echo ERROR: PyInstaller install failed. & goto :fail )

:: --- 6. Install vina (optional) ---
echo.
echo Installing optional Python vina binding...
"%DOCKMEOW_WIN_VENV%\Scripts\pip.exe" install --quiet --no-warn-script-location vina
if errorlevel 1 (
    echo WARNING: Python vina binding not installed from PyPI.
    echo   Build continues - bundled vina.exe fallback will be used when present.
)

:: --- 7. Read version (via temp file to avoid quoting issues) ---
set PYTHONPATH=src
"%DOCKMEOW_WIN_VENV%\Scripts\python.exe" -c "from dockmeow.version import __version__; print(__version__)" > .ver.tmp 2>&1
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
"%DOCKMEOW_WIN_VENV%\Scripts\pyinstaller.exe" packaging\dockmeow.spec --clean --noconfirm --distpath dist\windows-x64
if errorlevel 1 ( echo ERROR: PyInstaller failed. & goto :fail )

if not exist "dist\windows-x64\DockMeow\DockMeow.exe" (
    echo ERROR: dist\windows-x64\DockMeow\DockMeow.exe not found after build.
    goto :fail
)
echo   Built: dist\windows-x64\DockMeow\DockMeow.exe

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
    echo   Raw app folder is ready at: dist\windows-x64\DockMeow\
    goto :done
)
echo   Found: !ISCC!

:: --- 10. Build installer ---
if not exist "dist\installers" mkdir "dist\installers"
"!ISCC!" /DMyAppVersion=!VERSION! /DMyAppSourceDir=..\..\dist\windows-x64\DockMeow packaging\windows\installer.iss
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
