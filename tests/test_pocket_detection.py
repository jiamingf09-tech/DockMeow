import pytest

from dockmeow.core import pocket
from dockmeow.core.pocket import Pocket
from dockmeow.core.receptor import HeteroGroup, ReceptorInfo


def test_fpocket_files_use_natural_order_and_native_scores(tmp_path) -> None:
    paths = [
        tmp_path / "pocket10_atm.pdb",
        tmp_path / "pocket2_atm.pdb",
        tmp_path / "pocket1_atm.pdb",
    ]
    assert [path.name for path in sorted(paths, key=pocket._pocket_file_number)] == [
        "pocket1_atm.pdb",
        "pocket2_atm.pdb",
        "pocket10_atm.pdb",
    ]

    info = tmp_path / "receptor_info.txt"
    info.write_text(
        "Pocket 1 :\n\tScore : \t0.088\n\tDruggability Score : \t0.028\n"
        "Pocket 2 :\n\tScore : \t-0.077\n",
        encoding="utf-8",
    )
    assert pocket._parse_fpocket_scores(info) == {1: 0.088, 2: -0.077}


def test_detect_pockets_uses_preserved_original_pdb_for_cocrystal(
    tmp_path,
    monkeypatch,
) -> None:
    prepared = tmp_path / "prepared.pdb"
    prepared.write_text(
        "ATOM      1  CA  GLY A   1       0.000   0.000   0.000  1.00 20.00           C\n",
        encoding="utf-8",
    )
    original = tmp_path / "original.pdb"
    original.write_text(
        "HETATM    1  C1  FLC A 710      10.000  20.000  30.000  1.00 20.00           C\n"
        "HETATM    2  C2  FLC A 710      12.000  22.000  32.000  1.00 20.00           C\n",
        encoding="utf-8",
    )
    receptor = ReceptorInfo(
        pdb_path=prepared,
        pdbqt_path=tmp_path / "prepared.pdbqt",
        chains=["A"],
        n_residues=1,
        hetero_groups=[HeteroGroup("FLC", "A", 710, 13, False, False, True)],
        original_pdb_path=original,
    )
    monkeypatch.setattr(pocket, "_run_fpocket", lambda *_args: [])

    pockets = pocket.detect_pockets(receptor)

    assert pockets[0].source == "cocrystal"
    assert pockets[0].center == pytest.approx((11.0, 21.0, 31.0))
    assert "FLC" in pockets[0].label


def test_fpocket_is_recommended_only_without_cocrystal(tmp_path, monkeypatch) -> None:
    prepared = tmp_path / "prepared.pdb"
    prepared.write_text(
        "ATOM      1  CA  GLY A   1       0.000   0.000   0.000  1.00 20.00           C\n",
        encoding="utf-8",
    )
    receptor = ReceptorInfo(
        pdb_path=prepared,
        pdbqt_path=tmp_path / "prepared.pdbqt",
        chains=["A"],
        n_residues=1,
    )
    fpocket_result = Pocket(1, (0, 0, 0), (15, 15, 15), 0.42, label="口袋 1")
    monkeypatch.setattr(pocket, "_run_fpocket", lambda *_args: [fpocket_result])

    pockets = pocket.detect_pockets(receptor)

    assert pockets[0].label == "口袋 1（推荐）"
