"""Developer tool — sign and issue a DockMeow license file.

Requires dockmeow_private.pem in the repo root (never committed to git).

Usage (command-line):
    python tools/issue_license.py --type trial \\
        --email user@example.com \\
        --machine-factors mb=abc12345...,cpu=def67890...,mac=1234abcd...

    python tools/issue_license.py --type perpetual \\
        --email user@example.com \\
        --machine-id DM-853caa58-9fd8639c-a3e827c6

Legacy full-factor mode is still supported:
    python tools/issue_license.py --type perpetual \\
        --email user@example.com \\
        --machine-factors mb=abc12345...,cpu=def67890...,mac=1234abcd...

Usage (interactive — omit all flags):
    python tools/issue_license.py

Output: issued/<LICENSE_ID>.dmlic
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import uuid
from pathlib import Path

_REPO_ROOT       = Path(__file__).parent.parent
PRIVATE_KEY_PATH = _REPO_ROOT / "dockmeow_private.pem"
ISSUED_DIR       = _REPO_ROOT / "issued"
_SRC_PATH        = _REPO_ROOT / "src"
if _SRC_PATH.exists():
    sys.path.insert(0, str(_SRC_PATH))

# Trial duration in seconds (24 hours)
TRIAL_DURATION_SECONDS = 24 * 3600

_COUNTER_FILE = ISSUED_DIR / ".counter"


def _next_license_no(license_type: str) -> str:
    """Atomically increment the per-year counter and return a human-readable ID.

    Format:
        perpetual  → DM-2026-00042
        trial      → DM-TRIAL-2026-00042
    """
    import datetime

    ISSUED_DIR.mkdir(exist_ok=True)
    year = datetime.date.today().year

    # Simple file-lock counter (single-operator tool — no need for heavy locking)
    try:
        n = int(_COUNTER_FILE.read_text(encoding="utf-8").strip()) + 1
    except (FileNotFoundError, ValueError):
        n = 1
    _COUNTER_FILE.write_text(str(n), encoding="utf-8")

    prefix = "DM-TRIAL" if license_type == "trial" else "DM"
    return f"{prefix}-{year}-{n:05d}"


def _load_private_key(path: Path):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    if not path.exists():
        print(f"ERROR: Private key not found at {path}", file=sys.stderr)
        print("Run `python tools/generate_keypair.py` first.", file=sys.stderr)
        sys.exit(1)
    return load_pem_private_key(path.read_bytes(), password=None)


def _sign(private_key, payload: dict) -> str:
    """Sign the canonical JSON of payload (without 'signature') → base64url str."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    message = json.dumps(
        {k: v for k, v in payload.items() if k != "signature"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    sig = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def issue(
    license_type: str,
    email: str,
    machine_factors: dict[str, str] | None = None,
    machine_id: str | None = None,
    license_id: str | None = None,
    private_key_path: Path = PRIVATE_KEY_PATH,
) -> Path:
    """Issue and sign a license file.

    Args:
        license_type:    ``"trial"`` or ``"perpetual"``.
        email:           Licensee email address.
        machine_factors: Legacy dict with ``mb``, ``cpu``, ``mac`` keys.
        machine_id:      Copyable device ID shown by the app (preferred).
        license_id:      Optional explicit UUID; auto-generated if None.
        private_key_path: Path to the RSA private key PEM file.

    Returns:
        Path to the created .dmlic file in ``issued/``.
    """
    if license_type not in ("trial", "perpetual"):
        raise ValueError(f"license_type must be 'trial' or 'perpetual', got {license_type!r}")
    if not machine_id and not machine_factors:
        raise ValueError("machine_id or machine_factors is required")

    now = time.time()
    lid = license_id or str(uuid.uuid4())
    lno = _next_license_no(license_type)
    expires_at: float | None = None
    if license_type == "trial":
        expires_at = now + TRIAL_DURATION_SECONDS

    payload: dict = {
        "license_id": lid,
        "license_no": lno,
        "email":      email,
        "type":       license_type,
        "issued_at":  now,
        "expires_at": expires_at,
    }
    if machine_id:
        from dockmeow.licensing.machine import normalize_machine_id
        payload["machine_id"] = normalize_machine_id(machine_id)
    if machine_factors:
        payload["machine"] = machine_factors

    private_key = _load_private_key(private_key_path)
    payload["signature"] = _sign(private_key, payload)

    ISSUED_DIR.mkdir(exist_ok=True)
    out_path = ISSUED_DIR / f"{lno}.dmlic"
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def _parse_factors(factors_str: str) -> dict[str, str]:
    """Parse 'mb=abc...,cpu=def...,mac=123...' into a dict."""
    result: dict[str, str] = {}
    for part in factors_str.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _interactive() -> tuple[str, str, dict[str, str] | None, str | None]:
    """Prompt the operator interactively and return the machine binding."""
    print("\n" + "=" * 50)
    print("DockMeow 许可证签发工具（交互模式）")
    print("=" * 50)
    while True:
        ltype = input("许可证类型 [trial/perpetual]: ").strip().lower()
        if ltype in ("trial", "perpetual"):
            break
        print("请输入 trial 或 perpetual")
    email = input("用户邮箱: ").strip()
    print("\n请粘贴用户提供的设备 ID（DM-xxx-yyy-zzz）或旧版完整机器因子：")
    binding = input("> ").strip()
    if binding.upper().startswith("DM-"):
        return ltype, email, None, binding
    return ltype, email, _parse_factors(binding), None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Issue a DockMeow license file (.dmlic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--type", choices=["trial", "perpetual"], dest="license_type")
    parser.add_argument("--email")
    parser.add_argument("--machine-id", "--machine-code", dest="machine_id")
    parser.add_argument("--machine-factors", dest="machine_factors")
    parser.add_argument("--license-id", dest="license_id")
    parser.add_argument("--key", default=str(PRIVATE_KEY_PATH),
                        help="Path to private key PEM file")
    args = parser.parse_args()

    if args.license_type and args.email and (args.machine_id or args.machine_factors):
        # Command-line mode
        ltype   = args.license_type
        email   = args.email
        machine_id = args.machine_id
        factors = None
        if args.machine_factors:
            if args.machine_factors.strip().upper().startswith("DM-"):
                machine_id = args.machine_factors
            else:
                factors = _parse_factors(args.machine_factors)
    else:
        # Interactive mode
        ltype, email, factors, machine_id = _interactive()

    out = issue(
        license_type=ltype,
        email=email,
        machine_factors=factors,
        machine_id=machine_id,
        license_id=args.license_id if hasattr(args, "license_id") else None,
        private_key_path=Path(args.key),
    )

    import time as _time
    data = json.loads(out.read_text(encoding="utf-8"))
    exp = data.get("expires_at")
    exp_str = (
        "永久" if exp is None
        else _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime(exp))
    )
    print(f"\n✓ 许可证已签发")
    print(f"  文件: {out}")
    print(f"  编号: {data['license_no']}")
    print(f"  ID:   {data['license_id']}")
    print(f"  类型: {data['type']}")
    print(f"  邮箱: {data['email']}")
    print(f"  过期: {exp_str}")


if __name__ == "__main__":
    main()
