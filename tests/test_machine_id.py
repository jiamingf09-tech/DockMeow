"""Tests for licensing.machine — machine fingerprinting."""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from dockmeow.licensing.machine import (
    _factor_cpu,
    _factor_mac,
    _factor_motherboard,
    _hash16,
    get_machine_factors,
    get_machine_id,
    match_machine,
)

_HEX16 = re.compile(r"^[0-9a-f]{16}$")


class TestHash16:
    def test_empty_returns_empty(self):
        assert _hash16("") == ""

    def test_nonempty_returns_16_hex(self):
        result = _hash16("hello")
        assert _HEX16.match(result), f"Not 16 hex chars: {result!r}"

    def test_deterministic(self):
        assert _hash16("x") == _hash16("x")

    def test_different_inputs_different_outputs(self):
        assert _hash16("a") != _hash16("b")


class TestGetMachineFactors:
    def test_returns_three_keys(self):
        f = get_machine_factors()
        assert set(f.keys()) == {"mb", "cpu", "mac"}

    def test_values_are_16_char_hex_or_empty(self):
        f = get_machine_factors()
        for key, val in f.items():
            assert val == "" or _HEX16.match(val), (
                f"factor {key!r} has unexpected value {val!r}"
            )

    def test_deterministic_across_calls(self):
        """Two consecutive calls return identical factors."""
        assert get_machine_factors() == get_machine_factors()

    def test_cpu_factor_never_empty(self):
        """CPU factor should always succeed (uses stdlib only)."""
        f = get_machine_factors()
        assert f["cpu"] != "", "cpu factor should always be collectible"


class TestMatchMachine:
    @pytest.fixture()
    def current(self):
        return get_machine_factors()

    def test_exact_match_passes(self, current):
        assert match_machine(current) is True

    def test_two_of_three_match_passes(self, current):
        stored = dict(current)
        stored["mb"] = "0000000000000000"
        assert match_machine(stored) is True

    def test_one_of_three_match_fails(self, current):
        stored = dict(current)
        stored["mb"] = "0000000000000000"
        stored["cpu"] = "1111111111111111"
        assert match_machine(stored) is False

    def test_zero_match_fails(self, current):
        stored = {"mb": "aaaaaaaaaaaaaaaa", "cpu": "bbbbbbbbbbbbbbbb", "mac": "cccccccccccccccc"}
        assert match_machine(stored) is False

    def test_empty_stored_factors_returns_false(self):
        assert match_machine({}) is False

    def test_single_factor_stored_passes_when_matching(self):
        """If only one factor is stored and it matches, compared==1 → min(2,1)=1 match needed."""
        current = get_machine_factors()
        stored = {"cpu": current["cpu"]}
        assert match_machine(stored) is True

    def test_single_factor_stored_fails_when_mismatching(self):
        stored = {"cpu": "0000000000000000"}
        assert match_machine(stored) is False


