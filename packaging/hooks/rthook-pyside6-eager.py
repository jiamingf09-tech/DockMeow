# Runtime hook: force eager import of all PySide6 sub-modules used by DockMeow.
#
# In PyInstaller bundles Shiboken uses lazy-import, which calls dlopen() the
# first time a sub-module is accessed.  If that access comes from a QThread
# worker (not the main thread) macOS dyld raises EXC_BAD_ACCESS and the
# process dies without any Python traceback.
#
# This hook runs in the main thread at frozen-app startup, before any user
# code executes, so every subsequent access is a plain dict lookup.

import sys  # noqa: F401 (ensure sys is available)

try:
    import PySide6.QtCore              # noqa: F401
    import PySide6.QtGui               # noqa: F401
    import PySide6.QtWidgets           # noqa: F401
    import PySide6.QtWebEngineCore     # noqa: F401
    import PySide6.QtWebEngineWidgets  # noqa: F401
    import PySide6.QtNetwork           # noqa: F401
    import PySide6.QtOpenGL            # noqa: F401
    import PySide6.QtOpenGLWidgets     # noqa: F401
    import PySide6.QtPrintSupport      # noqa: F401
except Exception:  # noqa: BLE001
    pass
