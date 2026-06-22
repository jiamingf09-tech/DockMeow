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
    if [[ ! -L "$WEBENGINE_HELPERS" || ! -d "$VERSIONED_HELPERS" ]]; then
        echo "ERROR: QtWebEngine Helpers framework layout is invalid" >&2
        exit 1
    fi
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
