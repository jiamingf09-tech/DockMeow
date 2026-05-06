"""Regression tests: real-world PDB/SDF files with edge cases."""
from __future__ import annotations

import sys
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "real_world"
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_ailanthone_sdf(tmp_path):
    """Ailanthone SDF should parse and prepare without error."""
    from dockmeow.core.ligand import prepare_ligand_from_file

    info = prepare_ligand_from_file(_DATA / "Ailanthone.sdf", tmp_path)
    assert info.n_atoms == 27  # 20 C + 7 O
    assert info.pdbqt_path.exists()
    assert info.pdbqt_path.stat().st_size > 0
    assert info.source_format == "sdf"


def test_1svc_detect_nucleic_acids():
    """1SVC.pdb should have its DNA chain detected."""
    from dockmeow.core.receptor import detect_nucleic_acid_chains

    na_chains = detect_nucleic_acid_chains(_DATA / "1SVC.pdb")
    assert len(na_chains) > 0
    assert "D" in na_chains


def test_1svc_strip_nucleic_acids(tmp_path):
    """1SVC with strip_nucleic_acids=True should succeed without DNA chain."""
    from dockmeow.core.receptor import prepare_receptor

    info = prepare_receptor(
        _DATA / "1SVC.pdb",
        tmp_path,
        strip_nucleic_acids=True,
    )
    assert "D" not in info.chains
    assert len(info.chains) > 0  # protein chains remain
    assert info.pdbqt_path.exists()
    assert info.pdbqt_path.stat().st_size > 0
    assert "D" in info.nucleic_acid_chains
