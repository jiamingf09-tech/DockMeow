from pathlib import Path

from dockmeow.core import receptor
from dockmeow.core.exceptions import ReceptorPreparationError

PDB_TEXT = """\
ATOM      1  N   GLY A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C
ATOM      3  C   GLY A   1       1.500   1.000   0.000  1.00 20.00           C
ATOM      4  O   GLY A   1       1.500   2.000   0.000  1.00 20.00           O
TER
END
"""


def test_prepare_receptor_retries_without_missing_atoms_on_pdbqt_error(
    tmp_path,
    monkeypatch,
) -> None:
    input_pdb = tmp_path / "receptor.pdb"
    input_pdb.write_text(PDB_TEXT, encoding="utf-8")

    fixer_calls: list[bool] = []
    pdbqt_calls: list[Path] = []

    def fake_run_pdbfixer(input_pdb, output_pdb, add_missing_atoms, ph, cb):
        fixer_calls.append(add_missing_atoms)
        output_pdb.write_text(PDB_TEXT, encoding="utf-8")
        if cb:
            cb("受体准备", 40, "fixed")
        return []

    def fake_pdb_to_pdbqt(input_pdb, output_pdbqt, cb, original_pdb=None):
        pdbqt_calls.append(input_pdb)
        if len(pdbqt_calls) == 1:
            raise ReceptorPreparationError(
                "mock valence failure",
                "受体 PDBQT 生成失败。",
            )
        output_pdbqt.write_text("REMARK mock pdbqt\n", encoding="utf-8")
        return ["retry warning"]

    monkeypatch.setattr(receptor, "_run_pdbfixer", fake_run_pdbfixer)
    monkeypatch.setattr(receptor, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

    info = receptor.prepare_receptor(input_pdb, tmp_path / "work")

    assert fixer_calls == [True, False]
    assert len(pdbqt_calls) == 2
    assert info.pdbqt_path.read_text(encoding="utf-8") == "REMARK mock pdbqt\n"
    assert info.chains == ["A"]
    assert info.n_residues == 1
    assert any("不补全缺失原子" in warning for warning in info.warnings)
    assert "retry warning" in info.warnings
