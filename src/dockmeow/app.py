"""Top-level QApplication setup and application lifecycle management."""

from __future__ import annotations

import logging as _logging
import os
import sys
import time as _time
import traceback as _traceback
from pathlib import Path as _Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dockmeow.utils.logging_setup import setup_logging
from dockmeow.utils.paths import resource_path


def _configure_webengine_flags() -> None:
    """Install Chromium flags before QtWebEngine is imported.

    Platform-specific notes:
    - Frozen (PyInstaller) macOS bundles require extra flags because:
    - The app is not code-signed, so macOS refuses to spawn Chromium's
      separate GPU subprocess → use --in-process-gpu to keep GPU in-process.
    - Without a sandbox entitlement the Chromium sandbox init fails →
      --no-sandbox disables it (acceptable for a local desktop tool with no
      untrusted web content; we only render inline HTML + local PDB text).
    - On Windows, prefer ANGLE/D3D11 WebGL so py3Dmol can render the same
      colorful cartoon/stick scene as macOS. Operators can still opt into the
      stable CPU Canvas path with DOCKMEOW_WEBENGINE_MODE=cpu/software/canvas
      on machines with broken WebGL drivers.
    - --disable-renderer-accessibility avoids VoiceOver/MSAA Chromium AX crashes.
    """
    _flags = [
        "--disable-renderer-accessibility",
    ]
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        # Additional stability flags for PyInstaller .app bundle
        _flags += [
            "--in-process-gpu",       # no separate GPU subprocess (unsigned app)
            "--no-sandbox",           # no sandbox entitlement in unsigned bundle
            "--disable-dev-shm-usage",  # avoid /dev/shm issues
        ]
    elif sys.platform == "win32":
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        mode = os.environ.get("DOCKMEOW_WEBENGINE_MODE", "angle-d3d11").strip().lower()
        _flags += ["--no-sandbox"]
        if mode in {"software", "canvas", "cpu"}:
            _flags += ["--disable-gpu"]
        elif mode == "swiftshader":
            _flags += [
                "--ignore-gpu-blocklist",
                "--enable-webgl",
                "--enable-webgl2",
                "--enable-unsafe-swiftshader",
                "--use-gl=swiftshader-webgl",
            ]
        elif mode in {"angle-d3d11", "d3d11", "gpu", "auto"}:
            _flags += [
                "--ignore-gpu-blocklist",
                "--enable-webgl",
                "--enable-webgl2",
                "--enable-unsafe-swiftshader",
                "--use-angle=d3d11",
            ]
        else:
            _flags += [
                "--ignore-gpu-blocklist",
                "--enable-webgl",
                "--enable-webgl2",
                "--enable-unsafe-swiftshader",
            ]

    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    parts = current.split()
    webengine_mode = os.environ.get("DOCKMEOW_WEBENGINE_MODE", "angle-d3d11").strip().lower()
    if sys.platform == "win32" and webengine_mode not in {"software", "canvas", "cpu"}:
        parts = [
            part for part in parts
            if part.split("=", 1)[0]
            not in {"--disable-gpu", "--disable-software-rasterizer"}
        ]
    for flag in _flags:
        if flag not in parts:
            parts.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts).strip()


def _force_pyside_eager_import() -> None:
    """Pre-import every PySide6 sub-module in the MAIN THREAD.

    Must be called AFTER QApplication is created (QtWebEngineWidgets requires it).

    In PyInstaller bundles PySide6 uses Shiboken lazy-import which calls
    ``dlopen`` the first time a sub-module is accessed.  When that access
    happens inside a QThread worker macOS dyld raises EXC_BAD_ACCESS
    (``mach_o::Header::forEachLoadCommand`` is not re-entrant from non-main
    threads).  Importing everything here converts future accesses to plain
    dict lookups – no dlopen needed.
    """
    _mods = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport",
    ]
    for _mod in _mods:
        try:
            __import__(_mod)
        except Exception:  # noqa: BLE001
            pass