class TestPlatformFactors:
    """Test Windows and Linux code paths by mocking sys.platform and subprocess."""

    # --- Motherboard ---

    def test_motherboard_windows(self):
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.subprocess.check_output",
                  return_value=b"UUID\r\n12345678-ABCD-EF01-2345-6789ABCDEF01\r\n"),
        ):
            mock_sys.platform = "win32"
            result = _factor_motherboard()
        assert "12345678" in result

    def test_motherboard_linux_machine_id(self, tmp_path):
        machine_id = "abc123def456789012345678"
        fake_machine_id = tmp_path / "machine-id"
        fake_machine_id.write_text(machine_id)
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.Path") as mock_path_cls,
        ):
            mock_sys.platform = "linux"
            mock_instance = mock_path_cls.return_value
            mock_instance.exists.return_value = True
            mock_instance.read_text.return_value = machine_id + "\n"
            result = _factor_motherboard()
        assert result == machine_id

    def test_motherboard_subprocess_error_returns_empty(self):
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.subprocess.check_output",
                  side_effect=Exception("subprocess failed")),
        ):
            mock_sys.platform = "darwin"
            result = _factor_motherboard()
        assert result == ""

    # --- CPU fallback ---

    def test_cpu_exception_returns_empty(self):
        with patch("dockmeow.licensing.machine.platform") as mock_plat:
            mock_plat.processor.side_effect = Exception("no cpu")
            result = _factor_cpu()
        assert result == ""

    # --- MAC address ---

    def test_mac_windows(self):
        csv_output = b'"AA-BB-CC-DD-EE-FF","Media disconnected"\r\n'
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.subprocess.check_output",
                  return_value=csv_output),
        ):
            mock_sys.platform = "win32"
            result = _factor_mac()
        assert result == "aabbccddeeff"

    def test_mac_linux_sysfs(self, tmp_path):
        net_dir = tmp_path / "net"
        eth0 = net_dir / "eth0"
        eth0.mkdir(parents=True)
        (eth0 / "address").write_text("02:11:22:33:44:55\n")
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.Path", return_value=net_dir),
        ):
            mock_sys.platform = "linux"
            # Can't easily mock Path("/sys/class/net") via patching Path itself
            # so test via direct call with mocked net_dir iteration
        # Instead test the linux path via sys.platform + real filesystem mock
        import dockmeow.licensing.machine as m_mod
        with (
            patch.object(m_mod, "sys") as mock_sys,
        ):
            mock_sys.platform = "linux"
            with patch("dockmeow.licensing.machine.Path") as mock_path_cls:
                mock_net = mock_path_cls.return_value
                mock_net.exists.return_value = True
                mock_iface = type("Iface", (), {
                    "name": "eth0",
                    "startswith": lambda self, x: False,
                })()
                addr_file = type("AF", (), {
                    "exists": lambda self: True,
                    "read_text": lambda self: "02:11:22:33:44:55\n",
                })()
                mock_iface.__truediv__ = lambda self, x: addr_file
                mock_net.__iter__ = lambda self: iter([mock_iface])
                result = _factor_mac()
            assert result != ""

    def test_mac_all_paths_fail_uses_uuid_node(self):
        # ifconfig returns output with no valid ether line → falls through to uuid.getnode
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.subprocess.check_output",
                  return_value=b"lo0: flags=8049<UP,LOOPBACK> mtu 16384\n\n"),
            patch("dockmeow.licensing.machine.uuid") as mock_uuid,
        ):
            mock_sys.platform = "darwin"
            mock_uuid.getnode.return_value = 0x123456789ABC
            result = _factor_mac()
        assert result == "123456789abc"

    def test_mac_exception_returns_empty(self):
        with (
            patch("dockmeow.licensing.machine.sys") as mock_sys,
            patch("dockmeow.licensing.machine.subprocess.check_output",
                  side_effect=OSError("fail")),
            patch("dockmeow.licensing.machine.uuid") as mock_uuid,
        ):
            mock_sys.platform = "darwin"
            mock_uuid.getnode.side_effect = Exception("uuid fail")
            result = _factor_mac()
        assert result == ""


class TestMachineIdFull:
    def test_format_is_dm_prefix(self):
        mid = get_machine_id()
        assert mid.startswith("DM-"), f"Expected DM- prefix, got {mid!r}"

    def test_format_has_three_segments(self):
        mid = get_machine_id()
        parts = mid.split("-")
        assert len(parts) == 4, f"Expected DM-xxx-yyy-zzz, got {mid!r}"
        assert parts[0] == "DM"
        for seg in parts[1:]:
            assert len(seg) == 8, f"Segment {seg!r} should be 8 chars"

    def test_deterministic(self):
        assert get_machine_id() == get_machine_id()

    def test_fallback_zeros_on_empty_factors(self):
        """If all factors return empty, id should use 00000000 placeholders."""
        with (
            patch("dockmeow.licensing.machine._factor_motherboard", return_value=""),
            patch("dockmeow.licensing.machine._factor_cpu", return_value=""),
            patch("dockmeow.licensing.machine._factor_mac", return_value=""),
        ):
            mid = get_machine_id()
        assert mid == "DM-00000000-00000000-00000000"
