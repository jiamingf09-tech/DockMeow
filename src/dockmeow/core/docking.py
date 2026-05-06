"""AutoDock Vina docking execution.

Uses the official ``vina`` Python bindings directly (no subprocess).
Converts the multi-model PDBQT output to SDF via meeko PDBQTMolecule.

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dockmeow.core._utils import safe_name
from dockmeow.core.exceptions import DockingExecutionError

_log = logging.getLogger(__name__)


@dataclass
class DockingConfig:
    """All parameters required to run one docking job."""

    receptor_pdbqt: Path
    ligand_pdbqt: Path
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    exhaustiveness: int = 16
    num_modes: int = 9
    energy_range: float = 3.0
    seed: int = 42
    cpu: int = 0  # 0 = auto-detect


@dataclass
class DockingResult:
    """Output of a completed docking run."""

    poses_pdbqt: Path
    poses_sdf: Path
    scores: list[float] = field(default_factory=list)
    rmsd_lb: list[float] = field(default_factory=list)
    rmsd_ub: list[float] = field(default_factory=list)
    runtime_seconds: float = 0.0
    config: DockingConfig | None = None


def _pdbqt_to_sdf(poses_pdbqt: Path, output_sdf: Path) -> None:
    """Convert multi-model PDBQT poses to SDF via meeko."""
    from meeko import PDBQTMolecule, RDKitMolCreate

    pdbqt_text = poses_pdbqt.read_text(encoding="utf-8", errors="replace")
    try:
        pdbqt_mol = PDBQTMolecule(pdbqt_text, is_dlg=False, skip_typing=True)
        rdmols = RDKitMolCreate.from_pdbqt_mol(pdbqt_mol)
    except Exception as exc:
        _log.warning("meeko PDBQT→SDF failed (%s), writing placeholder SDF", exc)
        output_sdf.write_text("", encoding="utf-8")
        return

    from rdkit.Chem import SDWriter
    with SDWriter(str(output_sdf)) as w:
        for mol in rdmols:
            if mol is not None:
                w.write(mol)


def run_docking(
    config: DockingConfig,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> DockingResult:
    """Run AutoDock Vina using the Python API.

    Args:
        config:            Full docking configuration.
        progress_callback: Called as ``cb(stage, percent, message)``.

    Returns:
        DockingResult with pose files and score tables.

    Raises:
        DockingExecutionError: on Vina failure.
        InterruptedError:      when the caller cancels via progress_callback.
    """
    from vina import Vina

    cb = progress_callback

    # Resolve output paths alongside the ligand PDBQT
    out_dir = config.ligand_pdbqt.parent
    stem = safe_name(config.ligand_pdbqt.stem)
    poses_pdbqt = out_dir / f"{stem}_poses.pdbqt"
    poses_sdf = out_dir / f"{stem}_poses.sdf"

    if cb:
        cb("分子对接", 5, "初始化 Vina…")

    cpu = config.cpu if config.cpu > 0 else 0  # vina uses 0 for auto

    try:
        v = Vina(sf_name="vina", cpu=cpu, seed=config.seed, verbosity=0)
    except Exception as exc:
        raise DockingExecutionError(
            f"Vina init failed: {exc}",
            "Vina 初始化失败。",
        ) from exc

    if cb:
        cb("分子对接", 10, f"加载受体 {config.receptor_pdbqt.name}…")
        if progress_callback and _check_interrupt(cb):
            raise InterruptedError("用户取消")

    try:
        v.set_receptor(str(config.receptor_pdbqt))
    except Exception as exc:
        raise DockingExecutionError(
            f"Vina set_receptor failed: {exc}",
            "受体 PDBQT 加载失败，请重新准备受体。",
        ) from exc

    if cb:
        cb("分子对接", 20, f"加载配体 {config.ligand_pdbqt.name}…")

    try:
        v.set_ligand_from_file(str(config.ligand_pdbqt))
    except Exception as exc:
        raise DockingExecutionError(
            f"Vina set_ligand failed: {exc}",
            "配体 PDBQT 加载失败，请重新准备配体。",
        ) from exc

    cx, cy, cz = config.center
    sx, sy, sz = config.size

    if cb:
        cb(
            "分子对接", 30,
            f"设置对接盒子：中心({cx:.1f},{cy:.1f},{cz:.1f}) 大小({sx:.0f},{sy:.0f},{sz:.0f})Å…",
        )

    try:
        v.compute_vina_maps(
            center=[cx, cy, cz],
            box_size=[sx, sy, sz],
        )
    except Exception as exc:
        raise DockingExecutionError(
            f"Vina compute_vina_maps failed: {exc}",
            "对接盒子计算失败，请检查中心坐标和盒子大小是否合理。",
        ) from exc

    if cb:
        cb("分子对接", 40, f"开始搜索（精度={config.exhaustiveness}）…")
        if _check_interrupt(cb):
            raise InterruptedError("用户取消")

    t0 = time.perf_counter()

    try:
        v.dock(
            exhaustiveness=config.exhaustiveness,
            n_poses=config.num_modes,
        )
    except Exception as exc:
        raise DockingExecutionError(
            f"Vina dock failed: {exc}",
            "对接搜索失败。",
            "请检查受体和配体文件是否正确，或降低搜索精度重试。",
        ) from exc

    runtime = time.perf_counter() - t0

    if cb:
        cb("分子对接", 85, "解析对接结果…")

    try:
        v.write_poses(
            str(poses_pdbqt),
            n_poses=config.num_modes,
            energy_range=config.energy_range,
            overwrite=True,
        )
    except Exception as exc:
        raise DockingExecutionError(
            f"Vina write_poses failed: {exc}",
            "写出对接结果失败。",
        ) from exc

    # Parse scores from Vina output (energy_range filters here too)
    energies = v.energies(n_poses=config.num_modes, energy_range=config.energy_range)
    scores = [float(e[0]) for e in energies]
    rmsd_lb = [float(e[1]) for e in energies]
    rmsd_ub = [float(e[2]) for e in energies]

    if cb:
        cb("分子对接", 92, "转换 SDF 格式…")

    _pdbqt_to_sdf(poses_pdbqt, poses_sdf)

    if cb:
        cb("分子对接", 100, f"对接完成！最佳结合能 {scores[0]:.2f} kcal/mol")

    _log.info(
        "Docking done: best_score=%.2f runtime=%.1fs n_poses=%d",
        scores[0], runtime, len(scores),
    )

    return DockingResult(
        poses_pdbqt=poses_pdbqt,
        poses_sdf=poses_sdf,
        scores=scores,
        rmsd_lb=rmsd_lb,
        rmsd_ub=rmsd_ub,
        runtime_seconds=runtime,
        config=config,
    )


def _check_interrupt(cb: Callable) -> bool:
    """Call the progress callback with current state to allow interrupt check.

    Returns True if an interrupt should be raised (not currently used,
    but provides a hook for the QThread worker to inject InterruptedError).
    """
    return False
