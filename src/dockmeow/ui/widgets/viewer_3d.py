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
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from dockmeow.utils.paths import resource_path

_log = logging.getLogger(__name__)


def _prefer_native_viewer() -> bool:
    backend = os.environ.get("DOCKMEOW_VIEWER_BACKEND", "").strip().lower()
    if backend in {"native", "qt", "painter"}:
        return True
    if backend in {"webengine", "webgl", "3dmol"}:
        return False
    # Default to the 3Dmol / WebEngine viewer on every platform — including
    # frozen macOS .app bundles — so the packaged app matches the source run
    # (real cartoon view) and the drag-aspect fix applies there too.
    # Frozen macOS previously fell back to a native Qt painter because
    # QtWebEngine could crash when macOS accessibility clients attached; that is
    # now mitigated in app.create_app() via QAccessible.setActive(False).
    # Escape hatch: set DOCKMEOW_VIEWER_BACKEND=native if a machine still fails.
    return False


if _prefer_native_viewer():
    QWebEnginePage = None
    QWebEngineView = QWidget
else:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView

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
        "html, body { width:100%; height:100%; overflow:hidden; background:#1E1E2E; }"
        "#v { position:absolute; inset:0; width:100%; height:100%; overflow:hidden; }"
        "#v canvas { width:100% !important; height:100% !important; display:block; }"
        "</style>"
        f"<script>{js_src}</script>"
        "</head><body>"
        "<div id='v'></div>"
        "<script>"
        "var _v = null, _fallbackActive = false;"
        "var _renderBackend = 'initializing';"
        "var _webglInfo = {available:false, version:'', vendor:'', renderer:'', error:''};"
        "var _fallbackAtoms = [], _fallbackBonds = [], _fallbackShapes = [];"
        "var _fallbackStyles = {}, _fallbackFocus = null, _fallbackZoom = 1;"
        "var _fallbackModel = 0, _fallbackBg = '#1E1E2E';"
        "var _fallbackCanvas = null, _fallbackCtx = null, _fallbackReady = false;"
        "var _fallbackRotX = -0.45, _fallbackRotY = 0.75;"
        "var _fallbackDrag = false, _fallbackLast = null;"
        "var _resizeToken = 0;"
        "var _lastSyncW = 0, _lastSyncH = 0;"
        "function _fallbackElement(name, elem) {"
        "  var e = (elem || '').trim();"
        "  if (e) { return e; }"
        "  var n = (name || '').trim();"
        "  if (!n) { return 'C'; }"
        "  if (n[0] >= '0' && n[0] <= '9') { n = n.slice(1); }"
        "  return n.slice(0, 2).trim() || n.slice(0, 1) || 'C';"
        "}"
        "function _fallbackColor(atom) {"
        "  var e = (atom.elem || 'C').toUpperCase();"
        "  if (atom.model > 0 && e === 'C') { return '#35D07F'; }"
        "  var colors = {H:'#D7DEE8',C:'#8FB3FF',N:'#5FA8FF',O:'#FF6B6B',"
        "                S:'#FFD166',P:'#C77DFF',CL:'#72E06A',F:'#7FE7C4',"
        "                BR:'#B8895A',I:'#9D7AD9'};"
        "  return colors[e] || colors[e.slice(0, 1)] || '#E5E7EB';"
        "}"
        "function _probeWebGL() {"
        "  var info = {available:false, version:'', vendor:'', renderer:'', error:''};"
        "  try {"
        "    var canvas = document.createElement('canvas');"
        "    var gl = canvas.getContext('webgl2') || canvas.getContext('webgl') ||"
        "             canvas.getContext('experimental-webgl');"
        "    if (!gl) { info.error = 'no WebGL context'; return info; }"
        "    info.available = true;"
        "    info.version = gl.getParameter(gl.VERSION) || '';"
        "    info.vendor = gl.getParameter(gl.VENDOR) || '';"
        "    info.renderer = gl.getParameter(gl.RENDERER) || '';"
        "    var dbg = gl.getExtension('WEBGL_debug_renderer_info');"
        "    if (dbg) {"
        "      info.vendor = gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) || info.vendor;"
        "      info.renderer = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || info.renderer;"
        "    }"
        "  } catch (e) {"
        "    info.error = String(e && (e.message || e));"
        "  }"
        "  return info;"
        "}"
        "function _fallbackEnsure() {"
        "  if (_fallbackReady) { return; }"
        "  var host = document.getElementById('v');"
        "  host.innerHTML = '';"
        "  _fallbackCanvas = document.createElement('canvas');"
        "  _fallbackCanvas.style.width = '100%';"
        "  _fallbackCanvas.style.height = '100%';"
        "  _fallbackCanvas.style.display = 'block';"
        "  host.appendChild(_fallbackCanvas);"
        "  _fallbackCtx = _fallbackCanvas.getContext('2d');"
        "  _fallbackCanvas.addEventListener('mousedown', function(e) {"
        "    _fallbackDrag = true; _fallbackLast = {x:e.clientX, y:e.clientY};"
        "  });"
        "  window.addEventListener('mouseup', function() { _fallbackDrag = false; });"
        "  window.addEventListener('mousemove', function(e) {"
        "    if (!_fallbackDrag || !_fallbackLast) { return; }"
        "    _fallbackRotY += (e.clientX - _fallbackLast.x) * 0.01;"
        "    _fallbackRotX += (e.clientY - _fallbackLast.y) * 0.01;"
        "    _fallbackLast = {x:e.clientX, y:e.clientY};"
        "    _fallbackDraw();"
        "  });"
        "  window.addEventListener('resize', _fallbackResize);"
        "  _fallbackReady = true;"
        "  _fallbackResize();"
        "}"
        "function _fallbackResize() {"
        "  if (!_fallbackCanvas) { return; }"
        "  var host = document.getElementById('v');"
        "  var dpr = window.devicePixelRatio || 1;"
        "  var w = Math.max(200, host.clientWidth || 900);"
        "  var h = Math.max(200, host.clientHeight || 650);"
        "  _fallbackCanvas.width = Math.floor(w * dpr);"
        "  _fallbackCanvas.height = Math.floor(h * dpr);"
        "  _fallbackCtx.setTransform(dpr, 0, 0, dpr, 0, 0);"
        "  _fallbackDraw();"
        "}"
        "function _fallbackParsePdb(text, model) {"
        "  var lines = String(text || '').split(/\\r?\\n/);"
        "  lines.forEach(function(line) {"
        "    if (line.indexOf('ATOM') !== 0 && line.indexOf('HETATM') !== 0) { return; }"
        "    var x = parseFloat(line.slice(30, 38));"
        "    var y = parseFloat(line.slice(38, 46));"
        "    var z = parseFloat(line.slice(46, 54));"
        "    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) { return; }"
        "    _fallbackAtoms.push({x:x, y:y, z:z, model:model,"
        "      name:line.slice(12,16).trim(), chain:(line.slice(21,22)||' '),"
        "      resi:parseInt(line.slice(22,26),10)||0,"
        "      elem:_fallbackElement(line.slice(12, 16), line.slice(76, 78))});"
        "  });"
        "}"
        "function _fallbackParseSdf(text, model) {"
        "  var lines = String(text || '').split(/\\r?\\n/);"
        "  var countsIndex = -1;"
        "  for (var ci = 0; ci < Math.min(8, lines.length); ci++) {"
        "    if (/^\\s*\\d+\\s+\\d+/.test(lines[ci])) { countsIndex = ci; break; }"
        "  }"
        "  var count = countsIndex >= 0 ? parseInt(lines[countsIndex].slice(0, 3), 10) : 0;"
        "  var bondCount = countsIndex >= 0 ? parseInt(lines[countsIndex].slice(3, 6), 10) : 0;"
        "  if (!isFinite(count) || count < 1) { return; }"
        "  var atomStart = countsIndex + 1;"
        "  var start = _fallbackAtoms.length;"
        "  for (var i = 0; i < count && atomStart + i < lines.length; i++) {"
        "    var line = lines[atomStart + i];"
        "    var x = parseFloat(line.slice(0, 10));"
        "    var y = parseFloat(line.slice(10, 20));"
        "    var z = parseFloat(line.slice(20, 30));"
        "    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) { continue; }"
        "    _fallbackAtoms.push({x:x, y:y, z:z, model:model, name:'',"
        "      chain:' ', resi:i + 1,"
        "      elem:_fallbackElement(line.slice(31, 34), line.slice(31, 34))});"
        "  }"
        "  if (!isFinite(bondCount) || bondCount < 1) { return; }"
        "  for (var b = 0; b < bondCount && atomStart + count + b < lines.length; b++) {"
        "    var bl = lines[atomStart + count + b];"
        "    var a1 = parseInt(bl.slice(0, 3), 10) - 1;"
        "    var a2 = parseInt(bl.slice(3, 6), 10) - 1;"
        "    var order = parseInt(bl.slice(6, 9), 10) || 1;"
        "    if (a1 >= 0 && a2 >= 0 && a1 < count && a2 < count) {"
        "      _fallbackBonds.push({model:model, a:start + a1, b:start + a2, order:order});"
        "    }"
        "  }"
        "}"
        "function _fallbackAtomsFor(sel) {"
        "  if (sel && typeof sel.model === 'number') {"
        "    return _fallbackAtoms.filter(function(a){return a.model === sel.model;});"
        "  }"
        "  return _fallbackAtoms.slice();"
        "}"
        "function _fallbackStyle(model) {"
        "  return _fallbackStyles[String(model)] || _fallbackStyles['*'] || {};"
        "}"
        "function _fallbackProjector(w, h) {"
        "  var focusAtoms = _fallbackFocus ? _fallbackAtomsFor(_fallbackFocus) : _fallbackAtoms;"
        "  if (!focusAtoms.length) { focusAtoms = _fallbackAtoms; }"
        "  var cx = 0, cy = 0, cz = 0;"
        "  focusAtoms.forEach(function(a) { cx += a.x; cy += a.y; cz += a.z; });"
        "  cx /= focusAtoms.length; cy /= focusAtoms.length; cz /= focusAtoms.length;"
        "  var maxd = 1;"
        "  _fallbackAtoms.forEach(function(a) {"
        "    maxd = Math.max(maxd, Math.abs(a.x-cx), Math.abs(a.y-cy), Math.abs(a.z-cz));"
        "  });"
        "  var scale = Math.min(w, h) * 0.42 / maxd * _fallbackZoom;"
        "  var sx = Math.sin(_fallbackRotX), cxr = Math.cos(_fallbackRotX);"
        "  var sy = Math.sin(_fallbackRotY), cyr = Math.cos(_fallbackRotY);"
        "  return function(a) {"
        "    var x = a.x - cx, y = a.y - cy, z = a.z - cz;"
        "    var x1 = x * cyr + z * sy;"
        "    var z1 = -x * sy + z * cyr;"
        "    var y1 = y * cxr - z1 * sx;"
        "    var z2 = y * sx + z1 * cxr;"
        "    return {x:w/2 + x1*scale, y:h/2 - y1*scale, z:z2, atom:a};"
        "  };"
        "}"
        "function _fallbackStroke(points, color, width, alpha) {"
        "  if (points.length < 2) { return; }"
        "  _fallbackCtx.save();"
        "  _fallbackCtx.globalAlpha = alpha;"
        "  _fallbackCtx.strokeStyle = color;"
        "  _fallbackCtx.lineWidth = width;"
        "  _fallbackCtx.lineJoin = 'round';"
        "  _fallbackCtx.lineCap = 'round';"
        "  _fallbackCtx.beginPath();"
        "  _fallbackCtx.moveTo(points[0].x, points[0].y);"
        "  for (var i = 1; i < points.length; i++) {"
        "    _fallbackCtx.lineTo(points[i].x, points[i].y);"
        "  }"
        "  _fallbackCtx.stroke();"
        "  _fallbackCtx.restore();"
        "}"
        "function _fallbackDrawReceptor(project) {"
        "  var atoms = _fallbackAtomsFor({model:0});"
        "  if (!atoms.length) { return; }"
        "  var trace = atoms.filter(function(a){return (a.name || '').toUpperCase() === 'CA';});"
        "  if (trace.length < 5) {"
        "    var step = Math.max(1, Math.floor(atoms.length / 180));"
        "    trace = atoms.filter(function(_a, i){return i % step === 0;});"
        "  }"
        "  var chains = {};"
        "  trace.forEach(function(a){(chains[a.chain] = chains[a.chain] || []).push(project(a));});"
        "  Object.keys(chains).forEach(function(chain) {"
        "    _fallbackStroke(chains[chain], '#8FB3FF', 6, 0.38);"
        "    _fallbackStroke(chains[chain], '#D7E5FF', 2.2, 0.78);"
        "  });"
        "}"
        "function _fallbackDrawBox(shape, project) {"
        "  var cx = shape.center.x, cy = shape.center.y, cz = shape.center.z;"
        "  var sx = shape.dimensions.w / 2, sy = shape.dimensions.h / 2,"
        "      sz = shape.dimensions.d / 2;"
        "  var corners = ["
        "    {x:cx-sx,y:cy-sy,z:cz-sz},{x:cx+sx,y:cy-sy,z:cz-sz},"
        "    {x:cx+sx,y:cy+sy,z:cz-sz},{x:cx-sx,y:cy+sy,z:cz-sz},"
        "    {x:cx-sx,y:cy-sy,z:cz+sz},{x:cx+sx,y:cy-sy,z:cz+sz},"
        "    {x:cx+sx,y:cy+sy,z:cz+sz},{x:cx-sx,y:cy+sy,z:cz+sz}"
        "  ].map(project);"
        "  var edges = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];"
        "  _fallbackCtx.save();"
        "  _fallbackCtx.strokeStyle = shape.color || '#FF9500';"
        "  _fallbackCtx.globalAlpha = shape.opacity || 0.85;"
        "  _fallbackCtx.lineWidth = shape.linewidth || 2;"
        "  edges.forEach(function(e){"
        "    _fallbackCtx.beginPath();"
        "    _fallbackCtx.moveTo(corners[e[0]].x, corners[e[0]].y);"
        "    _fallbackCtx.lineTo(corners[e[1]].x, corners[e[1]].y);"
        "    _fallbackCtx.stroke();"
        "  });"
        "  _fallbackCtx.restore();"
        "}"
        "function _fallbackDrawLigands(project) {"
        "  var pts = _fallbackAtoms.filter(function(a){return a.model > 0;}).map(project);"
        "  var byIndex = {};"
        "  pts.forEach(function(p){byIndex[_fallbackAtoms.indexOf(p.atom)] = p;});"
        "  _fallbackCtx.save();"
        "  _fallbackBonds.forEach(function(b) {"
        "    var p1 = byIndex[b.a], p2 = byIndex[b.b];"
        "    if (!p1 || !p2) { return; }"
        "    _fallbackCtx.globalAlpha = 0.96;"
        "    _fallbackCtx.strokeStyle = '#35D07F';"
        "    _fallbackCtx.lineWidth = Math.max(3, Math.min(7, 3 + (b.order || 1)));"
        "    _fallbackCtx.lineCap = 'round';"
        "    _fallbackCtx.beginPath();"
        "    _fallbackCtx.moveTo(p1.x, p1.y); _fallbackCtx.lineTo(p2.x, p2.y);"
        "    _fallbackCtx.stroke();"
        "  });"
        "  pts.sort(function(a, b) { return a.z - b.z; });"
        "  pts.forEach(function(p) {"
        "    _fallbackCtx.beginPath();"
        "    _fallbackCtx.arc(p.x, p.y, 5.5, 0, Math.PI * 2);"
        "    _fallbackCtx.fillStyle = _fallbackColor(p.atom);"
        "    _fallbackCtx.globalAlpha = 0.98;"
        "    _fallbackCtx.fill();"
        "    _fallbackCtx.strokeStyle = '#F8FAFC';"
        "    _fallbackCtx.globalAlpha = 0.45;"
        "    _fallbackCtx.lineWidth = 1;"
        "    _fallbackCtx.stroke();"
        "  });"
        "  _fallbackCtx.restore();"
        "}"
        "function _fallbackDraw() {"
        "  if (!_fallbackReady || !_fallbackCtx) { return; }"
        "  var host = document.getElementById('v');"
        "  var w = Math.max(200, host.clientWidth || 900);"
        "  var h = Math.max(200, host.clientHeight || 650);"
        "  _fallbackCtx.fillStyle = _fallbackBg;"
        "  _fallbackCtx.fillRect(0, 0, w, h);"
        "  if (!_fallbackAtoms.length) { return; }"
        "  var project = _fallbackProjector(w, h);"
        "  _fallbackDrawReceptor(project);"
        "  _fallbackShapes.forEach(function(s){_fallbackDrawBox(s, project);});"
        "  _fallbackDrawLigands(project);"
        "}"
        "function _fallbackViewer() {"
        "  _fallbackActive = true;"
        "  _renderBackend = 'canvas-fallback';"
        "  _fallbackEnsure();"
        "  return {"
        "    removeAllModels:function(){"
        "      _fallbackAtoms=[];_fallbackBonds=[];_fallbackStyles={};"
        "      _fallbackFocus=null;_fallbackZoom=1;_fallbackModel=0;_fallbackDraw();"
        "    },"
        "    removeAllShapes:function(){_fallbackShapes=[];_fallbackDraw();},"
        "    addModel:function(text, fmt){"
        "      var model = _fallbackModel++;"
        "      if (fmt === 'sdf') {_fallbackParseSdf(text, model);}"
        "      else {_fallbackParsePdb(text, model);}"
        "      _fallbackDraw(); return {model:model};"
        "    },"
        "    setStyle:function(sel, style){"
        "      var key = sel && typeof sel.model === 'number' ? String(sel.model) : '*';"
        "      _fallbackStyles[key] = style || {}; _fallbackDraw();"
        "    },"
        "    zoomTo:function(sel){_fallbackFocus = sel || null; _fallbackDraw();},"
        "    zoom:function(factor){if (factor) {_fallbackZoom *= factor;} _fallbackDraw();},"
        "    render:function(){_fallbackDraw();},"
        "    addBox:function(shape){_fallbackShapes.push(shape); _fallbackDraw();},"
        "    selectedAtoms:function(sel){"
        "      return _fallbackAtomsFor(sel);"
        "    },"
        "    getView:function(){return [0,0,0,0,0,0,1,0];}, setView:function(){},"
        "    setBackgroundColor:function(c){_fallbackBg = c; _fallbackDraw();},"
        "    pngURI:function(){_fallbackDraw(); return _fallbackCanvas.toDataURL('image/png');}"
        "  };"
        "}"
        "function _viewerAspect(w, h) {"
        "  if (_v && _v.renderer && typeof _v.renderer.getAspect === 'function') {"
        "    return _v.renderer.getAspect(w, h);"
        "  }"
        "  return w / h;"
        "}"
        # Re-assert the projection aspect WITHOUT reallocating the WebGL drawing
        # buffer.  3Dmol rebuilds the orthographic frustum every render via
        # camera.top = camera.right / ASPECT, so as long as ASPECT matches the
        # live canvas the molecule never stretches.  Cheap enough to call on each
        # interaction event.
        "function _reassertAspect(w, h) {"
        "  if (!_v) { return; }"
        "  _v.ASPECT = _viewerAspect(w, h);"
        "  if (_v.camera) {"
        "    _v.camera.aspect = _v.ASPECT;"
        "    if (typeof _v.camera.updateProjectionMatrix === 'function') {"
        "      _v.camera.updateProjectionMatrix();"
        "    }"
        "  }"
        "}"
        "function syncViewerSize() {"
        "  var host = document.getElementById('v');"
        "  var rect = host.getBoundingClientRect ? host.getBoundingClientRect() : null;"
        "  var w = Math.round((rect && rect.width) || host.clientWidth"
        " || window.innerWidth || 900);"
        "  var h = Math.round((rect && rect.height) || host.clientHeight"
        " || window.innerHeight || 650);"
        "  w = Math.max(200, w); h = Math.max(200, h);"
        "  if (_fallbackActive) { _fallbackResize(); return {width:w,height:h,fallback:true}; }"
        "  try {"
        "    var canvas = host.querySelector('canvas');"
        "    var changed = (w !== _lastSyncW || h !== _lastSyncH);"
        "    if (_v) {"
        "      if (changed) {"
        "        _v.WIDTH = w; _v.HEIGHT = h;"
        "        _v.ASPECT = _viewerAspect(w, h);"
        "        if (_v.renderer && typeof _v.renderer.setSize === 'function') {"
        "          _v.renderer.setSize(w, h);"
        "        }"
        "        if (_v.camera) {"
        "          _v.camera.aspect = _v.ASPECT;"
        "          if (typeof _v.camera.updateProjectionMatrix === 'function') {"
        "            _v.camera.updateProjectionMatrix();"
        "          }"
        "        }"
        "        if (typeof _v.setSlabAndFog === 'function') { _v.setSlabAndFog(); }"
        "      } else {"
        "        _reassertAspect(w, h);"
        "      }"
        "    }"
        "    canvas = host.querySelector('canvas');"
        "    if (canvas && changed) {"
        "      var dpr = window.devicePixelRatio || 1;"
        "      var cw = Math.max(1, Math.round(w * dpr));"
        "      var ch = Math.max(1, Math.round(h * dpr));"
        "      canvas.style.width = w + 'px';"
        "      canvas.style.height = h + 'px';"
        "      if (!_v || !_v.renderer) {"
        "        canvas.width = cw; canvas.height = ch;"
        "      }"
        "    }"
        "    _lastSyncW = w; _lastSyncH = h;"
        "    return {width:w,height:h,fallback:false,"
        "            aspect:w / h,"
        "            canvasWidth:canvas ? canvas.width : 0,"
        "            canvasHeight:canvas ? canvas.height : 0};"
        "  } catch (e) {"
        "    return {width:w,height:h,fallback:false,error:String(e && (e.message || e))};"
        "  }"
        "}"
        "function scheduleViewerResize() {"
        "  if (_resizeToken) { cancelAnimationFrame(_resizeToken); }"
        "  _resizeToken = requestAnimationFrame(function() {"
        "    _resizeToken = 0;"
        "    syncViewerSize();"
        "    try { if (_v) { _v.render(); } } catch (e) {}"
        "  });"
        "}"
        "window.addEventListener('resize', scheduleViewerResize);"
        "try {"
        "  _webglInfo = _probeWebGL();"
        "  if (!_webglInfo.available) { throw new Error(_webglInfo.error || 'WebGL unavailable'); }"
        "  _v = $3Dmol.createViewer(document.getElementById('v'),"
        "                           {backgroundColor:'#1E1E2E'});"
        "  _fallbackActive = false;"
        "  _renderBackend = 'py3dmol-webgl';"
        "} catch (e) {"
        "  _webglInfo.error = String(e && (e.message || e));"
        "  console.error('3Dmol WebGL unavailable; using Canvas fallback:', e);"
        "  _v = _fallbackViewer();"
        "}"
        "syncViewerSize();"
        "try {"
        "  if (window.ResizeObserver) {"
        "    new ResizeObserver(scheduleViewerResize).observe(document.getElementById('v'));"
        "  }"
        "} catch (e) {}"
        # Re-sync the aspect the instant the user starts interacting, in the
        # CAPTURE phase so it runs before 3Dmol's own mouse/wheel handlers.  This
        # is what stops the molecule from stretching/flattening on the first drag
        # or zoom after results load (ASPECT may have gone stale between loads).
        "function _resyncForInteraction() {"
        "  if (_v && !_fallbackActive) { try { syncViewerSize(); } catch (e) {} }"
        "}"
        "try {"
        "  var _ihost = document.getElementById('v');"
        "  ['mousedown','wheel','touchstart','dblclick'].forEach(function(ev) {"
        "    _ihost.addEventListener(ev, _resyncForInteraction, true);"
        "  });"
        "} catch (e) {}"
        # ---- public JS API called from Python via runJavaScript ----
        "function loadReceptor(pdbText) {"
        "  syncViewerSize();"
        "  _v.removeAllModels(); _v.removeAllShapes();"
        "  _v.addModel(pdbText, 'pdb');"
        "  _v.setStyle({}, {cartoon:{color:'spectrum'}});"
        "  _v.zoomTo(); _v.render();"
        "  requestAnimationFrame(function(){syncViewerSize();_v.zoomTo();_v.render();});"
        "}"
        "function loadLigand(sdfText) {"
        "  syncViewerSize();"
        "  _v.addModel(sdfText, 'sdf');"
        "  _v.setStyle({model:-1}, {stick:{colorscheme:'greenCarbon'}});"
        "  _v.zoomTo({model:-1}); _v.zoom(0.7); _v.render();"
        "  requestAnimationFrame(function(){"
        "syncViewerSize();_v.zoomTo({model:-1});_v.zoom(0.7);_v.render();});"
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
        "  syncViewerSize();"
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
        "  requestAnimationFrame(function(){syncViewerSize();_v.zoomTo();_v.render();});"
        "}"
        "function setViewerBg(hexColor) {"
        "  _v.setBackgroundColor(hexColor); _v.render();"
        "}"
        # Screenshot: render → wait for GPU frame → return pngURI
        "function requestScreenshot() {"
        "  syncViewerSize();"
        "  _v.render();"
        "  return new Promise(function(resolve) {"
        "    requestAnimationFrame(function() {"
        "      syncViewerSize();"
        "      _v.render();"
        "      requestAnimationFrame(function() { resolve(_v.pngURI()); });"
        "    });"
        "  });"
        "}"
        "function viewerStatus() {"
        "  var atoms = 0;"
        "  var size = syncViewerSize();"
        "  try { atoms = _v.selectedAtoms({}).length; } catch (e) { atoms = -1; }"
        "  return {fallback:!!_fallbackActive, backend:_renderBackend,"
        "          webgl:_webglInfo, atoms:atoms, size:size};"
        "}"
        "</script>"
        "</body></html>"
    )


