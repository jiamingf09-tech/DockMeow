# Ensure QtWebEngine locales and resources are bundled.
# PyInstaller's built-in PySide6 hooks handle the main binaries;
# this hook adds the data files that the WebEngine process needs at runtime.

from pathlib import Path

from PyInstaller.utils.hooks import get_package_paths

_, pkg_path = get_package_paths("PySide6")

_pkg = Path(pkg_path)

datas = []

# Qt WebEngine resources (translations, pak files, icudtl.dat)
for sub in (
    "Qt/lib/QtWebEngineCore.framework/Helpers",
    "Qt/lib/QtWebEngineCore.framework/Resources",
    "Qt/translations",
    "Qt/resources",
):
    p = _pkg / sub
    if p.exists():
        datas.append((str(p), f"PySide6/{sub}"))

# WebEngineProcess helper binary (needed for sandboxed renderer)
for candidate in (
    "Qt/lib/QtWebEngineCore.framework/Helpers/QtWebEngineProcess.app",
    "Qt/libexec/QtWebEngineProcess",
):
    p = _pkg / candidate
    if p.exists():
        datas.append((str(p), f"PySide6/{candidate}"))
