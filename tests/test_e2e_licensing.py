"""End-to-end license lifecycle: keygen → issue → activate → verify → tamper → expire.

Covers the complete operator + user flow:
  1. Keypair already generated (private key on disk)
  2. Operator issues a perpetual license for this machine
  3. User activates the license (copies to app_data dir)
  4. Verification succeeds
  5. Tampering the payload → verification fails
  6. Signature stripped → verification fails
  7. Operator issues a trial license that is already expired
  8. Expired trial → verification fails with Chinese expiry message
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_PRIVATE_KEY = _REPO_ROOT / "dockmeow_private.pem"

# Add tools/ to path so issue_license importable
sys.path.insert(0, str(_REPO_ROOT / "tools"))


@pytest.fixture(scope="module")
def private_key_available():
    if not _PRIVATE_KEY.exists():
        pytest.skip("dockmeow_private.pem not found — run tools/generate_keypair.py")


@pytest.fixture(scope="module")
def machine_factors():
    from dockmeow.licensing.machine import get_machine_factors
    return get_machine_factors()


@pytest.fixture()
def issued_dir(tmp_path):
    d = tmp_path / "issued"
    d.mkdir()
    return d


@pytest.fixture()
def app_data(tmp_path):
    d = tmp_path / "app_data"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Step 1–4: perpetual license happy path
# ---------------------------------------------------------------------------


def test_e2e_issue_activate_verify(private_key_available, machine_factors, tmp_path):
    """Full flow: issue perpetual → activate → verify succeeds."""
    import issue_license as il

    # Step 2: Issue
    out = il.issue(
        license_type="perpetual",
        email="e2e@test.com",
        machine_factors=machine_factors,
        private_key_path=_PRIVATE_KEY,
    )
    assert out.exists(), "issue() did not create .dmlic file"
    data = json.loads(out.read_text())
    assert data["type"] == "perpetual"
    assert data["expires_at"] is None
    assert "signature" in data
    # license_no must be present and have DM-{YYYY}-{NNNNN} format
    assert "license_no" in data
    import re
    assert re.match(r"^DM-\d{4}-\d{5}$", data["license_no"]), (
        f"Unexpected license_no format: {data['license_no']!r}"
    )
    # filename must be based on license_no
    assert out.name == f"{data['license_no']}.dmlic"

    # Step 3: Activate (copy to app_data)
    app_data = tmp_path / "app_data"
    app_data.mkdir()
    with patch("dockmeow.licensing.verifier.app_data_dir", return_value=app_data):
        from dockmeow.licensing.verifier import activate
        activate(out)
    assert (app_data / "license.dmlic").exists()

    # Step 4: Verify — patch module-level LICENSE_FILE since it's set at import time
    from dockmeow.licensing import verifier as _verifier_mod
    installed = app_data / "license.dmlic"
    with patch.object(_verifier_mod, "LICENSE_FILE", installed):
        v = _verifier_mod.LicenseVerifier()
        result = v.load_and_verify()
    assert result["email"] == "e2e@test.com"
    assert result["type"] == "perpetual"


def test_e2e_issue_with_visible_machine_id(private_key_available, tmp_path, monkeypatch):
    """Full flow: issue from the single device ID shown in the app."""
    import issue_license as il

    machine_id = "DM-00000000-e345de8b-4ad5ebb9"
    monkeypatch.setattr("dockmeow.licensing.machine.get_machine_id", lambda: machine_id)

    out = il.issue(
        license_type="perpetual",
        email="single-code@test.com",
        machine_id=machine_id,
        private_key_path=_PRIVATE_KEY,
    )
    data = json.loads(out.read_text())
    assert data["machine_id"] == machine_id
    assert "machine" not in data

    app_data = tmp_path / "app_data"
    app_data.mkdir()
    with patch("dockmeow.licensing.verifier.app_data_dir", return_value=app_data):
        from dockmeow.licensing.verifier import activate
        activate(out)
    assert (app_data / "license.dmlic").exists()


# ---------------------------------------------------------------------------
# Step 5: tamper payload after signing → fail
# ---------------------------------------------------------------------------


def test_e2e_tampered_payload_fails(private_key_available, machine_factors, tmp_path):
    import issue_license as il

    out = il.issue(
        license_type="perpetual",
        email="tamper@test.com",
        machine_factors=machine_factors,
        private_key_path=_PRIVATE_KEY,
    )
    data = json.loads(out.read_text())
    data["email"] = "hacker@evil.com"
    out.write_text(json.dumps(data))

    from dockmeow.core.exceptions import LicenseError
    from dockmeow.licensing.verifier import LicenseVerifier
    v = LicenseVerifier()
    with pytest.raises(LicenseError):
        v.load_and_verify(out)


# ---------------------------------------------------------------------------
# Step 6: stripped signature → fail
# ---------------------------------------------------------------------------


def test_e2e_no_signature_fails(private_key_available, machine_factors, tmp_path):
    import issue_license as il

    out = il.issue(
        license_type="perpetual",
        email="nosig@test.com",
        machine_factors=machine_factors,
        private_key_path=_PRIVATE_KEY,
    )
    data = json.loads(out.read_text())
    del data["signature"]
    out.write_text(json.dumps(data))

    from dockmeow.core.exceptions import LicenseError
    from dockmeow.licensing.verifier import LicenseVerifier
    v = LicenseVerifier()
    with pytest.raises(LicenseError, match="signature"):
        v.load_and_verify(out)


# ---------------------------------------------------------------------------
# Step 7–8: trial license already expired → fail
# ---------------------------------------------------------------------------


def test_e2e_expired_trial_fails(private_key_available, machine_factors, tmp_path):
    import issue_license as il

    # Issue a trial with duration=0 by patching the duration constant
    with patch.object(il, "TRIAL_DURATION_SECONDS", -3600):  # already expired
        out = il.issue(
            license_type="trial",
            email="expired@test.com",
            machine_factors=machine_factors,
            private_key_path=_PRIVATE_KEY,
        )
    data = json.loads(out.read_text())
    assert data["expires_at"] is not None
    assert data["expires_at"] < time.time()
    assert data.get("license_no", "").startswith("DM-TRIAL-")

    from dockmeow.core.exceptions import LicenseError
    from dockmeow.licensing.verifier import LicenseVerifier
    v = LicenseVerifier()
    with pytest.raises(LicenseError, match="expired"):
        v.load_and_verify(out)


# ---------------------------------------------------------------------------
# Machine mismatch
# ---------------------------------------------------------------------------


def test_e2e_machine_mismatch_fails(private_key_available, machine_factors, tmp_path):
    import issue_license as il

    # Issue for wrong machine (2 factors changed)
    bad = dict(machine_factors)
    bad["mb"] = "0000000000000000"
    bad["mac"] = "1111111111111111"
    out = il.issue(
        license_type="perpetual",
        email="wrong@machine.com",
        machine_factors=bad,
        private_key_path=_PRIVATE_KEY,
    )

    from dockmeow.core.exceptions import LicenseError
    from dockmeow.licensing.verifier import LicenseVerifier
    v = LicenseVerifier()
    with pytest.raises(LicenseError, match="fingerprint"):
        v.load_and_verify(out)


# ---------------------------------------------------------------------------
# get_machine_id tool output format
# ---------------------------------------------------------------------------


def test_e2e_get_machine_id_output(capsys):
    """get_machine_id.py main() prints a DM-xxx banner."""
    sys.path.insert(0, str(_REPO_ROOT / "tools"))
    import get_machine_id as gmi
    with patch.object(gmi, "_pause"):  # skip interactive pause
        gmi.main()
    captured = capsys.readouterr()
    assert "DM-" in captured.out
    assert "mb=" in captured.out
    assert "cpu=" in captured.out
    assert "mac=" in captured.out
