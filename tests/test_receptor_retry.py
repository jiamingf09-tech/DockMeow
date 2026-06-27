from pathlib import Path

import pytest

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
                "mock unrecoverable meeko failure",
                "受体 PDBQT 生成失败。",
            )
        output_pdbqt.write_text(PDB_TEXT, encoding="utf-8")
        return ["retry warning"]

    monkeypatch.setattr(receptor, "_run_pdbfixer", fake_run_pdbfixer)
    monkeypatch.setattr(receptor, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

    info = receptor.prepare_receptor(
        input_pdb,
        tmp_path / "work",
        add_missing_atoms=True,
    )

    assert fixer_calls == [True, False]
    assert len(pdbqt_calls) == 2
    assert info.pdbqt_path.read_text(encoding="utf-8") == PDB_TEXT
    assert info.chains == ["A"]
    assert info.n_residues == 1
    assert any("兼容模式" in warning for warning in info.warnings)
    assert "retry warning" in info.warnings


def test_prepare_receptor_uses_sanitized_meeko_retry_before_rerunning_pdbfixer(
    tmp_path,
    monkeypatch,
) -> None:
    input_pdb = tmp_path / "receptor.pdb"
    input_pdb.write_text(PDB_TEXT, encoding="utf-8")

    fixer_calls = 0
    pdbqt_inputs: list[str] = []

    def fake_run_pdbfixer(input_pdb, output_pdb, add_missing_atoms, ph, cb):
        nonlocal fixer_calls
        fixer_calls += 1
        output_pdb.write_text(
            PDB_TEXT
            + "ATOM      5  H1  GLY A   1       1.500   2.500   0.000  1.00 20.00           H\n"
            + "ATOM      6  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            + "CONECT    5    2\n",
            encoding="utf-8",
        )
        return []

    def fake_pdb_to_pdbqt(input_pdb, output_pdbqt, cb):
        text = input_pdb.read_text(encoding="utf-8")
        pdbqt_inputs.append(text)
        if len(pdbqt_inputs) == 1:
            raise ReceptorPreparationError(
                "meeko Polymer unexpected error: Explicit valence for atom # 2 C, 5, is greater than permitted",
                "受体 PDBQT 生成失败。",
            )
        assert " H1 " not in text
        assert text.count(" CA ") == 1
        assert "CONECT" not in text
        output_pdbqt.write_text(PDB_TEXT, encoding="utf-8")
        return ["sanitized retry warning"]

    monkeypatch.setattr(receptor, "_run_pdbfixer", fake_run_pdbfixer)
    monkeypatch.setattr(receptor, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

    info = receptor.prepare_receptor(input_pdb, tmp_path / "work")

    assert fixer_calls == 1
    assert len(pdbqt_inputs) == 2
    assert "sanitized retry warning" in info.warnings
    assert any("更保守的兼容清洗" in warning for warning in info.warnings)
    assert any("移除" in warning for warning in info.warnings)


def test_prepare_receptor_uses_fast_mode_by_default(tmp_path, monkeypatch) -> None:
    input_pdb = tmp_path / "receptor.pdb"
    input_pdb.write_text(PDB_TEXT, encoding="utf-8")
    fixer_calls: list[bool] = []

    def fake_run_pdbfixer(input_pdb, output_pdb, add_missing_atoms, ph, cb):
        fixer_calls.append(add_missing_atoms)
        output_pdb.write_text(PDB_TEXT, encoding="utf-8")
        return []

    def fake_pdb_to_pdbqt(input_pdb, output_pdbqt, cb):
        output_pdbqt.write_text(PDB_TEXT, encoding="utf-8")
        return []

    monkeypatch.setattr(receptor, "_run_pdbfixer", fake_run_pdbfixer)
    monkeypatch.setattr(receptor, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

    info = receptor.prepare_receptor(input_pdb, tmp_path / "work")

    assert fixer_calls == [False]
    assert info.n_residues == 1
    assert info.warnings == []


def test_prepare_receptor_reuses_cached_outputs(tmp_path, monkeypatch) -> None:
    input_pdb = tmp_path / "receptor.pdb"
    input_pdb.write_text(PDB_TEXT, encoding="utf-8")
    fixer_calls = 0
    pdbqt_calls = 0

    def fake_run_pdbfixer(input_pdb, output_pdb, add_missing_atoms, ph, cb):
        nonlocal fixer_calls
        fixer_calls += 1
        output_pdb.write_text(PDB_TEXT, encoding="utf-8")
        return []

    def fake_pdb_to_pdbqt(input_pdb, output_pdbqt, cb):
        nonlocal pdbqt_calls
        pdbqt_calls += 1
        output_pdbqt.write_text(PDB_TEXT, encoding="utf-8")
        return ["cached warning"]

    monkeypatch.setattr(receptor, "_run_pdbfixer", fake_run_pdbfixer)
    monkeypatch.setattr(receptor, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

    work_dir = tmp_path / "work"
    first = receptor.prepare_receptor(input_pdb, work_dir)
    second = receptor.prepare_receptor(input_pdb, work_dir)

    assert fixer_calls == 1
    assert pdbqt_calls == 1
    assert first.pdbqt_path == second.pdbqt_path
    assert second.original_pdb_path is not None
    assert second.original_pdb_path.exists()
    assert second.warnings == ["cached warning"]


def test_meeko_warning_summary_is_bounded_and_deduplicated() -> None:
    messages = ["Lone hydrogen is ignored"] * 1000
    messages += [
        "Template matching failed for residue_key='A:12'",
        "Template matching failed for residue_key='A:13'",
        "Template matching failed for residue_key='B:7'",
        "one useful warning",
        "one useful warning",
    ]

    summary = receptor._summarize_meeko_warnings(messages)

    assert len(summary) == 2
    assert "3 个" in summary[0]
    assert "A:12" in summary[0]
    assert summary[1] == "one useful warning"

    overflow = receptor._summarize_meeko_warnings(
        [f"technical warning {index}" for index in range(5)],
        limit=3,
    )
    assert overflow == [
        "technical warning 0",
        "technical warning 1",
        "另有 3 条技术性提示已收起。",
    ]


def test_sanitize_pdb_for_meeko_strips_problematic_records() -> None:
    raw = """\
ATOM      1  CA AGLY A   1       1.000   0.000   0.000  1.00 20.00           C
ATOM      2  CA BGLY A   1       2.000   0.000   0.000  1.00 20.00           C
ATOM      3  H1  GLY A   1       1.500   2.500   0.000  1.00 20.00           H
CONECT    3    1
END
"""

    cleaned, warnings = receptor._sanitize_pdb_for_meeko(raw)

    assert cleaned.count(" CA ") == 1
    assert " H1 " not in cleaned
    assert "CONECT" not in cleaned
    assert "AGLY" not in cleaned
    assert any("可疑氢原子" in warning for warning in warnings)
    assert any("重复原子记录" in warning for warning in warnings)
    assert any("辅助连接记录" in warning for warning in warnings)


def test_pdbqt_coverage_rejects_catastrophically_incomplete_output(tmp_path) -> None:
    def pdb_for_residues(count: int) -> str:
        return "".join(
            f"ATOM  {resi:5d}  CA  GLY A{resi:4d}    "
            "   0.000   0.000   0.000  1.00 20.00           C\n"
            for resi in range(1, count + 1)
        )

    output_pdbqt = tmp_path / "partial.pdbqt"
    output_pdbqt.write_text(pdb_for_residues(5), encoding="utf-8")

    with pytest.raises(ReceptorPreparationError, match="5/20 residues"):
        receptor._validate_pdbqt_coverage(pdb_for_residues(20), output_pdbqt)
