"""Developer utility — encode plaintext strings for use in obfuscation.py.

Usage:
    python tools/string_encode.py "签名无效"
    # → _x("KQQEDgcMUgQOAAcMUgEMDgULBA==")

The output is a Python expression ready to paste into obfuscation.py.
"""

from __future__ import annotations

import base64
import sys

_KEY = 0x4D


def encode(plaintext: str) -> str:
    """Return the _x("...") expression for the given plaintext."""
    raw = plaintext.encode("utf-8")
    xored = bytes(c ^ _KEY for c in raw)
    b64 = base64.b64encode(xored).decode("ascii")
    return f'_x("{b64}")'


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/string_encode.py <plaintext>")
        sys.exit(1)
    print(encode(sys.argv[1]))
