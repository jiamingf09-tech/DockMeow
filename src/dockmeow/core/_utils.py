"""Internal utilities shared across core modules."""

from __future__ import annotations

import hashlib
import re


def safe_name(name: str) -> str:
    """Sanitise a filename so it is safe on all platforms.

    Replaces any character outside [A-Za-z0-9._-] with underscores,
    ensures the result is non-empty and does not start with a dot,
    and caps length at 64 characters.

    Args:
        name: Original filename (stem only, no path).

    Returns:
        Safe filename string up to 64 characters.
    """
    clean = re.sub(r"[^A-Za-z0-9._\-]", "_", name)
    if not clean or clean.startswith("."):
        clean = "file_" + hashlib.md5(name.encode()).hexdigest()[:8]
    return clean[:64]
