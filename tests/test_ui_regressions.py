"""Regression tests for GUI flow bugs fixed after the 1SVC/Ailanthone audit."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeViewer(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.loaded_receptors: list[Path] = []
        self.boxes: list[object] = []
        self.pocket_groups: list[tuple[list[object], object | None]] = []

    def load_receptor(self, pdb_path: Path) -> None:
        self.loaded_receptors.append(Path(pdb_path))

    def show_box(self, pocket_or_center, size=None) -> None:
        self.boxes.append(pocket_or_center if size is None else (pocket_or_center, size))

    def show_pockets(self, pockets: list[object], selected: object | None = None) -> None:
        self.pocket_groups.append((list(pockets), selected))


def _patch_viewers(monkeypatch) -> None:
    import dockmeow.ui.pages.page_pocket as page_pocket
    import dockmeow.ui.pages.page_receptor as page_receptor
    import dockmeow.ui.pages.page_results as page_results

    monkeypatch.setattr(page_receptor, "Viewer3D", FakeViewer)
    monkeypatch.setattr(page_pocket, "Viewer3D", FakeViewer)
    monkeypatch.setattr(page_results, "Viewer3D", FakeViewer)


def test_receptor_page_uses_prepared_pdb_path(qapp, tmp_path, monkeypatch) -> None:
    _patch_viewers(monkeypatch)

    from dockmeow.core.receptor import HeteroGroup
    from dockmeow.ui.pages.page_receptor import ReceptorPage

    raw_pdb = tmp_path / "1SVC.pdb"
    clean_pdb = tmp_path / "1SVC_clean.pdb"
    raw_pdb.write_text("raw", encoding="utf-8")
    clean_pdb.write_text("clean", encoding="utf-8")

    page = ReceptorPage()
    page._pdb_path = raw_pdb
    emitted: list[tuple[object, Path]] = []
    page.receptor_ready.connect(lambda info, path: emitted.append((info, Path(path))))

    info = SimpleNamespace(
        pdb_path=clean_pdb,
        hetero_groups=[
            HeteroGroup("HOH", "D", 101, 1, True, False, False),
            HeteroGroup("MG", "A", 1, 1, False, True, False),
        ],
        warnings=[],
        nucleic_acid_chains=["D"],
    )

    page._on_done(info)

    assert page._viewer.loaded_receptors == [clean_pdb]
    assert emitted == [(info, clean_pdb)]
    hetero_items = [
        page._hetero_list.item(i).text() for i in range(page._hetero_list.count())
    ]
    assert all("chain=D" not in item for item in hetero_items)
    assert any("chain=A" in item for item in hetero_items)


def test_ligand_ready_does_not_auto_navigate(qapp, tmp_path, monkeypatch) -> None:
    _patch_viewers(monkeypatch)

    import dockmeow.ui.pages.page_pocket as page_pocket
    from dockmeow.ui.main_window import MainWindow

    set_receptor_calls: list[Path] = []
    monkeypatch.setattr(
        page_pocket.PocketPage,
        "set_receptor",
        lambda self, receptor_info, pdb_path: set_receptor_calls.append(Path(pdb_path)),
    )

    clean_pdb = tmp_path / "1SVC_clean.pdb"
    clean_pdb.write_text("clean", encoding="utf-8")
    win = MainWindow(None)
    receptor_info = SimpleNamespace(pdb_path=clean_pdb, pdbqt_path=tmp_path / "r.pdbqt")
    ligand_info = SimpleNamespace(pdbqt_path=tmp_path / "l.pdbqt")

    win._on_receptor_ready(receptor_info, clean_pdb)
    win._go_to_page(1)
    win._on_ligand_ready(ligand_info)

    assert win._stack.currentIndex() == 1
    assert win._next_btn.isEnabled()
    assert set_receptor_calls == [clean_pdb]

    win._on_next_clicked()
    assert win._stack.currentIndex() == 2


def test_pocket_selection_highlights_without_signal(qapp, monkeypatch) -> None:
    _patch_viewers(monkeypatch)

    from dockmeow.core.pocket import Pocket
    from dockmeow.ui.pages.page_pocket import PocketPage

    page = PocketPage()
    emitted: list[object] = []
    page.pocket_selected.connect(emitted.append)
    p1 = Pocket(1, (1, 2, 3), (20, 20, 20), 10.0, source="fpocket", label="口袋 1")
    p2 = Pocket(2, (4, 5, 6), (18, 18, 18), 8.0, source="fpocket", label="口袋 2")

    page._on_pockets([p1, p2])
    assert page.get_selected_pocket() == p1
    assert emitted == []
    assert page._viewer.pocket_groups[-1] == ([p1, p2], p1)

    page._on_card_selected(p2)
    assert page.get_selected_pocket() == p2
    assert emitted == []
    assert page._viewer.pocket_groups[-1] == ([p1, p2], p2)


def test_custom_box_creates_custom_pocket(qapp, monkeypatch) -> None:
    _patch_viewers(monkeypatch)

    from PySide6.QtWidgets import QDialog

    import dockmeow.ui.dialogs.custom_box_dialog as custom_box_dialog
    from dockmeow.core.pocket import Pocket
    from dockmeow.ui.pages.page_pocket import PocketPage

    class FakeDialog:
        def __init__(self, default_center, default_size, parent=None) -> None:
            self.default_center = default_center
            self.default_size = default_size

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_box(self):
            return (10.0, 20.0, 30.0), (25.0, 25.0, 25.0)

    monkeypatch.setattr(custom_box_dialog, "CustomBoxDialog", FakeDialog)

    page = PocketPage()
    initial = Pocket(1, (1, 2, 3), (20, 20, 20), 10.0, source="fpocket", label="口袋 1")
    page._on_pockets([initial])
    page._on_custom_box()

    selected = page.get_selected_pocket()
    assert selected is not None
    assert selected.source == "custom"
    assert selected.label == "自定义盒子"
    assert selected.center == (10.0, 20.0, 30.0)
    assert selected.size == (25.0, 25.0, 25.0)
    assert page._viewer.boxes[-1] == selected


def test_pocket_candidate_column_has_room_to_read(qapp, monkeypatch) -> None:
    _patch_viewers(monkeypatch)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSizePolicy

    from dockmeow.core.pocket import Pocket
    from dockmeow.ui.pages.page_pocket import PocketPage

    page = PocketPage()
    p1 = Pocket(1, (1, 2, 3), (20, 20, 20), 10.0, source="fpocket", label="口袋 1")
    page._on_pockets([p1])

    left_panel = page._splitter.widget(0)
    viewer_panel = page._splitter.widget(1)

    assert left_panel.minimumWidth() >= 360
    assert left_panel.sizePolicy().horizontalStretch() == 2
    assert viewer_panel.sizePolicy().horizontalStretch() == 3
    assert page._scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert viewer_panel is page._viewer
    assert page._cards[0].sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


def test_viewer_box_rendering_uses_orange_fill_and_wireframe() -> None:
    from dockmeow.ui.widgets.viewer_3d import _HTML

    assert "#FF9500" in _HTML
    assert "#888888" in _HTML
    assert "wireframe:false" in _HTML
    assert "wireframe:true,linewidth:lineWidth" in _HTML


def test_activation_dialog_shows_same_machine_id_source(qapp, monkeypatch) -> None:
    import dockmeow.ui.dialogs.activation_dialog as activation_dialog

    monkeypatch.setattr(
        activation_dialog, "get_machine_id", lambda: "DM-12345678-90ABCDEF-11223344"
    )

    dlg = activation_dialog.ActivationDialog()

    assert dlg._machine_id_value.text() == "DM-12345678-90ABCDEF-11223344"
    assert dlg._copy_machine_id_btn.isEnabled()


def test_activation_dialog_copy_button_copies_machine_id(qapp, monkeypatch) -> None:
    import dockmeow.ui.dialogs.activation_dialog as activation_dialog

    machine_id = "DM-AAAABBBB-CCCCDDDD-EEEEFFFF"
    monkeypatch.setattr(activation_dialog, "get_machine_id", lambda: machine_id)

    dlg = activation_dialog.ActivationDialog()
    qapp.clipboard().clear()

    dlg._copy_machine_id_btn.click()

    assert qapp.clipboard().text() == machine_id
