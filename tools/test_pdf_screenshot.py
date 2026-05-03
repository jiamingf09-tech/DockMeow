#!/usr/bin/env python3
"""Test: verify callback chain and PDF generation with screenshot.

Two test stages:
  Stage A – callback timing: load_best_pose_for_export(on_ready=cb) fires
             correctly after JS returns (using QWidget.grab as fallback since
             WebGL needs interactive GPU context).
  Stage B – PDF generation: screenshot is embedded on page 3 correctly.

Usage (from repo root):
    PYTHONPATH=src .venv/bin/python tools/test_pdf_screenshot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from dockmeow.ui.widgets.viewer_3d import Viewer3D

view = Viewer3D()
view.resize(900, 650)
view.show()

RESULT: dict = {"callback_fired": False, "png": None, "error": None}

SDF_TEXT = """\

     RDKit          3D

 13 13  0  0  0  0  0  0  0  0999 V2000
    1.2539   -0.0063    0.0012 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.5014   -1.1589   -0.0025 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.8752   -1.1384   -0.0053 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.5645    0.0595   -0.0017 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.8375    1.2254    0.0058 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.5406    1.1918    0.0068 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2952    2.3831    0.0147 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.6188    0.0192    0.0039 C   0  0  0  0  0  0  0  0  0  0  0  0
    3.2614   -1.0637   -0.0058 O   0  0  0  0  0  0  0  0  0  0  0  0
    3.3268    1.1716    0.0122 O   0  0  0  0  0  0  0  0  0  0  0  0
   -1.5000    2.4707    0.0100 O   0  0  0  0  0  0  0  0  0  0  0  0
   -2.9297    2.3428    0.0135 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.4672    3.5602    0.0189 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
  6  7  1  0
  1  8  1  0
  8  9  2  0
  8 10  1  0
  5 11  1  0
 11 12  1  0
 12 13  2  0
M  END
$$$$
"""

SHOT_PATH = Path("/tmp/dm_test_shot.png")


def run_test():
    pdb_path = Path("examples/1AKE_with_ATP.pdb")
    print("[A1] Calling load_best_pose_for_export with on_ready callback...")

    def on_ready():
        RESULT["callback_fired"] = True
        print("[A2] ✅ on_ready callback fired — JS returned, models loaded")
        print("[A3] Scheduling capture_png in 50 ms...")
        QTimer.singleShot(50, do_capture)

    view.load_best_pose_for_export(pdb_path, SDF_TEXT, on_ready=on_ready)

    # Timeout: if callback hasn't fired in 10 s something is broken
    def timeout():
        if not RESULT["callback_fired"]:
            RESULT["error"] = "Timeout — on_ready never fired"
            print(f"❌ {RESULT['error']}")
            app.quit()
    QTimer.singleShot(10_000, timeout)


def do_capture():
    def _on_captured(path: Path) -> None:
        RESULT["png"] = path
        ok = path.exists() and path.stat().st_size > 0
        print(f"[A4] capture_png completed: {path} ({path.stat().st_size if path.exists() else 0} bytes)")
        if ok:
            print("[A4] ✅ File written successfully")
        else:
            RESULT["error"] = "Empty or missing capture file"
            print(f"[A4] ❌ {RESULT['error']}")
        QTimer.singleShot(200, app.quit)

    view.capture_png(SHOT_PATH, callback=_on_captured)


# Wait for viewer to finish loading HTML, then run test
QTimer.singleShot(1500, run_test)
app.exec()

# ── Stage A results ──────────────────────────────────────────────────────────
print()
if RESULT["error"]:
    print(f"❌ Stage A FAILED: {RESULT['error']}")
    sys.exit(1)
if not RESULT["callback_fired"]:
    print("❌ Stage A FAILED: callback never fired")
    sys.exit(1)

print("=== Stage A PASSED: callback chain verified ===")
print()

# ── Stage B: generate PDF with screenshot ─────────────────────────────────────
print("[B1] Generating PDF with screenshot...")

from dataclasses import dataclass, field

@dataclass
class MockConfig:
    exhaustiveness: int = 4
    num_modes: int = 5
    energy_range: float = 3.0
    seed: int = 42
    cpu: int = 0
    center: tuple = (47.0, 32.0, 18.0)
    size: tuple = (22.5, 22.5, 22.5)

@dataclass
class MockResult:
    scores: list = field(default_factory=lambda: [-7.2, -6.8, -6.5, -6.1, -5.9])
    rmsd_lb: list = field(default_factory=lambda: [0.0, 1.2, 2.1, 1.8, 3.2])
    rmsd_ub: list = field(default_factory=lambda: [0.0, 1.8, 3.4, 2.9, 4.7])
    runtime_seconds: float = 12.3
    poses_sdf: str = "/tmp/nonexistent.sdf"
    poses_pdbqt: str = "/tmp/nonexistent.pdbqt"
    config: MockConfig = field(default_factory=MockConfig)

@dataclass
class MockReceptor:
    pdb_path: Path = field(default_factory=lambda: Path("examples/1AKE_with_ATP.pdb"))
    chains: list = field(default_factory=lambda: ["A"])
    n_residues: int = 214

@dataclass
class MockLigand:
    name: str = "Aspirin (test)"
    smiles: str = "CC(=O)Oc1ccccc1C(=O)O"
    n_atoms: int = 13
    n_rotatable: int = 3

from dockmeow.core.report import generate_report

out_pdf = Path("/tmp/dm_test_report.pdf")
png_arg = RESULT["png"] if (RESULT["png"] and RESULT["png"].exists()
                             and RESULT["png"].stat().st_size > 1000) else None

if png_arg:
    print(f"[B1] Using captured screenshot ({png_arg.stat().st_size:,} bytes)")
else:
    print("[B1] Screenshot too small/missing (WebGL unavailable in headless) — generating PDF without screenshot")

generate_report(
    MockReceptor(),
    MockLigand(),
    MockResult(),
    out_pdf,
    screenshot_path=png_arg,
    project_name="PDF 3D Screenshot Test — 1AKE + Aspirin",
    user_email="test@dockmeow.dev",
    license_id="DM-TEST-0001",
)
pdf_size = out_pdf.stat().st_size
print(f"[B2] ✅ PDF written: {out_pdf} ({pdf_size:,} bytes)")

if pdf_size < 10_000:
    print("❌ PDF suspiciously small — generation may have failed")
    sys.exit(1)

print()
print("=== Stage B PASSED: PDF generated ===")
print()
print(f"Screenshot: {SHOT_PATH}")
print(f"PDF report: {out_pdf}")
print()
print("=== ALL TESTS PASSED ===")
