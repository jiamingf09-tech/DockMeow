"""Developer tool — inspect and validate an issued license file.

Usage:
    python tools/revoke_check.py path/to/license.dmlic

Prints license metadata and signature validity.
Does NOT check machine binding (operator machine ≠ user machine).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))


def inspect_license(dmlic_path: Path) -> None:
    """Print human-readable metadata from a .dmlic file."""
    from dockmeow.licensing.verifier import LicenseVerifier
    from dockmeow.core.exceptions import LicenseError

    if not dmlic_path.exists():
        print(f"ERROR: File not found: {dmlic_path}")
        sys.exit(1)

    try:
        data = json.loads(dmlic_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: Cannot parse JSON: {exc}")
        sys.exit(1)

    exp = data.get("expires_at")
    issued = data.get("issued_at", 0)
    exp_str = "永久" if exp is None else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp))
    iss_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(issued))

    print("=" * 50)
    print(f"  License No : {data.get('license_no', '(legacy)')}")
    print(f"  License ID : {data.get('license_id', '?')}")
    print(f"  Type       : {data.get('type', '?')}")
    print(f"  Email      : {data.get('email', '?')}")
    print(f"  Issued     : {iss_str}")
    print(f"  Expires    : {exp_str}")
    mf = data.get("machine", {})
    print(f"  Machine    : mb={mf.get('mb','?')} cpu={mf.get('cpu','?')} mac={mf.get('mac','?')}")
    print("-" * 50)

    # Verify signature (skipped if keystore is empty)
    try:
        v = LicenseVerifier()
        v.verify_signature(data)
        print("  Signature  : ✓ VALID")
    except LicenseError as exc:
        if "Public key not configured" in str(exc):
            print("  Signature  : ⚠ skipped (keystore empty — run generate_keypair.py first)")
        else:
            print(f"  Signature  : ✗ INVALID ({exc})")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python tools/revoke_check.py <path_to.dmlic>")
        sys.exit(1)
    inspect_license(Path(sys.argv[1]))
