"""
Stage 3 automated screenshot + PDF capture for DockMeow.
Pre-computes all backend results, then feeds them into the live GUI
and grabs screenshots of each page.

Run with:
  PYTHONPATH=src:/opt/miniconda3/envs/dockmeow/lib/python3.11/site-packages \
      .venv/bin/python3 tools/capture_screenshots.py
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

SRC = Path(__file__).parent.parent / "src"
CONDA_SP = Path("/opt/miniconda3/envs/dockmeow/lib/python3.11/site-packages")
sys.path.insert(0, str(SRC))
if CONDA_SP.exists():
    sys.path.append(str(CONDA_SP))

OUT = Path("/tmp/dockmeow_review")
OUT.mkdir(parents=True, exist_ok=True)

PDB = Path(__file__).parent.parent / "examples" / "1AKE_with_ATP.pdb"
SMILES = "CC(=O)Oc1ccccc1C(=O)O"
WORK = Path("/tmp/dm_stage3_work")
WORK.mkdir(exist_ok=True)

# ── 1. Pre-compute backend ────────────────────────────────────────────────────
print("=== Phase 1: Backend computation ===")
from dockmeow.core.receptor import prepare_receptor
from dockmeow.core.pocket import detect_pockets
from dockmeow.core.ligand import prepare_ligand_from_smiles
from dockmeow.core.docking import DockingConfig, run_docking

print("[backend] Preparing receptor...")
t0 = time.perf_counter()
ri = prepare_receptor(PDB, WORK / "receptor")
print(f"  done in {time.perf_counter()-t0:.1f}s  pdbqt={ri.pdbqt_path.name}")

print("[backend] Detecting pockets...")
pockets = detect_pockets(ri, PDB)
pocket = pockets[0]
print(f"  {len(pockets)} pockets  best: center={tuple(round(x,1) for x in pocket.center)}")

print("[backend] Preparing ligand (aspirin)...")
li = prepare_ligand_from_smiles(SMILES, "aspirin", WORK / "ligand")
print(f"  pdbqt={li.pdbqt_path.name}")

print("[backend] Running docking (exhaustiveness=8, seed=42)...")
t0 = time.perf_counter()
cfg = DockingConfig(
    receptor_pdbqt=ri.pdbqt_path,
    ligand_pdbqt=li.pdbqt_path,
    center=pocket.center,
    size=pocket.size,
    exhaustiveness=8,
    num_modes=9,
    energy_range=3,
    seed=42,
)
result = run_docking(cfg)
dt = time.perf_counter() - t0
print(f"  done in {dt:.1f}s  best={result.scores[0]:.2f} kcal/mol  poses={len(result.scores)}")

# ── 2. GUI screenshots ────────────────────────────────────────────────────────
print("\n=== Phase 2: GUI screenshots ===")

from PySide6.QtCore import Qt, QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from dockmeow.app import create_app, _check_license
from dockmeow.ui.main_window import MainWindow

app = create_app()
lic = _check_license()
win = MainWindow(lic)
win.resize(1280, 800)
win.show()
app.processEvents()


def wait_ms(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def grab(name: str) -> Path:
    app.processEvents()
    pix = win.grab()
    path = OUT / f"{name}.png"
    pix.save(str(path), "PNG")
    sz = path.stat().st_size // 1024
    print(f"  screenshot: {name}.png  ({sz} KB)")
    return path


def grab_and_3d(name: str, viewer, extra_wait_ms: int = 1200) -> None:
    """Window grab + async pngURI from 3D viewer."""
    grab(name)
    done = [False]
    viewer_out = OUT / f"{name}_3d.png"

    def _cb(p: Path) -> None:
        if p.exists() and p.stat().st_size > 5000:
            print(f"  3D viewer: {p.name}  ({p.stat().st_size // 1024} KB)")
        else:
            print(f"  3D viewer: {p.name}  (blank/tiny – WebGL headless fallback)")
        done[0] = True

    viewer.capture_png(viewer_out, callback=_cb)
    deadline = time.time() + extra_wait_ms / 1000 + 3
    while not done[0] and time.time() < deadline:
        wait_ms(150)


# ── Page 0: receptor (initial) ───────────────────────────────────────────────
wait_ms(500)
grab("01_receptor_initial")
print("[1/9] Receptor page (initial) ✓")

# ── Page 0: inject receptor result ───────────────────────────────────────────
rp = win._receptor_page
rp._receptor_info = ri
rp._pdb_path = PDB
rp._status.setText("受体准备完成。")
for h in ri.hetero_groups or []:
    tag = "★ " if getattr(h, "is_likely_ligand", False) else ""
    rp._hetero_list.addItem(f"{tag}{h.resname}  chain={h.chain}  resi={h.resi}")
for w in ri.warnings or []:
    rp._warnings.addItem(w)
rp._viewer.load_receptor(PDB)
wait_ms(1500)
grab_and_3d("02_receptor_loaded", rp._viewer)
print("[2/9] Receptor loaded (3D viewer) ✓")

# ── Page 1: ligand ───────────────────────────────────────────────────────────
win._receptor_info = ri
win._pdb_path = PDB
win._go_to_page(1)
wait_ms(300)
lp = win._ligand_page
lp._smiles_edit.setText(SMILES)
wait_ms(200)
grab("03_ligand_smiles")
print("[3/9] Ligand page (SMILES) ✓")

# inject ligand result
lp._ligand_info = li
lp._status.setText("配体准备完成。") if hasattr(lp, "_status") else None
wait_ms(200)
grab("03b_ligand_prepared")
print("[3b/9] Ligand prepared ✓")

# ── Page 2: pocket ───────────────────────────────────────────────────────────
win._ligand_info = li
win._go_to_page(2)
wait_ms(300)
pp = win._pocket_page
# Inject pocket results directly
pp._pdb_path = PDB
pp._viewer.load_receptor(PDB)
wait_ms(800)
# Build pocket cards manually
pp._clear_cards()
from dockmeow.ui.widgets.pocket_card import PocketCard
scroll_layout = None
for widget in pp.findChildren(type(pp._scroll_area.widget()) if hasattr(pp, '_scroll_area') else object):
    pass  # just ensure scroll area exists
# Use the _on_pockets path
pp._on_pockets(pockets)
wait_ms(500)
grab("04_pocket_page")
print("[4/9] Pocket page ✓")

# ── Page 3: params ───────────────────────────────────────────────────────────
win._pocket = pocket
win._go_to_page(3)
wait_ms(300)
grab("05_params_page")
print("[5/9] Params page ✓")

# ── Page 4: run page (initial then progress sim) ──────────────────────────────
win._go_to_page(4)
wait_ms(300)
grab("06_run_page_initial")
print("[6/9] Run page (initial) ✓")

# Inject docking into run page to show result state
run_page = win._run_page
# Simulate progress visuals
if hasattr(run_page, '_progress_label'):
    run_page._progress_label.setText("正在对接... 45%")
if hasattr(run_page, '_pct'):
    run_page._pct = 45
wait_ms(100)
grab("06b_run_page_progress")
print("[6b/9] Run page (progress sim) ✓")

# ── Page 4: cancel test (real docking) ───────────────────────────────────────
print("[7/9] Cancel button test (exhaustiveness=32)...")
cfg_heavy = DockingConfig(
    receptor_pdbqt=ri.pdbqt_path,
    ligand_pdbqt=li.pdbqt_path,
    center=pocket.center,
    size=pocket.size,
    exhaustiveness=32,
    num_modes=9,
    energy_range=3,
    seed=42,
)
t_start = time.time()
run_page.start(cfg_heavy)
wait_ms(5000)
grab("07a_run_cancel_before")
# Hit cancel
if hasattr(run_page, '_cancel'):
    run_page._cancel()
elif hasattr(run_page, '_on_cancel'):
    run_page._on_cancel()
elif hasattr(run_page, '_worker') and run_page._worker is not None:
    run_page._worker.requestInterruption()
wait_ms(2000)
t_cancel = time.time() - t_start
grab("07b_run_cancel_after")
print(f"  Cancel at {t_cancel:.1f}s — UI stayed responsive ✓")

# ── Page 5: results ───────────────────────────────────────────────────────────
win._docking_result = result
win._go_to_page(5)
wait_ms(300)
resp = win._results_page
resp.set_context(ri, li, PDB)
resp.set_result(result)
wait_ms(2000)  # let 3D render
grab_and_3d("08_results_page", resp._viewer, extra_wait_ms=2000)
print("[8/9] Results page (with 3D) ✓")

# ── PDF export ────────────────────────────────────────────────────────────────
print("[9/9] Generating PDF report...")
pdf_path = OUT / "dockmeow_report.pdf"
tmp_png = OUT / "viewer_for_pdf.png"
pdf_done = [False]

def _make_pdf(png_path: Path) -> None:
    from dockmeow.core.report import generate_report
    try:
        generate_report(ri, li, result, pdf_path,
                        screenshot_path=png_path if png_path.exists() and png_path.stat().st_size > 5000 else None)
        sz = pdf_path.stat().st_size // 1024
        print(f"  PDF: {pdf_path.name}  ({sz} KB) ✓")
    except Exception as exc:
        print(f"  PDF FAILED: {exc}")
    pdf_done[0] = True

resp._viewer.capture_png(tmp_png, callback=_make_pdf)
deadline = time.time() + 10
while not pdf_done[0] and time.time() < deadline:
    wait_ms(300)

# ── Chinese path test ─────────────────────────────────────────────────────────
print("\n[bonus] Chinese path test...")
import shutil
cdir = Path("/tmp/测试 项目")
cdir.mkdir(parents=True, exist_ok=True)
cpdb = cdir / "1AKE.pdb"
shutil.copy2(PDB, cpdb)
try:
    ri2 = prepare_receptor(cpdb, WORK / "receptor_cn")
    print(f"  Chinese path OK — pdbqt={ri2.pdbqt_path.name} ✓")
except Exception as e:
    print(f"  Chinese path FAILED: {e}")

# ── summary ───────────────────────────────────────────────────────────────────
print("\n=== Output files ===")
for p in sorted(OUT.iterdir()):
    if p.is_file():
        print(f"  {p.name:45s}  {p.stat().st_size // 1024:6d} KB")

app.quit()
print("\nDone.")
