"""3D molecular viewer widget wrapping py3Dmol inside QWebEngineView.

3Dmol-min.js is loaded from the bundled local copy
(src/dockmeow/bundled/web/3Dmol-min.js) — no CDN, fully offline.

Screenshot strategy:
    1. Call JS ``_v.render()``  → ``requestAnimationFrame`` → ``_v.pngURI()``
    2. The data-URI is returned via ``runJavaScript`` callback.
    3. Decode base64 → write PNG.
    This avoids ``QWidget.grab()`` which returns blank on QWebEngine's
    out-of-process renderer.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

from dockmeow.utils.paths import resource_path

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML template — 3Dmol loaded inline from local file at class-definition time
# so each instance reuses the already-read string.
# ---------------------------------------------------------------------------

def _build_html() -> str:
    js_path = resource_path("bundled/web/3Dmol-min.js")
    try:
        js_src = js_path.read_text(encoding="utf-8")
    except Exception as exc:
        _log.warning("Cannot read bundled 3Dmol-min.js (%s); viewer will be empty", exc)
        js_src = ""
    return (
        "<!DOCTYPE html><html><head>"
        "<meta charset='utf-8'>"
        "<style>"
        "* { margin:0; padding:0; }"
        "html, body { width:100%; height:100%; background:#1E1E2E; }"
        "#v { position:absolute; inset:0; }"
        "</style>"
        f"<script>{js_src}</script>"
        "</head><body>"
        "<div id='v'></div>"
        "<script>"
        "var _v = $3Dmol.createViewer(document.getElementById('v'),"
        "                             {backgroundColor:'#1E1E2E'});"
        # ---- public JS API called from Python via runJavaScript ----
        "function loadReceptor(pdbText) {"
        "  _v.removeAllModels(); _v.removeAllShapes();"
        "  _v.addModel(pdbText, 'pdb');"
        "  _v.setStyle({}, {cartoon:{color:'spectrum'}});"
        "  _v.zoomTo(); _v.render();"
        "}"
        "function loadLigand(sdfText) {"
        "  _v.addModel(sdfText, 'sdf');"
        "  _v.setStyle({model:-1}, {stick:{colorscheme:'greenCarbon'}});"
        "  _v.zoomTo({model:-1}); _v.zoom(0.7); _v.render();"
        "}"
        "function showBox(cx,cy,cz,sx,sy,sz) {"
        "  _v.addBox({center:{x:cx,y:cy,z:cz},"
        "             dimensions:{w:sx,h:sy,d:sz},"
        "             color:'#7C9EF8',opacity:0.2,wireframe:true});"
        "  _v.render();"
        "}"
        "function clearAll() {"
        "  _v.removeAllModels(); _v.removeAllShapes(); _v.render();"
        "}"
        # Load receptor + best pose together, zoom to ligand for PDF export
        "function loadBestPose(pdbText, sdfText) {"
        "  _v.removeAllModels(); _v.removeAllShapes();"
        "  _v.addModel(pdbText, 'pdb');"
        "  _v.setStyle({model:0}, {cartoon:{color:'spectrum',opacity:0.85}});"
        "  _v.addModel(sdfText, 'sdf');"
        "  _v.setStyle({model:1}, {stick:{colorscheme:'greenCarbon',radius:0.25}});"
        "  _v.zoomTo({model:1}); _v.zoom(1.2); _v.render();"
        "}"
        # Screenshot: render → wait for GPU frame → return pngURI
        "function requestScreenshot() {"
        "  _v.render();"
        "  return new Promise(function(resolve) {"
        "    requestAnimationFrame(function() {"
        "      resolve(_v.pngURI());"
        "    });"
        "  });"
        "}"
        "</script>"
        "</body></html>"
    )


_HTML = _build_html()


class Viewer3D(QWebEngineView):
    """Renders receptor + ligand poses using py3Dmol (offline, bundled JS)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ready = False
        self._pending: list[str] = []
        self._pending_callbacks: list[Callable[[], None]] = []
        self.loadFinished.connect(self._on_load_finished)
        # Use a data URL base so that local resource requests are allowed
        self.setHtml(_HTML, QUrl("qrc:/"))

    # ------------------------------------------------------------------
    def _on_load_finished(self, ok: bool) -> None:
        self._ready = bool(ok)
        if ok:
            for js in self._pending:
                self.page().runJavaScript(js)
            self._pending.clear()
            for cb in self._pending_callbacks:
                cb()
            self._pending_callbacks.clear()
        else:
            _log.warning("Viewer3D: page load failed")

    def _run_js(self, js: str) -> None:
        if self._ready:
            self.page().runJavaScript(js)
        else:
            self._pending.append(js)

    # ------------------------------------------------------------------
    def load_receptor(self, pdb_path: Path) -> None:
        try:
            text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning("Viewer3D.load_receptor: cannot read %s: %s", pdb_path, exc)
            return
        self._run_js(f"loadReceptor({json.dumps(text)});")

    def load_ligand_pose(self, sdf_content: str) -> None:
        self._run_js(f"loadLigand({json.dumps(sdf_content)});")

    def show_box(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
    ) -> None:
        cx, cy, cz = center
        sx, sy, sz = size
        self._run_js(f"showBox({cx},{cy},{cz},{sx},{sy},{sz});")

    def clear(self) -> None:
        self._run_js("clearAll();")

    def load_best_pose_for_export(
        self,
        pdb_path: Path,
        sdf_content: str,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Load receptor + best pose together, zoom to binding pocket (for PDF export).

        Args:
            pdb_path:   Receptor PDB file.
            sdf_content: Best-pose SDF text.
            on_ready:   Optional callback invoked after the JS ``loadBestPose`` call
                        returns (i.e. models are loaded and render() was issued).
                        Use this to schedule capture_png immediately after rendering,
                        avoiding fixed-duration timer assumptions.
        """
        try:
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning("Viewer3D.load_best_pose_for_export: cannot read %s: %s", pdb_path, exc)
            if on_ready is not None:
                on_ready()
            return
        js = f"loadBestPose({json.dumps(pdb_text)}, {json.dumps(sdf_content)});"
        if on_ready is not None:
            if self._ready:
                # worldId=0 (MainWorld) required by PySide6 ≤ 6.7; also accepted by 6.11+
                self.page().runJavaScript(js, 0, lambda _: on_ready())
            else:
                # Queue both the JS and the callback for when the page is ready
                def _deferred_run() -> None:
                    self.page().runJavaScript(js, 0, lambda _: on_ready())
                self._pending_callbacks.append(_deferred_run)
        else:
            self._run_js(js)

    # --- Compatibility wrappers (legacy API) ---------------------------
    def show_receptor(self, pdb_path) -> None:
        self.load_receptor(Path(pdb_path))

    def show_pose(self, sdf_path, pose_index: int = 0) -> None:  # noqa: ARG002
        try:
            self.load_ligand_pose(Path(sdf_path).read_text(encoding="utf-8"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def capture_png(
        self, output_path: Path, callback: Callable[[Path], None] | None = None
    ) -> None:
        """Snapshot the current viewer to a PNG file.

        Uses ``_v.pngURI()`` via JS (reads WebGL canvas directly) rather than
        ``QWidget.grab()``, which returns blank frames on QWebEngine's
        out-of-process GPU renderer.

        Flow: render() → requestAnimationFrame → pngURI() → base64 decode → write.
        Falls back to grab() if the JS path fails (e.g. viewer not ready).
        """
        out = Path(output_path)

        def _on_png_uri(result: str | None) -> None:
            if result and isinstance(result, str) and result.startswith("data:image/png;base64,"):
                try:
                    raw = base64.b64decode(result.split(",", 1)[1])
                    out.write_bytes(raw)
                    _log.debug("Viewer3D: screenshot written via pngURI (%d bytes)", len(raw))
                    if callback is not None:
                        callback(out)
                    return
                except Exception as exc:
                    _log.warning("Viewer3D: pngURI decode failed (%s), falling back to grab()", exc)
            # Fallback
            _log.warning("Viewer3D: pngURI returned empty/invalid — falling back to QWidget.grab()")
            pix = self.grab()
            if not pix.isNull():
                pix.save(str(out), "PNG")
            if callback is not None:
                callback(out)

        if not self._ready:
            # Not yet loaded — just grab and hope
            QTimer.singleShot(800, lambda: self.capture_png(output_path, callback))
            return

        # render() → wait one animation frame → read pngURI
        # worldId=0 (MainWorld) keeps this compatible with PySide6 ≤ 6.7 and 6.11+
        def _request() -> None:
            self.page().runJavaScript(
                "new Promise(function(res) {"
                "  _v.render();"
                "  requestAnimationFrame(function() { res(_v.pngURI()); });"
                "});",
                0,
                _on_png_uri,
            )

        QTimer.singleShot(50, _request)

    def capture_screenshot(self, output_path) -> None:
        """Alias kept for API compatibility."""
        self.capture_png(Path(output_path))
