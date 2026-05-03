"""Standalone tool for users — collect and display the machine fingerprint.

Compiled separately with PyInstaller into a small standalone executable.
When run, it shows a console banner with the machine ID string and full
factor details.  The "press any key to exit" pause prevents the console
window from closing before the user can read it (crucial on Windows).

Usage:
    python tools/get_machine_id.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly without installing the package
_src = Path(__file__).parent.parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))


def main() -> None:
    """Print or display the machine fingerprint."""
    try:
        from dockmeow.licensing.machine import get_machine_factors, get_machine_id
    except ImportError as exc:
        print(f"ERROR: Cannot import dockmeow: {exc}")
        _pause()
        sys.exit(1)

    mid     = get_machine_id()
    factors = get_machine_factors()

    mb  = factors.get("mb")  or "(采集失败)"
    cpu = factors.get("cpu") or "(采集失败)"
    mac = factors.get("mac") or "(采集失败)"

    banner = f"""
============================================
  DockMeow 机器指纹
============================================
  指纹 ID:  {mid}

  完整因子（请发送以下内容给客服）:
    mb={mb}
    cpu={cpu}
    mac={mac}
============================================
"""
    print(banner)
    _pause()


def _pause() -> None:
    """Wait for a keypress so the console stays open on Windows double-click."""
    try:
        if sys.platform == "win32":
            import msvcrt
            print("[按任意键退出]")
            msvcrt.getch()
        else:
            input("[按 Enter 键退出]")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
