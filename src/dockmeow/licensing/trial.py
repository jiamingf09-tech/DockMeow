"""Offline trial-use tracking for unlicensed sessions.

A fresh install gets MAX_FREE_DOCKINGS free docking runs and TRIAL_DAYS days
from first launch.  Both limits must hold simultaneously — whichever expires
first ends the trial.

State is stored in the machine-bound encrypted .dms file (state.py) so it
cannot be trivially reset by deleting a plain-text file.  The clock-rollback
guard in time_guard.py further protects the time-based limit.

Public API
----------
get_trial_status() -> TrialStatus
    Read-only snapshot: remaining uses, days remaining, whether trial is valid.

consume_docking_run() -> TrialStatus
    Decrement the use counter.  Call AFTER a successful docking run.
    Returns the updated status.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_FREE_DOCKINGS: int = 5
TRIAL_DAYS: int = 14

# ── State keys ────────────────────────────────────────────────────────────────
_KEY_FIRST_LAUNCH = "trial_first_launch"
_KEY_USES_CONSUMED = "trial_uses_consumed"


@dataclass(frozen=True)
class TrialStatus:
    """Snapshot of trial state."""

    uses_remaining: int          # ≥ 0
    days_remaining: float        # may be negative (expired)
    uses_expired: bool
    time_expired: bool

    @property
    def is_valid(self) -> bool:
        """True when the user may still run a docking without a license."""
        return not self.uses_expired and not self.time_expired

    @property
    def summary_zh(self) -> str:
        """Short Chinese description for the status bar."""
        if self.uses_expired:
            return "试用次数已用完，请激活软件继续使用。"
        if self.time_expired:
            return f"试用期（{TRIAL_DAYS} 天）已结束，请激活软件继续使用。"
        days = max(0, int(self.days_remaining))
        return (
            f"试用模式 — 剩余 {self.uses_remaining} 次对接 / "
            f"{days} 天"
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load() -> dict:
    from dockmeow.licensing.state import load_state
    return load_state()


def _save(state: dict) -> None:
    from dockmeow.licensing.state import save_state
    save_state(state)


def _ensure_first_launch(state: dict) -> dict:
    """Record first-launch timestamp if not already set."""
    if _KEY_FIRST_LAUNCH not in state:
        state[_KEY_FIRST_LAUNCH] = time.time()
        _save(state)
    return state


# ── Public API ────────────────────────────────────────────────────────────────

def get_trial_status() -> TrialStatus:
    """Return a read-only snapshot of the current trial state."""
    state = _load()
    state = _ensure_first_launch(state)

    consumed: int = int(state.get(_KEY_USES_CONSUMED, 0))
    uses_remaining = max(0, MAX_FREE_DOCKINGS - consumed)
    uses_expired = uses_remaining == 0

    first_launch: float = float(state.get(_KEY_FIRST_LAUNCH, time.time()))
    elapsed_days = (time.time() - first_launch) / 86400.0
    days_remaining = TRIAL_DAYS - elapsed_days
    time_expired = days_remaining <= 0

    return TrialStatus(
        uses_remaining=uses_remaining,
        days_remaining=days_remaining,
        uses_expired=uses_expired,
        time_expired=time_expired,
    )


def consume_docking_run() -> TrialStatus:
    """Decrement the trial use counter by one and persist.

    Call this AFTER a docking run completes successfully so that a crash
    or error does not unfairly consume a use.

    Returns:
        Updated TrialStatus.
    """
    state = _load()
    state = _ensure_first_launch(state)

    consumed = int(state.get(_KEY_USES_CONSUMED, 0))
    state[_KEY_USES_CONSUMED] = consumed + 1
    _save(state)

    return get_trial_status()


def reset_trial_for_testing() -> None:  # pragma: no cover
    """Development helper — erase trial counters.  Never call in production."""
    from dockmeow.licensing.state import load_state, save_state
    state = load_state()
    state.pop(_KEY_FIRST_LAUNCH, None)
    state.pop(_KEY_USES_CONSUMED, None)
    save_state(state)