def _install_excepthook() -> None:
    """Install a global exception handler that shows a dialog instead of crashing."""
    import sys as _sys

    def _excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
        _logging.getLogger("dockmeow").critical("未捕获异常:\n%s", tb_str)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None,
                    "发生意外错误",
                    f"软件遇到未预期的错误，已记录到日志。\n\n"
                    f"如反复出现，请将日志发送给客服。\n\n"
                    f"错误类型: {exc_type.__name__}\n"
                    f"详情: {exc_value}",
                )
        except Exception:
            pass

    _sys.excepthook = _excepthook


def create_app() -> QApplication:
    """Create and configure the QApplication instance."""
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("DockMeow")
    app.setOrganizationName("DockMeow")

    qss = resource_path("ui/resources/styles.qss")
    if qss.exists():
        try:
            app.setStyleSheet(qss.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    return app


def _check_license() -> dict | None:
    """Best-effort license check; returns the payload or None."""
    from dockmeow.core.exceptions import LicenseError
    from dockmeow.licensing.time_guard import check_clock_integrity
    from dockmeow.licensing.verifier import LicenseVerifier

    try:
        check_clock_integrity()
    except Exception:  # noqa: BLE001
        pass
    try:
        return LicenseVerifier().load_and_verify()
    except LicenseError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _run_e2e_smoke(app: QApplication) -> int:
    """Run a hidden packaged-app smoke test when requested by environment."""
    import json as _json
    import tempfile as _tempfile

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QImage

    from dockmeow.core.docking import DockingConfig, run_docking
    from dockmeow.core.ligand import prepare_ligand_from_file
    from dockmeow.core.pocket import detect_pockets
    from dockmeow.core.receptor import prepare_receptor
    from dockmeow.ui.widgets.viewer_3d import Viewer3D

    root = _Path(__file__).resolve().parents[2]
    default_pdb = root / "example" / "1SVC.pdb"
    default_ligand = root / "example" / "Ailanthone.sdf"

    pdb_path = _Path(os.environ.get("DOCKMEOW_SMOKE_PDB", str(default_pdb)))
    ligand_path = _Path(os.environ.get("DOCKMEOW_SMOKE_LIGAND", str(default_ligand)))
    out_dir = _Path(
        os.environ.get(
            "DOCKMEOW_SMOKE_OUT",
            str(_Path(_tempfile.gettempdir()) / "dockmeow_e2e_smoke"),
        )
    )
    result_json = _Path(
        os.environ.get("DOCKMEOW_SMOKE_RESULT", str(out_dir / "smoke_result.json"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    result_json.parent.mkdir(parents=True, exist_ok=True)

    result_data: dict[str, object] = {
        "ok": False,
        "pdb": str(pdb_path),
        "ligand": str(ligand_path),
        "out_dir": str(out_dir),
    }

    def _write_result(code: int, error: str | None = None) -> int:
        if error:
            result_data["error"] = error
        result_json.write_text(
            _json.dumps(result_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return code

    def _wait_ms(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def _image_has_content(path: _Path) -> bool:
        if not path.exists() or path.stat().st_size < 5000:
            return False
        image = QImage(str(path))
        if image.isNull() or image.width() < 64 or image.height() < 64:
            return False
        colors: set[int] = set()
        x_step = max(1, image.width() // 32)
        y_step = max(1, image.height() // 32)
        for x in range(0, image.width(), x_step):
            for y in range(0, image.height(), y_step):
                colors.add(int(image.pixel(x, y)))
                if len(colors) > 2:
                    return True
        return False

    def _split_sdf_blocks(text: str) -> list[str]:
        blocks: list[str] = []
        for raw in text.split("$$$$"):
            block = raw.strip()
            if block:
                blocks.append(block + "\n$$$$\n")
        return blocks

    def _viewer_status(viewer: Viewer3D, key: str) -> dict[str, object]:
        status: dict[str, object] = {}

        def _read_once() -> dict[str, object]:
            done = {"value": False}
            current: dict[str, object] = {}

            def _on_status(value: object) -> None:
                if isinstance(value, str):
                    try:
                        decoded = _json.loads(value)
                    except Exception:  # noqa: BLE001
                        current["raw"] = repr(value)
                    else:
                        if isinstance(decoded, dict):
                            current.update(decoded)
                        else:
                            current["raw"] = repr(decoded)
                elif isinstance(value, dict):
                    current.update(value)
                else:
                    current["raw"] = repr(value)
                done["value"] = True

            viewer.page().runJavaScript(
                "JSON.stringify(viewerStatus());", 0, _on_status
            )
            deadline = _time.time() + 1
            while not done["value"] and _time.time() < deadline:
                _wait_ms(100)
                app.processEvents()
            return current

        deadline = _time.time() + 10
        while _time.time() < deadline:
            status = _read_once()
            atoms = status.get("atoms")
            if isinstance(atoms, (int, float)) and atoms > 0:
                break
            _wait_ms(150)
            app.processEvents()

        result_data[f"{key}_viewer_status"] = status
        fallback_allowed = (
            bool(os.environ.get("DOCKMEOW_SMOKE_ALLOW_FALLBACK"))
            or os.environ.get("DOCKMEOW_WEBENGINE_MODE", "angle-d3d11").strip().lower()
            in {"software", "canvas", "cpu"}
        )
        if "fallback" not in status and not fallback_allowed:
            raise RuntimeError(f"3D viewer status unavailable: {status!r}")
        if status.get("fallback") is True and not fallback_allowed:
            raise RuntimeError(
                "3D viewer is using Canvas fallback instead of py3Dmol/WebGL"
            )
        atoms = status.get("atoms")
        if not isinstance(atoms, (int, float)) or atoms <= 0:
            raise RuntimeError(f"3D viewer loaded no atoms for {key}: {status!r}")
        return status

    def _capture_viewer_png(viewer: Viewer3D, key: str, path: _Path) -> None:
        done = {"value": False}

        def _on_capture(captured_path: _Path) -> None:
            done["value"] = True
            result_data[f"{key}_png"] = str(captured_path)
            result_data[f"{key}_png_size"] = (
                captured_path.stat().st_size if captured_path.exists() else 0
            )

        viewer.capture_png(path, callback=_on_capture)
        deadline = _time.time() + 20
        while not done["value"] and _time.time() < deadline:
            _wait_ms(100)
            app.processEvents()

        if not _image_has_content(path):
            raise RuntimeError(f"3D viewer capture is blank or missing: {path}")

    try:
        t0 = _time.perf_counter()
        viewer_receptor_path = pdb_path
        best_sdf_block: str | None = None
        pockets_for_preview: list[object] = []
        selected_pocket: object | None = None
        if not os.environ.get("DOCKMEOW_SMOKE_VIEWER_ONLY"):
            receptor = prepare_receptor(pdb_path, out_dir / "receptor")
            ligand = prepare_ligand_from_file(ligand_path, out_dir / "ligand")
            pockets = detect_pockets(receptor, pdb_path)
            pocket = pockets[0]
            pockets_for_preview = list(pockets)
            selected_pocket = pocket
            docking = run_docking(
                DockingConfig(
                    receptor_pdbqt=receptor.pdbqt_path,
                    ligand_pdbqt=ligand.pdbqt_path,
                    center=pocket.center,
                    size=pocket.size,
                    exhaustiveness=int(
                        os.environ.get("DOCKMEOW_SMOKE_EXHAUSTIVENESS", "1")
                    ),
                    num_modes=int(os.environ.get("DOCKMEOW_SMOKE_NUM_MODES", "3")),
                    seed=42,
                )
            )
            viewer_receptor_path = _Path(receptor.pdb_path)
            result_data.update(
                {
                    "best_score": docking.scores[0],
                    "pose_count": len(docking.scores),
                    "pdbqt": str(receptor.pdbqt_path),
                    "poses_pdbqt": str(docking.poses_pdbqt),
                    "poses_sdf": str(docking.poses_sdf),
                    "pocket_source": getattr(pocket, "source", ""),
                    "pocket_center": list(getattr(pocket, "center", ())),
                    "pocket_size": list(getattr(pocket, "size", ())),
                }
            )
            sdf_text = (
                _Path(docking.poses_sdf).read_text(
                    encoding="utf-8", errors="replace"
                )
                if _Path(docking.poses_sdf).exists()
                else ""
            )
            sdf_blocks = _split_sdf_blocks(sdf_text)
            result_data["sdf_block_count"] = len(sdf_blocks)
            if sdf_blocks:
                best_sdf_block = sdf_blocks[0]
            else:
                return _write_result(4, "Docking produced no previewable SDF pose")
        else:
            result_data["viewer_only"] = True
            smoke_sdf = os.environ.get("DOCKMEOW_SMOKE_SDF")
            if smoke_sdf:
                sdf_path = _Path(smoke_sdf)
                sdf_text = (
                    sdf_path.read_text(encoding="utf-8", errors="replace")
                    if sdf_path.exists()
                    else ""
                )
                sdf_blocks = _split_sdf_blocks(sdf_text)
                result_data["sdf_block_count"] = len(sdf_blocks)
                if sdf_blocks:
                    best_sdf_block = sdf_blocks[0]
                else:
                    return _write_result(4, "Smoke SDF has no previewable pose")

        viewer = Viewer3D()
        viewer.resize(900, 650)
        viewer.show()
        app.processEvents()
        viewer.load_receptor(viewer_receptor_path)
        _wait_ms(1500)

        _viewer_status(viewer, "receptor")
        _capture_viewer_png(viewer, "receptor", out_dir / "viewer_receptor.png")

        if pockets_for_preview:
            viewer.load_receptor_with_pockets(
                viewer_receptor_path, pockets_for_preview, selected_pocket
            )
            _wait_ms(500)
            _viewer_status(viewer, "pocket")
            _capture_viewer_png(viewer, "pocket", out_dir / "viewer_pocket.png")

        if best_sdf_block is not None:
            viewer.load_result_pose(viewer_receptor_path, best_sdf_block)
            _wait_ms(1500)
            _viewer_status(viewer, "result_pose")
            _capture_viewer_png(
                viewer, "result_pose", out_dir / "viewer_result_pose.png"
            )

        viewer.close()
        viewer.deleteLater()
        _wait_ms(200)

        result_data.update(
            {
                "runtime_seconds": round(_time.perf_counter() - t0, 3),
            }
        )
        result_data["ok"] = True
        return _write_result(0)
    except Exception as exc:  # noqa: BLE001
        _logging.getLogger("dockmeow").exception("DockMeow smoke test failed")
        return _write_result(2, f"{type(exc).__name__}: {exc}")


def run() -> int:
    """Full application lifecycle: create → license-check → main window → exec."""
    _configure_webengine_flags()
    setup_logging()
    _install_excepthook()
    _log = _logging.getLogger("dockmeow")
    _log.info("DockMeow startup: begin")

    # QApplication must exist before importing QtWebEngineWidgets.
    app = create_app()
    _log.info("DockMeow startup: QApplication ready")

    # Pre-import PySide6 sub-modules so worker QThreads never trigger
    # Shiboken lazy-import / dlopen (macOS PyInstaller dyld crash).
    # Scientific C-extensions are pre-loaded at module level in
    # receptor.py and ligand.py which are imported via main_window below.
    _force_pyside_eager_import()
    _log.info("DockMeow startup: PySide eager import finished")

    if os.environ.get("DOCKMEOW_SMOKE_E2E"):
        return _run_e2e_smoke(app)

    license_data = _check_license()
    _log.info("DockMeow startup: license check finished")

    from dockmeow.ui.main_window import MainWindow

    window = MainWindow(license_data)
    window.show()
    _log.info("DockMeow startup: main window shown")
    return app.exec()
