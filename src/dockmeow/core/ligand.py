"""Ligand (small molecule) preparation pipeline.

Supported input:
- SMILES string (via RDKit ETKDGv3 + UFF 3D generation)
- File: .sdf, .mol2, .mol (via RDKit)

Flow (both paths):
    input → RDKit add Hs → ETKDGv3 conformer → UFF minimize
          → meeko MoleculePreparation.prepare()
          → PDBQTWriterLegacy.write_string() → .pdbqt file

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dockmeow.core._utils import safe_name
from dockmeow.core.exceptions import LigandPreparationError

_log = logging.getLogger(__name__)

# Pre-load C-extensions in the main thread (same reason as receptor.py).
try:
    import rdkit.Chem as _rdkit_preload          # noqa: F401
    import rdkit.Chem.AllChem as _rdkit_ac       # noqa: F401
    import meeko as _meeko_preload               # noqa: F401
except Exception:  # noqa: BLE001
    pass


@dataclass
class LigandInfo:
    """Output descriptor after successful ligand preparation."""

    pdbqt_path: Path
    name: str
    n_atoms: int
    n_rotatable: int
    smiles: str
    source_format: str  # "smiles" | "sdf" | "mol2" | "mol"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mol_to_3d(mol, name: str):
    """Add hydrogens and generate a 3D conformer with ETKDGv3 + UFF."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    ret = AllChem.EmbedMolecule(mol, params)
    if ret == -1:
        # Fallback: random coords + UFF minimise
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        ret = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    if ret == -1:
        raise LigandPreparationError(
            f"RDKit EmbedMolecule failed for {name!r}",
            f"配体 {name!r} 的 3D 构象生成失败。",
            "请检查 SMILES 是否正确，或尝试提供 SDF 文件。",
        )
    result = AllChem.UFFOptimizeMolecule(mol, maxIters=2000)
    if result == 1:
        _log.warning("UFF optimisation did not converge for %s", name)
    return mol


