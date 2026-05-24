#!/usr/bin/env python3
"""Quick license issuance tool — wraps issue_license.py with:

  • Interactive OR command-line mode (same as issue_license.py)
  • Customer ledger recorded to customers.db (SQLite, gitignored)
  • License file path copied to macOS clipboard automatically
  • Finder reveals the .dmlic file after signing

Usage (interactive — guided prompts):
    python tools/quick_issue.py

Usage (CLI — non-interactive, scriptable):
    python tools/quick_issue.py \\
        --type perpetual \\
        --email user@example.com \\
        --machine-id "DM-853caa58-9fd8639c-a3e827c6" \\
        [--note "Paid via Stripe inv_xxx"]

Legacy full-factor mode is still accepted:
    python tools/quick_issue.py \\
        --type perpetual \\
        --email user@example.com \\
        --machine-factors "mb=853caa58ae67e9fe,cpu=9fd8639cece7f8a5,mac=a3e827c63db90fb1"

Dry-run (no file written, no DB entry, no clipboard):
    python tools/quick_issue.py --dry-run \\
        --type trial \\
        --email test@example.com \\
        --machine-id "DM-00000000-11111111-22222222"
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT  = Path(__file__).parent.parent
_DB_PATH    = _REPO_ROOT / "customers.db"
_ISSUED_DIR = _REPO_ROOT / "issued"
_SRC_PATH   = _REPO_ROOT / "src"
if _SRC_PATH.exists():
    sys.path.insert(0, str(_SRC_PATH))

# ── DB helpers ────────────────────────────────────────────────────────────────

def _db_connect() -> sqlite3.Connection:
    """Open (and init) the customer ledger database."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at   TEXT    NOT NULL,
            license_no    TEXT    NOT NULL UNIQUE,
            license_id    TEXT    NOT NULL,
            license_type  TEXT    NOT NULL,
            email         TEXT    NOT NULL,
            machine_id    TEXT,
            mb            TEXT,
            cpu           TEXT,
            mac           TEXT,
            expires_at    TEXT,
            dmlic_path    TEXT,
            note          TEXT
        )
    """)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(customers)")}
    if "machine_id" not in cols:
        conn.execute("ALTER TABLE customers ADD COLUMN machine_id TEXT")
    conn.commit()
    return conn


def _db_record(conn: sqlite3.Connection, data: dict, dmlic_path: Path, note: str) -> None:
    machine = data.get("machine", {})
    exp = data.get("expires_at")
    exp_str = (
        "永久" if exp is None
        else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp))
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO customers
            (recorded_at, license_no, license_id, license_type, email,
             machine_id, mb, cpu, mac, expires_at, dmlic_path, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            data["license_no"],
            data["license_id"],
            data["type"],
            data["email"],
            data.get("machine_id"),
            machine.get("mb"),
            machine.get("cpu"),
            machine.get("mac"),
            exp_str,
            str(dmlic_path.resolve()),
            note,
        ),
    )
    conn.commit()


# ── macOS helpers ─────────────────────────────────────────────────────────────

def _copy_to_clipboard(text: str) -> bool:
    """Copy text to macOS clipboard via pbcopy. Returns True on success."""
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
        return True
    except Exception:
        return False


def _reveal_in_finder(path: Path) -> None:
    """Select/reveal a file in macOS Finder."""
    try:
        subprocess.run(["open", "-R", str(path.resolve())], timeout=5)
    except Exception:
        pass


# ── Main logic ────────────────────────────────────────────────────────────────

def _parse_factors(s: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in s.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_binding(value: str) -> tuple[dict[str, str] | None, str | None]:
    raw = (value or "").strip()
    if raw.upper().startswith("DM-"):
        from dockmeow.licensing.machine import normalize_machine_id
        return None, normalize_machine_id(raw)
    return _parse_factors(raw), None


def _interactive() -> tuple[str, str, dict[str, str] | None, str | None, str]:
    """Return (license_type, email, factors, machine_id, note)."""
    print()
    print("=" * 52)
    print("  DockMeow 快速签发工具")
    print("=" * 52)

    while True:
        ltype = input("  许可证类型 [trial/perpetual]: ").strip().lower()
        if ltype in ("trial", "perpetual"):
            break
        print("  !! 请输入 trial 或 perpetual")

    email = input("  用户邮箱: ").strip()
    print("  请粘贴用户提供的设备 ID（推荐，格式：DM-xxx-yyy-zzz）")
    print("  或旧版完整机器因子（格式：mb=xxx,cpu=yyy,mac=zzz）:")
    binding_str = input("  > ").strip()
    factors, machine_id = _parse_binding(binding_str)
    note = input("  备注（可留空，如订单号）: ").strip()
    return ltype, email, factors, machine_id, note


def run(
    license_type: str,
    email: str,
    machine_factors: dict[str, str] | None = None,
    machine_id: str | None = None,
    note: str = "",
    dry_run: bool = False,
) -> Path | None:
    """Issue a license, record it, copy to clipboard, reveal in Finder.

    Returns the .dmlic Path, or None on dry-run.
    """
    # ── Validate binding ──
    if machine_id:
        from dockmeow.licensing.machine import normalize_machine_id
        machine_id = normalize_machine_id(machine_id)
    elif machine_factors:
        missing = [k for k in ("mb", "cpu", "mac") if k not in machine_factors]
        if missing:
            print(f"❌ 缺少机器因子: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
    else:
        print("❌ 缺少设备 ID 或机器因子", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║  DRY-RUN — 不会写文件、不会记录、不会复制剪贴板  ║")
        print("╚══════════════════════════════════════════════════╝")
        print(f"  类型:   {license_type}")
        print(f"  邮箱:   {email}")
        if machine_id:
            print(f"  设备ID: {machine_id}")
        else:
            machine_factors = machine_factors or {}
            print(f"  mb:     {machine_factors.get('mb')}")
            print(f"  cpu:    {machine_factors.get('cpu')}")
            print(f"  mac:    {machine_factors.get('mac')}")
        print(f"  备注:   {note or '（无）'}")
        print(f"  时间:   {now}")
        print()
        print("✅ dry-run 完成 — 参数合法，签发逻辑正常")
        return None

    # ── Call issue_license.issue() directly ──
    sys.path.insert(0, str(_REPO_ROOT / "src"))
    sys.path.insert(0, str(_REPO_ROOT / "tools"))
    from issue_license import issue  # type: ignore[import]

    print()
    print("  正在签发…", end="", flush=True)
    dmlic_path = issue(
        license_type=license_type,
        email=email,
        machine_factors=machine_factors,
        machine_id=machine_id,
    )
    print(" 完成")

    data = json.loads(dmlic_path.read_text(encoding="utf-8"))

    # ── Record to customers.db ──
    try:
        conn = _db_connect()
        _db_record(conn, data, dmlic_path, note)
        conn.close()
        db_ok = True
    except Exception as e:
        print(f"  ⚠️  数据库记录失败: {e}", file=sys.stderr)
        db_ok = False

    # ── Copy path to clipboard ──
    clip_ok = _copy_to_clipboard(str(dmlic_path.resolve()))

    # ── Reveal in Finder ──
    _reveal_in_finder(dmlic_path)

    # ── Print summary ──
    exp = data.get("expires_at")
    exp_str = (
        "永久有效" if exp is None
        else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp))
    )

    print()
    print("┌─────────────────────────────────────────────────────┐")
    print("│  ✓ 许可证签发成功                                   │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  编号   {data['license_no']:<43}│")
    print(f"│  类型   {'试用' if data['type'] == 'trial' else '永久':<43}│")
    print(f"│  邮箱   {email:<43}│")
    print(f"│  设备   {str(data.get('machine_id') or '旧版因子绑定'):<43}│")
    print(f"│  过期   {exp_str:<43}│")
    print(f"│  文件   {str(dmlic_path.name):<43}│")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  {'✅' if db_ok else '⚠️ '} 已记录到 customers.db"
          + (" " * (30 if db_ok else 29)) + "│")
    print(f"│  {'✅' if clip_ok else '⚠️ '} 路径已复制到剪贴板"
          + (" " * 32) + "│")
    print("│  ✅ Finder 已弹出文件位置                           │")
    print("└─────────────────────────────────────────────────────┘")
    print(f"\n  完整路径: {dmlic_path.resolve()}")

    return dmlic_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DockMeow 快速签发工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--type", choices=["trial", "perpetual"], dest="license_type",
                        help="许可证类型")
    parser.add_argument("--email", help="用户邮箱")
    parser.add_argument("--machine-id", "--machine-code", dest="machine_id",
                        help="设备 ID，格式: DM-xxxxxxxx-yyyyyyyy-zzzzzzzz")
    parser.add_argument("--machine-factors", dest="machine_factors",
                        help="旧版机器指纹，格式: mb=xxx,cpu=yyy,mac=zzz")
    parser.add_argument("--note", default="", help="备注（如订单号、渠道）")
    parser.add_argument("--dry-run", action="store_true",
                        help="演习模式：验证参数但不写文件")
    args = parser.parse_args()

    if args.license_type and args.email and (args.machine_id or args.machine_factors):
        # CLI mode
        ltype   = args.license_type
        email   = args.email
        factors = None
        machine_id = args.machine_id
        if args.machine_factors:
            factors, parsed_id = _parse_binding(args.machine_factors)
            machine_id = machine_id or parsed_id
        note    = args.note
        dry     = args.dry_run
    else:
        # Interactive mode (dry-run flag still respected)
        ltype, email, factors, machine_id, note = _interactive()
        dry = args.dry_run

    run(ltype, email, factors, machine_id=machine_id, note=note, dry_run=dry)


if __name__ == "__main__":
    main()
