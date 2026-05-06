"""Result post-processing utilities.

Handles:
- Parsing multi-model PDBQT output into individual pose files.
- Converting PDBQT poses to SDF/PDB for export.

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dockmeow.core.docking import DockingResult

_log = logging.getLogger(__name__)


def split_poses_to_sdf(result: DockingResult, output_dir: Path) -> list[Path]:
    """Split a multi-pose SDF into individual per-pose SDF files.

    Args:
        result:     DockingResult containing the combined poses_sdf.
        output_dir: Directory where individual files are written.

    Returns:
        List of per-pose SDF paths, ordered by rank (best score first).
    """
    from rdkit.Chem import SDMolSupplier, SDWriter

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    if not result.poses_sdf.exists() or result.poses_sdf.stat().st_size == 0:
        _log.warning("poses_sdf is empty or missing: %s", result.poses_sdf)
        return paths

    supplier = SDMolSupplier(str(result.poses_sdf), removeHs=False)
    for i, mol in enumerate(supplier, start=1):
        if mol is None:
            continue
        out = output_dir / f"pose_{i:02d}.sdf"
        with SDWriter(str(out)) as w:
            w.write(mol)
        paths.append(out)

    return paths


def export_poses_pdb(result: DockingResult, output_dir: Path) -> list[Path]:
    """Convert PDBQT poses to individual PDB files by splitting the PDBQT.

    Args:
        result:     DockingResult.
        output_dir: Destination directory.

    Returns:
        List of PDB paths, rank-ordered.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    if not result.poses_pdbqt.exists():
        return paths

    pdbqt_text = result.poses_pdbqt.read_text(encoding="utf-8", errors="replace")
    models = pdbqt_text.split("MODEL ")
    # First element is empty (before first MODEL keyword)
    for i, block in enumerate(models[1:], start=1):
        pdb_lines = [
            line for line in block.splitlines()
            if line.startswith(("ATOM  ", "HETATM", "ROOT", "ENDROOT",
                                "BRANCH", "ENDBRANCH", "TORSDOF"))
            or line.strip() == "ENDMDL"
        ]
        # Keep only ATOM/HETATM for a minimal PDB
        atom_lines = [ln for ln in pdb_lines if ln.startswith(("ATOM  ", "HETATM"))]
        if not atom_lines:
            continue
        out = output_dir / f"pose_{i:02d}.pdb"
        out.write_text("\n".join(atom_lines) + "\nEND\n", encoding="utf-8")
        paths.append(out)

    return paths
