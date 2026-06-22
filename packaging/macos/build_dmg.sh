#!/usr/bin/env bash
# Build macOS .dmg installer for DockMeow.
# Usage: ./packaging/macos/build_dmg.sh [--sign "Developer ID Application: ..."]
# Requires: .venv-build with PyInstaller installed, create-dmg (brew install create-dmg)

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APP_NAME="DockMeow"
BUNDLE_ID="com.dockmeow.app"
SIGN_ID="${SIGN_ID:-}"   # Override via env or --sign flag

while [[ $# -gt 0 ]]; do
    case $1 in
        --sign) SIGN_ID="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Version ──────────────────────────────────────────────────────────────────
PYTHONPATH=src VERSION=$(.venv-build/bin/python -c "from dockmeow.version import __version__; print(__version__)")
ARCH=$(uname -m)   # arm64 or x86_64
DMG_NAME="${APP_NAME}-${VERSION}-${ARCH}.dmg"
DIST_BASE="dist/macos-${ARCH}"
WORK_BASE="build/macos-${ARCH}"
DIST_APP="${DIST_BASE}/DockMeow.app"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  DockMeow ${VERSION} macOS ${ARCH} build"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Step 1: PyInstaller ───────────────────────────────────────────────────────
echo ""
echo "▶ Running PyInstaller…"
PYTHONPATH=src .venv-build/bin/pyinstaller packaging/dockmeow.spec \
    --clean --noconfirm --distpath "$DIST_BASE" --workpath "$WORK_BASE"

if [[ ! -d "$DIST_APP" ]]; then
    echo "ERROR: $DIST_APP not found after PyInstaller run."
    exit 1
fi

echo "  App bundle: $DIST_APP ($(du -sh "$DIST_APP" | cut -f1))"

# ── Step 2: Fix boost dylib rpath inside the bundle ──────────────────────────
echo ""
echo "▶ Fixing boost dylib rpaths…"
FRAMEWORKS="$DIST_APP/Contents/Frameworks"
for dylib in libboost_thread.dylib libboost_filesystem.dylib; do
    src="$FRAMEWORKS/$dylib"
    if [[ -f "$src" ]]; then
        install_name_tool -id "@rpath/$dylib" "$src" 2>/dev/null || true
        install_name_tool -add_rpath "@loader_path/../Frameworks" "$src" 2>/dev/null || true
        echo "  Fixed: $dylib"
    fi
done

# Fix vina .so to find boost via @loader_path/../Frameworks
VINA_SO="$DIST_APP/Contents/MacOS/vina/_vina_wrapper.cpython-311-darwin.so"
if [[ -f "$VINA_SO" ]]; then
    for dylib in libboost_thread.dylib libboost_filesystem.dylib; do
        install_name_tool -change "@rpath/$dylib" \
            "@loader_path/../../Frameworks/$dylib" "$VINA_SO" 2>/dev/null || true
    done
    echo "  Fixed vina rpath"
fi

# ── Step 3: Code sign ────────────────────────────────────────────────────────
echo ""
if [[ -n "$SIGN_ID" ]]; then
    echo "▶ Code signing with: $SIGN_ID"
else
    echo "▶ Ad-hoc signing with entitlements"
fi

SIGN_ID="${SIGN_ID:--}" packaging/macos/sign_app.sh "$DIST_APP"

# ── Step 4: DMG ──────────────────────────────────────────────────────────────
echo ""
echo "▶ Creating DMG: $DMG_NAME"

PACKAGE_PATH="dist/$DMG_NAME"
ZIP_NAME="${APP_NAME}-${VERSION}-${ARCH}.zip"
ZIP_PATH="dist/$ZIP_NAME"

rm -f "$PACKAGE_PATH" "$ZIP_PATH"

if command -v create-dmg &>/dev/null; then
    if ! create-dmg \
        --volname "$APP_NAME" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "${APP_NAME}.app" 175 190 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 425 190 \
        "$PACKAGE_PATH" \
        "$DIST_APP"; then
        echo "  create-dmg failed; falling back to ZIP"
        ditto -c -k --keepParent "$DIST_APP" "$ZIP_PATH"
        PACKAGE_PATH="$ZIP_PATH"
    fi
else
    # Fallback: plain hdiutil
    echo "  create-dmg not found; using plain hdiutil"
    if ! hdiutil create -volname "$APP_NAME" -srcfolder "$DIST_APP" \
        -ov -format UDZO "$PACKAGE_PATH"; then
        echo "  hdiutil failed; falling back to ZIP"
        ditto -c -k --keepParent "$DIST_APP" "$ZIP_PATH"
        PACKAGE_PATH="$ZIP_PATH"
    fi
fi

SIZE=$(du -sh "$PACKAGE_PATH" | cut -f1)
echo ""
echo "✓ Package ready: $PACKAGE_PATH  ($SIZE)"

# ── Size check ───────────────────────────────────────────────────────────────
SIZE_BYTES=$(stat -f%z "$PACKAGE_PATH")
LIMIT_BYTES=$((1500 * 1024 * 1024))  # 1.5 GB
if [[ $SIZE_BYTES -gt $LIMIT_BYTES ]]; then
    echo "⚠ WARNING: package exceeds 1.5 GB target (${SIZE})"
fi
