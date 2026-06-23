import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DOCKMEOW_VIEWER_BACKEND", "native")

from PySide6.QtWidgets import QApplication

from dockmeow.core.receptor import HeteroGroup, ReceptorInfo
from dockmeow.ui.pages.page_receptor import ReceptorPage

PDB_TEXT = """\
ATOM      1  N   GLY A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C
ATOM      3  C   GLY A   1       1.500   1.000   0.000  1.00 20.00           C
ATOM      4  O   GLY A   1       1.500   2.000   0.000  1.00 20.00           O
TER
END
"""


def test_receptor_page_hides_waters_and_renders_prepared_model(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    pdb_path = tmp_path / "prepared.pdb"
    pdbqt_path = tmp_path / "prepared.pdbqt"
    pdb_path.write_text(PDB_TEXT, encoding="utf-8")
    pdbqt_path.write_text(PDB_TEXT, encoding="utf-8")

    info = ReceptorInfo(
        pdb_path=pdb_path,
        pdbqt_path=pdbqt_path,
        chains=["A"],
        n_residues=1,
        hetero_groups=[
            HeteroGroup("HOH", "A", 10, 1, True, False, False),
            HeteroGroup("HOH", "A", 11, 1, True, False, False),
            HeteroGroup("ASP", "A", 900, 13, False, False, True),
        ],
    )

    page = ReceptorPage()
    page.resize(1200, 700)
    page.show()
    page._on_done(info)
    app.processEvents()

    assert page._hetero_list.count() == 1
    assert page._hetero_list.item(0).text().startswith("★ ASP")
    assert "已隐藏 2 个水分子" in page._hetero_label.text()
    assert not page._warnings.isVisible()
    assert page._viewer is not None
    assert page._viewer.viewer_status()["atoms"] == 4
    assert page._viewer_layout.currentWidget() is page._viewer

    page.close()
    app.processEvents()