_HTML = "" if _prefer_native_viewer() else _build_html()


class _WebEngineViewer3D(QWebEngineView):
    """Renders receptor + ligand poses using py3Dmol (offline, bundled JS)."""

    #: Default background color (dark, matching app theme)
    DEFAULT_BG = "#1E1E2E"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ready = False
        self._pending: list[str] = []
        self._pending_callbacks: list[Callable[[], None]] = []
        self._bg_color: str = self.DEFAULT_BG
        self._capture_token = 0
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
        if self._ready:
            QTimer.singleShot(0, lambda: self.page().runJavaScript("scheduleViewerResize();"))

    def set_background_color(self, hex_color: str) -> None:
        """Change the viewer canvas background color (e.g. '#FFFFFF').

        The color is persisted so ``capture_png`` captures with the chosen
        background.  Pass ``Viewer3D.DEFAULT_BG`` to restore the dark default.
        """
        self._bg_color = hex_color
        self._run_js(f"setViewerBg('{hex_color}');")

    def refit(self) -> None:
        """Re-sync the canvas size/aspect and refit zoom to the molecule.

        Call after the viewer becomes visible / is resized so the orthographic
        projection matches the real canvas size (prevents the stretched look).
        ``zoomTo`` only adjusts zoom + translation, never the rotation, so the
        current orientation is preserved.
        """
        self._run_js(
            "syncViewerSize(); if (_v) { try { _v.zoomTo(); } catch (e) {} _v.render(); }"
        )

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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._ready:
            self.page().runJavaScript("scheduleViewerResize();")

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

        # render() → wait two animation frames → read pngURI.  Avoid returning
        # a JS Promise directly; some Qt WebEngine builds hand the unresolved
        # Promise object back to Python, which forces a QWidget.grab() fallback.
        # worldId=0 (MainWorld) keeps this compatible with PySide6 ≤ 6.7 and 6.11+
        def _request() -> None:
            self._capture_token += 1
            token = self._capture_token
            self.page().runJavaScript(
                "(function() {"
                f"  window._dmScreenshotToken = {token};"
                "  window._dmScreenshotReady = false;"
                "  window._dmScreenshotUri = '';"
                "  syncViewerSize();"
                "  _v.render();"
                "  requestAnimationFrame(function() {"
                "    syncViewerSize();"
                "    _v.render();"
                "    requestAnimationFrame(function() {"
                f"      if (window._dmScreenshotToken === {token}) {{"
                "        window._dmScreenshotUri = _v.pngURI();"
                "        window._dmScreenshotReady = true;"
                "      }"
                "    });"
                "  });"
                "  return true;"
                "})();",
                0,
            )

            def _poll(attempt: int = 0) -> None:
                if attempt >= 30:
                    _on_png_uri(None)
                    return
                self.page().runJavaScript(
                    f"(window._dmScreenshotToken === {token} && "
                    "window._dmScreenshotReady) ? window._dmScreenshotUri : null;",
                    0,
                    lambda result: (
                        _on_png_uri(result)
                        if result
                        else QTimer.singleShot(100, lambda: _poll(attempt + 1))
                    ),
                )

            QTimer.singleShot(80, _poll)

        QTimer.singleShot(50, _request)

    def capture_screenshot(self, output_path) -> None:
        """Alias kept for API compatibility."""
        self.capture_png(Path(output_path))


