"""Binding pocket detection.

Priority order:
    1. Co-crystal ligand (is_likely_ligand HETATM in original PDB)
       → geometric centre + 22.5 Å cube, source="cocrystal"
    2. fpocket bundled binary → top-3 pockets, source="fpocket"
       size = (max_dim - min_dim + 5 Å padding), clamped to [15, 30] Å
    3. Whole-protein blind docking box, source="whole"

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from dockmeow.core.exceptions import PocketDetectionError
from dockmeow.core.receptor import HeteroGroup, ReceptorInfo
from dockmeow.utils.subprocess import hidden_subprocess_kwargs

_log = logging.getLogger(__name__)

_BOX_SIZE_MIN = 15.0
_BOX_SIZE_MAX = 30.0
_COCRYSTAL_BOX = 22.5
_FPOCKET_PADDING = 5.0
_POCKET_FILE_RE = re.compile(r"pocket(?P<number>\d+)_atm\.(?:pdb|pqr)$", re.IGNORECASE)
_POCKET_HEADER_RE = re.compile(r"^\s*Pocket\s+(?P<number>\d+)\s*:", re.IGNORECASE)
_POCKET_SCORE_RE = re.compile(
    r"^\s*Score\s*:\s*(?P<score>[-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass
class Pocket:
    """Describes one candidate binding pocket."""

    pocket_id: int
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    score: float
    residues: list[str] = field(default_factory=list)
    source: str = "fpocket"   # "cocrystal" | "fpocket" | "whole"
    label: str = ""           # e.g. "口袋 1（推荐）" / "全蛋白盲对接"


# ---------------------------------------------------------------------------
# Co-crystal detection
# ---------------------------------------------------------------------------

def _cocrystal_center(
    pdb_path: Path, ligands: list[HeteroGroup]
) -> tuple[float, float, float] | None:
    """Return the geometric centre of the first is_likely_ligand group."""
    target = next((h for h in ligands if h.is_likely_ligand), None)
    if target is None:
        return None

    coords: list[tuple[float, float, float]] = []
    with open(pdb_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("HETATM"):
                continue
            resname = line[17:20].strip()
            chain = line[21].strip() or " "
            try:
                resi = int(line[22:26].strip())
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
            except (ValueError, IndexError):
                continue
            if resname == target.resname and chain == target.chain and resi == target.resi:
                coords.append((x, y, z))

    if not coords:
        return None

    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)
    cz = sum(c[2] for c in coords) / len(coords)
    return (cx, cy, cz)


# ---------------------------------------------------------------------------
# Whole-protein box
# ---------------------------------------------------------------------------

def whole_protein_box(receptor: ReceptorInfo, padding: float = 5.0) -> Pocket:
    """Compute a bounding box covering the entire receptor protein.

    Args:
        receptor: Prepared receptor.
        padding:  Ångström padding added on each side.

    Returns:
        A single Pocket with source="whole".
    """
    coords: list[tuple[float, float, float]] = []
    pdb_text = receptor.pdb_path.read_text(encoding="utf-8", errors="replace")
    for line in pdb_text.splitlines():
        if not line.startswith(("ATOM  ", "ATOM")):
            continue
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except (ValueError, IndexError):
            continue
        coords.append((x, y, z))

    if not coords:
        raise PocketDetectionError(
            "No ATOM records found in receptor PDB",
            "受体 PDB 文件中没有找到蛋白原子坐标。",
        )

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]

    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2
    cz = (max(zs) + min(zs)) / 2

    sx = max(xs) - min(xs) + 2 * padding
    sy = max(ys) - min(ys) + 2 * padding
    sz = max(zs) - min(zs) + 2 * padding

    return Pocket(
        pocket_id=0,
        center=(round(cx, 3), round(cy, 3), round(cz, 3)),
        size=(round(sx, 3), round(sy, 3), round(sz, 3)),
        score=0.0,
        source="whole",
        label="全蛋白盲对接",
    )


# ---------------------------------------------------------------------------
# fpocket
# ---------------------------------------------------------------------------

def _run_fpocket(receptor_pdb: Path, work_dir: Path) -> list[Pocket]:
    """Run fpocket and parse its output into Pocket objects."""
    from dockmeow.utils.paths import fpocket_candidates, is_usable_executable

    binary = next((path for path in fpocket_candidates() if is_usable_executable(path)), None)
    if binary is None:
        searched = ", ".join(str(path) for path in fpocket_candidates())
        raise FileNotFoundError(f"fpocket binary not found; searched: {searched}")

    # fpocket writes output next to the input PDB, not in cwd.
    # Copy the PDB into work_dir so output lands there (keeps temp directories clean).
    local_pdb = work_dir / "receptor.pdb"
    if receptor_pdb.resolve() != local_pdb.resolve():
        shutil.copy2(receptor_pdb, local_pdb)

    out_dir = work_dir / f"{local_pdb.stem}_out"
    # Run from work_dir and pass a local filename. Older fpocket releases do not
    # parse Windows absolute paths with backslashes correctly.
    cmd = [str(binary), "-f", local_pdb.name, "-w", "pdb"]

    _log.debug("Running fpocket: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(work_dir),
            **hidden_subprocess_kwargs(),
        )
        if proc.returncode != 0 and "-w" in cmd:
            fallback_cmd = [str(binary), "-f", local_pdb.name]
            _log.debug("Retrying fpocket without -w: %s", " ".join(fallback_cmd))
            proc = subprocess.run(
                fallback_cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(work_dir),
                **hidden_subprocess_kwargs(),
            )
    except OSError as exc:
        raise PocketDetectionError(
            f"fpocket could not execute: {exc}",
            "fpocket 二进制无法执行。",
            "已自动使用全蛋白盲对接盒子。",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PocketDetectionError(
            "fpocket timed out",
            "口袋检测超时（>2 分钟）。",
            "已自动使用全蛋白盲对接盒子。",
        ) from exc

    if proc.returncode != 0:
        raise PocketDetectionError(
            f"fpocket returned {proc.returncode}: {proc.stderr[:200]}",
            "fpocket 口袋检测失败。",
            "已自动使用全蛋白盲对接盒子。",
        )

    # fpocket 4.x writes <stem>_out/pockets/pocket*_atm.pdb (individual pocket files)
    # Older versions placed them directly in <stem>_out/ — check both layouts.
    if out_dir.exists():
        pqr_files = list(out_dir.rglob("pocket*_atm.pdb"))
        if not pqr_files:
            pqr_files = list(out_dir.rglob("pocket*_atm.pqr"))
    else:
        pqr_files = []

    pqr_files.sort(key=_pocket_file_number)
    scores = _parse_fpocket_scores(out_dir / f"{local_pdb.stem}_info.txt")

    pockets: list[Pocket] = []
    for pqr in pqr_files[:3]:
        coords = _parse_pdb_coords(pqr)
        if not coords:
            continue
        pocket_number = _pocket_file_number(pqr)
        center, size = _box_from_coords(coords, _FPOCKET_PADDING)
        pockets.append(
            Pocket(
                pocket_id=pocket_number,
                center=center,
                size=size,
                score=scores.get(pocket_number, 0.0),
                source="fpocket",
                label=f"口袋 {pocket_number}",
            )
        )

    return pockets


def _pocket_file_number(path: Path) -> int:
    match = _POCKET_FILE_RE.search(path.name)
    return int(match.group("number")) if match else 10**9


def _parse_fpocket_scores(info_path: Path) -> dict[int, float]:
    """Read the native fpocket Score for each numbered pocket."""
    try:
        lines = info_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    scores: dict[int, float] = {}
    current_pocket: int | None = None
    for line in lines:
        header = _POCKET_HEADER_RE.match(line)
        if header:
            current_pocket = int(header.group("number"))
            continue
        score = _POCKET_SCORE_RE.match(line)
        if current_pocket is not None and score:
            scores[current_pocket] = float(score.group("score"))
    return scores


def _parse_pdb_coords(path: Path) -> list[tuple[float, float, float]]:
    coords = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith(("ATOM  ", "HETATM", "ATOM")):
                continue
            try:
                x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
                coords.append((x, y, z))
            except (ValueError, IndexError):
                continue
    return coords


def _box_from_coords(
    coords: list[tuple[float, float, float]],
    padding: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2
    cz = (max(zs) + min(zs)) / 2

    def _clamp(v: float) -> float:
        return max(_BOX_SIZE_MIN, min(_BOX_SIZE_MAX, v))

    sx = _clamp(max(xs) - min(xs) + padding)
    sy = _clamp(max(ys) - min(ys) + padding)
    sz = _clamp(max(zs) - min(zs) + padding)
    return (round(cx, 3), round(cy, 3), round(cz, 3)), (round(sx, 3), round(sy, 3), round(sz, 3))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_pockets(
    receptor: ReceptorInfo,
    original_pdb: Path | None = None,
) -> list[Pocket]:
    """Detect binding pockets for the prepared receptor.

    Priority:
        1. Co-crystal ligand in original_pdb → cocrystal pocket
        2. fpocket binary → top-3 pockets
        3. Whole-protein box fallback

    Args:
        receptor:     ReceptorInfo from prepare_receptor().
        original_pdb: Original (unstripped) PDB to look for co-crystal ligands.

    Returns:
        Ordered list of Pocket objects (best first); always non-empty.
    """
    pockets: list[Pocket] = []

    if original_pdb is None:
        original_pdb = getattr(receptor, "original_pdb_path", None)

    # --- Priority 1: co-crystal ligand ---
    if original_pdb is not None and receptor.hetero_groups:
        try:
            center = _cocrystal_center(original_pdb, receptor.hetero_groups)
            if center is not None:
                ligand = next(h for h in receptor.hetero_groups if h.is_likely_ligand)
                pockets.append(
                    Pocket(
                        pocket_id=1,
                        center=center,
                        size=(_COCRYSTAL_BOX, _COCRYSTAL_BOX, _COCRYSTAL_BOX),
                        score=1.0,
                        source="cocrystal",
                        label=f"共结晶口袋（{ligand.resname}，推荐）",
                    )
                )
                _log.info(
                    "Co-crystal pocket detected: %s chain=%s resi=%d centre=%s",
                    ligand.resname, ligand.chain, ligand.resi, center,
                )
        except Exception as exc:
            _log.warning("Co-crystal detection failed: %s", exc)

    # --- Priority 2: fpocket ---
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_work = Path(tmpdir)
        try:
            fp_pockets = _run_fpocket(receptor.pdb_path, tmp_work)
            if fp_pockets and not pockets:
                fp_pockets[0].label += "（推荐）"
            pockets.extend(fp_pockets)
            _log.info("fpocket returned %d pockets", len(fp_pockets))
        except FileNotFoundError:
            _log.info("fpocket binary not available, skipping")
        except PocketDetectionError as exc:
            _log.warning("fpocket failed: %s", exc)

    if pockets:
        try:
            whole = whole_protein_box(receptor)
            pockets.append(whole)
        except Exception:
            pass
        return pockets

    # --- Priority 3: whole-protein fallback ---
    _log.info("Using whole-protein blind docking box as fallback")
    try:
        whole = whole_protein_box(receptor)
        pockets.append(whole)
    except PocketDetectionError:
        raise  # propagate if even this fails

    return pockets
