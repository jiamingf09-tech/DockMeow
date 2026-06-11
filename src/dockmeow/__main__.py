"""Entry point: ``python -m dockmeow`` launches the GUI application."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _run_docking_child(config_path: str) -> int:
    """Run docking in a non-GUI child process and stream JSONL status."""
    from dockmeow.core.docking import DockingConfig, run_docking
    from dockmeow.core.exceptions import DockMeowError

    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    cfg = DockingConfig(
        receptor_pdbqt=Path(data["receptor_pdbqt"]),
        ligand_pdbqt=Path(data["ligand_pdbqt"]),
        center=tuple(float(v) for v in data["center"]),
        size=tuple(float(v) for v in data["size"]),
        pocket_source=str(data.get("pocket_source", "config")),
        exhaustiveness=int(data["exhaustiveness"]),
        num_modes=int(data["num_modes"]),
        energy_range=float(data["energy_range"]),
        seed=int(data["seed"]),
        cpu=int(data.get("cpu", 0)),
    )

    def emit(payload: dict) -> None:
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    def cb(stage: str, pct: int, msg: str) -> None:
        emit({"type": "progress", "stage": stage, "pct": int(pct), "msg": msg})

    try:
        result = run_docking(cfg, progress_callback=cb)
    except DockMeowError as exc:
        emit({
            "type": "failed",
            "user_message": exc.user_message,
            "suggestion": getattr(exc, "suggestion", "") or "",
        })
        return 2
    except Exception as exc:  # noqa: BLE001
        emit({
            "type": "failed",
            "user_message": f"对接失败：{exc}",
            "suggestion": "请检查参数与输入文件后重试。",
        })
        return 2

    emit({
        "type": "ok",
        "poses_pdbqt": str(result.poses_pdbqt),
        "poses_sdf": str(result.poses_sdf),
        "scores": result.scores,
        "rmsd_lb": result.rmsd_lb,
        "rmsd_ub": result.rmsd_ub,
        "runtime_seconds": result.runtime_seconds,
    })
    return 0


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--dockmeow-docking-child":
        sys.exit(_run_docking_child(sys.argv[2]))

    from dockmeow.app import run

    sys.exit(run())


if __name__ == "__main__":
    main()
