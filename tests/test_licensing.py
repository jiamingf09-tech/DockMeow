"""Tests for licensing.verifier — full license verification pipeline."""

from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from dockmeow.core.exceptions import LicenseError
from dockmeow.licensing.machine import get_machine_factors
from dockmeow.licensing.verifier import LicenseVerifier, _canonical, activate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRIVATE_KEY_PATH = Path(__file__).parent.parent / "dockmeow_private.pem"


def _load_private_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    if not _PRIVATE_KEY_PATH.exists():
        pytest.skip("dockmeow_private.pem not found — run tools/generate_keypair.py")
    return load_pem_private_key(_PRIVATE_KEY_PATH.read_bytes(), password=None)


def _sign(private_key, payload: dict) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    message = _canonical(payload)
    sig = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def _make_payload(
    factors: dict | None = None,
    expires_at: float | None = None,
    license_type: str = "perpetual",
) -> dict:
    """Build a properly signed payload for this machine."""
    if factors is None:
        factors = get_machine_factors()
    payload: dict = {
        "license_id": str(uuid.uuid4()),
        "email":      "test@example.com",
        "type":       license_type,
        "issued_at":  time.time(),
        "expires_at": expires_at,
        "machine":    factors,
    }
    pk = _load_private_key()
    payload["signature"] = _sign(pk, payload)
    return payload


def _write_dmlic(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / f"{payload['license_id']}.dmlic"
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLicenseVerifier:
    def test_valid_perpetual_license_passes(self, tmp_path):
        payload = _make_payload(license_type="perpetual")
        path = _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        result = v.load_and_verify(path)
        assert result["type"] == "perpetual"

    def test_valid_trial_license_passes(self, tmp_path):
        payload = _make_payload(
            license_type="trial", expires_at=time.time() + 3600
        )
        path = _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        result = v.load_and_verify(path)
        assert result["type"] == "trial"

    def test_tampered_signature_raises(self, tmp_path):
        payload = _make_payload()
        payload["signature"] = "AAAAAAAAAAAAAAAAAAAAAA"
        path = _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        with pytest.raises(LicenseError, match="signature"):
            v.load_and_verify(path)

    def test_tampered_field_raises(self, tmp_path):
        payload = _make_payload()
        path = _write_dmlic(tmp_path, payload)
        # Modify after signing — signature no longer valid
        data = json.loads(path.read_text())
        data["email"] = "hacker@evil.com"
        path.write_text(json.dumps(data))
        v = LicenseVerifier()
        with pytest.raises(LicenseError):
            v.load_and_verify(path)

    def test_expired_trial_raises(self, tmp_path):
        payload = _make_payload(license_type="trial", expires_at=time.time() - 1)
        path = _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        with pytest.raises(LicenseError, match="expired"):
            v.load_and_verify(path)

    def test_machine_mismatch_raises(self, tmp_path):
        """Modify 2 of 3 machine factors → should fail (only 1 match)."""
        current = get_machine_factors()
        bad_factors = dict(current)
        bad_factors["mb"] = "0000000000000000"
        bad_factors["mac"] = "1111111111111111"
        payload = _make_payload(factors=bad_factors)
        path = _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        with pytest.raises(LicenseError, match="fingerprint"):
            v.load_and_verify(path)

    def test_one_factor_mismatch_passes(self, tmp_path):
        """Modify only 1 of 3 machine factors → should still pass (2/3 rule)."""
        current = get_machine_factors()
        one_off = dict(current)
        one_off["mb"] = "0000000000000000"
        payload = _make_payload(factors=one_off)
        path = _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        result = v.load_and_verify(path)
        assert result is not None

    def test_corrupted_json_raises(self, tmp_path):
        path = tmp_path / "bad.dmlic"
        path.write_text("{not valid json!!!", encoding="utf-8")
        v = LicenseVerifier()
        with pytest.raises(LicenseError, match="parse failed"):
            v.load_and_verify(path)

    def test_missing_file_raises(self, tmp_path):
        path = tmp_path / "nonexistent.dmlic"
        v = LicenseVerifier()
        with pytest.raises(LicenseError, match="not found"):
            v.load_and_verify(path)

    def test_missing_signature_raises(self, tmp_path):
        payload = _make_payload()
        del payload["signature"]
        _write_dmlic(tmp_path, payload)
        v = LicenseVerifier()
        with pytest.raises(LicenseError, match="missing signature"):
            v.verify_signature(payload)


class TestActivate:
    def test_activate_copies_file_to_app_data(self, tmp_path):
        payload = _make_payload()
        src = _write_dmlic(tmp_path, payload)
        dest_dir = tmp_path / "app_data"
        dest_dir.mkdir()
        with patch("dockmeow.licensing.verifier.app_data_dir", return_value=dest_dir):
            activate(src)
        assert (dest_dir / "license.dmlic").exists()

    def test_activate_invalid_raises_and_does_not_copy(self, tmp_path):
        payload = _make_payload()
        payload["signature"] = "invalidsig"
        src = _write_dmlic(tmp_path, payload)
        dest_dir = tmp_path / "app_data"
        dest_dir.mkdir()
        with patch("dockmeow.licensing.verifier.app_data_dir", return_value=dest_dir):
            with pytest.raises(LicenseError):
                activate(src)
        assert not (dest_dir / "license.dmlic").exists()


class TestCanonical:
    def test_excludes_signature_key(self):
        payload = {"a": 1, "signature": "xyz", "b": 2}
        result = _canonical(payload)
        data = json.loads(result.decode())
        assert "signature" not in data
        assert data == {"a": 1, "b": 2}

    def test_output_is_sorted(self):
        payload = {"z": 3, "a": 1, "m": 2}
        result = _canonical(payload).decode()
        keys = [k for k in ["a", "m", "z"] if k in result]
        positions = [result.index(f'"{k}"') for k in keys]
        assert positions == sorted(positions)
