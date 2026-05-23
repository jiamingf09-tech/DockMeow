"""License file verification — RSA-2048 PSS signature + machine binding + expiry.

Verification order (all must pass):
    1. JSON parse
    2. RSA-2048 PSS signature over ``json.dumps(payload, sort_keys=True)``
    3. Machine binding:
       - New licenses: copyable ``machine_id`` must match exactly.
       - Legacy licenses: stored factors must match current machine (≥2/3 rule).
    4. Expiry: ``expires_at`` must be None or > time.time()

License file format (.dmlic) — UTF-8 JSON:
    {
        "license_id":  "...",        # UUID4
        "email":       "...",
        "type":        "trial" | "perpetual",
        "issued_at":   1234567890.0, # UNIX timestamp
        "expires_at":  1234567890.0, # UNIX timestamp or null
        "machine_id":  "DM-xxxxxxxx-yyyyyyyy-zzzzzzzz",
        "machine": {
            "mb":  "16hex",
            "cpu": "16hex",
            "mac": "16hex"
        },                          # legacy / optional
        "signature":   "base64-url-encoded PSS signature"
    }
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from dockmeow.core.exceptions import LicenseError
from dockmeow.utils.paths import app_data_dir

LICENSE_FILE: Path = app_data_dir() / "license.dmlic"


def _canonical(payload: dict) -> bytes:
    """Serialize the payload (without 'signature') for signing/verification."""
    data = {k: v for k, v in payload.items() if k != "signature"}
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


class LicenseVerifier:
    """Stateless verifier; load once per session."""

    def __init__(self) -> None:
        self._public_key = self._load_public_key()

    def _load_public_key(self):
        """Reconstruct the RSA public key from its three stored fragments."""
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        from dockmeow.licensing._keystore import _kp1, _kp2, _kp3

        pem = _kp1 + _kp2 + _kp3
        if not pem.strip():
            raise LicenseError(
                "Public key not configured (_keystore.py fragments are empty).",
                "许可证验证失败：系统未配置公钥。",
                "请联系技术支持。",
            )
        return load_pem_public_key(pem)

    def verify_signature(self, data: dict) -> bool:
        """Verify the RSA-2048 PSS signature on a license payload dict.

        Args:
            data: Full license dict including ``"signature"`` key.

        Returns:
            True if signature is valid.

        Raises:
            LicenseError: if signature is missing or invalid.
        """
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        sig_b64 = data.get("signature", "")
        if not sig_b64:
            raise LicenseError(
                "License missing signature field.",
                "许可证文件损坏（缺少签名）。",
                "请重新获取许可证文件。",
            )
        try:
            sig = base64.urlsafe_b64decode(sig_b64 + "==")
        except Exception as exc:
            raise LicenseError(
                f"Signature base64 decode failed: {exc}",
                "许可证签名格式错误。",
            ) from exc

        message = _canonical(data)
        try:
            self._public_key.verify(
                sig,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature as exc:
            raise LicenseError(
                "RSA-PSS signature verification failed.",
                "许可证签名无效，文件可能已被篡改。",
                "请联系客服重新获取许可证。",
            ) from exc

    def verify_machine(self, data: dict) -> bool:
        """Check machine binding.

        Args:
            data: Full license dict.

        Returns:
            True if machine matches.

        Raises:
            LicenseError: if machine does not match.
        """
        from dockmeow.licensing.machine import match_machine, match_machine_id

        stored_id = data.get("machine_id")
        if stored_id:
            matched = match_machine_id(str(stored_id))
        else:
            stored = data.get("machine", {})
            matched = match_machine(stored)

        if not matched:
            raise LicenseError(
                "Machine fingerprint mismatch.",
                "此许可证不适用于当前设备。",
                "如需换绑，请联系客服购买新许可证（老用户 5 折）。",
            )
        return True

    def verify_expiry(self, data: dict) -> bool:
        """Check license expiry.

        Args:
            data: Full license dict.

        Returns:
            True if license is still valid.

        Raises:
            LicenseError: if license has expired.
        """
        from dockmeow.licensing.time_guard import is_license_expired

        expires_at = data.get("expires_at")
        if is_license_expired(expires_at):
            raise LicenseError(
                f"License expired at {expires_at}.",
                "许可证已过期。",
                "请续费或联系客服获取新许可证。",
            )
        return True

    def load_and_verify(self, dmlic_path: Path | None = None) -> dict:
        """Load, parse and fully verify a .dmlic license file.

        Args:
            dmlic_path: Path to the .dmlic file; defaults to the installed location.

        Returns:
            The verified license payload dict.

        Raises:
            LicenseError: on any verification failure.
        """
        path = dmlic_path or LICENSE_FILE
        if not path.exists():
            raise LicenseError(
                f"License file not found: {path}",
                "未找到许可证文件，请先激活软件。",
                "将 .dmlic 文件复制到软件目录并重启。",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise LicenseError(
                f"License JSON parse failed: {exc}",
                "许可证文件已损坏，无法读取。",
                "请重新获取许可证文件。",
            ) from exc

        self.verify_signature(data)
        self.verify_machine(data)
        self.verify_expiry(data)
        return data


def activate(dmlic_path: Path) -> None:
    """Copy a .dmlic file to the app data directory and verify it.

    Args:
        dmlic_path: Path to the .dmlic file provided by the user.

    Raises:
        LicenseError: if the file fails verification.
    """
    import shutil

    verifier = LicenseVerifier()
    verifier.load_and_verify(dmlic_path)  # verify before copying

    dest = app_data_dir() / "license.dmlic"
    shutil.copy2(dmlic_path, dest)
