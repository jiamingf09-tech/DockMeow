"""QThread worker for AutoDock Vina docking execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dockmeow.core.docking import DockingConfig, DockingResult
from dockmeow.core.exceptions import DockMeowError
from dockmeow.utils.subprocess import hidden_subprocess_kwargs


def _should_isolate_docking() -> bool:
    mode = os.environ.get("DOCKMEOW_DOCKING_ISOLATION", "").strip().lower()
    if mode in {"1", "true", "yes", "subprocess", "process"}:
        return True
    if mode in {"0", "false", "no", "thread", "inprocess"}:
        return False
    return sys.platform == "darwin" and getattr(sys, "frozen", False)


class DockingWorker(QThread):
    """Run docking in a background thread; supports cancellation."""

    progress = Signal(str, int, str)   # stage, percent, message
    finished_ok = Signal(object)       # DockingResult
    failed = Signal(str, str)          # user_message, suggestion

    def __init__(self, config: DockingConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        """Thread entry point — calls core.docking.run_docking with interrupt check."""
        if _should_isolate_docking():
            self._run_isolated()
            return

        from dockmeow.core.docking import run_docking

        try:
            def cb(stage: str, pct: int, msg: str) -> None:
                if self.isInterruptionRequested():
                    raise InterruptedError()
                self.progress.emit(stage, int(pct), msg)

            result = run_docking(self.config, progress_callback=cb)
            self.finished_ok.emit(result)
        except InterruptedError:
            return
        except DockMeowError as e:
            self.failed.emit(e.user_message, getattr(e, "suggestion", "") or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"对接失败：{e}", "请检查参数与输入文件后重试。")

    def _run_isolated(self) -> None:
        cfg_path = self._write_config_json()
        cmd = [sys.executable, "--dockmeow-docking-child", str(cfg_path)]
        proc: subprocess.Popen[str] | None = None
        output_tail: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **hidden_subprocess_kwargs(),
            )
            assert proc.stdout is not None
            result: DockingResult | None = None
            while True:
                if self.isInterruptionRequested():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise InterruptedError()

                line = proc.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        output_tail.append(line)
                        output_tail = output_tail[-20:]
                    payload = self._parse_child_payload(line)
                    if payload is not None:
                        kind = payload.get("type")
                        if kind == "progress":
                            self.progress.emit(
                                str(payload.get("stage", "")),
                                int(payload.get("pct", 0)),
                                str(payload.get("msg", "")),
                            )
                        elif kind == "ok":
                            result = DockingResult(
                                poses_pdbqt=Path(str(payload["poses_pdbqt"])),
                                poses_sdf=Path(str(payload["poses_sdf"])),
                                scores=[float(v) for v in payload.get("scores", [])],
                                rmsd_lb=[float(v) for v in payload.get("rmsd_lb", [])],
                                rmsd_ub=[float(v) for v in payload.get("rmsd_ub", [])],
                                runtime_seconds=float(payload.get("runtime_seconds", 0.0)),
                                config=self.config,
                            )
                        elif kind == "failed":
                            self.failed.emit(
                                str(payload.get("user_message", "对接失败。")),
                                str(payload.get("suggestion", "")),
                            )
                            return
                    continue

                if proc.poll() is not None:
                    break

            if result is not None and proc.returncode == 0:
                self.finished_ok.emit(result)
                return

            detail = "\n".join(output_tail[-6:]).strip()
            self.failed.emit(
                "对接子进程异常退出。",
                detail or "请检查输入文件和对接参数后重试。",
            )
        except InterruptedError:
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"对接失败：{exc}", "请检查参数与输入文件后重试。")
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
            try:
                cfg_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _write_config_json(self) -> Path:
        payload = {
            "receptor_pdbqt": str(self.config.receptor_pdbqt),
            "ligand_pdbqt": str(self.config.ligand_pdbqt),
            "center": list(self.config.center),
            "size": list(self.config.size),
            "pocket_source": self.config.pocket_source,
            "exhaustiveness": self.config.exhaustiveness,
            "num_modes": self.config.num_modes,
            "energy_range": self.config.energy_range,
            "seed": self.config.seed,
            "cpu": self.config.cpu,
        }
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix="_dockmeow_docking.json",
            delete=False,
        )
        with handle:
            json.dump(payload, handle)
        return Path(handle.name)

    @staticmethod
    def _parse_child_payload(line: str) -> dict | None:
        if not line.startswith("{"):
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
