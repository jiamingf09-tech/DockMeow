"""Shared pytest fixtures for DockMeow test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_dir() -> Path:
    """Return the path to tests/data/."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    """Return the path to examples/."""
    return Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="session")
def example_receptor(examples_dir: Path) -> Path:
    """Path to 1AKE PDB (has AP5 co-crystal ligand)."""
    p = examples_dir / "1AKE_with_ATP.pdb"
    if not p.exists():
        pytest.skip(f"Example PDB not found: {p}")
    return p


@pytest.fixture(scope="session")
def example_receptor_4dfr(examples_dir: Path) -> Path:
    """Path to 4DFR PDB (has MTX co-crystal ligand)."""
    p = examples_dir / "4DFR_methotrexate.pdb"
    if not p.exists():
        pytest.skip(f"Example PDB not found: {p}")
    return p


@pytest.fixture(scope="session")
def aspirin_smiles() -> str:
    return "CC(=O)Oc1ccccc1C(=O)O"


@pytest.fixture(scope="session")
def methotrexate_smiles() -> str:
    return "CN(Cc1cnc2nc(N)nc(N)c2n1)c1ccc(C(=O)N[C@@H](CCC(=O)O)C(=O)O)cc1"


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Fresh temporary working directory for each test."""
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytest.fixture(scope="session")
def prepared_receptor(tmp_path_factory, examples_dir):
    """Prepared receptor shared across the whole test session (slow op)."""
    from dockmeow.core.receptor import prepare_receptor

    p = examples_dir / "1AKE_with_ATP.pdb"
    if not p.exists():
        pytest.skip("Example PDB not found")

    work = tmp_path_factory.mktemp("receptor_prep")
    return prepare_receptor(p, work)


@pytest.fixture(scope="session")
def prepared_ligand(tmp_path_factory, aspirin_smiles):
    """Prepared aspirin ligand shared across the whole test session."""
    from dockmeow.core.ligand import prepare_ligand_from_smiles

    work = tmp_path_factory.mktemp("ligand_prep")
    return prepare_ligand_from_smiles(aspirin_smiles, "aspirin", work)
