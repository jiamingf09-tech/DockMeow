"""Clock-rollback detection and trial expiry enforcement.

Strategy:
    After every significant operation the current ``time.time()`` is persisted
    to the encrypted state file via ``update_time_anchor()``.
    On startup and before docking, ``check_clock_integrity()`` compares
    ``time.time()`` against the stored maximum.  A rollback greater than
    CLOCK_TOLERANCE_SECONDS is flagged as an anomaly and the application freezes.

Tolerance: 3 600 s (1 hour) to accommodate DST transitions and time-zone changes.
"""

from __future__ import annotations

import time

CLOCK_TOLERANCE_SECONDS: int = 3600
_ANCHOR_KEY = "time_anchor"


def update_time_anchor() -> None:
    """Persist the current timestamp as the new high-water mark.

    Call after every successful operation (receptor prep, ligand prep, docking).
    Only advances the anchor — never moves it backward.
    """
    from dockmeow.licensing.state import load_state, save_state

    state = load_state()
    current = time.time()
    existing = state.get(_ANCHOR_KEY, 0.0)
    if current > existing:
        state[_ANCHOR_KEY] = current
        save_state(state)


def check_clock_integrity() -> tuple[bool, str]:
    """Detect system clock rollback.

    Returns:
        (ok, message) — ok=True means no anomaly; message is empty in that case.
        ok=False with a Chinese message string when rollback detected.
    """
    from dockmeow.licensing.state import load_state

    state = load_state()
    anchor = state.get(_ANCHOR_KEY)
    if anchor is None:
        return True, ""

    current = time.time()
    delta = anchor - current
    if delta > CLOCK_TOLERANCE_SECONDS:
        msg = (
            f"检测到系统时钟异常（回拨 {int(delta)} 秒）。"
            "请确认系统时间正确后重启软件。"
        )
        return False, msg
    return True, ""


def is_license_expired(expires_at: float | None) -> bool:
    """Check whether a license has passed its expiry timestamp.

    Args:
        expires_at: UNIX timestamp of expiry, or ``None`` for perpetual.

    Returns:
        True if the license has expired; False otherwise.
    """
    if expires_at is None:
        return False
    return time.time() > expires_at
