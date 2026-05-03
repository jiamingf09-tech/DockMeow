"""Entry point: ``python -m dockmeow`` launches the GUI application."""

from __future__ import annotations

import sys


def main() -> None:
    from dockmeow.app import run

    sys.exit(run())


if __name__ == "__main__":
    main()