def _mol_to_pdbqt(mol, name: str, work_dir: Path) -> LigandInfo:
    """Convert an RDKit Mol (with 3D coords) to PDBQT via meeko."""
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    stem = safe_name(name)
    output_pdbqt = work_dir / f"{stem}.pdbqt"

    try:
        prep = MoleculePreparation()
        mol_setups = prep.prepare(mol)
    except Exception as exc:
        raise LigandPreparationError(
            f"meeko MoleculePreparation failed: {exc}",
            "配体 PDBQT 准备失败。",
            "请确认分子结构合理（无价键错误、无孤立原子）。",
        ) from exc

    if not mol_setups:
        raise LigandPreparationError(
            "meeko returned no setups",
            "meeko 无法处理该配体分子。",
        )

    try:
        pdbqt_str, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
    except Exception as exc:
        raise LigandPreparationError(
            f"meeko write_string failed: {exc}",
            "配体 PDBQT 写出失败。",
        ) from exc

    if not is_ok:
        raise LigandPreparationError(
            f"meeko write_string error: {error_msg}",
            "配体 PDBQT 写出失败。",
            "请确认分子结构合理（无价键错误、无孤立原子）。",
        )
    if not pdbqt_str.strip():
        raise LigandPreparationError(
            "meeko write_string returned empty string",
            "生成的 PDBQT 为空，配体可能无法对接。",
        )

    output_pdbqt.write_text(pdbqt_str, encoding="utf-8")

    smiles = Chem.MolToSmiles(Chem.RemoveHs(mol))
    n_atoms = mol.GetNumHeavyAtoms()
    n_rot = Descriptors.NumRotatableBonds(mol)

    return LigandInfo(
        pdbqt_path=output_pdbqt,
        name=name,
        n_atoms=n_atoms,
        n_rotatable=n_rot,
        smiles=smiles,
        source_format="smiles",  # overridden by callers
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare_ligand_from_smiles(
    smiles: str,
    name: str,
    work_dir: Path,
    ph: float = 7.4,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> LigandInfo:
    """Generate a 3D conformer from a SMILES string and produce PDBQT.

    Args:
        smiles:            SMILES string for the ligand.
        name:              Molecule name used for output file naming.
        work_dir:          Directory for output files.
        ph:                pH for protonation state (passed to Meeko).
        progress_callback: Called as ``cb(stage, percent, message)``.

    Returns:
        LigandInfo with path and metadata.

    Raises:
        LigandPreparationError: on SMILES parse failure, 3D generation failure,
                                or Meeko preparation failure.
    """
    from rdkit import Chem

    cb = progress_callback
    work_dir.mkdir(parents=True, exist_ok=True)

    if cb:
        cb("配体准备", 10, f"解析 SMILES: {smiles[:50]}…")

    mol = Chem.MolFromSmiles(smiles) if smiles.strip() else None
    if mol is None:
        raise LigandPreparationError(
            f"RDKit cannot parse SMILES: {smiles!r}",
            "SMILES 格式无效，请检查分子式是否正确。",
            "可以在 https://www.cheminfo.org/ 验证 SMILES。",
        )

    if cb:
        cb("配体准备", 30, "生成 3D 构象…")

    mol = _mol_to_3d(mol, name)

    if cb:
        cb("配体准备", 70, "生成 PDBQT…")

    info = _mol_to_pdbqt(mol, name, work_dir)
    info.source_format = "smiles"

    if cb:
        cb("配体准备", 100, "配体准备完成。")

    _log.info(
        "Ligand prepared from SMILES: %s | atoms=%d rotatable=%d",
        name, info.n_atoms, info.n_rotatable,
    )
    return info


def prepare_ligand_from_file(
    input_file: Path,
    work_dir: Path,
    ph: float = 7.4,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> LigandInfo:
    """Prepare a ligand from an SDF / MOL2 / MOL file.

    Args:
        input_file:        Path to the ligand structure file.
        work_dir:          Directory for output files.
        ph:                pH for protonation state.
        progress_callback: Called as ``cb(stage, percent, message)``.

    Returns:
        LigandInfo with path and metadata.

    Raises:
        LigandPreparationError: on file parse or preparation failure.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    cb = progress_callback
    work_dir.mkdir(parents=True, exist_ok=True)

    suffix = input_file.suffix.lower()
    if cb:
        cb("配体准备", 10, f"读取 {input_file.name}…")

    if suffix in (".sdf", ".mol"):
        supplier = Chem.SDMolSupplier(str(input_file), removeHs=False)
        mol = next((m for m in supplier if m is not None), None)
        fmt = "sdf" if suffix == ".sdf" else "mol"
    elif suffix == ".mol2":
        mol = Chem.MolFromMol2File(str(input_file), removeHs=False)
        fmt = "mol2"
    else:
        raise LigandPreparationError(
            f"不支持 {suffix} 格式",
            f"不支持 {suffix} 格式，请提供 .sdf、.mol2 或 .mol 文件。",
        )

    if mol is None:
        raise LigandPreparationError(
            f"RDKit failed to parse {input_file}",
            f"无法读取 {input_file.name}，文件可能已损坏。",
            "请在 OpenBabel 或 ChemDraw 中检查文件是否有效。",
        )

    name = input_file.stem

    # If no 3D coords, generate them
    if mol.GetNumConformers() == 0 or mol.GetConformer().Is3D() is False:
        if cb:
            cb("配体准备", 30, "生成 3D 构象…")
        mol = _mol_to_3d(mol, name)
    else:
        if cb:
            cb("配体准备", 30, "已有 3D 坐标，优化构象…")
        mol = Chem.AddHs(mol, addCoords=True)
        AllChem.UFFOptimizeMolecule(mol, maxIters=2000)

    if cb:
        cb("配体准备", 70, "生成 PDBQT…")

    info = _mol_to_pdbqt(mol, name, work_dir)
    info.source_format = fmt

    if cb:
        cb("配体准备", 100, "配体准备完成。")

    _log.info(
        "Ligand prepared from file: %s | atoms=%d rotatable=%d",
        name, info.n_atoms, info.n_rotatable,
    )
    return info
