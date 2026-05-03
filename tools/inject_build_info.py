"""CI tool — inject build-time metadata before PyInstaller packaging.

Actions performed:
    1. Compute SHA-256 of verifier.py and _keystore.py source files.
    2. Patch those expected hashes into obfuscation.py (integrity_check).
    3. Write the git commit hash / build timestamp into version.py.

Run: python tools/inject_build_info.py
Called automatically by the release.yml workflow.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LICENSING_DIR = ROOT / "src" / "dockmeow" / "licensing"
OBFUSCATION_PY = LICENSING_DIR / "obfuscation.py"
VERSION_PY = ROOT / "src" / "dockmeow" / "version.py"


def _git_short_hash() -> str:
    """Return the short git commit hash, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _sha256_file(path: Path) -> str:
    """Return hex SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _patch_obfuscation(verifier_hash: str, keystore_hash: str) -> None:
    """Patch _EXPECTED_HASHES in obfuscation.py with the computed hashes."""
    text = OBFUSCATION_PY.read_text(encoding="utf-8")

    # Match the _EXPECTED_HASHES dict block and replace the empty string values.
    # Pattern targets the exact two-key dict written in the source file.
    pattern = (
        r'(_EXPECTED_HASHES: dict\[str, str\] = \{\n'
        r'    "verifier": ")"([^"]*)"'
        r'(,\n'
        r'    "_keystore": ")"([^"]*)"'
        r'(,?\n\})'
    )
    replacement = (
        r'\g<1>' + verifier_hash + r'"\g<3>' + keystore_hash + r'"\g<5>'
    )

    new_text, count = re.subn(pattern, replacement, text)
    if count == 0:
        # Fallback: replace each empty-string value individually
        new_text = re.sub(
            r'("verifier":\s*)"([^"]*)"',
            r'\g<1>"' + verifier_hash + '"',
            text,
        )
        new_text = re.sub(
            r'("_keystore":\s*)"([^"]*)"',
            r'\g<1>"' + keystore_hash + '"',
            new_text,
        )
        if new_text == text:
            print(
                "WARNING: inject_build_info: could not patch _EXPECTED_HASHES "
                "in obfuscation.py — pattern not found.",
                file=sys.stderr,
            )
            return

    OBFUSCATION_PY.write_text(new_text, encoding="utf-8")
    print(f"Patched {OBFUSCATION_PY.relative_to(ROOT)}")
    print(f"  verifier  hash: {verifier_hash}")
    print(f"  _keystore hash: {keystore_hash}")


def _append_build_metadata(commit: str, build_time: str) -> None:
    """Append __build_commit__ and __build_time__ to version.py if absent."""
    text = VERSION_PY.read_text(encoding="utf-8")

    lines_to_add: list[str] = []
    if "__build_commit__" not in text:
        lines_to_add.append(f'__build_commit__ = "{commit}"')
    if "__build_time__" not in text:
        lines_to_add.append(f'__build_time__ = "{build_time}"')

    if not lines_to_add:
        print("version.py already contains build metadata — skipping.")
        return

    separator = "\n" if text.endswith("\n") else "\n\n"
    new_text = text.rstrip("\n") + separator + "\n".join(lines_to_add) + "\n"
    VERSION_PY.write_text(new_text, encoding="utf-8")
    print(f"Updated {VERSION_PY.relative_to(ROOT)}")
    for line in lines_to_add:
        print(f"  + {line}")


def main() -> None:
    errors: list[str] = []

    # 1. Git commit hash
    commit = _git_short_hash()
    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Build commit: {commit}  build_time: {build_time}")

    # 2. Compute SHA-256 of the two key source files
    verifier_hash = ""
    keystore_hash = ""

    verifier_py = LICENSING_DIR / "verifier.py"
    keystore_py = LICENSING_DIR / "_keystore.py"

    try:
        if verifier_py.exists():
            verifier_hash = _sha256_file(verifier_py)
            print(f"SHA-256 verifier.py:  {verifier_hash}")
        else:
            errors.append(f"Source file not found: {verifier_py}")
    except Exception as exc:
        errors.append(f"Failed to hash verifier.py: {exc}")

    try:
        if keystore_py.exists():
            keystore_hash = _sha256_file(keystore_py)
            print(f"SHA-256 _keystore.py: {keystore_hash}")
        else:
            errors.append(f"Source file not found: {keystore_py}")
    except Exception as exc:
        errors.append(f"Failed to hash _keystore.py: {exc}")

    # 3. Patch obfuscation.py
    if verifier_hash or keystore_hash:
        try:
            _patch_obfuscation(verifier_hash, keystore_hash)
        except Exception as exc:
            errors.append(f"Failed to patch obfuscation.py: {exc}")
    else:
        errors.append("Skipping obfuscation.py patch — no hashes computed.")

    # 4. Append build metadata to version.py
    try:
        _append_build_metadata(commit, build_time)
    except Exception as exc:
        errors.append(f"Failed to update version.py: {exc}")

    # Report any non-fatal errors
    if errors:
        print("\nWARNINGS / non-fatal errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    print("\ninject_build_info: done.")


if __name__ == "__main__":
    main()
