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
DIST_APP="dist/DockMeow.app"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  DockMeow ${VERSION} macOS ${ARCH} build"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Step 1: PyInstaller ───────────────────────────────────────────────────────
echo ""
echo "▶ Running PyInstaller…"
PYTHONPATH=src .venv-build/bin/pyinstaller packaging/dockmeow.spec \
    --clean --noconfirm

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
# Always apply at least an ad-hoc signature WITH entitlements so that
#   com.apple.security.cs.disable-library-validation takes effect.
# Without this, macOS 15 (Library Validation) kills the process the moment
# Shiboken's lazy-import calls dlopen() for an unsigned PySide6 dylib.
#
# Signing order MUST be inside-out:
#   1. individual .so / .dylib files
#   2. nested .app helpers
#   3. .framework bundles (deepest-path first via `sort -r`)
#   4. main executable (with entitlements)
#   5. outer .app bundle (with entitlements)
#
# --deep is intentionally NOT used: Qt's QtWebEngineCore.framework has
# a non-standard Versions/ layout that causes --deep to fail on macOS 15.

_SIGN_ID="${SIGN_ID:--}"          # use "-" (ad-hoc) when no Developer ID
_ENTITLEMENTS="packaging/macos/entitlements.plist"
_OPTS=""
[[ -n "$SIGN_ID" ]] && _OPTS="--options runtime"

echo ""
if [[ -n "$SIGN_ID" ]]; then
    echo "▶ Code signing with: $SIGN_ID"
else
    echo "▶ Ad-hoc signing with entitlements (disable-library-validation)…"
fi

# Strategy: we do NOT sign .framework bundles because the Qt framework
# layout inside a PyInstaller COLLECT bundle has partial/empty Resources
# directories that cause codesign to leave broken _CodeSignature symlinks,
# which hdiutil cannot read.
#
# This is safe because the main executable embeds
# com.apple.security.cs.disable-library-validation, so macOS skips
# signature checks on loaded dylibs entirely.
#
# Order: (1) individual binaries, (2) main exe with entitlements, (3) bundle.

# 1. Sign all .so and .dylib files (not inside .framework to avoid sealing issues)
find "$DIST_APP/Contents" \( -name "*.so" -o -name "*.dylib" \) \
    ! -path "*/.framework/*" ! -path "*/Versions/*" | \
while read -r f; do
    codesign --force --sign "$_SIGN_ID" $_OPTS "$f" 2>/dev/null || true
done

# 2. Sign dylibs that ARE inside frameworks but only at the leaf level
find "$DIST_APP/Contents/Frameworks" -name "*.dylib" | \
while read -r f; do
    codesign --force --sign "$_SIGN_ID" $_OPTS "$f" 2>/dev/null || true
done

# 3. Sign any nested .app helpers (e.g. QtWebEngineProcess.app)
find "$DIST_APP/Contents" -name "*.app" -mindepth 2 | sort -r | while read -r a; do
    codesign --force --sign "$_SIGN_ID" $_OPTS \
        --entitlements "$_ENTITLEMENTS" "$a" 2>/dev/null || true
done

# 4. Sign the main executable with entitlements
codesign --force --sign "$_SIGN_ID" $_OPTS \
    --entitlements "$_ENTITLEMENTS" \
    "$DIST_APP/Contents/MacOS/DockMeow"

# 5. Sign the outer .app bundle with entitlements (no --deep to avoid framework issues)
codesign --force --sign "$_SIGN_ID" $_OPTS \
    --entitlements "$_ENTITLEMENTS" \
    "$DIST_APP"

echo "  Entitlements embedded: $(codesign -d --entitlements - \
    "$DIST_APP/Contents/MacOS/DockMeow" 2>/dev/null | \
    grep -c 'disable-library-validation') disable-library-validation key(s)"

# ── Step 4: DMG ──────────────────────────────────────────────────────────────
echo ""
echo "▶ Creating DMG: $DMG_NAME"

rm -f "dist/$DMG_NAME"

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "$APP_NAME" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "${APP_NAME}.app" 175 190 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 425 190 \
        "dist/$DMG_NAME" \
        "$DIST_APP"
else
    # Fallback: plain hdiutil
    echo "  create-dmg not found; using plain hdiutil"
    hdiutil create -volname "$APP_NAME" -srcfolder "$DIST_APP" \
        -ov -format UDZO "dist/$DMG_NAME"
fi

SIZE=$(du -sh "dist/$DMG_NAME" | cut -f1)
echo ""
echo "✓ DMG ready: dist/$DMG_NAME  ($SIZE)"

# ── Size check ───────────────────────────────────────────────────────────────
SIZE_BYTES=$(stat -f%z "dist/$DMG_NAME")
LIMIT_BYTES=$((1500 * 1024 * 1024))  # 1.5 GB
if [[ $SIZE_BYTES -gt $LIMIT_BYTES ]]; then
    echo "⚠ WARNING: DMG exceeds 1.5 GB target (${SIZE})"
fi
