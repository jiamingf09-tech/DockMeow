"""Tests for core.results — pose export utilities."""

from __future__ import annotations

import pytest

from dockmeow.core.results import export_poses_pdb, split_poses_to_sdf


class TestSplitPosesToSdf:
    def test_returns_list_of_paths(self, tmp_path, docking_result):
        paths = split_poses_to_sdf(docking_result, tmp_path / "split")
        assert isinstance(paths, list)

    def test_each_file_exists(self, tmp_path, docking_result):
        paths = split_poses_to_sdf(docking_result, tmp_path / "split")
        for p in paths:
            assert p.exists()

    def test_files_are_valid_sdf(self, tmp_path, docking_result):
        paths = split_poses_to_sdf(docking_result, tmp_path / "split")
        for p in paths:
            content = p.read_text()
            assert "$$$$" in content


class TestExportPosesPdb:
    def test_returns_list_of_paths(self, tmp_path, docking_result):
        paths = export_poses_pdb(docking_result, tmp_path / "pdb")
        assert isinstance(paths, list)

    def test_each_file_exists(self, tmp_path, docking_result):
        paths = export_poses_pdb(docking_result, tmp_path / "pdb")
        for p in paths:
            assert p.exists()

    def test_pdb_files_have_atom_records(self, tmp_path, docking_result):
        paths = export_poses_pdb(docking_result, tmp_path / "pdb")
        for p in paths:
            content = p.read_text()
            assert "ATOM" in content or "HETATM" in content


# Provide docking_result fixture here too (re-use from test_docking via conftest injection)
@pytest.fixture
def docking_result(prepared_receptor, prepared_ligand, tmp_path):
    import shutil

    from dockmeow.core.docking import DockingConfig, run_docking
    from dockmeow.core.pocket import detect_pockets

    pocket = detect_pockets(prepared_receptor)[0]
    lig_copy = tmp_path / prepared_ligand.pdbqt_path.name
    shutil.copy2(prepared_ligand.pdbqt_path, lig_copy)

    config = DockingConfig(
        receptor_pdbqt=prepared_receptor.pdbqt_path,
        ligand_pdbqt=lig_copy,
        center=pocket.center,
        size=pocket.size,
        exhaustiveness=4,
        num_modes=3,
        seed=42,
    )
    return run_docking(config)
