#!/usr/bin/env bash
# Build Linux AppImage for DockMeow.
set -euo pipefail

# ── Navigate to repo root ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/../.."

# ── Version and architecture ──────────────────────────────────────────────────
VERSION="$(python -c "import sys; sys.path.insert(0, 'src'); from dockmeow.version import __version__; print(__version__)")"
ARCH="$(uname -m)"
APPIMAGE_NAME="DockMeow-${VERSION}-${ARCH}.AppImage"

echo "Building AppImage: ${APPIMAGE_NAME}  (arch=${ARCH})"

# ── Create AppDir structure ───────────────────────────────────────────────────
APPDIR="dist/DockMeow.AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"
mkdir -p dist/installers

# Copy PyInstaller output into usr/bin/
if [[ ! -d "dist/DockMeow" ]]; then
    echo "ERROR: dist/DockMeow not found — run PyInstaller first." >&2
    exit 1
fi
cp -r dist/DockMeow/. "${APPDIR}/usr/bin/"

# ── Icons ─────────────────────────────────────────────────────────────────────
ICON_SRC=""
for candidate in "packaging/linux/DockMeow.png" "logo.png" "src/dockmeow/ui/resources/icon.png"; do
    if [[ -f "${candidate}" ]]; then
        ICON_SRC="${candidate}"
        break
    fi
done

if [[ -n "${ICON_SRC}" ]]; then
    cp "${ICON_SRC}" "${APPDIR}/dockmeow.png"
    cp "${ICON_SRC}" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/dockmeow.png"
else
    echo "WARNING: No icon file found; AppImage will lack an icon." >&2
    # Create a minimal placeholder so appimagetool doesn't error
    touch "${APPDIR}/dockmeow.png"
fi

# ── .desktop file ─────────────────────────────────────────────────────────────
cat > "${APPDIR}/dockmeow.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=DockMeow
Comment=Molecular docking made easy
Exec=DockMeow --no-sandbox %U
Icon=dockmeow
Categories=Science;Chemistry;
Terminal=false
StartupNotify=true
EOF

# ── AppRun wrapper ────────────────────────────────────────────────────────────
cat > "${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${HERE}/usr/bin/DockMeow" --no-sandbox "$@"
EOF
chmod +x "${APPDIR}/AppRun"

# ── Obtain appimagetool ───────────────────────────────────────────────────────
if command -v appimagetool &>/dev/null; then
    APPIMAGETOOL="appimagetool"
else
    echo "appimagetool not found in PATH — downloading from AppImageKit releases/continuous..."
    APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    APPIMAGETOOL_BIN="/tmp/appimagetool-${ARCH}.AppImage"
    wget -q --show-progress -O "${APPIMAGETOOL_BIN}" "${APPIMAGETOOL_URL}"
    chmod +x "${APPIMAGETOOL_BIN}"
    APPIMAGETOOL="${APPIMAGETOOL_BIN}"
fi

# ── Build AppImage ────────────────────────────────────────────────────────────
ARCH="${ARCH}" "${APPIMAGETOOL}" "${APPDIR}" "dist/installers/${APPIMAGE_NAME}"

echo ""
echo "AppImage created: dist/installers/${APPIMAGE_NAME}"
