import sys
import types
from pathlib import Path

from dockmeow.core import docking
from dockmeow.core.docking import DockingConfig


def test_python_vina_backend_reads_rmsd_from_written_poses(tmp_path, monkeypatch) -> None:
    receptor = tmp_path / "receptor.pdbqt"
    ligand = tmp_path / "ligand.pdbqt"
    receptor.write_text("RECEPTOR\n", encoding="utf-8")
    ligand.write_text("LIGAND\n", encoding="utf-8")

    class FakeVina:
        def __init__(self, **_kwargs):
            pass

        def set_receptor(self, _path):
            pass

        def set_ligand_from_file(self, _path):
            pass

        def compute_vina_maps(self, **_kwargs):
            pass

        def dock(self, **_kwargs):
            pass

        def write_poses(self, path, **_kwargs):
            Path(path).write_text(
                "REMARK VINA RESULT:    -7.100      0.000      0.000\n"
                "REMARK VINA RESULT:    -6.500      2.300      3.400\n",
                encoding="utf-8",
            )

        def energies(self, **_kwargs):
            return [[-7.1, -5.2, -1.4], [-6.5, -4.8, -1.1]]

    monkeypatch.setitem(sys.modules, "vina", types.SimpleNamespace(Vina=FakeVina))
    monkeypatch.setenv("DOCKMEOW_VINA_BACKEND", "python")
    monkeypatch.setattr(
        docking,
        "_pdbqt_to_sdf",
        lambda _input, output: output.write_text("", encoding="utf-8"),
    )

    result = docking.run_docking(
        DockingConfig(
            receptor_pdbqt=receptor,
            ligand_pdbqt=ligand,
            center=(0, 0, 0),
            size=(15, 15, 15),
            num_modes=2,
        )
    )

    assert result.scores == [-7.1, -6.5]
    assert result.rmsd_lb == [0.0, 2.3]
    assert result.rmsd_ub == [0.0, 3.4]