@dataclass(slots=True)
class _Atom3D:
    x: float
    y: float
    z: float
    elem: str
    name: str = ""
    chain: str = ""
    model: int = 0


@dataclass(slots=True)
class _Bond3D:
    a: int
    b: int
    order: int = 1


@dataclass(slots=True)
class _Box3D:
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    selected: bool = False


def _guess_element(name: str, elem: str = "") -> str:
    value = (elem or "").strip()
    if value:
        return value.upper()
    cleaned = "".join(ch for ch in (name or "").strip() if ch.isalpha())
    return (cleaned[:2] or "C").upper()


class _NativeViewer3D(QWidget):
    """Small native Qt molecular preview used by frozen macOS builds."""

    DEFAULT_BG = "#1E1E2E"
    _CHAIN_COLORS = (
        "#6EA8FE", "#54D17A", "#C77DFF", "#F59E0B",
        "#22D3EE", "#F97316", "#A3E635", "#F472B6",
    )
    _ELEMENT_COLORS = {
        "H": "#E5E7EB",
        "C": "#35D07F",
        "N": "#60A5FA",
        "O": "#F87171",
        "S": "#FBBF24",
        "P": "#C084FC",
        "CL": "#86EFAC",
        "F": "#5EEAD4",
        "BR": "#B8895A",
        "I": "#A78BFA",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bg_color = self.DEFAULT_BG
        self._receptor_atoms: list[_Atom3D] = []
        self._ligand_atoms: list[_Atom3D] = []
        self._bonds: list[_Bond3D] = []
        self._boxes: list[_Box3D] = []
        self._rot_x = -0.45
        self._rot_y = 0.75
        self._zoom = 1.0
        self._last_pos: QPoint | None = None
        self.setMinimumSize(240, 200)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("DockMeow native 3D preview")
        self.setAccessibleDescription("Molecular preview rendered by native Qt")

    # ------------------------------------------------------------------
    def suspend_for_page_hide(self) -> None:
        self.clearFocus()
        self.setEnabled(False)
        self.hide()

    def resume_after_page_show(self) -> None:
        self.setEnabled(True)
        self.show()
        self.update()

    def set_background_color(self, hex_color: str) -> None:
        self._bg_color = hex_color
        self.update()

    def refit(self) -> None:
        """Repaint; the native projector auto-fits to the live widget size."""
        self.update()

    def viewer_status(self) -> dict[str, object]:
        return {
            "fallback": False,
            "backend": "native-qt",
            "atoms": len(self._receptor_atoms) + len(self._ligand_atoms),
            "size": {
                "width": max(1, self.width()),
                "height": max(1, self.height()),
                "aspect": max(1, self.width()) / max(1, self.height()),
            },
        }

    # ------------------------------------------------------------------
    def load_receptor(self, pdb_path: Path) -> None:
        try:
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning("NativeViewer3D.load_receptor: cannot read %s: %s", pdb_path, exc)
            return
        self._receptor_atoms = self._parse_pdb(pdb_text)
        self._ligand_atoms = []
        self._bonds = []
        self._boxes = []
        self._zoom = 1.0
        self.update()

    def load_ligand_pose(self, sdf_content: str) -> None:
        atoms, bonds = self._parse_sdf(sdf_content)
        self._ligand_atoms = atoms
        self._bonds = bonds
        self.update()

    def load_result_pose(self, pdb_path: Path, sdf_content: str) -> None:
        try:
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning("NativeViewer3D.load_result_pose: cannot read %s: %s", pdb_path, exc)
            return
        self._receptor_atoms = self._parse_pdb(pdb_text)
        self._ligand_atoms, self._bonds = self._parse_sdf(sdf_content)
        self._boxes = []
        self._zoom = 1.0
        self._orient_ligand_to_front()
        self.update()

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
        self._boxes = [_Box3D(tuple(map(float, center)), tuple(map(float, size)), True)]
        self.update()

    def show_pockets(self, pockets: list[object], selected: object | None = None) -> None:
        self._boxes = self._boxes_from_pockets(pockets, selected)
        self.update()

    def load_receptor_with_pockets(
        self,
        pdb_path: Path,
        pockets: list[object],
        selected: object | None = None,
    ) -> None:
        try:
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.warning(
                "NativeViewer3D.load_receptor_with_pockets: cannot read %s: %s",
                pdb_path,
                exc,
            )
            return
        self._receptor_atoms = self._parse_pdb(pdb_text)
        self._ligand_atoms = []
        self._bonds = []
        self._boxes = self._boxes_from_pockets(pockets, selected)
        self._zoom = 1.0
        self.update()

    def clear(self) -> None:
        self._receptor_atoms = []
        self._ligand_atoms = []
        self._bonds = []
        self._boxes = []
        self.update()

    def load_best_pose_for_export(
        self,
        pdb_path: Path,
        sdf_content: str,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        self.load_result_pose(pdb_path, sdf_content)
        if on_ready is not None:
            QTimer.singleShot(0, on_ready)

    def capture_png(
        self, output_path: Path, callback: Callable[[Path], None] | None = None
    ) -> None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        pix = self.grab()
        if not pix.isNull():
            pix.save(str(out), "PNG")
        if callback is not None:
            callback(out)

    def capture_screenshot(self, output_path) -> None:
        self.capture_png(Path(output_path))

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_pdb(text: str) -> list[_Atom3D]:
        atoms: list[_Atom3D] = []
        for line in text.splitlines():
            if not (line.startswith("ATOM") or line.startswith("HETATM")):
                continue
            try:
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
            except ValueError:
                continue
            name = line[12:16].strip()
            chain = (line[21:22] or " ").strip()
            atoms.append(
                _Atom3D(
                    x=x,
                    y=y,
                    z=z,
                    elem=_guess_element(name, line[76:78] if len(line) >= 78 else ""),
                    name=name,
                    chain=chain,
                    model=0,
                )
            )
        return atoms

    @staticmethod
    def _parse_sdf(text: str) -> tuple[list[_Atom3D], list[_Bond3D]]:
        lines = text.splitlines()
        counts_idx = -1
        atom_count = 0
        bond_count = 0
        for idx, line in enumerate(lines[:10]):
            parts = line.split()
            if len(parts) >= 2 and parts[0].lstrip("-").isdigit() and parts[1].isdigit():
                counts_idx = idx
                atom_count = int(parts[0])
                bond_count = int(parts[1])
                break
        if counts_idx < 0 or atom_count <= 0:
            return [], []

        atoms: list[_Atom3D] = []
        atom_start = counts_idx + 1
        for idx in range(atom_count):
            if atom_start + idx >= len(lines):
                break
            parts = lines[atom_start + idx].split()
            if len(parts) < 4:
                continue
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            except ValueError:
                continue
            atoms.append(_Atom3D(x=x, y=y, z=z, elem=_guess_element(parts[3]), model=1))

        bonds: list[_Bond3D] = []
        bond_start = atom_start + atom_count
        for idx in range(bond_count):
            if bond_start + idx >= len(lines):
                break
            parts = lines[bond_start + idx].split()
            if len(parts) < 2:
                continue
            try:
                a = int(parts[0]) - 1
                b = int(parts[1]) - 1
                order = int(parts[2]) if len(parts) >= 3 else 1
            except ValueError:
                continue
            if 0 <= a < len(atoms) and 0 <= b < len(atoms):
                bonds.append(_Bond3D(a=a, b=b, order=order))
        return atoms, bonds

    @staticmethod
    def _boxes_from_pockets(
        pockets: list[object],
        selected: object | None,
    ) -> list[_Box3D]:
        selected_key = None
        if selected is not None:
            selected_key = (
                getattr(selected, "pocket_id", None),
                getattr(selected, "source", None),
            )
        boxes: list[_Box3D] = []
        for idx, pocket in enumerate(pockets):
            key = (getattr(pocket, "pocket_id", None), getattr(pocket, "source", None))
            boxes.append(
                _Box3D(
                    center=tuple(map(float, getattr(pocket, "center"))),
                    size=tuple(map(float, getattr(pocket, "size"))),
                    selected=key == selected_key if selected_key is not None else idx == 0,
                )
            )
        return boxes

    # ------------------------------------------------------------------
    def _orient_ligand_to_front(self) -> None:
        if not self._receptor_atoms or not self._ligand_atoms:
            return
        rx, ry, rz = self._centroid(self._receptor_atoms)
        lx, ly, lz = self._centroid(self._ligand_atoms)
        dx, dy, dz = lx - rx, ly - ry, lz - rz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 0.5:
            return
        dx, dy, dz = dx / dist, dy / dist, dz / dist
        self._rot_y = math.atan2(dx, dz)
        self._rot_x = -math.atan2(dy, math.sqrt(dx * dx + dz * dz))

    @staticmethod
    def _centroid(atoms: list[_Atom3D]) -> tuple[float, float, float]:
        if not atoms:
            return (0.0, 0.0, 0.0)
        n = float(len(atoms))
        return (
            sum(a.x for a in atoms) / n,
            sum(a.y for a in atoms) / n,
            sum(a.z for a in atoms) / n,
        )

    def _points_for_bounds(self) -> list[tuple[float, float, float]]:
        points = [(a.x, a.y, a.z) for a in self._receptor_trace()]
        points.extend((a.x, a.y, a.z) for a in self._ligand_atoms)
        for box in self._boxes:
            points.extend(self._box_corners(box))
        return points or [(0.0, 0.0, 0.0)]

    def _projector(self):
        width = max(1, self.width())
        height = max(1, self.height())
        points = self._points_for_bounds()
        xs, ys, zs = zip(*points)
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        cz = (min(zs) + max(zs)) / 2.0
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
        scale = min(width, height) * 0.42 * self._zoom / (span / 2.0)
        sin_x, cos_x = math.sin(self._rot_x), math.cos(self._rot_x)
        sin_y, cos_y = math.sin(self._rot_y), math.cos(self._rot_y)

        def project(point: tuple[float, float, float]) -> tuple[float, float, float]:
            x, y, z = point[0] - cx, point[1] - cy, point[2] - cz
            x1 = x * cos_y + z * sin_y
            z1 = -x * sin_y + z * cos_y
            y1 = y * cos_x - z1 * sin_x
            z2 = y * sin_x + z1 * cos_x
            return (width / 2.0 + x1 * scale, height / 2.0 - y1 * scale, z2)

        return project

    def _receptor_trace(self) -> list[_Atom3D]:
        atoms = [a for a in self._receptor_atoms if a.name.upper() == "CA"]
        if len(atoms) < 5:
            step = max(1, len(self._receptor_atoms) // 260)
            atoms = self._receptor_atoms[::step]
        return atoms

    @staticmethod
    def _box_corners(box: _Box3D) -> list[tuple[float, float, float]]:
        cx, cy, cz = box.center
        sx, sy, sz = (v / 2.0 for v in box.size)
        return [
            (cx - sx, cy - sy, cz - sz),
            (cx + sx, cy - sy, cz - sz),
            (cx + sx, cy + sy, cz - sz),
            (cx - sx, cy + sy, cz - sz),
            (cx - sx, cy - sy, cz + sz),
            (cx + sx, cy - sy, cz + sz),
            (cx + sx, cy + sy, cz + sz),
            (cx - sx, cy + sy, cz + sz),
        ]

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._bg_color))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        project = self._projector()
        self._draw_receptor(painter, project)
        self._draw_boxes(painter, project)
        self._draw_ligand(painter, project)
        painter.end()

    def _draw_receptor(self, painter: QPainter, project) -> None:
        trace = self._receptor_trace()
        if len(trace) < 2:
            return
        chains: dict[str, list[_Atom3D]] = {}
        for atom in trace:
            chains.setdefault(atom.chain or " ", []).append(atom)
        for idx, (_chain, atoms) in enumerate(chains.items()):
            color = QColor(self._CHAIN_COLORS[idx % len(self._CHAIN_COLORS)])
            shadow = QColor(color)
            shadow.setAlphaF(0.22)
            pen = QPen(shadow, 6.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            self._draw_polyline(painter, [project((a.x, a.y, a.z)) for a in atoms])

            color.setAlphaF(0.72)
            pen = QPen(color, 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            self._draw_polyline(painter, [project((a.x, a.y, a.z)) for a in atoms])

    @staticmethod
    def _draw_polyline(
        painter: QPainter,
        points: list[tuple[float, float, float]],
    ) -> None:
        for a, b in zip(points, points[1:]):
            painter.drawLine(round(a[0]), round(a[1]), round(b[0]), round(b[1]))

    def _draw_boxes(self, painter: QPainter, project) -> None:
        edges = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
        for box in self._boxes:
            color = QColor("#FF9500" if box.selected else "#9CA3AF")
            color.setAlphaF(0.88 if box.selected else 0.35)
            painter.setPen(QPen(color, 2.0 if box.selected else 1.0))
            corners = [project(p) for p in self._box_corners(box)]
            for a, b in edges:
                painter.drawLine(
                    round(corners[a][0]),
                    round(corners[a][1]),
                    round(corners[b][0]),
                    round(corners[b][1]),
                )

    def _draw_ligand(self, painter: QPainter, project) -> None:
        if not self._ligand_atoms:
            return
        projected = [project((a.x, a.y, a.z)) for a in self._ligand_atoms]
        bond_pen = QPen(QColor("#35D07F"), 4.0)
        bond_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bond_pen)
        for bond in self._bonds:
            a = projected[bond.a]
            b = projected[bond.b]
            painter.drawLine(round(a[0]), round(a[1]), round(b[0]), round(b[1]))

        order = sorted(range(len(self._ligand_atoms)), key=lambda i: projected[i][2])
        for idx in order:
            atom = self._ligand_atoms[idx]
            x, y, _z = projected[idx]
            color = QColor(self._ELEMENT_COLORS.get(atom.elem.upper(), "#35D07F"))
            painter.setPen(QPen(QColor("#0F172A"), 1.0))
            painter.setBrush(color)
            r = 5 if atom.elem.upper() != "H" else 3
            painter.drawEllipse(round(x - r), round(y - r), 2 * r, 2 * r)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = event.position().toPoint()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._last_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        pos = event.position().toPoint()
        delta = pos - self._last_pos
        self._last_pos = pos
        self._rot_y += delta.x() * 0.01
        self._rot_x += delta.y() * 0.01
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802, ARG002
        self._last_pos = None

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self._zoom = max(0.2, min(4.0, self._zoom * factor))
        self.update()


Viewer3D = _NativeViewer3D if _prefer_native_viewer() else _WebEngineViewer3D
