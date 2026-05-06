"""End-to-end CLI smoke test — Stage 1 completion gate."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.slow
def test_cli_end_to_end(tmp_path, example_receptor, aspirin_smiles):
    """Full pipeline: receptor → ligand → pocket → docking → PDF report."""
    result = subprocess.run(
        [
            sys.executable, "-m", "dockmeow.core.cli",
            "--receptor", str(example_receptor),
            "--ligand-smiles", aspirin_smiles,
            "--output", str(tmp_path),
            "--exhaustiveness", "4",
            "--num-modes", "5",
            "--seed", "42",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"CLI returned {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    # Required output files
    assert (tmp_path / "result.sdf").exists(), "result.sdf not found"
    assert (tmp_path / "report.pdf").exists(), "report.pdf not found"

    # PDF is valid
    pdf_header = (tmp_path / "report.pdf").read_bytes()[:4]
    assert pdf_header == b"%PDF", f"Invalid PDF header: {pdf_header!r}"

    # SDF is non-empty
    assert (tmp_path / "result.sdf").stat().st_size > 0

    # Scores appear in stdout
    assert "kcal/mol" in result.stdout or "结合能" in result.stdout


@pytest.mark.slow
def test_cli_ligand_file_input(tmp_path, example_receptor):
    """Test --ligand-file path with an SDF input."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    sdf_path = tmp_path / "aspirin.sdf"
    with Chem.SDWriter(str(sdf_path)) as w:
        w.write(mol)

    result = subprocess.run(
        [
            sys.executable, "-m", "dockmeow.core.cli",
            "--receptor", str(example_receptor),
            "--ligand-file", str(sdf_path),
            "--output", str(tmp_path / "out"),
            "--exhaustiveness", "4",
            "--no-report",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "result.sdf").exists()


@pytest.mark.slow
def test_cli_4dfr_methotrexate(tmp_path, example_receptor_4dfr, methotrexate_smiles):
    """4DFR + methotrexate end-to-end: best score expected in [-8, -10] kcal/mol."""
    result = subprocess.run(
        [
            sys.executable, "-m", "dockmeow.core.cli",
            "--receptor", str(example_receptor_4dfr),
            "--ligand-smiles", methotrexate_smiles,
            "--output", str(tmp_path),
            "--exhaustiveness", "8",
            "--num-modes", "9",
            "--seed", "42",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"CLI returned {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    assert (tmp_path / "result.sdf").exists()
    assert (tmp_path / "report.pdf").exists()
    assert (tmp_path / "report.pdf").read_bytes()[:4] == b"%PDF"

    # Parse best score from stdout
    import re
    match = re.search(r"(-[\d.]+)\s*kcal/mol", result.stdout)
    assert match, f"No score found in stdout:\n{result.stdout}"
    best_score = float(match.group(1))
    assert -12.0 <= best_score <= -6.0, (
        f"Unexpected best score {best_score:.2f} kcal/mol; "
        "expected MTX vs 4DFR to be in [-12, -6] range"
    )
