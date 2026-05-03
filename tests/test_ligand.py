"""Tests for core.ligand — ligand preparation pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from dockmeow.core.ligand import prepare_ligand_from_smiles, prepare_ligand_from_file, LigandInfo
from dockmeow.core.exceptions import LigandPreparationError


class TestPrepareLigandFromSmiles:
    def test_aspirin_returns_ligand_info(self, prepared_ligand):
        assert isinstance(prepared_ligand, LigandInfo)

    def test_pdbqt_exists(self, prepared_ligand):
        assert prepared_ligand.pdbqt_path.exists()
        assert prepared_ligand.pdbqt_path.stat().st_size > 0

    def test_pdbqt_has_atom_records(self, prepared_ligand):
        text = prepared_ligand.pdbqt_path.read_text()
        assert "ATOM" in text or "HETATM" in text

    def test_source_format_is_smiles(self, prepared_ligand):
        assert prepared_ligand.source_format == "smiles"

    def test_n_atoms_correct_aspirin(self, prepared_ligand):
        # Aspirin: C9H8O4 → 13 heavy atoms
        assert prepared_ligand.n_atoms == 13

    def test_n_rotatable_positive(self, prepared_ligand):
        assert prepared_ligand.n_rotatable >= 2

    def test_smiles_roundtrip(self, prepared_ligand):
        assert prepared_ligand.smiles  # non-empty canonical SMILES

    def test_invalid_smiles_raises(self, work_dir):
        with pytest.raises(LigandPreparationError):
            prepare_ligand_from_smiles("not_a_smiles!!!!", "bad", work_dir)

    def test_empty_smiles_raises(self, work_dir):
        with pytest.raises(LigandPreparationError):
            prepare_ligand_from_smiles("", "empty", work_dir)

    def test_complex_molecule(self, work_dir):
        """Methotrexate (many rotatable bonds) should prepare successfully."""
        mtx_smiles = "CN(Cc1cnc2nc(N)nc(N)c2n1)c1ccc(C(=O)N[C@@H](CCC(=O)O)C(=O)O)cc1"
        result = prepare_ligand_from_smiles(mtx_smiles, "methotrexate", work_dir)
        assert result.pdbqt_path.exists()
        assert result.n_atoms > 20


class TestPrepareLigandFromFile:
    def test_sdf_input(self, tmp_path):
        """Generate a test SDF and prepare it."""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        sdf_path = tmp_path / "aspirin.sdf"
        with Chem.SDWriter(str(sdf_path)) as w:
            w.write(mol)
        result = prepare_ligand_from_file(sdf_path, tmp_path / "work")
        assert result.pdbqt_path.exists()
        assert result.source_format == "sdf"

    def test_unsupported_format_raises(self, tmp_path):
        fake = tmp_path / "mol.xyz"
        fake.write_text("fake xyz")
        with pytest.raises(LigandPreparationError, match="不支持"):
            prepare_ligand_from_file(fake, tmp_path / "work")

    def test_corrupt_sdf_raises(self, tmp_path):
        bad = tmp_path / "bad.sdf"
        bad.write_text("this is not a valid SDF file\n$$$$\n")
        with pytest.raises(LigandPreparationError):
            prepare_ligand_from_file(bad, tmp_path / "work")
