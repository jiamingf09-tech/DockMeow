"""Multi-factor machine fingerprinting.

Three independent factors are collected:
    mb  — Motherboard / platform UUID  (most stable)
    cpu — CPU model + architecture + core count
    mac — Primary non-virtual MAC address

Matching rule: current machine passes if it matches ≥ 2 of the 3 stored factors.
This tolerates one hardware change (e.g., NIC replacement or CPU upgrade) without
invalidating the license.

Platform notes:
    macOS   — IOPlatformUUID via ioreg
    Windows — WMIC csproduct UUID
    Linux   — /etc/machine-id or /var/lib/dbus/machine-id
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path


def _factor_motherboard() -> str:
    """Return the raw platform/motherboard UUID string."""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode(errors="replace")
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[-2].strip()
        elif sys.platform == "win32":
            out = subprocess.check_output(
                ["wmic", "csproduct", "get", "UUID"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode(errors="replace")
            lines = [ln.strip() for ln in out.splitlines()
                     if ln.strip() and ln.strip() != "UUID"]
            if lines:
                return lines[0]
        else:
            for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                p = Path(candidate)
                if p.exists():
                    val = p.read_text(encoding="utf-8", errors="replace").strip()
                    if val:
                        return val
    except Exception:
        pass
    return ""


def _factor_cpu() -> str:
    """Return a stable string describing the CPU model + arch + core count."""
    try:
        model = platform.processor() or platform.machine()
        arch = platform.machine()
        cores = str(os.cpu_count() or 0)
        return f"{model}|{arch}|{cores}"
    except Exception:
        return ""


def _factor_mac() -> str:
    """Return the primary non-loopback, non-virtual MAC address as hex."""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(
                ["ifconfig"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode(errors="replace")
            for block in out.split("\n\n"):
                if block.startswith("lo") or "LOOPBACK" in block:
                    continue
                m = re.search(r"ether\s+([0-9a-f:]{17})", block)
                if m:
                    mac = m.group(1).replace(":", "")
                    if mac not in ("000000000000", "ffffffffffff"):
                        return mac
        elif sys.platform == "win32":
            out = subprocess.check_output(
                ["getmac", "/fo", "csv", "/nh"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode(errors="replace")
            for line in out.splitlines():
                parts = line.strip().strip('"').split('","')
                if parts and parts[0] not in ("N/A", ""):
                    mac = parts[0].replace("-", "").replace(":", "").lower()
                    if len(mac) == 12 and mac != "000000000000":
                        return mac
        else:
            net_dir = Path("/sys/class/net")
            if net_dir.exists():
                for iface in sorted(net_dir.iterdir()):
                    if iface.name == "lo" or iface.name.startswith(
                        ("veth", "docker", "br-", "virbr")
                    ):
                        continue
                    addr_file = iface / "address"
                    if addr_file.exists():
                        mac = addr_file.read_text().strip().replace(":", "")
                        if len(mac) == 12 and mac != "000000000000":
                            return mac
        node = uuid.getnode()
        if node and not (node >> 40 & 1):
            return format(node, "012x")
    except Exception:
        pass
    return ""


def _hash16(raw: str) -> str:
    """Truncate SHA-256 of raw to 16 lowercase hex chars; empty in → empty out."""
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def get_machine_factors() -> dict[str, str]:
    """Collect and hash the three machine factors.

    Returns:
        Dict with keys ``mb``, ``cpu``, ``mac``.
        Each value is a 16-char lowercase hex string, or ``""`` if collection failed.
    """
    return {
        "mb":  _hash16(_factor_motherboard()),
        "cpu": _hash16(_factor_cpu()),
        "mac": _hash16(_factor_mac()),
    }


def get_machine_id() -> str:
    """Return a single stable machine identifier string.

    Format: ``DM-<mb[:8]>-<cpu[:8]>-<mac[:8]>``
    """
    f = get_machine_factors()
    mb  = (f.get("mb")  or "00000000")[:8]
    cpu = (f.get("cpu") or "00000000")[:8]
    mac = (f.get("mac") or "00000000")[:8]
    return f"DM-{mb}-{cpu}-{mac}"


def match_machine(stored_factors: dict[str, str]) -> bool:
    """Check whether the current machine matches stored factors (≥ 2/3 rule).

    Args:
        stored_factors: Dict with ``mb``, ``cpu``, ``mac`` keys from the license.

    Returns:
        True if at least 2 of the 3 non-empty stored factors match the current machine.
    """
    current = get_machine_factors()
    matches = 0
    compared = 0
    for key in ("mb", "cpu", "mac"):
        stored = stored_factors.get(key, "")
        curr   = current.get(key, "")
        if not stored:
            continue
        compared += 1
        if stored == curr:
            matches += 1
    if compared == 0:
        return False
    return matches >= min(2, compared)
