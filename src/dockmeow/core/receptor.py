"""Receptor (protein) preparation pipeline.

Flow:
    input PDB → copy to work_dir/safe_name
             → PDBFixer: add missing residues/atoms, protonate at given pH
             → strip waters / HETATM (unless kept by caller)
             → meeko Polymer.from_pdb_string() → PDBQTWriterLegacy.write_from_polymer()

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dockmeow.core._utils import safe_name
from dockmeow.core.exceptions import ReceptorPreparationError

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-load C-extensions in the main thread.
#
# On macOS, PyInstaller frozen bundles forbid dlopen() from non-main threads
# (EXC_BAD_ACCESS in mach_o::Header::forEachLoadCommand).  This module is
# always imported by prepare_worker → page_receptor → main_window inside
# run(), i.e. in the main thread before any QThread worker starts.
# The function-level lazy imports below are kept for proper error messages
# when a package is genuinely absent.
# ---------------------------------------------------------------------------
try:
    import pdbfixer as _pdbfixer_preload      # noqa: F401
    import openmm as _openmm_preload          # noqa: F401
    import openmm.app as _openmm_app_preload  # noqa: F401
    import meeko as _meeko_preload            # noqa: F401
except Exception:  # noqa: BLE001
    pass

# DNA and RNA residue names — these are NOT standard amino acids and will
# cause PDBFixer's replaceNonstandardResidues() to raise KeyError.
_DNA_RESNAMES = frozenset({"DA", "DC", "DG", "DT", "DI", "DU"})
_RNA_RESNAMES = frozenset({"A", "C", "G", "U", "I"})
_NUCLEIC_RESNAMES = _DNA_RESNAMES | _RNA_RESNAMES

# Residues that must never be mistaken for a drug-like co-crystal ligand.
# Sources: PDB Chemical Component Dictionary common contaminants list +
#          common crystallography additives.
_NON_LIGAND_RESNAMES = frozenset(
    # Water
    "HOH WAT H2O DOD"
    # Common metal ions
    " MG CA ZN FE MN CU CO NI NA K CL BR I F SE"
    " BA CD HG PB PT RU AU AG CU1 FE2 FE3"
    # Common anions / small molecules used in crystallisation
    " SO4 PO4 PO3 NO3 CL IOD"
    # Common cryoprotectants / precipitants / buffers
    " EDO GOL PEG PG4 MPD DMS DMF ACE ACT EOH"
    " IPA TRS EPE MES HEPES MOPS PIPE"
    # Glycerol-related & polyols
    " GLY GLU GLN"  # only if HETATM — free amino acids as additives
    " CIT FMT ACY"
    # Sugars & glycan residues (glycoproteins)
    " NAG NDG BMA MAN FUC GAL GLA BGC GLC"
    " FUL SIA A2G LAT"
    # Nucleotides sometimes present as cofactors but not drug targets by default
    # (commented out — ATP/ADP/GTP are legitimate co-crystal ligands)
    # Lipid / detergent fragments
    " OLA PLM STE"
    # Amine / DMSO artefacts
    " DMS DMSO"
    .split()
)
# Atoms counted to decide if a HETATM group is ligand-sized
_LIGAND_ATOM_MIN = 5
_LIGAND_ATOM_MAX = 150


@dataclass
class HeteroGroup:
    """One non-standard residue (HETATM) found in the raw PDB."""

    resname: str
    chain: str
    resi: int
    n_atoms: int
    is_water: bool
    is_ion: bool
    is_likely_ligand: bool  # heuristic: not water/ion, 5–150 heavy atoms


@dataclass
class ReceptorInfo:
    """Output descriptor after successful receptor preparation."""

    pdb_path: Path
    pdbqt_path: Path
    chains: list[str]
    n_residues: int
    hetero_groups: list[HeteroGroup] = field(default_factory=list)
    waters_removed: int = 0
    warnings: list[str] = field(default_factory=list)
    nucleic_acid_chains: list[str] = field(default_factory=list)  # DNA/RNA chains detected


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_pdbfixer_added_atoms(fixed_pdb_text: str, original_pdb: Path) -> str:
    """Return a version of fixed_pdb_text that keeps only atoms present in the
    original PDB (by chain/residue/atom-name key).

    Used as a fallback when PDBFixer's addMissingAtoms places heavy atoms in
    positions that trigger valence errors in meeko's DetermineConnectivity
    (e.g. cis-proline CD too close to the preceding residue's carbonyl O).
    """
    try:
        orig_text = original_pdb.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fixed_pdb_text

    orig_keys: set[tuple[str, str, int, str]] = set()
    for line in orig_text.splitlines():
        if not line.startswith(("ATOM", "HETATM")) or len(line) < 27:
            continue
        name = line[12:16].strip()
        chain = line[21].strip() or " "
        try:
            resi = int(line[22:26].strip())
        except ValueError:
            continue
        resname = line[17:20].strip()
        orig_keys.add((chain, resname, resi, name))

    out: list[str] = []
    for line in fixed_pdb_text.splitlines(keepends=True):
        if not line.startswith(("ATOM", "HETATM")) or len(line) < 27:
            out.append(line)
            continue
        name = line[12:16].strip()
        chain = line[21].strip() or " "
        try:
            resi = int(line[22:26].strip())
        except ValueError:
            out.append(line)
            continue
        resname = line[17:20].strip()
        # Keep H atoms (meeko adds its own; no H in original RCSB PDB anyway)
        # Keep only atoms that existed in the original structure
        elem = line[76:78].strip() if len(line) >= 78 else ""
        if elem == "H" or (chain, resname, resi, name) in orig_keys:
            out.append(line)
        # else: skip PDBFixer-added heavy atom

    return "".join(out)


def _parse_hetero_groups(pdb_text: str) -> list[HeteroGroup]:
    """Extract HETATM groups from raw PDB text."""
    groups: dict[tuple[str, str, int], list] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("HETATM"):
            continue
        resname = line[17:20].strip()
        chain = line[21].strip() or " "
        try:
            resi = int(line[22:26].strip())
        except ValueError:
            continue
        key = (resname, chain, resi)
        groups.setdefault(key, []).append(line)

    result: list[HeteroGroup] = []
    for (resname, chain, resi), lines in groups.items():
        n = len(lines)
        is_water = resname in ("HOH", "WAT", "H2O")
        is_non_ligand = resname in _NON_LIGAND_RESNAMES
        is_likely = (
            not is_non_ligand
            and _LIGAND_ATOM_MIN <= n <= _LIGAND_ATOM_MAX
        )
        result.append(
            HeteroGroup(
                resname=resname,
                chain=chain,
                resi=resi,
                n_atoms=n,
                is_water=is_water,
                is_ion=is_non_ligand and not is_water,
                is_likely_ligand=is_likely,
            )
        )
    return result


def _strip_hetatm(
    pdb_text: str,
    keep: list[tuple[str, str, int]] | None,
) -> tuple[str, int]:
    """Remove HETATM records, optionally keeping selected residues.

    Args:
        pdb_text: Raw PDB file content.
        keep:     List of (resname, chain, resi) to preserve.

    Returns:
        (cleaned_pdb_text, n_waters_removed)
    """
    keep_set: set[tuple[str, str, int]] = set(keep) if keep else set()
    lines_out: list[str] = []
    waters_removed = 0

    for line in pdb_text.splitlines(keepends=True):
        if not line.startswith("HETATM"):
            lines_out.append(line)
            continue
        resname = line[17:20].strip()
        chain = line[21].strip() or " "
        try:
            resi = int(line[22:26].strip())
        except ValueError:
            continue  # skip malformed
        key = (resname, chain, resi)
        if key in keep_set:
            lines_out.append(line)
        else:
            if resname in ("HOH", "WAT", "H2O"):
                waters_removed += 1
    return "".join(lines_out), waters_removed


def detect_nucleic_acid_chains(pdb_path: Path) -> list[str]:
    """Scan a PDB file and return chain IDs that contain DNA/RNA residues."""
    na_chains: set[str] = set()
    try:
        text = pdb_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        if not line.startswith(("ATOM  ", "ATOM", "HETATM")):
            continue
        if len(line) < 26:
            continue
        resname = line[17:20].strip()
        chain = line[21].strip() or " "
        if resname in _NUCLEIC_RESNAMES:
            na_chains.add(chain)
    return sorted(na_chains)


def strip_nucleic_acid_chains(pdb_text: str) -> str:
    """Return a copy of pdb_text with all DNA/RNA ATOM/HETATM records removed.

    Also removes TER records that reference a stripped DNA/RNA residue, since a
    dangling TER line confuses PDBFixer's PDB parser.
    """
    out: list[str] = []
    for line in pdb_text.splitlines(keepends=True):
        if line.startswith(("ATOM  ", "ATOM", "HETATM")):
            resname = line[17:20].strip() if len(line) >= 20 else ""
            if resname in _NUCLEIC_RESNAMES:
                continue
        elif line.startswith("TER"):
            # TER records carry the trailing residue name in cols 18-20
            resname = line[17:20].strip() if len(line) >= 20 else ""
            if resname in _NUCLEIC_RESNAMES:
                continue
        out.append(line)
    return "".join(out)


def _run_pdbfixer(
    input_pdb: Path,
    output_pdb: Path,
    add_missing_atoms: bool,
    ph: float,
    cb: Callable | None,
) -> list[str]:
    """Run PDBFixer and return a list of warning strings."""
    from openmm.app import PDBFile
    from pdbfixer import PDBFixer

    warnings: list[str] = []

    if cb:
        cb("受体准备", 10, "正在使用 PDBFixer 修复结构…")

    try:
        fixer = PDBFixer(filename=str(input_pdb))
    except Exception as exc:
        raise ReceptorPreparationError(
            f"PDBFixer cannot load file: {exc}",
            "PDB 文件无法解析，请确认文件格式正确。",
            "请从 RCSB PDB 重新下载标准格式文件，或在 PyMOL 中另存为 PDB。",
        ) from exc

    try:
        fixer.findMissingResidues()
    except Exception as exc:
        _log.warning("PDBFixer findMissingResidues failed (%s), continuing", exc)
        warnings.append(f"缺失残基检测失败（{exc}），已跳过。")

    try:
        fixer.findNonstandardResidues()
        if hasattr(fixer, "nonstandardResidues"):
            fixer.nonstandardResidues = [
                (res, name)
                for res, name in fixer.nonstandardResidues
                if res.name not in _NUCLEIC_RESNAMES
            ]
        fixer.replaceNonstandardResidues()
    except KeyError as exc:
        _log.warning("PDBFixer replaceNonstandardResidues KeyError (%s), skipping", exc)
        warnings.append(f"非标准残基 {exc} 替换失败（可能是修饰氨基酸或未知残基），已跳过。")
    except Exception as exc:
        _log.warning("PDBFixer replaceNonstandardResidues failed (%s), skipping", exc)
        warnings.append(f"非标准残基替换失败（{exc}），已跳过。")

    try:
        fixer.removeHeterogens(keepWater=False)
    except Exception as exc:
        _log.warning("PDBFixer removeHeterogens failed (%s), skipping", exc)
        warnings.append(f"杂原子移除失败（{exc}），已跳过。")

    try:
        fixer.findMissingAtoms()
        if add_missing_atoms:
            fixer.addMissingAtoms()
    except Exception as exc:
        _log.warning("PDBFixer addMissingAtoms failed (%s), skipping", exc)
        warnings.append(f"缺失原子补全失败（{exc}），已跳过。")

    try:
        fixer.addMissingHydrogens(ph)
    except Exception as exc:
        _log.warning("PDBFixer addMissingHydrogens failed (%s), skipping", exc)
        warnings.append(f"氢原子添加失败（{exc}），已跳过。")

    if cb:
        cb("受体准备", 40, "PDBFixer 修复完成，写出临时文件…")

    try:
        import io as _io
        buf = _io.StringIO()
        PDBFile.writeFile(fixer.topology, fixer.positions, buf)
        pdb_raw = buf.getvalue()
    except Exception as exc:
        raise ReceptorPreparationError(
            f"PDBFixer write failed: {exc}",
            "写出修复后的 PDB 文件时出错。",
        ) from exc

    cleaned_lines: list[str] = []
    for line in pdb_raw.splitlines(keepends=True):
        if line.startswith(("ATOM", "HETATM")) and len(line) > 16 and line[16] not in (" ", ""):
            line = line[:16] + " " + line[17:]
        cleaned_lines.append(line)

    try:
        output_pdb.write_text("".join(cleaned_lines), encoding="utf-8")
    except OSError as exc:
        raise ReceptorPreparationError(
            f"PDBFixer write failed: {exc}",
            "写出修复后的 PDB 文件时出错。",
        ) from exc

    return warnings


def _pdb_to_pdbqt(
    input_pdb: Path,
    output_pdbqt: Path,
    cb: Callable | None,
    original_pdb: Path | None = None,
) -> list[str]:
    """Convert PDB to PDBQT using meeko Polymer API.

    Args:
        input_pdb:    Fixed/cleaned PDB to convert.
        output_pdbqt: Destination PDBQT path.
        cb:           Progress callback.
        original_pdb: Raw PDB before PDBFixer (used for fallback atom filtering).

    Returns:
        List of warning strings emitted by meeko for skipped residues.
    """
    import logging as _logging

    from meeko import (
        MoleculePreparation,
        PDBQTWriterLegacy,
        Polymer,
        PolymerCreationError,
        ResidueChemTemplates,
    )

    if cb:
        cb("受体准备", 70, "正在使用 meeko 生成 PDBQT…")

    pdb_text = input_pdb.read_text(encoding="utf-8", errors="replace")

    # Capture WARNING-level messages from the meeko logger so callers can
    # surface "skipped residue" notices (emitted by allow_bad_res=True).
    meeko_warnings: list[str] = []

    class _Capture(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            if record.levelno >= _logging.WARNING:
                meeko_warnings.append(record.getMessage())

    _capture = _Capture()
    _meeko_log = _logging.getLogger("meeko")
    _meeko_log.addHandler(_capture)
    try:
        templates = ResidueChemTemplates.create_from_defaults()
    except Exception as exc:
        _meeko_log.removeHandler(_capture)
        raise ReceptorPreparationError(
            f"meeko residue templates unavailable: {exc}",
            "受体 PDBQT 生成失败。",
            "请确认打包版本包含 meeko/data/residue_chem_templates.json。",
        ) from exc

    mk_prep = MoleculePreparation()
    try:
        polymer = Polymer.from_pdb_string(
            pdb_text,
            templates,
            mk_prep,
            allow_bad_res=True,
            default_altloc="A",
        )
    except PolymerCreationError as exc:
        _meeko_log.removeHandler(_capture)
        raise ReceptorPreparationError(
            f"meeko Polymer creation failed: {exc}",
            "meeko 无法解析受体结构，可能含有不标准残基。",
            "请检查 PDB 文件中是否有非标准氨基酸，尝试手动删除后重试。",
        ) from exc
    except Exception as first_exc:
        # Fallback: PDBFixer's addMissingAtoms can place atoms (e.g. cis-Pro CD) within
        # bonding distance of neighbouring residue atoms, triggering a valence error in
        # meeko's DetermineConnectivity.  Retry with heavy-atom-only PDB stripped of any
        # atom added by PDBFixer (identified as no element in the original structure).
        _meeko_log.removeHandler(_capture)
        _meeko_log.addHandler(_capture)
        try:
            pdb_heavy = _strip_pdbfixer_added_atoms(pdb_text, original_pdb or input_pdb)
            _log.warning(
                "meeko first attempt failed (%s); retrying with heavy-atom-only PDB",
                first_exc,
            )
            polymer = Polymer.from_pdb_string(
                pdb_heavy,
                templates,
                mk_prep,
                allow_bad_res=True,
                default_altloc="A",
            )
            meeko_warnings.append(
                f"受体 PDBQT 生成时遇到问题（{first_exc}），已跳过 PDBFixer 新增原子重试。"
            )
        except Exception as exc:
            _meeko_log.removeHandler(_capture)
            raise ReceptorPreparationError(
                f"meeko Polymer unexpected error: {exc}",
                "受体 PDBQT 生成失败。",
            ) from exc
    finally:
        _meeko_log.removeHandler(_capture)

    try:
        rigid_pdbqt, _flex_dict = PDBQTWriterLegacy.write_from_polymer(polymer)
    except Exception as exc:
        raise ReceptorPreparationError(
            f"meeko PDBQT write failed: {exc}",
            "受体 PDBQT 写出失败。",
        ) from exc

    output_pdbqt.write_text(rigid_pdbqt, encoding="utf-8")

    if cb:
        cb("受体准备", 90, "PDBQT 生成完成。")

    return meeko_warnings


def _get_chains_and_residues(pdb_text: str) -> tuple[list[str], int]:
    """Parse ATOM records to get chain IDs and residue count."""
    seen_residues: set[tuple[str, int]] = set()
    chains: set[str] = set()
    for line in pdb_text.splitlines():
        if not line.startswith(("ATOM  ", "ATOM")):
            continue
        if len(line) < 26:
            continue
        chain = line[21].strip() or " "
        try:
            resi = int(line[22:26].strip())
        except ValueError:
            continue
        chains.add(chain)
        seen_residues.add((chain, resi))
    return sorted(chains), len(seen_residues)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare_receptor(
    input_pdb: Path,
    work_dir: Path,
    keep_hetero: list[tuple[str, str, int]] | None = None,
    remove_waters: bool = True,
    add_missing_atoms: bool = True,
    ph: float = 7.4,
    progress_callback: Callable[[str, int, str], None] | None = None,
    strip_nucleic_acids: bool = False,
) -> ReceptorInfo:
    """Prepare a PDB receptor for AutoDock Vina docking.

    Args:
        input_pdb:            Path to the raw PDB file.
        work_dir:             Directory for intermediate and output files.
        keep_hetero:          List of (resname, chain, resi) tuples to preserve.
        remove_waters:        Strip HOH records when True.
        add_missing_atoms:    Run PDBFixer addMissingAtoms / addMissingHydrogens.
        ph:                   pH value passed to PDBFixer protonation.
        progress_callback:    Called as ``cb(stage, percent, message)``.
        strip_nucleic_acids:  If True, remove DNA/RNA chains before PDBFixer.

    Returns:
        ReceptorInfo with paths and metadata.

    Raises:
        ReceptorPreparationError: on any preparation failure.
    """
    cb = progress_callback
    work_dir.mkdir(parents=True, exist_ok=True)

    stem = safe_name(input_pdb.stem)
    raw_copy = work_dir / f"{stem}_raw.pdb"
    fixed_pdb = work_dir / f"{stem}_fixed.pdb"
    clean_pdb = work_dir / f"{stem}_clean.pdb"
    output_pdbqt = work_dir / f"{stem}.pdbqt"

    if cb:
        cb("受体准备", 5, f"加载 {input_pdb.name}…")

    try:
        shutil.copy2(input_pdb, raw_copy)
    except OSError as exc:
        raise ReceptorPreparationError(
            f"Cannot copy PDB: {exc}",
            "无法读取 PDB 文件，请检查文件是否被占用或路径是否正确。",
        ) from exc

    raw_text = raw_copy.read_text(encoding="utf-8", errors="replace")
    hetero_groups = _parse_hetero_groups(raw_text)
    _log.debug("Found %d HETATM groups in %s", len(hetero_groups), input_pdb.name)

    # Detect nucleic acid chains
    na_chains = detect_nucleic_acid_chains(raw_copy)
    warnings: list[str] = []

    if na_chains and strip_nucleic_acids:
        stripped_text = strip_nucleic_acid_chains(raw_text)
        raw_copy.write_text(stripped_text, encoding="utf-8")
        warnings.append(
            f"已自动移除核酸链（DNA/RNA）：{', '.join(na_chains)}。"
            f"如需对接蛋白-核酸界面，请手动保留并注意处理限制。"
        )
        _log.info("Stripped nucleic acid chains %s from %s", na_chains, input_pdb.name)
    elif na_chains and not strip_nucleic_acids:
        warnings.append(
            f"检测到核酸链：{', '.join(na_chains)}。"
            f"PDB 含 DNA/RNA 时建议选择「移除核酸链」以确保处理成功。"
        )

    used_pdbfixer = True
    try:
        fixer_warnings = _run_pdbfixer(raw_copy, fixed_pdb, add_missing_atoms, ph, cb)
        warnings.extend(fixer_warnings)
    except ModuleNotFoundError as exc:
        used_pdbfixer = False
        _log.warning("PDBFixer/OpenMM unavailable; using raw PDB fallback: %s", exc)
        warnings.append(
            "未检测到 OpenMM/PDBFixer，已跳过缺失残基/原子修复；"
            "将直接清洗原始 PDB 并生成 PDBQT。"
        )
        if cb:
            cb("受体准备", 40, "未检测到 OpenMM/PDBFixer，跳过结构修复。")
        try:
            shutil.copy2(raw_copy, fixed_pdb)
        except OSError as copy_exc:
            raise ReceptorPreparationError(
                f"Cannot create fallback receptor PDB: {copy_exc}",
                "无法创建受体准备临时文件。",
            ) from copy_exc

    fixed_text = fixed_pdb.read_text(encoding="utf-8", errors="replace")
    cleaned_text, n_waters = _strip_hetatm(fixed_text, keep=keep_hetero)
    clean_pdb.write_text(cleaned_text, encoding="utf-8")

    chains, n_residues = _get_chains_and_residues(cleaned_text)

    meeko_warnings = _pdb_to_pdbqt(clean_pdb, output_pdbqt, cb, original_pdb=raw_copy)
    warnings.extend(meeko_warnings)

    # Auto-retry without addMissingAtoms if PDBQT came out empty (meeko's
    # template matching fails when PDBFixer over-extends a structure).  Keep
    # retry progress monotonic so the GUI does not appear to restart stage 1.
    if (
        used_pdbfixer
        and add_missing_atoms
        and output_pdbqt.exists()
        and output_pdbqt.stat().st_size == 0
    ):
        _log.warning("PDBQT empty after first attempt; retrying without addMissingAtoms")
        warnings.append("PDBQT 首次生成为空，已自动以「不补全缺失原子」模式重试。")
        if cb:
            cb("受体准备", 92, "首次 PDBQT 为空，正在使用兼容模式重试…")

        def retry_cb(stage: str, pct: int, msg: str) -> None:
            if cb is None:
                return
            mapped = 92 + max(0, min(100, int(pct))) * 7 // 100
            cb(stage, mapped, msg)

        _run_pdbfixer(raw_copy, fixed_pdb, False, ph, retry_cb if cb else None)
        fixed_text2 = fixed_pdb.read_text(encoding="utf-8", errors="replace")
        cleaned_text2, _ = _strip_hetatm(fixed_text2, keep=keep_hetero)
        clean_pdb.write_text(cleaned_text2, encoding="utf-8")
        meeko_warnings2 = _pdb_to_pdbqt(
            clean_pdb, output_pdbqt, retry_cb if cb else None, original_pdb=raw_copy
        )
        warnings.extend(meeko_warnings2)
        chains, n_residues = _get_chains_and_residues(cleaned_text2)

    if cb:
        cb("受体准备", 100, "受体准备完成。")

    info = ReceptorInfo(
        pdb_path=clean_pdb,
        pdbqt_path=output_pdbqt,
        chains=chains,
        n_residues=n_residues,
        hetero_groups=hetero_groups,
        waters_removed=n_waters,
        warnings=warnings,
        nucleic_acid_chains=na_chains,
    )
    _log.info(
        "Receptor prepared: %s | chains=%s residues=%d na_chains=%s",
        output_pdbqt.name, chains, n_residues, na_chains,
    )
    return info
