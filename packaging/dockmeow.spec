# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DockMeow / 一键对接  (cross-platform)
# Run from repo root:
#   pyinstaller packaging/dockmeow.spec --clean --noconfirm
#
# vina note: no macOS arm64 wheel on PyPI; the .so is copied from conda:
#   cp -r /opt/miniconda3/envs/dockmeow/lib/python3.11/site-packages/vina \
#          <pip-site-packages>/
# The boost dylibs it links are bundled explicitly in `binaries` below.

from pathlib import Path
import os
import platform
import sys
import sysconfig

block_cipher = None

ROOT    = Path(SPECPATH).parent          # repo root
SRC     = ROOT / "src" / "dockmeow"

# Use the active venv's site-packages (works for both .venv-build and conda envs)
VENV_SP = Path(sysconfig.get_path("purelib"))

# Conda lib dir — override via CONDA_LIB env var in CI; default to macOS arm64 path
CONDA_LIB = Path(os.environ.get("CONDA_LIB", "/opt/miniconda3/envs/dockmeow/lib"))

# ── Platform flags ────────────────────────────────────────────────────────────

IS_MACOS   = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX   = sys.platform.startswith("linux")

# ── Binaries ─────────────────────────────────────────────────────────────────

_binaries = []
_OPENMM_APP_DATA = VENV_SP / "openmm" / "app" / "data"
_PDBFIXER_TEMPLATES = VENV_SP / "pdbfixer" / "templates"
_PDBFIXER_SOFT_XML = VENV_SP / "pdbfixer" / "soft.xml"
_MEEKO_DATA = VENV_SP / "meeko" / "data"
_QTWEBENGINE_PROCESS = VENV_SP / "PySide6" / "QtWebEngineProcess.exe"
_QTWEBENGINE_LOCALES = VENV_SP / "PySide6" / "translations" / "qtwebengine_locales"

# vina .so (macOS only — no arm64 PyPI wheel; copied from conda by CI)
if IS_MACOS:
    vina_sos = list((VENV_SP / "vina").glob("_vina_wrapper*.so"))
    for vina_so in vina_sos:
        _binaries.append((str(vina_so), "vina"))

    # Boost dylibs required by vina .so (linked via @rpath)
    for dylib in ("libboost_thread.dylib", "libboost_filesystem.dylib"):
        p = CONDA_LIB / dylib
        if p.exists():
            _binaries.append((str(p), "."))

# fpocket binary (placed by CI/build pipeline; app falls back gracefully if absent)
if IS_MACOS:
    arch_dir = "macos_arm64" if platform.machine() == "arm64" else "macos_x64"
    fpocket = SRC / "bundled" / "fpocket" / arch_dir / "fpocket"
    if fpocket.exists():
        _binaries.append((str(fpocket), f"bundled/fpocket/{arch_dir}"))
elif IS_LINUX:
    fpocket = SRC / "bundled" / "fpocket" / "linux" / "fpocket"
    if fpocket.exists():
        _binaries.append((str(fpocket), "bundled/fpocket/linux"))
elif IS_WINDOWS:
    fpocket = SRC / "bundled" / "fpocket" / "windows" / "fpocket.exe"
    if fpocket.exists():
        _binaries.append((str(fpocket), "bundled/fpocket/windows"))

    if _QTWEBENGINE_PROCESS.exists():
        _binaries.append((str(_QTWEBENGINE_PROCESS), "PySide6"))

# OpenMM's PDB parser loads XML replacement tables via paths relative to
# openmm.app.pdbfile.__file__.  In macOS bundles PyInstaller places collected
# package binaries under Contents/Frameworks/openmm, so these data files must be
# available there as well as under Resources.
if _OPENMM_APP_DATA.exists():
    for data_file in _OPENMM_APP_DATA.rglob("*"):
        if data_file.is_file():
            rel = data_file.relative_to(_OPENMM_APP_DATA)
            _binaries.append((str(data_file), str(Path("openmm") / "app" / "data" / rel.parent)))

if _PDBFIXER_TEMPLATES.exists():
    for template_file in _PDBFIXER_TEMPLATES.rglob("*"):
        if template_file.is_file():
            rel = template_file.relative_to(_PDBFIXER_TEMPLATES)
            _binaries.append((str(template_file), str(Path("pdbfixer") / "templates" / rel.parent)))

if _PDBFIXER_SOFT_XML.exists():
    _binaries.append((str(_PDBFIXER_SOFT_XML), "pdbfixer"))

if _MEEKO_DATA.exists():
    for data_file in _MEEKO_DATA.rglob("*"):
        if data_file.is_file():
            rel = data_file.relative_to(_MEEKO_DATA)
            _binaries.append((str(data_file), str(Path("meeko") / "data" / rel.parent)))

# ── Data files ────────────────────────────────────────────────────────────────

_PYSIDE6 = VENV_SP / "PySide6"

# Locate QtWebEngine resource directory (platform-specific layout)
_WEBENGINE_RESOURCES = None

if IS_MACOS:
    _candidate = (
        _PYSIDE6 / "Qt" / "lib" / "QtWebEngineCore.framework" / "Resources"
    )
    if _candidate.exists():
        _WEBENGINE_RESOURCES = _candidate
