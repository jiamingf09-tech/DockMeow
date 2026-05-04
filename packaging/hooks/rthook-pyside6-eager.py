# Runtime hook: pre-import PySide6 core modules in the main thread.
#
# In PyInstaller bundles Shiboken uses lazy-import, which calls dlopen() on
# first access.  If that access comes from a QThread worker macOS dyld raises
# EXC_BAD_ACCESS.  Importing here (main thread, before any worker starts)
# converts all subsequent accesses to plain sys.modules lookups.
#
# IMPORTANT: Only import modules that are safe BEFORE QApplication exists.
#   - QtWebEngineWidgets / QtWebEngineCore require QApplication → handled in
#     app.py _force_pyside_eager_import() which runs after create_app().
#   - Scientific libraries (openmm, meeko, rdkit …) can trigger GPU/OpenCL
#     probing before display initialisation → also handled in app.py.

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
