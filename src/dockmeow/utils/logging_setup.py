"""Application-wide logging configuration.

Log file location: ``<user_workspace>/logs/dockmeow_<date>.log``
Console handler:   WARNING+ (so terminal users see problems without noise)
File handler:      DEBUG+   (full technical details for support tickets)
Licensing handler: separate ``<user_workspace>/logs/licensing.log`` (DEBUG+)
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_dir: Path | None = None) -> None:
    """Configure root logger with rotating file handler and console handler.

    Args:
        log_dir: Directory for log files. Defaults to ``user_workspace()/logs``.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers on repeated calls (e.g. in tests)
    if root.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console: WARNING+ only
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir is None:
        from dockmeow.utils.paths import user_workspace
        log_dir = user_workspace() / "logs"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    # Main rotating file: DEBUG+, keep 7 days of daily files
    main_log = log_dir / "dockmeow.log"
    try:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            main_log, when="midnight", backupCount=7, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception:
        return

    # Licensing-specific file: all licensing module logs go here too
    lic_log = log_dir / "licensing.log"
    try:
        lic_handler = logging.handlers.TimedRotatingFileHandler(
            lic_log, when="midnight", backupCount=7, encoding="utf-8"
        )
        lic_handler.setLevel(logging.DEBUG)
        lic_handler.setFormatter(fmt)
        lic_handler.addFilter(_PrefixFilter("dockmeow.licensing"))
        root.addHandler(lic_handler)
    except Exception:
        return


class _PrefixFilter(logging.Filter):
    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(self.prefix)


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger.

    Args:
        name: Typically ``__name__`` of the calling module.
    """
    return logging.getLogger(name)
