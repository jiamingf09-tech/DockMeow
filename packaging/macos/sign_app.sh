#!/usr/bin/env bash
# Normalize the PyInstaller Qt bundle, then apply and verify a macOS signature.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 /path/to/DockMeow.app" >&2
    exit 2
fi

APP_PATH="$1"
SIGN_ID="${SIGN_ID:--}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTITLEMENTS="${SCRIPT_DIR}/entitlements.plist"

if [[ ! -d "$APP_PATH/Contents" ]]; then
    echo "ERROR: app bundle not found: $APP_PATH" >&2
    exit 1
fi

WEBENGINE_FRAMEWORK="$APP_PATH/Contents/Frameworks/PySide6/Qt/lib/QtWebEngineCore.framework"
WEBENGINE_HELPERS="$WEBENGINE_FRAMEWORK/Helpers"
VERSIONED_HELPERS="$WEBENGINE_FRAMEWORK/Versions/A/Helpers"
VERSIONED_RESOURCES="$WEBENGINE_FRAMEWORK/Versions/A/Resources"
INVALID_VERSIONED_RESOURCES="$WEBENGINE_FRAMEWORK/Versions/Resources"

# PyInstaller places Helpers at the framework root. codesign requires all
# non-symlink framework content to live under Versions/<version>.
if [[ -d "$WEBENGINE_HELPERS" && ! -L "$WEBENGINE_HELPERS" ]]; then
    if [[ -e "$VERSIONED_HELPERS" ]]; then
        echo "ERROR: both QtWebEngine Helpers locations exist" >&2
        exit 1
    fi
    mv "$WEBENGINE_HELPERS" "$VERSIONED_HELPERS"
    ln -s "Versions/Current/Helpers" "$WEBENGINE_HELPERS"
fi

if [[ -d "$WEBENGINE_FRAMEWORK" ]]; then
    # PyInstaller can leave an empty Versions/Resources directory alongside
    # Versions/A. codesign treats every direct child of Versions as a framework
    # version, so that stray directory makes --deep --strict fail with
    # "embedded framework contains modified or invalid version".
    if [[ -e "$INVALID_VERSIONED_RESOURCES" || -L "$INVALID_VERSIONED_RESOURCES" ]]; then
        if [[ -d "$INVALID_VERSIONED_RESOURCES" && ! -L "$INVALID_VERSIONED_RESOURCES" ]]; then
            if find "$INVALID_VERSIONED_RESOURCES" -mindepth 1 -print -quit | grep -q .; then
                mkdir -p "$VERSIONED_RESOURCES"
                ditto "$INVALID_VERSIONED_RESOURCES" "$VERSIONED_RESOURCES"
            fi
        fi
        rm -rf "$INVALID_VERSIONED_RESOURCES"
    fi

    if [[ ! -L "$WEBENGINE_HELPERS" || ! -d "$VERSIONED_HELPERS" ]]; then
        echo "ERROR: QtWebEngine Helpers framework layout is invalid" >&2
        exit 1
    fi
    while IFS= read -r version_entry; do
        version_name="$(basename "$version_entry")"
        if [[ "$version_name" != "A" && "$version_name" != "Current" ]]; then
            echo "ERROR: invalid QtWebEngine framework version entry: $version_name" >&2
            exit 1
        fi
    done < <(find "$WEBENGINE_FRAMEWORK/Versions" -mindepth 1 -maxdepth 1 -print)
fi

# PyInstaller rewrites Qt framework install names to flat @rpath entries and
# places matching symlinks in Contents/Frameworks. Once Helpers is normalized
# under Versions/A, its generated rpath is two levels too shallow, so the
# renderer process cannot locate QtWebEngineCore and every WebEngine page fails.
WEBENGINE_PROCESS="$VERSIONED_HELPERS/QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess"
WEBENGINE_RPATH="@loader_path/../../../../../../../../../.."
if [[ -f "$WEBENGINE_PROCESS" ]]; then
    if ! otool -l "$WEBENGINE_PROCESS" | grep -Fq "path $WEBENGINE_RPATH "; then
        install_name_tool -add_rpath "$WEBENGINE_RPATH" "$WEBENGINE_PROCESS"
    fi
    if ! otool -l "$WEBENGINE_PROCESS" | grep -Fq "path $WEBENGINE_RPATH "; then
        echo "ERROR: QtWebEngineProcess rpath repair failed" >&2
        exit 1
    fi
    echo "QtWebEngineProcess rpath repaired"
fi

SIGN_ARGS=(--force --deep --sign "$SIGN_ID")
if [[ "$SIGN_ID" != "-" ]]; then
    SIGN_ARGS+=(--options runtime --timestamp)
fi

codesign "${SIGN_ARGS[@]}" --entitlements "$ENTITLEMENTS" "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

if [[ ! -f "$APP_PATH/Contents/_CodeSignature/CodeResources" ]]; then
    echo "ERROR: outer app resource seal was not created" >&2
    exit 1
fi

echo "macOS signature verified: $APP_PATH"
