@echo off
:: Minimal Windows raw-dist builder for existing build environments.
:: This wrapper intentionally has no underscore in its filename, which makes it
:: easier to run over remote desktops/input methods that mangle "_" keystrokes.

setlocal EnableDelayedExpansion
pushd "%~dp0..\.."

if exist ".venv-build-win-x64\python.exe" (
    set "PYTHON_CMD=.venv-build-win-x64\python.exe"
) else if exist ".venv-build-win-x64\Scripts\python.exe" (
    set "PYTHON_CMD=.venv-build-win-x64\Scripts\python.exe"
) else (
    echo ERROR: .venv-build-win-x64 Python was not found.
    popd
    exit /b 1
)

set "PYTHONPATH=src"
echo Using %PYTHON_CMD%
"%PYTHON_CMD%" -c "import importlib, sys; m = importlib.import_module('PyInstaller.__main__'); m.run(sys.argv[1:])" packaging\dockmeow.spec --clean --noconfirm --distpath dist\windows-x64
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    popd
    exit /b 1
)

if not exist "dist\windows-x64\DockMeow\DockMeow.exe" (
    echo ERROR: dist\windows-x64\DockMeow\DockMeow.exe not found after build.
    popd
    exit /b 1
)

echo Built: dist\windows-x64\DockMeow\DockMeow.exe
popd
exit /b 0
