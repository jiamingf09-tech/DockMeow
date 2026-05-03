"""Tests for core.docking — Vina docking execution."""

from __future__ import annotations

import pytest

from dockmeow.core.docking import DockingConfig, run_docking, DockingResult
from dockmeow.core.exceptions import DockingExecutionError


@pytest.fixture(scope="module")
def docking_result(tmp_path_factory, prepared_receptor, prepared_ligand):
    """Run one docking job (exhaustiveness=4 for speed); shared across module."""
    from dockmeow.core.pocket import detect_pockets
    import shutil

    pockets = detect_pockets(prepared_receptor)
    pocket = pockets[0]

    work = tmp_path_factory.mktemp("docking")
    lig_copy = work / prepared_ligand.pdbqt_path.name
    shutil.copy2(prepared_ligand.pdbqt_path, lig_copy)

    config = DockingConfig(
        receptor_pdbqt=prepared_receptor.pdbqt_path,
        ligand_pdbqt=lig_copy,
        center=pocket.center,
        size=pocket.size,
        exhaustiveness=4,   # fast for testing
        num_modes=5,
        seed=42,
    )
    return run_docking(config)


class TestRunDocking:
    def test_returns_docking_result(self, docking_result):
        assert isinstance(docking_result, DockingResult)

    def test_scores_nonempty(self, docking_result):
        assert len(docking_result.scores) > 0

    def test_best_score_is_negative(self, docking_result):
        """Valid docking scores should be negative kcal/mol."""
        assert docking_result.scores[0] < 0.0

    def test_scores_sorted_ascending(self, docking_result):
        """Best (most negative) score is first."""
        assert docking_result.scores == sorted(docking_result.scores)

    def test_scores_in_reasonable_range(self, docking_result):
        """Typical docking scores are between -15 and 0 kcal/mol."""
        for score in docking_result.scores:
            assert -20.0 < score < 0.0

    def test_poses_pdbqt_exists(self, docking_result):
        assert docking_result.poses_pdbqt.exists()
        assert docking_result.poses_pdbqt.stat().st_size > 0

    def test_poses_sdf_exists(self, docking_result):
        assert docking_result.poses_sdf.exists()

    def test_runtime_positive(self, docking_result):
        assert docking_result.runtime_seconds > 0

    def test_rmsd_lists_match_scores(self, docking_result):
        assert len(docking_result.rmsd_lb) == len(docking_result.scores)
        assert len(docking_result.rmsd_ub) == len(docking_result.scores)

    def test_invalid_receptor_raises(self, tmp_path, prepared_ligand):
        fake_pdbqt = tmp_path / "fake.pdbqt"
        fake_pdbqt.write_text("this is not a valid pdbqt file\n")
        config = DockingConfig(
            receptor_pdbqt=fake_pdbqt,
            ligand_pdbqt=prepared_ligand.pdbqt_path,
            center=(0.0, 0.0, 0.0),
            size=(20.0, 20.0, 20.0),
            exhaustiveness=4,
        )
        with pytest.raises((DockingExecutionError, Exception)):
            run_docking(config)
