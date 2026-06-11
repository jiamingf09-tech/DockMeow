"""PyMOL integration — locate PyMOL, build a load script, and launch it.

Loads the *original* receptor PDB together with every docking pose so the user
can inspect the complex in full PyMOL.  All poses are loaded into a SINGLE
multi-state object (``multiplex=0``) so PyMOL's bottom frame slider / arrow keys
step through each conformation one at a time — i.e. if the run produced 10
poses, PyMOL shows 10 navigable states of the ligand.

No PySide6 imports permitted in this module so it stays GUI-free and unit
testable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dockmeow.utils.paths import is_usable_executable

# Object names used inside the generated PyMOL session.
RECEPTOR_OBJECT = "receptor"
POSES_OBJECT = "poses"


# ---------------------------------------------------------------------------
# Locating the PyMOL executable
# ---------------------------------------------------------------------------
def _candidate_names() -> list[str]:
    """Executable file names to look for, most-specific first."""
    if sys.platform == "win32":
        # PyMOLWin.exe = incentive/open-source GUI launcher; pymol.exe = conda.
        return ["PyMOLWin.exe", "pymol.exe", "PyMOL.exe", "pymol.bat", "pymol"]
    if sys.platform == "darwin":
        return ["pymol", "PyMOL", "MacPyMOL"]
    return ["pymol", "pymol.AppImage"]


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _conda_bases() -> list[Path]:
    """Possible conda/mamba install roots to scan for a pymol env."""
    home = Path.home()
    bases: list[Path] = []
    for name in ("anaconda3", "miniconda3", "miniforge3", "mambaforge"):
        bases.append(home / name)
    prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if prefix:
        base = Path(prefix)
        bases.append(base)
        # If we're inside an env (…/envs/<name>) include the root too.
        if base.parent.name == "envs":
            bases.append(base.parent.parent)
    return bases


def _extra_dirs() -> list[Path]:
    """Common install directories to scan beyond PATH."""
    home = Path.home()
    dirs: list[Path] = []

    if sys.platform == "win32":
        program_files = {
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("ProgramW6432", r"C:\Program Files"),
        }
        for pf in program_files:
            if pf:
                dirs += [Path(pf) / "PyMOL", Path(pf) / "PyMOL" / "PyMOL"]
        dirs.append(Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "pymol")
        dirs.append(home / "AppData" / "Local" / "Programs" / "PyMOL")
        dirs.append(home / "PyMOL")
        for base in _conda_bases():
            dirs += [base / "Scripts", base / "Library" / "bin", base]
            for env in _safe_iterdir(base / "envs"):
                dirs += [env / "Scripts", env / "Library" / "bin", env]
    elif sys.platform == "darwin":
        dirs += [
            Path("/Applications/PyMOL.app/Contents/MacOS"),
            Path("/Applications/PyMOL.app/Contents/bin"),
            Path("/Applications/MacPyMOL.app/Contents/MacOS"),
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin"),
        ]
        for base in _conda_bases():
            dirs.append(base / "bin")
            for env in _safe_iterdir(base / "envs"):
                dirs.append(env / "bin")
    else:  # linux / other unix
        dirs += [
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/opt/pymol/bin"),
            home / "bin",
            home / ".local" / "bin",
        ]
        for base in _conda_bases():
            dirs.append(base / "bin")
            for env in _safe_iterdir(base / "envs"):
                dirs.append(env / "bin")

    return dirs


def is_valid_pymol(path: Path | str | None) -> bool:
    """Return True if ``path`` points at an existing, runnable file."""
    if not path:
        return False
    p = Path(path)
    return p.is_file() and is_usable_executable(p)


def find_pymol() -> Path | None:
    """Best-effort search for a PyMOL executable.

    Order: ``PATH`` first (respects the user's environment / active conda env),
    then a list of common install locations for the current OS.

    Returns:
        Absolute path to a PyMOL launcher, or ``None`` if nothing was found.
    """
    for name in _candidate_names():
        found = shutil.which(name)
        if found and is_valid_pymol(found):
            return Path(found)

    seen: set[Path] = set()
    for directory in _extra_dirs():
        try:
            key = directory.resolve()
        except OSError:
            key = directory
        if key in seen:
            continue
        seen.add(key)
        for name in _candidate_names():
            candidate = directory / name
            if is_valid_pymol(candidate):
                return candidate
    return None


# ---------------------------------------------------------------------------
# Building the PyMOL load script
# ---------------------------------------------------------------------------
def build_pml(
    receptor_path: Path | str,
    poses_path: Path | str,
    *,
    receptor_object: str = RECEPTOR_OBJECT,
    poses_object: str = POSES_OBJECT,
    background: str = "white",
) -> str:
    """Return a ``.pml`` script that loads the receptor and all poses.

    The poses are loaded with ``multiplex=0`` so the multi-record SDF becomes a
    single object with one state per pose.  PyMOL's frame controls then switch
    between conformations.  File paths are embedded as ``repr()`` of their POSIX
    form, which quotes spaces and avoids Windows backslash-escape problems.

    Args:
        receptor_path:   Original receptor PDB.
        poses_path:      Multi-pose SDF (one record per conformation).
        receptor_object: PyMOL object name for the receptor.
        poses_object:    PyMOL object name for the poses.
        background:      Viewport background colour.

    Returns:
        The script text (PyMOL command file with an embedded python block).
    """
    receptor_repr = repr(Path(receptor_path).as_posix())
    poses_repr = repr(Path(poses_path).as_posix())
    receptor_name = repr(str(receptor_object))
    poses_name = repr(str(poses_object))
    bg_repr = repr(str(background))

    # NOTE: everything between ``python`` and ``python end`` is real Python and
    # must keep valid (4-space) indentation.
    return f"""# DockMeow -> PyMOL session
# Auto-generated.  Receptor + every docking pose (one state per conformation).
python
from pymol import cmd
try:
    from pymol import util
except Exception:
    util = None

cmd.reinitialize()
cmd.bg_color({bg_repr})

cmd.load({receptor_repr}, {receptor_name})
cmd.load({poses_repr}, {poses_name}, multiplex=0)

cmd.hide("everything")
cmd.show("cartoon", {receptor_name})
cmd.color("gray80", {receptor_name})
cmd.set("cartoon_transparency", 0.10, {receptor_name})

cmd.show("sticks", {poses_name})
cmd.set("stick_radius", 0.18, {poses_name})
if util is not None:
    try:
        util.cbag({poses_name})
    except Exception:
        cmd.color("green", {poses_name} + " and elem C")
else:
    cmd.color("green", {poses_name} + " and elem C")

# One state per pose; show a single conformation at a time so the frame
# slider / arrow keys step through all of them.
cmd.set("all_states", 0)
n_states = cmd.count_states({poses_name})

cmd.orient({poses_name})
cmd.zoom({poses_name}, 6.0)
cmd.set("state", 1)
cmd.deselect()
print("DockMeow: loaded %d pose state(s) into '%s'." % (n_states, {poses_name}))
print("DockMeow: use the frame slider (bottom-right) or arrow keys to switch poses.")
python end
"""


# ---------------------------------------------------------------------------
# Writing a session directory and launching PyMOL
# ---------------------------------------------------------------------------
def write_session(
    receptor_pdb: Path,
    poses_sdf: Path,
    dest_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Copy the structures next to a generated ``.pml`` in a session directory.

    Copying decouples the PyMOL session from DockMeow's transient working dir so
    the files stay valid for as long as PyMOL is open.

    Args:
        receptor_pdb: Source receptor PDB.
        poses_sdf:    Source multi-pose SDF.
        dest_dir:     Optional target directory; a temp dir is made if omitted.

    Returns:
        ``(session_dir, pml_path)``.

    Raises:
        FileNotFoundError: if either source structure is missing/empty.
    """
    receptor_pdb = Path(receptor_pdb)
    poses_sdf = Path(poses_sdf)
    if not receptor_pdb.is_file():
        raise FileNotFoundError(f"Receptor PDB not found: {receptor_pdb}")
    if not poses_sdf.is_file() or poses_sdf.stat().st_size == 0:
        raise FileNotFoundError(f"Poses SDF not found or empty: {poses_sdf}")

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="dockmeow_pymol_"))
    else:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

    receptor_dst = dest_dir / "receptor.pdb"
    poses_dst = dest_dir / "poses.sdf"
    shutil.copyfile(receptor_pdb, receptor_dst)
    shutil.copyfile(poses_sdf, poses_dst)

    pml_path = dest_dir / "dockmeow_session.pml"
    pml_path.write_text(build_pml(receptor_dst, poses_dst), encoding="utf-8")
    return dest_dir, pml_path


