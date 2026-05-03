"""Encrypted local state file for persisting the time anchor and activation flags.

Storage: ``<app_data_dir>/.dms``  (dot-prefixed to reduce casual visibility)

Encryption: AES-256-GCM with a key derived from the machine fingerprint + a fixed
application salt.  The salt is NOT secret (it's in the source), but it ensures
the derived key is specific to DockMeow, not just the machine fingerprint bytes.
Because the key is machine-bound, the state file cannot be moved to another
machine to reset the time anchor.

Key derivation:
    HKDF-SHA256(ikm=machine_id_bytes, salt=APP_SALT, info=b"dockmeow-state-v1",
                length=32)

Format on disk: 12-byte random nonce || GCM ciphertext+tag (16 extra bytes).
Plaintext: UTF-8 JSON object.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dockmeow.utils.paths import app_data_dir

_log = logging.getLogger(__name__)

_STATE_FILENAME = ".dms"
_APP_SALT = b"dockmeow-v1-salt-2024"


def _derive_key() -> bytes:
    """Derive a 32-byte AES key from the current machine's identity."""
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from dockmeow.licensing.machine import get_machine_id

    ikm = get_machine_id().encode("utf-8")
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=_APP_SALT,
        info=b"dockmeow-state-v1",
    )
    return hkdf.derive(ikm)


def _state_path() -> Path:
    return app_data_dir() / _STATE_FILENAME


def load_state() -> dict:
    """Read and decrypt the local state file.

    Returns:
        Parsed state dict, or ``{}`` if the file does not exist or decryption fails
        (e.g., file was tampered with or the machine was changed).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    path = _state_path()
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
        if len(raw) < 12 + 16:
            return {}
        nonce = raw[:12]
        ciphertext = raw[12:]
        key = _derive_key()
        aes = AESGCM(key)
        plaintext = aes.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        _log.debug("State file load failed (treating as empty): %s", exc)
        return {}


def save_state(state: dict) -> None:
    """Encrypt and write the state dict to disk.

    Args:
        state: Arbitrary JSON-serialisable dict.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        plaintext = json.dumps(state, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(12)
        key = _derive_key()
        aes = AESGCM(key)
        ciphertext = aes.encrypt(nonce, plaintext, None)
        _state_path().write_bytes(nonce + ciphertext)
    except Exception as exc:
        _log.warning("State file save failed: %s", exc)
