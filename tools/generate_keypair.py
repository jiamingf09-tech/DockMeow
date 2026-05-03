"""Developer tool — generate RSA-2048 key pair for license signing.

Outputs:
    dockmeow_private.pem  — KEEP SECRET, never commit to git
    dockmeow_public.pem   — for reference only
    Patches _keystore.py  — splits public key into 3 fragments at random byte offsets

Usage:
    python tools/generate_keypair.py

WARNING: Running this again invalidates all previously issued licenses.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_KEYSTORE  = _REPO_ROOT / "src" / "dockmeow" / "licensing" / "_keystore.py"
_PRIVATE   = _REPO_ROOT / "dockmeow_private.pem"
_PUBLIC    = _REPO_ROOT / "dockmeow_public.pem"


def generate_and_save() -> None:
    """Generate the key pair, save private key, patch _keystore.py."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    print("Generating RSA-2048 key pair…")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    # Save private key (PEM, no passphrase — operator keeps it safe)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _PRIVATE.write_bytes(priv_pem)
    print(f"  Private key → {_PRIVATE}  (NEVER commit this file)")

    # Save public key for reference
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _PUBLIC.write_bytes(pub_pem)
    print(f"  Public key  → {_PUBLIC}")

    # Split public PEM into 3 fragments at random byte positions
    # We split at byte boundaries (not line boundaries) to avoid obvious PEM structure
    n = len(pub_pem)
    # Generate 2 random split points in the middle third of the key
    lo = n // 4
    hi = 3 * n // 4
    splits = sorted([
        lo + os.urandom(1)[0] % (hi // 2 - lo),
        hi - os.urandom(1)[0] % (hi // 2 - lo),
    ])
    s1, s2 = splits
    kp1 = pub_pem[:s1]
    kp2 = pub_pem[s1:s2]
    kp3 = pub_pem[s2:]

    # Verify reassembly
    assert kp1 + kp2 + kp3 == pub_pem, "Fragment reassembly check failed"

    # Patch _keystore.py — write full file directly to avoid regex issues
    # with multiline bytes literals
    keystore_content = (
        '"""RSA-2048 public key stored in three fragments.\n'
        "\n"
        "The fragments are concatenated at runtime by LicenseVerifier._load_public_key().\n"
        "Split point positions are randomised at keygen time to make static analysis harder.\n"
        "\n"
        "IMPORTANT: This file contains the PUBLIC key only.\n"
        "           The PRIVATE key (dockmeow_private.pem) must never enter this repository.\n"
        '"""\n'
        "\n"
        "# Populated by tools/generate_keypair.py at keygen time.\n"
        f"_kp1: bytes = {kp1!r}\n"
        f"_kp2: bytes = {kp2!r}\n"
        f"_kp3: bytes = {kp3!r}\n"
    )
    _KEYSTORE.write_text(keystore_content, encoding="utf-8")
    print(f"  Patched keystore → {_KEYSTORE}")
    print(f"  Fragment sizes: {len(kp1)} / {len(kp2)} / {len(kp3)} bytes")
    print("\nDone.  Add dockmeow_private.pem to .gitignore and store it securely.")


if __name__ == "__main__":
    generate_and_save()
