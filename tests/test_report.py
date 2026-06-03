"""Tests for core.report — PDF report generation."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from dockmeow.core import report as report_module
from dockmeow.core.report import ReportData, generate_pdf_report


@pytest.fixture(scope="module")
def report_data(prepared_receptor, prepared_ligand):
    """Minimal ReportData for testing; uses a mock DockingResult."""
    from dockmeow.core.docking import DockingConfig, DockingResult
    from dockmeow.core.pocket import detect_pockets

    pocket = detect_pockets(prepared_receptor)[0]

    mock_result = DockingResult(
        poses_pdbqt=Path("/nonexistent/poses.pdbqt"),
        poses_sdf=Path("/nonexistent/poses.sdf"),
        scores=[-7.5, -7.2, -6.8],
        rmsd_lb=[0.0, 1.2, 1.8],
        rmsd_ub=[0.0, 2.1, 3.0],
        runtime_seconds=42.0,
        config=DockingConfig(
            receptor_pdbqt=prepared_receptor.pdbqt_path,
            ligand_pdbqt=prepared_ligand.pdbqt_path,
            center=pocket.center,
            size=pocket.size,
            exhaustiveness=16,
        ),
    )

    return ReportData(
        project_name="test_project",
        receptor=prepared_receptor,
        ligand=prepared_ligand,
        pocket=pocket,
        result=mock_result,
        user_email="test@dockmeow.local",
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


class TestGeneratePdfReport:
    def test_pdf_file_created(self, tmp_path, report_data):
        out = tmp_path / "report.pdf"
        generate_pdf_report(report_data, out, pose_screenshots=[])
        assert out.exists()

    def test_pdf_is_valid(self, tmp_path, report_data):
        out = tmp_path / "report.pdf"
        generate_pdf_report(report_data, out, pose_screenshots=[])
        header = out.read_bytes()[:4]
        assert header == b"%PDF", f"Not a valid PDF: {header!r}"

    def test_pdf_has_content(self, tmp_path, report_data):
        out = tmp_path / "report.pdf"
        generate_pdf_report(report_data, out, pose_screenshots=[])
        assert out.stat().st_size > 5_000  # reasonable minimum size

    def test_missing_screenshots_handled(self, tmp_path, report_data):
        """Non-existent screenshot paths are silently skipped."""
        fake_screens = [Path("/nonexistent/screenshot.png")]
        out = tmp_path / "report_no_screens.pdf"
        generate_pdf_report(report_data, out, pose_screenshots=fake_screens)
        assert out.exists()

    def test_output_dir_created_if_missing(self, tmp_path, report_data):
        out = tmp_path / "nested" / "dir" / "report.pdf"
        generate_pdf_report(report_data, out, pose_screenshots=[])
        assert out.exists()

    def test_chinese_text_readable(self, tmp_path, report_data):
        """CJK characters must be extractable (not rendered as squares ■)."""
        pdfplumber = pytest.importorskip("pdfplumber")
        out = tmp_path / "report_zh.pdf"
        generate_pdf_report(report_data, out, pose_screenshots=[])
        with pdfplumber.open(out) as pdf:
            text = " ".join(page.extract_text() or "" for page in pdf.pages)
        required = ["受体", "结合能", "免责声明", "分子对接分析报告", "一键对接"]
        missing = [kw for kw in required if kw not in text]
        assert not missing, (
            f"Chinese keywords not found in PDF (font may be missing/invalid): {missing}\n"
            f"Extracted text sample: {text[:500]!r}"
        )


class TestGenerateReport:
    def _capture_report_data(self, monkeypatch):
        captured = {}

        def fake_generate_pdf_report(data, output_path, pose_screenshots):
            captured["data"] = data
            captured["screenshots"] = pose_screenshots
            return Path(output_path)

        monkeypatch.setattr(
            report_module, "generate_pdf_report", fake_generate_pdf_report
        )
        return captured

    def _result_with_source(self, prepared_receptor, prepared_ligand, source: str):
        from dockmeow.core.docking import DockingConfig, DockingResult

        cfg = DockingConfig(
            receptor_pdbqt=prepared_receptor.pdbqt_path,
            ligand_pdbqt=prepared_ligand.pdbqt_path,
            center=(1.0, 2.0, 3.0),
            size=(20.0, 21.0, 22.0),
            pocket_source=source,
            exhaustiveness=8,
        )
        return DockingResult(
            poses_pdbqt=Path("/nonexistent/poses.pdbqt"),
            poses_sdf=Path("/nonexistent/poses.sdf"),
            scores=[-7.5],
            rmsd_lb=[0.0],
            rmsd_ub=[0.0],
            runtime_seconds=12.0,
            config=cfg,
        )

    def test_generate_report_preserves_pocket_source(
        self, tmp_path, prepared_receptor, prepared_ligand, monkeypatch
    ):
        captured = self._capture_report_data(monkeypatch)
        result = self._result_with_source(prepared_receptor, prepared_ligand, "fpocket")

        report_module.generate_report(
            prepared_receptor,
            prepared_ligand,
            result,
            tmp_path / "report.pdf",
            user_email="test@dockmeow.local",
        )

        assert captured["data"].pocket.source == "fpocket"

    def test_windows_report_notice_hidden_when_fpocket_binary_exists(
        self, tmp_path, prepared_receptor, prepared_ligand, monkeypatch
    ):
        captured = self._capture_report_data(monkeypatch)
        fake_fpocket = tmp_path / "fpocket.exe"
        fake_fpocket.write_text("", encoding="utf-8")
        monkeypatch.setattr(report_module.sys, "platform", "win32")
        monkeypatch.setattr(report_module, "fpocket_binary", lambda: fake_fpocket)
        result = self._result_with_source(prepared_receptor, prepared_ligand, "config")

        report_module.generate_report(
            prepared_receptor,
            prepared_ligand,
            result,
            tmp_path / "report.pdf",
            user_email="test@dockmeow.local",
        )

        assert captured["data"].os_warning == ""

    def test_windows_report_notice_describes_missing_fpocket_binary(
        self, tmp_path, prepared_receptor, prepared_ligand, monkeypatch
    ):
        captured = self._capture_report_data(monkeypatch)
        monkeypatch.setattr(report_module.sys, "platform", "win32")
        monkeypatch.setattr(report_module, "fpocket_binary", lambda: tmp_path / "missing.exe")
        result = self._result_with_source(prepared_receptor, prepared_ligand, "config")

        report_module.generate_report(
            prepared_receptor,
            prepared_ligand,
            result,
            tmp_path / "report.pdf",
            user_email="test@dockmeow.local",
        )

        warning = captured["data"].os_warning
        assert "未检测到可用 fpocket" in warning
        assert "暂不支持" not in warning
