"""Tests for licensing.time_guard — clock rollback detection."""

from __future__ import annotations

import time
from unittest.mock import patch


class TestCheckClockIntegrity:
    # time_guard uses lazy imports inside functions, so we patch at the state module.

    def test_no_anchor_passes(self):
        """First run (no state file) should always pass."""
        with patch("dockmeow.licensing.state.load_state", return_value={}):
            from dockmeow.licensing.time_guard import check_clock_integrity
            ok, msg = check_clock_integrity()
        assert ok is True
        assert msg == ""

    def test_normal_forward_time_passes(self):
        anchor = time.time() - 3600  # anchor 1 hour in the past → normal
        with patch("dockmeow.licensing.state.load_state",
                   return_value={"time_anchor": anchor}):
            from dockmeow.licensing.time_guard import check_clock_integrity
            ok, msg = check_clock_integrity()
        assert ok is True
        assert msg == ""

    def test_rollback_within_tolerance_passes(self):
        """A rollback of < CLOCK_TOLERANCE_SECONDS should pass."""
        from dockmeow.licensing.time_guard import CLOCK_TOLERANCE_SECONDS
        fake_now = time.time()
        anchor = fake_now + CLOCK_TOLERANCE_SECONDS - 1
        with (
            patch("dockmeow.licensing.state.load_state",
                  return_value={"time_anchor": anchor}),
            patch("dockmeow.licensing.time_guard.time") as mock_time,
        ):
            mock_time.time.return_value = fake_now
            from dockmeow.licensing.time_guard import check_clock_integrity
            ok, msg = check_clock_integrity()
        assert ok is True

    def test_large_rollback_fails(self):
        """A rollback of > CLOCK_TOLERANCE_SECONDS returns (False, message)."""
        from dockmeow.licensing.time_guard import CLOCK_TOLERANCE_SECONDS
        fake_now = time.time()
        anchor = fake_now + CLOCK_TOLERANCE_SECONDS + 100
        with (
            patch("dockmeow.licensing.state.load_state",
                  return_value={"time_anchor": anchor}),
            patch("dockmeow.licensing.time_guard.time") as mock_time,
        ):
            mock_time.time.return_value = fake_now
            from dockmeow.licensing.time_guard import check_clock_integrity
            ok, msg = check_clock_integrity()
        assert ok is False
        assert msg != ""

    def test_failure_message_is_chinese(self):
        from dockmeow.licensing.time_guard import CLOCK_TOLERANCE_SECONDS
        fake_now = time.time()
        anchor = fake_now + CLOCK_TOLERANCE_SECONDS + 100
        with (
            patch("dockmeow.licensing.state.load_state",
                  return_value={"time_anchor": anchor}),
            patch("dockmeow.licensing.time_guard.time") as mock_time,
        ):
            mock_time.time.return_value = fake_now
            from dockmeow.licensing.time_guard import check_clock_integrity
            _, msg = check_clock_integrity()
        assert any("一" <= ch <= "鿿" for ch in msg), (
            f"Expected Chinese in message, got: {msg!r}"
        )


class TestUpdateTimeAnchor:
    def test_anchor_advances_monotonically(self):
        saved = {}

        def fake_load():
            return dict(saved)

        def fake_save(state):
            saved.update(state)

        with (
            patch("dockmeow.licensing.state.load_state", side_effect=fake_load),
            patch("dockmeow.licensing.state.save_state", side_effect=fake_save),
        ):
            from dockmeow.licensing.time_guard import update_time_anchor
            update_time_anchor()
            first = saved.get("time_anchor", 0.0)
            time.sleep(0.01)
            update_time_anchor()
            second = saved.get("time_anchor", 0.0)
        assert second >= first

    def test_anchor_does_not_regress(self):
        """Calling update with an earlier time must not lower the stored anchor."""
        future_anchor = time.time() + 1000
        saved = {"time_anchor": future_anchor}

        def fake_load():
            return dict(saved)

        def fake_save(state):
            saved.update(state)

        with (
            patch("dockmeow.licensing.state.load_state", side_effect=fake_load),
            patch("dockmeow.licensing.state.save_state", side_effect=fake_save),
        ):
            from dockmeow.licensing.time_guard import update_time_anchor
            update_time_anchor()  # current time < future_anchor → should not save
        # save_state was never called, so saved still has the original future_anchor
        assert saved.get("time_anchor") == future_anchor


class TestIsLicenseExpired:
    def test_perpetual_never_expires(self):
        from dockmeow.licensing.time_guard import is_license_expired
        assert is_license_expired(None) is False

    def test_future_expires_at_not_expired(self):
        from dockmeow.licensing.time_guard import is_license_expired
        future = time.time() + 9999
        assert is_license_expired(future) is False

    def test_past_expires_at_is_expired(self):
        from dockmeow.licensing.time_guard import is_license_expired
        past = time.time() - 1
        assert is_license_expired(past) is True

    def test_zero_expires_at_is_expired(self):
        from dockmeow.licensing.time_guard import is_license_expired
        assert is_license_expired(0.0) is True
