# Runtime hook: force eager import of all C-extensions used by DockMeow workers.
#
# In PyInstaller bundles, PySide6 uses Shiboken lazy-import and scientific
# libraries (pdbfixer, openmm, meeko, rdkit) are not imported at startup.
# When QThread workers (PrepareReceptorWorker / PrepareLigandWorker) import
# these libraries for the first time, macOS dyld raises EXC_BAD_ACCESS in
# mach_o::Header::forEachLoadCommand — not catchable by Python, causing a
# silent process death.
#
# This hook runs in the MAIN THREAD at frozen-app startup, before any user
# code, so all subsequent accesses are plain sys.modules lookups.
#
# NOTE: QtWebEngineWidgets must be imported AFTER QApplication is created.
#       The PySide6 modules listed here are safe to import before QApplication.
#       The app.py _force_pyside_eager_import() call (after create_app()) handles
#       the WebEngine modules.

import sys  # noqa: F401

# --- PySide6 modules safe before QApplication ---
for _mod in [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtNetwork",
    "PySide6.QtOpenGL",
]:
    try:
        __import__(_mod)
    except Exception:
        pass

# --- Scientific C-extensions used by worker threads ---
for _mod in [
    "pdbfixer",
    "openmm",
    "openmm.app",
    "meeko",
    "rdkit",
    "rdkit.Chem",
    "rdkit.Chem.AllChem",
    "scipy",
    "scipy.spatial",
]:
    try:
        __import__(_mod)
    except Exception:
        pass
