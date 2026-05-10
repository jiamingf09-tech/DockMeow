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

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
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
        "function setPocketReceptorStyle() {"
        "  _v.setStyle({}, {cartoon:{color:'spectrum',opacity:0.55}});"
        "}"
        "function addDockBox(box, selected) {"
        "  var color = selected ? '#FF9500' : '#888888';"
        "  var fillOpacity = selected ? 0.25 : 0.15;"
        "  var wireOpacity = selected ? 0.85 : 0.15;"
        "  var lineWidth = selected ? 3 : 1;"
        "  if (selected) {"
        "  _v.addBox({center:{x:box.cx,y:box.cy,z:box.cz},"
        "             dimensions:{w:box.sx,h:box.sy,d:box.sz},"
        "             color:color,opacity:fillOpacity,wireframe:false});"
        "  }"
        "  _v.addBox({center:{x:box.cx,y:box.cy,z:box.cz},"
        "             dimensions:{w:box.sx,h:box.sy,d:box.sz},"
        "             color:color,opacity:wireOpacity,wireframe:true,linewidth:lineWidth});"
        "}"
        "function showBox(cx,cy,cz,sx,sy,sz) {"
        "  _v.removeAllShapes();"
        "  setPocketReceptorStyle();"
        "  addDockBox({cx:cx,cy:cy,cz:cz,sx:sx,sy:sy,sz:sz}, true);"
        "  _v.render();"
        "}"
        "function showBoxes(boxes, selectedIndex) {"
        "  _v.removeAllShapes();"
        "  setPocketReceptorStyle();"
        "  for (var i = 0; i < boxes.length; i++) {"
        "    addDockBox(boxes[i], i === selectedIndex);"
        "  }"
        "  _v.render();"
        "}"
        "function loadReceptorWithBoxes(pdbText, boxes, selectedIndex) {"
        "  loadReceptor(pdbText);"
        "  showBoxes(boxes, selectedIndex);"
        "}"
        "function clearAll() {"
        "  _v.removeAllModels(); _v.removeAllShapes(); _v.render();"
        "}"
        # Load receptor + best pose.
        # Strategy:
        #   • Protein rendered semi-transparent (opacity:0.5) so the ligand
        #     is always visible through the ribbon even when occluded.
        #   • Ligand rendered ball-and-stick at generous radii so it is clearly
        #     visible at whole-protein zoom level.
        #   • Rotation quaternion is computed so the receptor→ligand vector
        #     points toward the camera (+Z), further reducing occlusion.
        #   • Proper edge-case handling for dz≈±1 and degenerate geometries.
        "function loadBestPose(pdbText, sdfText) {"
        "  _v.removeAllModels(); _v.removeAllShapes();"
        "  _v.addModel(pdbText, 'pdb');"
        # Semi-transparent protein so the ligand shows through the ribbon
        "  _v.setStyle({model:0}, {cartoon:{color:'spectrum',opacity:0.5}});"
        "  _v.addModel(sdfText, 'sdf');"
        # Ball-and-stick at generous radii — visible at whole-protein scale
        "  _v.setStyle({model:1}, {"
        "    stick:{colorscheme:'greenCarbon',radius:0.4},"
        "    sphere:{colorscheme:'greenCarbon',radius:0.5}"
        "  });"
        "  var la=_v.selectedAtoms({model:1}), ra=_v.selectedAtoms({model:0});"
        # Bail out gracefully if no ligand atoms parsed (malformed SDF)
        "  if(la.length===0){_v.zoomTo();_v.render();return;}"
        # Compute ligand centroid
        "  var lx=0,ly=0,lz=0;"
        "  la.forEach(function(a){lx+=a.x;ly+=a.y;lz+=a.z;});"
        "  lx/=la.length;ly/=la.length;lz/=la.length;"
        # Compute receptor centroid (guard against empty receptor)
        "  var rx=0,ry=0,rz=0;"
        "  if(ra.length>0){"
        "    ra.forEach(function(a){rx+=a.x;ry+=a.y;rz+=a.z;});"
        "    rx/=ra.length;ry/=ra.length;rz/=ra.length;"
        "  }"
        # Unit vector receptor→ligand
        "  var dx=lx-rx,dy=ly-ry,dz=lz-rz;"
        "  var d=Math.sqrt(dx*dx+dy*dy+dz*dz);"
        # If ligand is at protein centroid (degenerate), just show whole complex
        "  if(d<0.5){_v.zoomTo();_v.render();return;}"
        "  dx/=d;dy/=d;dz/=d;"
        # Quaternion to rotate (dx,dy,dz) → (0,0,1) [camera direction]:
        #   axis = (dx,dy,dz) × (0,0,1) = (dy,-dx,0); angle = arccos(dz)
        # Edge cases handled explicitly to avoid divide-by-zero on axl:
        #   dz≈+1: ligand already faces camera → identity quaternion
        #   dz≈-1: ligand faces away       → 180° around Y axis
        "  var axl=Math.sqrt(dx*dx+dy*dy);"
        "  var qx=0,qy=0,qz=0,qw=1;"
        "  if(dz>0.99){"
        "    qx=0;qy=0;qz=0;qw=1;"           # identity — already correct
        "  }else if(dz<-0.99){"
        "    qx=0;qy=1;qz=0;qw=0;"           # 180° flip around Y
        "  }else{"
        "    var ang=Math.acos(dz);"
        "    var s=Math.sin(ang/2);"
        "    qx=(dy/axl)*s;qy=(-dx/axl)*s;qz=0;qw=Math.cos(ang/2);"
        "  }"
        # Apply rotation FIRST, then zoomTo() so it recomputes zoom/translation
        # for the new orientation — otherwise zoomTo() fits the *old* rotation
        # and the complex may not fill the viewport correctly after the rotation.
        # zoomTo() only touches translation+zoom; it never changes the quaternion.
        "  var v=_v.getView();v[3]=qx;v[4]=qy;v[5]=qz;v[6]=qw;"
        "  _v.setView(v);"
        "  _v.zoomTo();_v.render();"
        "}"
        "function setViewerBg(hexColor) {"
        "  _v.setBackgroundColor(hexColor); _v.render();"
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

    #: Default background color (dark, matching app theme)
    DEFAULT_BG = "#1E1E2E"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ready = False
        self._pending: list[str] = []
        self._pending_callbacks: list[Callable[[], None]] = []
        self._bg_color: str = self.DEFAULT_BG
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("DockMeow 3D preview")
        self.setAccessibleDescription("Molecular preview rendered by Qt WebEngine")
        self.loadFinished.connect(self._on_load_finished)
        # Use a data URL base so that local resource requests are allowed
        self.setHtml(_HTML, QUrl("qrc:/"))

    # ------------------------------------------------------------------
    def suspend_for_page_hide(self) -> None:
        """Temporarily remove the native WebEngine view from active page UI."""
        self.clearFocus()
        self.setEnabled(False)
        self.hide()
        try:
            self.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        except Exception:  # noqa: BLE001
            pass

    def resume_after_page_show(self) -> None:
        """Restore the WebEngine view after its page becomes visible again."""
        try:
            self.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except Exception:  # noqa: BLE001
            pass
        self.setEnabled(True)
        self.show()

    def set_background_color(self, hex_color: str) -> None:
        """Change the viewer canvas background color (e.g. '#FFFFFF').

        The color is persisted so ``capture_png`` captures with the chosen
        background.  Pass ``Viewer3D.DEFAULT_BG`` to restore the dark default.
        """
        self._bg_color = hex_color
        self._run_js(f"setViewerBg('{hex_color}');")

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

    def load_result_pose(self, pdb_path: Path, sdf_content: str) -> None:
        """Load receptor + ligand for the results page using ``loadBestPose``.

        This applies the ligand-facing rotation so the ligand is in the
        foreground, then zooms to fit the entire complex.  Use this instead
        of the separate ``load_receptor`` + ``load_ligand_pose`` pair on the
        results page so the view is always correct when poses are switched.
        """
        try:
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning("Viewer3D.load_result_pose: cannot read %s: %s", pdb_path, exc)
            return
        self._run_js(f"loadBestPose({json.dumps(pdb_text)}, {json.dumps(sdf_content)});")

    def show_box(
        self,
        center: tuple[float, float, float] | object,
        size: tuple[float, float, float] | None = None,
    ) -> None:
        if size is None and hasattr(center, "center") and hasattr(center, "size"):
            size = getattr(center, "size")
            center = getattr(center, "center")
        if size is None:
            raise ValueError("show_box() requires either a Pocket or center and size")
        cx, cy, cz = center
        sx, sy, sz = size
        self._run_js(f"showBox({cx},{cy},{cz},{sx},{sy},{sz});")

    def show_pockets(self, pockets: list[object], selected: object | None = None) -> None:
        boxes, selected_index = self._box_payloads(pockets, selected)
        self._run_js(f"showBoxes({json.dumps(boxes)}, {selected_index});")

    def load_receptor_with_pockets(
        self,
        pdb_path: Path,
        pockets: list[object],
        selected: object | None = None,
    ) -> None:
        try:
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning("Viewer3D.load_receptor_with_pockets: cannot read %s: %s", pdb_path, exc)
            return
        boxes, selected_index = self._box_payloads(pockets, selected)
        self._run_js(
            f"loadReceptorWithBoxes({json.dumps(pdb_text)}, "
            f"{json.dumps(boxes)}, {selected_index});"
        )

    @staticmethod
    def _box_payloads(
        pockets: list[object],
        selected: object | None = None,
    ) -> tuple[list[dict[str, float]], int]:
        boxes: list[dict[str, float]] = []
        selected_index = -1
        selected_key = None
        if selected is not None:
            selected_key = (
                getattr(selected, "pocket_id", None),
                getattr(selected, "source", None),
            )
        for idx, pocket in enumerate(pockets):
            cx, cy, cz = getattr(pocket, "center")
            sx, sy, sz = getattr(pocket, "size")
            boxes.append(
                {
                    "cx": float(cx),
                    "cy": float(cy),
                    "cz": float(cz),
                    "sx": float(sx),
                    "sy": float(sy),
                    "sz": float(sz),
                }
            )
            key = (getattr(pocket, "pocket_id", None), getattr(pocket, "source", None))
            if selected_key is not None and key == selected_key:
                selected_index = idx
        return boxes, selected_index

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
