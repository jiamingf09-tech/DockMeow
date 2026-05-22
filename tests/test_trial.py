"""Unit tests for the offline trial-use tracking system (trial.py)."""

from __future__ import annotations

import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(*, consumed: int = 0, first_launch: float | None = None) -> dict:
    """Build a minimal state dict as if loaded from .dms."""
    state: dict = {"trial_uses_consumed": consumed}
    if first_launch is not None:
        state["trial_first_launch"] = first_launch
    return state


# ---------------------------------------------------------------------------
# TrialStatus dataclass
# ---------------------------------------------------------------------------

class TestTrialStatus:
    def _make(self, uses_remaining=3, days_remaining=10.0,
               uses_expired=False, time_expired=False):
        from dockmeow.licensing.trial import TrialStatus
        return TrialStatus(
            uses_remaining=uses_remaining,
            days_remaining=days_remaining,
            uses_expired=uses_expired,
            time_expired=time_expired,
        )

    def test_is_valid_when_both_ok(self):
        ts = self._make()
        assert ts.is_valid

    def test_invalid_when_uses_expired(self):
        ts = self._make(uses_expired=True)
        assert not ts.is_valid

    def test_invalid_when_time_expired(self):
        ts = self._make(time_expired=True)
        assert not ts.is_valid

    def test_invalid_when_both_expired(self):
        ts = self._make(uses_expired=True, time_expired=True)
        assert not ts.is_valid

    def test_summary_shows_remaining_uses_and_days(self):
        ts = self._make(uses_remaining=3, days_remaining=7.9)
        summary = ts.summary_zh
        assert "3" in summary
        assert "7" in summary

    def test_summary_uses_expired_message(self):
        ts = self._make(uses_expired=True)
        assert "用完" in ts.summary_zh

    def test_summary_time_expired_message(self):
        ts = self._make(time_expired=True)
        assert "结束" in ts.summary_zh


# ---------------------------------------------------------------------------
# get_trial_status()
# ---------------------------------------------------------------------------

class TestGetTrialStatus:
    def test_fresh_install_has_max_uses(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        ts = trial_mod.get_trial_status()
        assert ts.uses_remaining == trial_mod.MAX_FREE_DOCKINGS
        assert ts.days_remaining > 0
        assert ts.is_valid

    def test_consumed_uses_reduce_remaining(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        # Pre-seed state with 3 consumed uses
        state = _make_state(consumed=3, first_launch=time.time())
        state_mod.save_state(state)

        ts = trial_mod.get_trial_status()
        assert ts.uses_remaining == trial_mod.MAX_FREE_DOCKINGS - 3

    def test_all_uses_consumed_marks_uses_expired(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        state = _make_state(consumed=trial_mod.MAX_FREE_DOCKINGS,
                             first_launch=time.time())
        state_mod.save_state(state)

        ts = trial_mod.get_trial_status()
        assert ts.uses_remaining == 0
        assert ts.uses_expired
        assert not ts.is_valid

    def test_old_first_launch_marks_time_expired(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        # First launch was TRIAL_DAYS + 1 day ago
        old_ts = time.time() - (trial_mod.TRIAL_DAYS + 1) * 86400
        state = _make_state(consumed=0, first_launch=old_ts)
        state_mod.save_state(state)

        ts = trial_mod.get_trial_status()
        assert ts.time_expired
        assert ts.days_remaining < 0
        assert not ts.is_valid


# ---------------------------------------------------------------------------
# consume_docking_run()
# ---------------------------------------------------------------------------

class TestConsumeDockingRun:
    def test_consume_decrements_remaining(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        before = trial_mod.get_trial_status()
        after = trial_mod.consume_docking_run()

        assert after.uses_remaining == before.uses_remaining - 1

    def test_consume_five_times_exhausts_trial(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        # Initialize
        trial_mod.get_trial_status()

        for _ in range(trial_mod.MAX_FREE_DOCKINGS):
            ts = trial_mod.consume_docking_run()

        assert ts.uses_remaining == 0
        assert ts.uses_expired
        assert not ts.is_valid

    def test_consume_beyond_max_does_not_go_negative(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        state = _make_state(consumed=trial_mod.MAX_FREE_DOCKINGS + 10,
                             first_launch=time.time())
        state_mod.save_state(state)

        ts = trial_mod.get_trial_status()
        assert ts.uses_remaining == 0

    def test_consume_persists_across_reload(self, tmp_path, monkeypatch):
        from dockmeow.licensing import state as state_mod
        from dockmeow.licensing import trial as trial_mod

        monkeypatch.setattr(state_mod, "_state_path", lambda: tmp_path / ".dms")
        monkeypatch.setattr(trial_mod, "_load", state_mod.load_state)
        monkeypatch.setattr(trial_mod, "_save", state_mod.save_state)

        trial_mod.get_trial_status()   # init first_launch
        trial_mod.consume_docking_run()
        trial_mod.consume_docking_run()

        # Re-check from fresh load
        ts2 = trial_mod.get_trial_status()
        assert ts2.uses_remaining == trial_mod.MAX_FREE_DOCKINGS - 2
