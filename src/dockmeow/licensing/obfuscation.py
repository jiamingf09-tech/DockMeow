"""Light obfuscation helpers and anti-debug checks.

Measures implemented:
    a. String obfuscation — critical strings encoded as XOR-over-base64 literals.
    b. Anti-debug check   — detect sys.gettrace(); exit silently if debugger found.
    c. Integrity check    — SHA-256 of key .pyc files compared against baked-in hashes.

Limitations (documented honestly):
    These measures raise the bar for casual inspection.  A determined reverser
    with Python knowledge can bypass them.  The real protection is the RSA-2048
    private key which never leaves the operator's possession.
"""

from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

_XOR_KEY = 0x4D  # 'M'

# SHA-256 hashes of the two most security-critical compiled modules.
# Populated by tools/inject_build_info.py before packaging.
# Empty strings = integrity check disabled (development mode).
_EXPECTED_HASHES: dict[str, str] = {
    "verifier": "9fe3587ea8b0d58c3fb2d937ca4d0f1892291ae410ce88b6debec613a3d7f1dc",
    "_keystore": "fac015eff887b163392c6f34d82553f503777f48720146a616af641520c8d32d",
}


def _x(b64s: str, key: int = _XOR_KEY) -> str:
    """Decode a string obfuscated as XOR-over-base64.

    Args:
        b64s: Base64-encoded XOR-encrypted bytes.
        key:  Single-byte XOR key (default 0x4D = 'M').

    Returns:
        The original plaintext string.
    """
    raw = base64.b64decode(b64s)
    return bytes(c ^ key for c in raw).decode("utf-8")


def antidbg_check() -> None:
    """Exit silently if a Python debugger trace function is active.

    Does not raise — silent exit is intentional so debugger output gives no hints.
    """
    if sys.gettrace() is not None:
        sys.exit(0)


def integrity_check() -> bool:
    """Verify SHA-256 hashes of key compiled modules.

    Returns:
        True if all baked-in hashes match (or no hashes are baked in).
        False if a hash mismatch is detected.
    """
    if not any(_EXPECTED_HASHES.values()):
        return True  # development mode — skip

    try:
        pkg_dir = Path(__file__).parent
        for name, expected in _EXPECTED_HASHES.items():
            if not expected:
                continue
            candidates = list(pkg_dir.glob(f"__pycache__/{name}.cpython-*.pyc"))
            if not candidates:
                # Source file hash fallback
                src = pkg_dir / f"{name}.py"
                if not src.exists():
                    return False
                actual = hashlib.sha256(src.read_bytes()).hexdigest()
            else:
                actual = hashlib.sha256(candidates[0].read_bytes()).hexdigest()
            if actual != expected:
                return False
    except Exception:
        return False
    return True
