"""Receptor (protein) preparation pipeline.

Flow:
    input PDB → copy to work_dir/safe_name
             → PDBFixer: standardise residues and protonate at given pH
             → strip waters / HETATM (unless kept by caller)
             → meeko Polymer.from_pdb_string() → PDBQTWriterLegacy.write_from_polymer()

The default path deliberately preserves the experimental heavy-atom model.
PDBFixer's heavy-atom completion is available as an opt-in repair mode because
it can create chemically invalid coordinates for otherwise usable structures.

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
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
    import meeko as _meeko_preload  # noqa: F401
    import openmm as _openmm_preload  # noqa: F401
    import openmm.app as _openmm_app_preload  # noqa: F401
    import pdbfixer as _pdbfixer_preload  # noqa: F401
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
_RECEPTOR_CACHE_SCHEMA = 1
_RECEPTOR_CACHE_DIRNAME = ".receptor-cache"


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
    original_pdb_path: Path | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _serialize_hetero_groups(groups: list[HeteroGroup]) -> list[dict[str, object]]:
    return [
        {
            "resname": group.resname,
            "chain": group.chain,
            "resi": group.resi,
            "n_atoms": group.n_atoms,
            "is_water": group.is_water,
            "is_ion": group.is_ion,
            "is_likely_ligand": group.is_likely_ligand,
        }
        for group in groups
    ]


def _deserialize_hetero_groups(payload: list[dict[str, object]]) -> list[HeteroGroup]:
    return [
        HeteroGroup(
            resname=str(item["resname"]),
            chain=str(item["chain"]),
            resi=int(item["resi"]),
            n_atoms=int(item["n_atoms"]),
            is_water=bool(item["is_water"]),
            is_ion=bool(item["is_ion"]),
            is_likely_ligand=bool(item["is_likely_ligand"]),
        )
        for item in payload
    ]


def _build_receptor_cache_key(
    raw_bytes: bytes,
    *,
    keep_hetero: list[tuple[str, str, int]] | None,
    remove_waters: bool,
    add_missing_atoms: bool,
    ph: float,
    strip_nucleic_acids: bool,
) -> tuple[str, str]:
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    request_payload = {
        "schema": _RECEPTOR_CACHE_SCHEMA,
        "source_sha256": source_sha256,
        "keep_hetero": sorted(list(keep_hetero or [])),
        "remove_waters": bool(remove_waters),
        "add_missing_atoms": bool(add_missing_atoms),
        "ph": round(float(ph), 3),
        "strip_nucleic_acids": bool(strip_nucleic_acids),
    }
    request_key = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return source_sha256, request_key


def _load_cached_receptor_info(
    cache_dir: Path,
    *,
    expected_source_sha256: str,
) -> ReceptorInfo | None:
    meta_path = cache_dir / "metadata.json"
    if not meta_path.exists():
        return None

    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if payload.get("schema") != _RECEPTOR_CACHE_SCHEMA:
        return None
    if payload.get("source_sha256") != expected_source_sha256:
        return None

    pdb_path = cache_dir / str(payload.get("pdb_path", ""))
    pdbqt_path = cache_dir / str(payload.get("pdbqt_path", ""))
    original_pdb_path = cache_dir / str(payload.get("original_pdb_path", ""))
    if not pdb_path.exists() or not pdbqt_path.exists() or not original_pdb_path.exists():
        return None

    return ReceptorInfo(
        pdb_path=pdb_path,
        pdbqt_path=pdbqt_path,
        chains=[str(item) for item in payload.get("chains", [])],
        n_residues=int(payload.get("n_residues", 0)),
        hetero_groups=_deserialize_hetero_groups(payload.get("hetero_groups", [])),
        waters_removed=int(payload.get("waters_removed", 0)),
        warnings=[str(item) for item in payload.get("warnings", [])],
        nucleic_acid_chains=[str(item) for item in payload.get("nucleic_acid_chains", [])],
        original_pdb_path=original_pdb_path,
    )


def _write_receptor_cache_metadata(
    cache_dir: Path,
    *,
    source_sha256: str,
    info: ReceptorInfo,
) -> None:
    payload = {
        "schema": _RECEPTOR_CACHE_SCHEMA,
        "source_sha256": source_sha256,
        "pdb_path": info.pdb_path.name,
        "pdbqt_path": info.pdbqt_path.name,
        "original_pdb_path": info.original_pdb_path.name if info.original_pdb_path else "",
        "chains": info.chains,
        "n_residues": info.n_residues,
        "hetero_groups": _serialize_hetero_groups(info.hetero_groups),
        "waters_removed": info.waters_removed,
        "warnings": info.warnings,
        "nucleic_acid_chains": info.nucleic_acid_chains,
    }
    (cache_dir / "metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def _detect_nucleic_acid_chains_from_text(pdb_text: str) -> list[str]:
    """Scan PDB text and return chain IDs that contain DNA/RNA residues."""
    na_chains: set[str] = set()
    for line in pdb_text.splitlines():
        if not line.startswith(("ATOM  ", "ATOM", "HETATM")):
            continue
        if len(line) < 26:
            continue
        resname = line[17:20].strip()
        chain = line[21].strip() or " "
        if resname in _NUCLEIC_RESNAMES:
            na_chains.add(chain)
    return sorted(na_chains)


def detect_nucleic_acid_chains(pdb_path: Path) -> list[str]:
    """Scan a PDB file and return chain IDs that contain DNA/RNA residues."""
    try:
        text = pdb_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return _detect_nucleic_acid_chains_from_text(text)


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

    if add_missing_atoms:
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

    if add_missing_atoms:
        try:
            fixer.findMissingAtoms()
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


_RESIDUE_KEY_RE = re.compile(r"residue_key\s*=\s*['\"]?([^'\"\s,;]+)")
_MEEKO_RECOVERABLE_ERROR_MARKERS = (
    "explicit valence",
    "updated ",
    "deleted ",
    "kekul",
    "sanitize",
    "valence",
)
_RESIDUE_TEMPLATES = None


def _summarize_meeko_warnings(messages: list[str], limit: int = 4) -> list[str]:
    """Collapse noisy Meeko logs into a bounded set of user-facing messages."""
    residue_keys: set[str] = set()
    other_messages: list[str] = []
    seen: set[str] = set()

    for raw_message in messages:
        message = " ".join(str(raw_message).split())
        if not message or "Lone hydrogen is ignored" in message:
            continue

        keys = _RESIDUE_KEY_RE.findall(message)
        if keys and any(word in message.lower() for word in ("template", "residue")):
            residue_keys.update(keys)
            continue

        if message in seen:
            continue
        seen.add(message)
        if len(message) > 220:
            message = message[:217].rstrip() + "..."
        other_messages.append(message)

    result: list[str] = []
    if residue_keys:
        ordered = sorted(residue_keys)
        examples = "、".join(ordered[:5])
        suffix = "等" if len(ordered) > 5 else ""
        result.append(
            f"Meeko 已跳过 {len(ordered)} 个无法匹配模板的残基"
            f"（示例：{examples}{suffix}）；这些残基不会参与对接。"
        )

    remaining = max(0, limit - len(result))
    if len(other_messages) > remaining and remaining > 0:
        visible_count = remaining - 1
        result.extend(other_messages[:visible_count])
        result.append(
            f"另有 {len(other_messages) - visible_count} 条技术性提示已收起。"
        )
    else:
        result.extend(other_messages[:remaining])
    return result[:limit]


def _sanitize_pdb_for_meeko(pdb_text: str) -> tuple[str, list[str]]:
    """Conservatively normalise PDB records for meeko rescue attempts."""
    cleaned_lines: list[str] = []
    seen_atoms: set[tuple[str, str, str, str, str]] = set()
    removed_hydrogens = 0
    removed_duplicates = 0
    removed_altlocs = 0
    removed_auxiliary = 0

    for line in pdb_text.splitlines(keepends=True):
        if line.startswith(("ANISOU", "CONECT", "MASTER")):
            removed_auxiliary += 1
            continue

        if not line.startswith(("ATOM  ", "ATOM", "HETATM")):
            cleaned_lines.append(line)
            continue

        if len(line) < 26:
            cleaned_lines.append(line)
            continue

        atom_name = line[12:16].strip()
        altloc = line[16].strip() if len(line) > 16 else ""
        resname = line[17:20].strip()
        chain = line[21].strip() or " "
        resi = line[22:26].strip()
        icode = line[26].strip() if len(line) > 26 else ""
        element = line[76:78].strip().upper() if len(line) >= 78 else ""

        if element == "H" or atom_name.startswith("H"):
            removed_hydrogens += 1
            continue

        dedupe_key = (chain, resi, icode, resname, atom_name)
        if dedupe_key in seen_atoms:
            removed_duplicates += 1
            continue

        seen_atoms.add(dedupe_key)
        if altloc:
            removed_altlocs += 1
            line = line[:16] + " " + line[17:]
        cleaned_lines.append(line)

    warnings: list[str] = []
    if removed_hydrogens:
        warnings.append(f"兼容模式已移除 {removed_hydrogens} 个可疑氢原子。")
    if removed_duplicates:
        warnings.append(f"兼容模式已跳过 {removed_duplicates} 个重复原子记录。")
    if removed_altlocs:
        warnings.append(f"兼容模式已规范 {removed_altlocs} 个备选构象标记。")
    if removed_auxiliary:
        warnings.append(f"兼容模式已忽略 {removed_auxiliary} 条辅助连接记录。")

    return "".join(cleaned_lines), warnings


def _is_recoverable_meeko_error(exc: ReceptorPreparationError) -> bool:
    technical = exc.args[0] if exc.args else ""
    parts = (
        technical,
        getattr(exc, "user_message", ""),
        getattr(exc, "suggestion", ""),
    )
    detail = " ".join(
        part for part in parts if part
    )
    lowered = detail.lower()
    return any(marker in lowered for marker in _MEEKO_RECOVERABLE_ERROR_MARKERS)


def _is_valence_meeko_error(exc: ReceptorPreparationError) -> bool:
    technical = exc.args[0] if exc.args else ""
    return "valence" in technical.lower()


def _get_residue_templates():
    global _RESIDUE_TEMPLATES
    if _RESIDUE_TEMPLATES is None:
        from meeko import ResidueChemTemplates

        _RESIDUE_TEMPLATES = ResidueChemTemplates.create_from_defaults()
    return _RESIDUE_TEMPLATES


def _pdb_to_pdbqt(
    input_pdb: Path,
    output_pdbqt: Path,
    cb: Callable | None,
) -> list[str]:
    """Convert PDB to PDBQT using meeko Polymer API.

    Args:
        input_pdb:    Fixed/cleaned PDB to convert.
        output_pdbqt: Destination PDBQT path.
        cb:           Progress callback.
    Returns:
        A bounded summary of warnings emitted by meeko for skipped residues.
    """
    import logging as _logging

    from meeko import MoleculePreparation, PDBQTWriterLegacy, Polymer, PolymerCreationError

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
        templates = _get_residue_templates()
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

    return _summarize_meeko_warnings(meeko_warnings)


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


def _validate_pdbqt_coverage(source_pdb_text: str, output_pdbqt: Path) -> None:
    """Reject empty or catastrophically incomplete receptor conversions."""
    _source_chains, expected_residues = _get_chains_and_residues(source_pdb_text)
    try:
        pdbqt_text = output_pdbqt.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ReceptorPreparationError(
            f"Cannot read generated receptor PDBQT: {exc}",
            "受体 PDBQT 生成失败。",
        ) from exc

    _output_chains, converted_residues = _get_chains_and_residues(pdbqt_text)
    if converted_residues == 0:
        raise ReceptorPreparationError(
            "Generated receptor PDBQT contains no ATOM records",
            "生成的受体 PDBQT 不包含有效原子。",
        )

    coverage = converted_residues / max(1, expected_residues)
    if expected_residues >= 20 and coverage < 0.8:
        raise ReceptorPreparationError(
            "Generated receptor PDBQT is incomplete: "
            f"{converted_residues}/{expected_residues} residues ({coverage:.1%})",
            "生成的受体 PDBQT 不完整，已停止使用该结果。",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare_receptor(
    input_pdb: Path,
    work_dir: Path,
    keep_hetero: list[tuple[str, str, int]] | None = None,
    remove_waters: bool = True,
    add_missing_atoms: bool = False,
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
        add_missing_atoms:    Opt in to PDBFixer heavy-atom/residue completion.
                              Hydrogens are added in both modes.
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

    if cb:
        cb("受体准备", 5, f"加载 {input_pdb.name}…")

    try:
        raw_bytes = input_pdb.read_bytes()
    except OSError as exc:
        raise ReceptorPreparationError(
            f"Cannot read PDB: {exc}",
            "无法读取 PDB 文件，请检查文件是否被占用或路径是否正确。",
        ) from exc

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    hetero_groups = _parse_hetero_groups(raw_text)
    _log.debug("Found %d HETATM groups in %s", len(hetero_groups), input_pdb.name)

    # Detect nucleic acid chains without re-reading the file.
    na_chains = _detect_nucleic_acid_chains_from_text(raw_text)
    warnings: list[str] = []

    source_sha256, request_key = _build_receptor_cache_key(
        raw_bytes,
        keep_hetero=keep_hetero,
        remove_waters=remove_waters,
        add_missing_atoms=add_missing_atoms,
        ph=ph,
        strip_nucleic_acids=strip_nucleic_acids,
    )
    cache_dir = work_dir / _RECEPTOR_CACHE_DIRNAME / f"{stem}_{request_key[:16]}"
    cached_info = _load_cached_receptor_info(
        cache_dir,
        expected_source_sha256=source_sha256,
    )
    if cached_info is not None:
        if cb:
            cb("受体准备", 20, "检测到相同受体缓存，正在复用已准备结果…")
            cb("受体准备", 100, "受体准备完成。")
        _log.info("Receptor cache hit: %s -> %s", input_pdb.name, cache_dir.name)
        return cached_info

    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = cache_dir / f"{stem}_raw.pdb"
    fixed_pdb = cache_dir / f"{stem}_fixed.pdb"
    clean_pdb = cache_dir / f"{stem}_clean.pdb"
    output_pdbqt = cache_dir / f"{stem}.pdbqt"

    try:
        raw_copy.write_bytes(raw_bytes)
    except OSError as exc:
        raise ReceptorPreparationError(
            f"Cannot copy PDB: {exc}",
            "无法读取 PDB 文件，请检查文件是否被占用或路径是否正确。",
        ) from exc

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
    final_text = cleaned_text

    def _write_attempt_input(pdb_text: str) -> None:
        clean_pdb.write_text(pdb_text, encoding="utf-8")

    def _run_meeko_attempt(
        pdb_text: str,
        *,
        attempt_label: str,
        attempt_cb: Callable[[str, int, str], None] | None,
        sanitize: bool = False,
    ) -> tuple[list[str], str]:
        text_to_convert = pdb_text
        local_warnings: list[str] = []
        if sanitize:
            text_to_convert, sanitize_warnings = _sanitize_pdb_for_meeko(pdb_text)
            local_warnings.extend(sanitize_warnings)
        _write_attempt_input(text_to_convert)
        meeko_warnings = _pdb_to_pdbqt(clean_pdb, output_pdbqt, attempt_cb)
        _validate_pdbqt_coverage(text_to_convert, output_pdbqt)
        _log.info("Receptor meeko attempt succeeded: %s", attempt_label)
        return local_warnings + meeko_warnings, text_to_convert

    def _retry_progress(base_pct: int, span_pct: int) -> Callable[[str, int, str], None] | None:
        if cb is None:
            return None

        def _mapped(stage: str, pct: int, msg: str) -> None:
            bounded = max(0, min(100, int(pct)))
            cb(stage, base_pct + bounded * span_pct // 100, msg)

        return _mapped

    try:
        meeko_warnings, final_text = _run_meeko_attempt(
            cleaned_text,
            attempt_label="primary",
            attempt_cb=cb,
        )
        warnings.extend(meeko_warnings)
    except ReceptorPreparationError as exc:
        rescue_success = False
        primary_valence_failure = (
            used_pdbfixer
            and add_missing_atoms
            and _is_valence_meeko_error(exc)
        )
        if _is_recoverable_meeko_error(exc) and not primary_valence_failure:
            warnings.append("检测到 meeko 解析异常，已自动启用更保守的兼容清洗重试。")
            if cb:
                cb("受体准备", 92, "首次 PDBQT 失败，正在执行兼容清洗重试…")
            try:
                meeko_warnings, final_text = _run_meeko_attempt(
                    cleaned_text,
                    attempt_label="sanitized-primary",
                    attempt_cb=_retry_progress(92, 4),
                    sanitize=True,
                )
                warnings.extend(meeko_warnings)
                rescue_success = True
            except ReceptorPreparationError as sanitize_exc:
                exc = sanitize_exc
        elif primary_valence_failure:
            warnings.append(
                "检测到补全后的结构触发 meeko 价态冲突，"
                "已直接切换到不补全原子的保守模式。"
            )

        if not rescue_success and used_pdbfixer and add_missing_atoms:
            _log.warning(
                "PDBQT attempt failed after addMissingAtoms; retrying without addMissingAtoms: %s",
                exc,
            )
            warnings.append(
                "检测到补全后的结构存在化学价态或完整性冲突，"
                "已自动改用兼容模式完成准备。"
            )
            if cb:
                cb("受体准备", 96, "兼容清洗仍失败，正在切换为不补全原子的保守模式…")

            retry_cb = _retry_progress(96, 3)
            retry_warnings = _run_pdbfixer(raw_copy, fixed_pdb, False, ph, retry_cb)
            fixed_text = fixed_pdb.read_text(encoding="utf-8", errors="replace")
            cleaned_text, n_waters = _strip_hetatm(fixed_text, keep=keep_hetero)

            try:
                meeko_warnings, final_text = _run_meeko_attempt(
                    cleaned_text,
                    attempt_label="retry-without-missing-atoms",
                    attempt_cb=retry_cb,
                )
                warnings.extend(retry_warnings + meeko_warnings)
                rescue_success = True
            except ReceptorPreparationError as retry_exc:
                if not _is_recoverable_meeko_error(retry_exc):
                    raise
                warnings.append("保守模式首次重试仍失败，已自动移除可疑氢/重复原子再次尝试。")
                meeko_warnings, final_text = _run_meeko_attempt(
                    cleaned_text,
                    attempt_label="sanitized-retry-without-missing-atoms",
                    attempt_cb=retry_cb,
                    sanitize=True,
                )
                warnings.extend(retry_warnings + meeko_warnings)
                rescue_success = True

        if not rescue_success:
            raise

    chains, n_residues = _get_chains_and_residues(final_text)

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
        original_pdb_path=raw_copy,
    )
    _write_receptor_cache_metadata(
        cache_dir,
        source_sha256=source_sha256,
        info=info,
    )
    _log.info(
        "Receptor prepared: %s | chains=%s residues=%d na_chains=%s",
        output_pdbqt.name, chains, n_residues, na_chains,
    )
    return info