def launch_pymol(pymol_exe: Path | str, script_path: Path | str) -> subprocess.Popen:
    """Launch the PyMOL GUI and run ``script_path``.

    The child is started in its own process group / session so quitting DockMeow
    does not close PyMOL.

    Args:
        pymol_exe:   PyMOL launcher resolved via :func:`find_pymol` or user input.
        script_path: ``.pml`` to run on startup.

    Returns:
        The :class:`subprocess.Popen` handle.

    Raises:
        FileNotFoundError: if ``pymol_exe`` is not a runnable file.
    """
    if not is_valid_pymol(pymol_exe):
        raise FileNotFoundError(f"PyMOL executable not usable: {pymol_exe}")

    script_path = Path(script_path)
    args = [str(pymol_exe), str(script_path)]

    popen_kwargs: dict[str, object] = {"cwd": str(script_path.parent)}
    if sys.platform == "win32":
        # New process group + detached so it outlives DockMeow; GUI still shows.
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        popen_kwargs["creationflags"] = flags
    else:
        popen_kwargs["start_new_session"] = True

    return subprocess.Popen(args, **popen_kwargs)  # noqa: S603


def export_to_pymol(
    receptor_pdb: Path,
    poses_sdf: Path,
    pymol_exe: Path | str,
    dest_dir: Path | None = None,
) -> tuple[subprocess.Popen, Path]:
    """High-level helper: write a session then launch PyMOL on it.

    Returns:
        ``(process, session_dir)``.
    """
    session_dir, pml_path = write_session(receptor_pdb, poses_sdf, dest_dir)
    proc = launch_pymol(pymol_exe, pml_path)
    return proc, session_dir