elif IS_LINUX:
    _candidate = _PYSIDE6 / "Qt" / "resources"
    if _candidate.exists():
        _WEBENGINE_RESOURCES = _candidate
elif IS_WINDOWS:
    _candidate = _PYSIDE6 / "resources"
    if _candidate.exists():
        _WEBENGINE_RESOURCES = _candidate

_datas = [
    # Destination must match resource_path() expectations:
    # resource_path("bundled/fonts") -> sys._MEIPASS / "bundled/fonts"
    (str(SRC / "bundled"),          "bundled"),
    (str(SRC / "ui" / "resources"), "ui/resources"),
]


def _add_data_if_exists(src_path, dest):
    """Collect optional package data only when that dependency is installed."""
    if src_path.exists():
        _datas.append((str(src_path), dest))


_add_data_if_exists(_OPENMM_APP_DATA, "openmm/app/data")
_add_data_if_exists(_PDBFIXER_TEMPLATES, "pdbfixer/templates")
_add_data_if_exists(_PDBFIXER_SOFT_XML, "pdbfixer")
_add_data_if_exists(_MEEKO_DATA, "meeko/data")

# Bundle QtWebEngine resources (.pak files, icudtl.dat, v8 snapshots, locales)
# into _MEIPASS/webengine_resources/ so the runtime hook can point Qt to them.
if _WEBENGINE_RESOURCES is not None:
    _datas.append((str(_WEBENGINE_RESOURCES), "webengine_resources"))

if IS_WINDOWS and _QTWEBENGINE_LOCALES.exists():
    _datas.append((str(_QTWEBENGINE_LOCALES), "webengine_resources/qtwebengine_locales"))

# ── Hidden imports ────────────────────────────────────────────────────────────
# Packages imported dynamically at runtime (not detected by static analysis)

_hidden = [
    # Qt WebEngine — critical for the 3D viewer
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtNetwork",
    # Docking / cheminformatics
    "vina",
    "meeko",
    "meeko.receptor_pdbqt",
    "meeko.polymer",
    "meeko.chemtempgen",
    "rdkit",
    "rdkit.Chem",
    "rdkit.Chem.AllChem",
    "rdkit.Chem.rdMolDescriptors",
    "rdkit.Chem.rdMolTransforms",
    # Structural biology
    "pdbfixer",
    "openmm",
    "openmm.app",
    "openmm.unit",
    "Bio",
    "Bio.PDB",
    "Bio.SeqUtils",
    "scipy",
    "scipy.spatial",
    "gemmi",
    # Reporting
    "reportlab",
    "reportlab.pdfbase",
    "reportlab.pdfbase.ttfonts",
    "reportlab.pdfbase.pdfmetrics",
    "reportlab.platypus",
    "reportlab.lib.styles",
    "reportlab.lib.pagesizes",
    "reportlab.lib.units",
    "reportlab.lib.colors",
    # Licensing
    "cryptography",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.asymmetric",
    "cryptography.hazmat.primitives.asymmetric.rsa",
    "cryptography.hazmat.primitives.asymmetric.padding",
    "cryptography.hazmat.primitives.hashes",
    "cryptography.hazmat.backends",
]

# ── Analysis ──────────────────────────────────────────────────────────────────

a = Analysis(
    [str(SRC / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[
        str(ROOT / "packaging" / "hooks" / "rthook-pyside6-eager.py"),
        str(ROOT / "packaging" / "hooks" / "rthook-webengine.py"),
    ],
    excludes=[
        # Test / dev tools not needed at runtime
        "pytest", "pytest_qt", "_pytest",
        "ruff", "mypy",
        # Heavy unused scientific libs
        "matplotlib", "IPython", "jupyter",
        "tkinter", "_tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Icon paths ────────────────────────────────────────────────────────────────

_ICNS = ROOT / "packaging" / "macos" / "DockMeow.icns"
_ICO  = ROOT / "packaging" / "windows" / "DockMeow.ico"

if IS_MACOS:
    _icon = str(_ICNS) if _ICNS.exists() else None
elif IS_WINDOWS:
    _icon = str(_ICO) if _ICO.exists() else None
else:
    _icon = None

# ── Executable ────────────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DockMeow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,      # UPX damages .so / dylib signatures on macOS; keep off
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

# ── Collection ────────────────────────────────────────────────────────────────

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DockMeow",
)

# ── macOS .app bundle ─────────────────────────────────────────────────────────

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="DockMeow.app",
        icon=str(_ICNS) if _ICNS.exists() else None,
        bundle_identifier="com.dockmeow.app",
        info_plist={
            "CFBundleName": "DockMeow",
            "CFBundleDisplayName": "一键对接",
            "CFBundleIdentifier": "com.dockmeow.app",
            "CFBundleVersion": "0.1.1",
            "CFBundleShortVersionString": "0.1.1",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,   # allow dark mode
            "LSMinimumSystemVersion": "13.0",
            "NSHumanReadableCopyright": "© 2026 DockMeow",
            # Qt WebEngine entitlements (unsigned dev build)
            "com.apple.security.cs.allow-jit": True,
            "com.apple.security.cs.allow-unsigned-executable-memory": True,
            "com.apple.security.cs.disable-library-validation": True,
        },
    )
