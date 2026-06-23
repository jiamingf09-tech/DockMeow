"""AutoDock Vina docking execution.

Uses the official ``vina`` Python bindings when available, then falls back to
the bundled Vina executable on platforms where the bindings are unavailable.
Converts the multi-model PDBQT output to SDF via meeko PDBQTMolecule.

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dockmeow.core._utils import safe_name
from dockmeow.core.exceptions import DockingExecutionError
from dockmeow.utils.subprocess import hidden_subprocess_kwargs

_log = logging.getLogger(__name__)
_VINA_RESULT_RE = re.compile(
    r"REMARK\s+VINA\s+RESULT:\s+"
    r"(?P<score>[-+]?\d+(?:\.\d+)?)\s+"
    r"(?P<rmsd_lb>[-+]?\d+(?:\.\d+)?)\s+"
    r"(?P<rmsd_ub>[-+]?\d+(?:\.\d+)?)"
)
_VINA_TABLE_RE = re.compile(
    r"^\s*\d+\s+"
    r"(?P<score>[-+]?\d+(?:\.\d+)?)\s+"
    r"(?P<rmsd_lb>[-+]?\d+(?:\.\d+)?)\s+"
    r"(?P<rmsd_ub>[-+]?\d+(?:\.\d+)?)\s*$"
)


@dataclass
class DockingConfig:
    """All parameters required to run one docking job."""

    receptor_pdbqt: Path
    ligand_pdbqt: Path
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    pocket_source: str = "config"
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

    # meeko returns ONE RDKit mol per ligand with one *conformer* per docked
    # pose.  SDWriter.write(mol) only emits the default conformer, which would
    # collapse every pose to a single record — breaking pose switching in the
    # viewer and the PyMOL multi-state export.  Write every conformer instead.
    from rdkit.Chem import SDWriter
    with SDWriter(str(output_sdf)) as w:
        for mol in rdmols:
            if mol is None:
                continue
            conformers = list(mol.GetConformers())
            if not conformers:
                w.write(mol)
                continue
            for pose_index, conf in enumerate(conformers, start=1):
                try:
                    mol.SetProp("_Name", f"pose_{pose_index}")
                except Exception:  # noqa: BLE001
                    pass
                w.write(mol, confId=conf.GetId())


def _vina_executable() -> Path | None:
    """Return a usable Vina CLI executable, preferring the bundled binary."""
    from dockmeow.utils.paths import vina_binary

    bundled = vina_binary()
    if bundled.exists():
        return bundled

    for name in ("vina", "vina.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _remove_existing_outputs(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _prefer_vina_cli() -> bool:
    backend = os.environ.get("DOCKMEOW_VINA_BACKEND", "").strip().lower()
    if backend in {"cli", "subprocess", "binary"}:
        return True
    if backend in {"python", "api", "binding", "bindings"}:
        return False
    return (
        sys.platform == "darwin"
        and getattr(sys, "frozen", False)
        and _vina_executable() is not None
    )


def _parse_vina_scores(
    poses_pdbqt: Path,
    stdout: str,
) -> tuple[list[float], list[float], list[float]]:
    """Parse score/RMSD rows from Vina PDBQT remarks or stdout table."""
    scores: list[float] = []
    rmsd_lb: list[float] = []
    rmsd_ub: list[float] = []

    if poses_pdbqt.exists():
        text = poses_pdbqt.read_text(encoding="utf-8", errors="replace")
        for match in _VINA_RESULT_RE.finditer(text):
            scores.append(float(match.group("score")))
            rmsd_lb.append(float(match.group("rmsd_lb")))
            rmsd_ub.append(float(match.group("rmsd_ub")))

    if scores:
        return scores, rmsd_lb, rmsd_ub

    for line in stdout.splitlines():
        match = _VINA_TABLE_RE.match(line)
        if match:
            scores.append(float(match.group("score")))
            rmsd_lb.append(float(match.group("rmsd_lb")))
            rmsd_ub.append(float(match.group("rmsd_ub")))

    return scores, rmsd_lb, rmsd_ub


def _run_docking_cli(
    config: DockingConfig,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> DockingResult:
    """Run AutoDock Vina via command-line executable fallback."""
    cb = progress_callback
    vina_exe = _vina_executable()
    if vina_exe is None:
        raise DockingExecutionError(
            "Vina executable backend is not available.",
            "当前安装包缺少 Vina 对接组件，无法执行分子对接。",
            "请重新安装包含 Vina 的 DockMeow 安装包，或联系技术支持获取当前平台可用的 Vina 组件。",
        )

    out_dir = config.ligand_pdbqt.parent
    stem = safe_name(config.ligand_pdbqt.stem)
    poses_pdbqt = out_dir / f"{stem}_poses.pdbqt"
    poses_sdf = out_dir / f"{stem}_poses.sdf"
    _remove_existing_outputs(poses_pdbqt, poses_sdf)

    if cb:
        cb("分子对接", 5, "初始化 Vina 命令行后端…")

    cx, cy, cz = config.center
    sx, sy, sz = config.size
    cpu = config.cpu if config.cpu > 0 else 0

    cmd = [
        str(vina_exe),
        "--receptor", str(config.receptor_pdbqt),
        "--ligand", str(config.ligand_pdbqt),
        "--center_x", f"{cx:.6f}",
        "--center_y", f"{cy:.6f}",
        "--center_z", f"{cz:.6f}",
        "--size_x", f"{sx:.6f}",
        "--size_y", f"{sy:.6f}",
        "--size_z", f"{sz:.6f}",
        "--exhaustiveness", str(config.exhaustiveness),
        "--num_modes", str(config.num_modes),
        "--energy_range", str(config.energy_range),
        "--seed", str(config.seed),
        "--cpu", str(cpu),
        "--verbosity", "1",
        "--out", str(poses_pdbqt),
    ]

    if cb:
        cb(
            "分子对接", 30,
            f"设置对接盒子：中心({cx:.1f},{cy:.1f},{cz:.1f}) 大小({sx:.0f},{sy:.0f},{sz:.0f})Å…",
        )
        if _check_interrupt(cb):
            raise InterruptedError("用户取消")
        cb("分子对接", 40, f"开始搜索（精度={config.exhaustiveness}）…")

    t0 = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_subprocess_kwargs(),
        )
    except OSError as exc:
        raise DockingExecutionError(
            f"Vina executable failed to start: {exc}",
            "Vina 对接后端启动失败。",
            "请确认安装包完整，或联系技术支持获取当前平台可用的 Vina 组件。",
        ) from exc
    runtime = time.perf_counter() - t0

    if completed.returncode != 0:
        output = (completed.stdout + "\n" + completed.stderr).strip()
        raise DockingExecutionError(
            f"Vina CLI failed with exit code {completed.returncode}: {output}",
            "对接搜索失败。",
            "请检查受体、配体和对接盒子参数是否正确，或降低搜索精度重试。",
        )

    if not poses_pdbqt.exists() or poses_pdbqt.stat().st_size == 0:
        raise DockingExecutionError(
            "Vina CLI finished without a non-empty pose file.",
            "对接完成但没有生成有效结果。",
            "请检查受体、配体和对接盒子参数是否正确。",
        )

    if cb:
        cb("分子对接", 85, "解析对接结果…")

    scores, rmsd_lb, rmsd_ub = _parse_vina_scores(poses_pdbqt, completed.stdout)
    if not scores:
        raise DockingExecutionError(
            "Vina CLI result did not contain parseable scores.",
            "对接结果解析失败。",
            "请保留工作目录并联系技术支持排查 Vina 输出。",
        )

    if cb:
        cb("分子对接", 92, "转换 SDF 格式…")

    _pdbqt_to_sdf(poses_pdbqt, poses_sdf)

    if cb:
        cb("分子对接", 100, f"对接完成！最佳结合能 {scores[0]:.2f} kcal/mol")

    _log.info(
        "Docking done via CLI: best_score=%.2f runtime=%.1fs n_poses=%d",
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


def run_docking(
    config: DockingConfig,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> DockingResult:
    """Run AutoDock Vina using the Python API or bundled executable fallback.

    Args:
        config:            Full docking configuration.
        progress_callback: Called as ``cb(stage, percent, message)``.

    Returns:
        DockingResult with pose files and score tables.

    Raises:
        DockingExecutionError: on Vina failure.
        InterruptedError:      when the caller cancels via progress_callback.
    """
    if _prefer_vina_cli():
        _log.info("Using Vina CLI backend for this runtime.")
        return _run_docking_cli(config, progress_callback)

    try:
        from vina import Vina
    except ModuleNotFoundError as exc:
        _log.info("Vina Python backend unavailable; falling back to CLI: %s", exc)
        return _run_docking_cli(config, progress_callback)

    cb = progress_callback

    # Resolve output paths alongside the ligand PDBQT
    out_dir = config.ligand_pdbqt.parent
    stem = safe_name(config.ligand_pdbqt.stem)
    poses_pdbqt = out_dir / f"{stem}_poses.pdbqt"
    poses_sdf = out_dir / f"{stem}_poses.sdf"
    _remove_existing_outputs(poses_pdbqt, poses_sdf)

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

    # The Python binding's energies() columns are energy components, not RMSD.
    # Parse the canonical VINA RESULT remarks written to PDBQT instead.
    scores, rmsd_lb, rmsd_ub = _parse_vina_scores(poses_pdbqt, "")
    if not scores:
        energies = v.energies(
            n_poses=config.num_modes,
            energy_range=config.energy_range,
        )
        scores = [float(e[0]) for e in energies]
        rmsd_lb = [0.0] * len(scores)
        rmsd_ub = [0.0] * len(scores)

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
