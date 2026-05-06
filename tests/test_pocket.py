"""Tests for core.pocket — binding pocket detection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dockmeow.core.pocket import (
    Pocket,
    _run_fpocket,
    detect_pockets,
    whole_protein_box,
)
from dockmeow.utils.paths import fpocket_binary


class TestWholeProteinBox:
    def test_returns_pocket(self, prepared_receptor):
        pocket = whole_protein_box(prepared_receptor)
        assert isinstance(pocket, Pocket)

    def test_source_is_whole(self, prepared_receptor):
        pocket = whole_protein_box(prepared_receptor)
        assert pocket.source == "whole"

    def test_center_is_float_triple(self, prepared_receptor):
        pocket = whole_protein_box(prepared_receptor)
        assert len(pocket.center) == 3
        assert all(isinstance(v, float) for v in pocket.center)

    def test_size_is_positive(self, prepared_receptor):
        pocket = whole_protein_box(prepared_receptor)
        assert all(v > 0 for v in pocket.size)

    def test_padding_applied(self, prepared_receptor):
        p5 = whole_protein_box(prepared_receptor, padding=5.0)
        p10 = whole_protein_box(prepared_receptor, padding=10.0)
        # Each dimension should differ by ~10 Å (2 * 5 padding)
        for a, b in zip(p5.size, p10.size):
            assert abs(b - a - 10.0) < 0.5


class TestDetectPockets:
    def test_always_returns_nonempty_list(self, prepared_receptor):
        pockets = detect_pockets(prepared_receptor)
        assert len(pockets) >= 1

    def test_cocrystal_pocket_detected(self, prepared_receptor, example_receptor):
        """1AKE has AP5, should give source=cocrystal."""
        pockets = detect_pockets(prepared_receptor, original_pdb=example_receptor)
        sources = [p.source for p in pockets]
        assert "cocrystal" in sources

    def test_cocrystal_pocket_is_first(self, prepared_receptor, example_receptor):
        pockets = detect_pockets(prepared_receptor, original_pdb=example_receptor)
        assert pockets[0].source == "cocrystal"

    def test_cocrystal_box_size(self, prepared_receptor, example_receptor):
        """Co-crystal box should be 22.5 Å on all sides."""
        pockets = detect_pockets(prepared_receptor, original_pdb=example_receptor)
        cocrystal = next(p for p in pockets if p.source == "cocrystal")
        for dim in cocrystal.size:
            assert abs(dim - 22.5) < 0.01

    def test_fpocket_skipped_gracefully_when_missing(self, prepared_receptor):
        """When fpocket binary is absent, falls back to whole-protein."""
        if fpocket_binary().exists():
            pytest.skip("fpocket binary present, skipping fallback test")
        pockets = detect_pockets(prepared_receptor)
        assert any(p.source == "whole" for p in pockets)

    @pytest.mark.skipif(
        not fpocket_binary().exists(),
        reason="fpocket binary not provided",
    )
    def test_fpocket_size_clamped(self, prepared_receptor):
        """fpocket box dimensions stay within [15, 30] Å."""
        pockets = detect_pockets(prepared_receptor)
        fp_pockets = [p for p in pockets if p.source == "fpocket"]
        for p in fp_pockets:
            for dim in p.size:
                assert 15.0 <= dim <= 30.0


# ---------------------------------------------------------------------------
# fpocket mocked tests — these run without the actual binary
# ---------------------------------------------------------------------------

def _make_pocket_pdb(path: Path, coords: list[tuple[float, float, float]]) -> None:
    """Write a minimal PDB file at `path` with ATOM records for each coord."""
    lines = []
    for i, (x, y, z) in enumerate(coords, start=1):
        lines.append(
            f"ATOM  {i:5d}  C   STP C   1    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


@pytest.fixture()
def fake_receptor_pdb(tmp_path: Path) -> Path:
    """Minimal PDB file usable as a receptor path in _run_fpocket."""
    p = tmp_path / "fake_receptor.pdb"
    p.write_text(
        "ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00  0.00           C\n"
        "END\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def fake_binary(tmp_path: Path) -> Path:
    """Zero-byte file that satisfies `.exists()` in fpocket_binary check."""
    b = tmp_path / "fpocket"
    b.touch()
    return b


class TestFpocketMocked:
    """fpocket code paths tested with mocked subprocess and fake output files."""

    def test_fpocket_output_parsing(
        self, tmp_path: Path, fake_receptor_pdb: Path, fake_binary: Path
    ) -> None:
        """_run_fpocket parses pocket*_atm.pdb files and returns Pocket objects."""
        out_dir = tmp_path / "fake_receptor_out"
        out_dir.mkdir()
        _make_pocket_pdb(
            out_dir / "pocket1_atm.pdb",
            [(10.0, 10.0, 10.0), (20.0, 20.0, 20.0)],
        )
        _make_pocket_pdb(
            out_dir / "pocket2_atm.pdb",
            [(5.0, 5.0, 5.0), (8.0, 8.0, 8.0)],
        )

        with patch("dockmeow.utils.paths.fpocket_binary", return_value=fake_binary), \
             patch("dockmeow.core.pocket.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            pockets = _run_fpocket(fake_receptor_pdb, tmp_path)

        assert len(pockets) == 2
        assert all(p.source == "fpocket" for p in pockets)
        assert pockets[0].pocket_id == 1
        assert pockets[1].pocket_id == 2
        # Centre of pocket1: midpoint of (10,10,10)-(20,20,20) = (15,15,15)
        for v in pockets[0].center:
            assert abs(v - 15.0) < 0.01

    def test_fpocket_subprocess_failure_falls_back_to_whole(
        self, prepared_receptor, fake_binary: Path
    ) -> None:
        """Non-zero returncode from fpocket triggers whole-protein fallback."""
        with patch("dockmeow.utils.paths.fpocket_binary", return_value=fake_binary), \
             patch("dockmeow.core.pocket.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="fpocket: error"
            )
            pockets = detect_pockets(prepared_receptor)

        assert len(pockets) >= 1
        assert pockets[-1].source == "whole"
        assert not any(p.source == "fpocket" for p in pockets)

    def test_fpocket_binary_missing_falls_back_to_whole(
        self, prepared_receptor, tmp_path: Path
    ) -> None:
        """Missing binary (FileNotFoundError) triggers whole-protein fallback."""
        nonexistent = tmp_path / "no_such_fpocket"
        with patch("dockmeow.utils.paths.fpocket_binary", return_value=nonexistent):
            pockets = detect_pockets(prepared_receptor)

        assert len(pockets) >= 1
        assert all(p.source in ("whole",) for p in pockets)

    def test_fpocket_empty_output_falls_back_to_whole(
        self, prepared_receptor, fake_binary: Path, tmp_path: Path
    ) -> None:
        """fpocket succeeds but produces no pocket*.pdb files → whole-protein fallback."""
        with patch("dockmeow.utils.paths.fpocket_binary", return_value=fake_binary), \
             patch("dockmeow.core.pocket.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # No pocket*_atm.pdb files created → _run_fpocket returns []
            pockets = detect_pockets(prepared_receptor)

        assert len(pockets) >= 1
        assert pockets[-1].source == "whole"
