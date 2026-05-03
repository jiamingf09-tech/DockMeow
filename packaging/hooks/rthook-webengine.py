# Runtime hook: set QTWEBENGINE_RESOURCES_PATH so QtWebEngine finds its .pak files.
# Must run before QApplication is created (runtime hooks run at frozen app startup).

import os
import sys

if hasattr(sys, "_MEIPASS"):
    # Resources were bundled to _MEIPASS/webengine_resources/
    webengine_res = os.path.join(sys._MEIPASS, "webengine_resources")
    if os.path.isdir(webengine_res):
        os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", webengine_res)
        locales = os.path.join(webengine_res, "qtwebengine_locales")
        if os.path.isdir(locales):
            os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", locales)
