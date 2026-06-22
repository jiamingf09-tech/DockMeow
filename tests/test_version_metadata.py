import plistlib
import tomllib
from pathlib import Path

from dockmeow.version import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_metadata_matches_package_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__

    with (ROOT / "packaging/macos/Info.plist").open("rb") as plist_file:
        macos_info = plistlib.load(plist_file)
    assert macos_info["CFBundleVersion"] == __version__
    assert macos_info["CFBundleShortVersionString"] == __version__

    spec = (ROOT / "packaging/dockmeow.spec").read_text(encoding="utf-8")
    assert f'"CFBundleVersion": "{__version__}"' in spec
    assert f'"CFBundleShortVersionString": "{__version__}"' in spec

    installer = (ROOT / "packaging/windows/installer.iss").read_text(encoding="utf-8")
    assert f'#define MyAppVersion "{__version__}"' in installer

    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")
    dockmeow_entry = f'[[package]]\nname = "dockmeow"\nversion = "{__version__}"'
    assert dockmeow_entry in lockfile
