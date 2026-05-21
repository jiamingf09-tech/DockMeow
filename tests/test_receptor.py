"""Tests for core.receptor — receptor preparation pipeline."""

from __future__ import annotations

import pytest

from dockmeow.core.exceptions import ReceptorPreparationError
from dockmeow.core.receptor import _parse_hetero_groups, prepare_receptor


class TestParseHeteroGroups:
    def test_detects_ap5_as_likely_ligand(self, example_receptor):
        text = example_receptor.read_text(encoding="utf-8", errors="replace")
        groups = _parse_hetero_groups(text)
        resnames = {g.resname for g in groups}
        assert "AP5" in resnames or "AAP5" in resnames or "BAP5" in resnames

    def test_water_flagged_correctly(self, example_receptor):
        text = example_receptor.read_text(encoding="utf-8", errors="replace")
        groups = _parse_hetero_groups(text)
        waters = [g for g in groups if g.is_water]
        assert len(waters) > 0

    def test_is_likely_ligand_atom_range(self):
        """is_likely_ligand requires 5-150 heavy atoms and not water/ion."""
        fake_pdb = "\n".join(
            f"HETATM{i+1:5d}  C   LIG A   1    "
            f"   1.000   2.000   3.000  1.00  0.00           C"
            for i in range(20)
        )
        groups = _parse_hetero_groups(fake_pdb)
        assert len(groups) == 1
        assert groups[0].is_likely_ligand is True

    def test_ion_not_likely_ligand(self):
        fake_pdb = (
            "HETATM    1 MG    MG A 501       1.000   2.000   3.000  "
            "1.00  0.00          MG"
        )
        groups = _parse_hetero_groups(fake_pdb)
        assert len(groups) == 1
        assert groups[0].is_ion is True
        assert groups[0].is_likely_ligand is False


class TestPrepareReceptor:
    def test_returns_receptor_info(self, prepared_receptor):
        from dockmeow.core.receptor import ReceptorInfo
        assert isinstance(prepared_receptor, ReceptorInfo)

    def test_pdbqt_exists(self, prepared_receptor):
        assert prepared_receptor.pdbqt_path.exists()
        assert prepared_receptor.pdbqt_path.stat().st_size > 0

    def test_pdbqt_has_atom_records(self, prepared_receptor):
        text = prepared_receptor.pdbqt_path.read_text()
        atom_lines = [ln for ln in text.splitlines() if ln.startswith("ATOM")]
        assert len(atom_lines) > 10

    def test_chains_populated(self, prepared_receptor):
        assert len(prepared_receptor.chains) > 0

    def test_residues_counted(self, prepared_receptor):
        assert prepared_receptor.n_residues > 50

    def test_hetero_groups_from_original(self, prepared_receptor):
        # hetero_groups parsed from raw PDB before stripping
        assert isinstance(prepared_receptor.hetero_groups, list)

    def test_chinese_path_safe_name(self, tmp_path, example_receptor):
        """Files with Chinese characters in stem are handled via safe_name."""
        chinese_pdb = tmp_path / "蛋白质_test.pdb"
        import shutil
        shutil.copy2(example_receptor, chinese_pdb)
        work = tmp_path / "work"
        result = prepare_receptor(chinese_pdb, work)
        assert result.pdbqt_path.exists()

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ReceptorPreparationError):
            prepare_receptor(tmp_path / "nonexistent.pdb", tmp_path / "work")

    def test_empty_pdbqt_retry_progress_is_monotonic(self, tmp_path, monkeypatch):
        """Compatibility retry must not make the GUI progress bar jump backward."""
        from dockmeow.core import receptor as receptor_mod

        pdb = tmp_path / "mini.pdb"
        fixed_atom = (
            "ATOM      1  N   ALA A   1      11.104  13.207  14.099  1.00 20.00           N\n"
            "END\n"
        )
        pdb.write_text(fixed_atom, encoding="utf-8")

        def fake_run_pdbfixer(input_pdb, output_pdb, add_missing_atoms, ph, cb):
            if cb:
                cb("受体准备", 10, "PDBFixer")
                cb("受体准备", 40, "PDBFixer done")
            output_pdb.write_text(fixed_atom, encoding="utf-8")
            return []

        calls = {"pdbqt": 0}

        def fake_pdb_to_pdbqt(input_pdb, output_pdbqt, cb, original_pdb=None):
            calls["pdbqt"] += 1
            if cb:
                cb("受体准备", 70, "meeko")
                cb("受体准备", 90, "meeko done")
            output_pdbqt.write_text(
                "" if calls["pdbqt"] == 1 else "RECEPTOR\n",
                encoding="utf-8",
            )
            return []

        monkeypatch.setattr(receptor_mod, "_run_pdbfixer", fake_run_pdbfixer)
        monkeypatch.setattr(receptor_mod, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

        progress: list[int] = []
        info = receptor_mod.prepare_receptor(
            pdb,
            tmp_path / "work",
            progress_callback=lambda _stage, pct, _msg: progress.append(int(pct)),
        )

        assert info.pdbqt_path.read_text(encoding="utf-8") == "RECEPTOR\n"
        assert calls["pdbqt"] == 2
        assert progress == sorted(progress)
        assert progress[-1] == 100

    def test_missing_pdbfixer_uses_raw_pdb_fallback(self, tmp_path, monkeypatch):
        """Windows builds without OpenMM/PDBFixer still prepare basic receptors."""
        from dockmeow.core import receptor as receptor_mod

        pdb = tmp_path / "mini.pdb"
        pdb.write_text(
            "ATOM      1  N   ALA A   1      11.104  13.207  14.099  1.00 20.00           N\n"
            "HETATM    2  O   HOH A   2      12.000  13.000  14.000  1.00 20.00           O\n"
            "END\n",
            encoding="utf-8",
        )

        def fake_run_pdbfixer(input_pdb, output_pdb, add_missing_atoms, ph, cb):
            raise ModuleNotFoundError("No module named 'openmm'")

        def fake_pdb_to_pdbqt(input_pdb, output_pdbqt, cb, original_pdb=None):
            text = input_pdb.read_text(encoding="utf-8")
            assert "HOH" not in text
            output_pdbqt.write_text("RECEPTOR\n", encoding="utf-8")
            return []

        monkeypatch.setattr(receptor_mod, "_run_pdbfixer", fake_run_pdbfixer)
        monkeypatch.setattr(receptor_mod, "_pdb_to_pdbqt", fake_pdb_to_pdbqt)

        info = receptor_mod.prepare_receptor(pdb, tmp_path / "work")

        assert info.pdbqt_path.read_text(encoding="utf-8") == "RECEPTOR\n"
        assert any("OpenMM/PDBFixer" in warning for warning in info.warnings)
        assert info.waters_removed == 1
