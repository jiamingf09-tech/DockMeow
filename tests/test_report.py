"""Tests for core.report — PDF report generation."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from dockmeow.core.report import ReportData, generate_pdf_report


@pytest.fixture(scope="module")
def report_data(prepared_receptor, prepared_ligand):
    """Minimal ReportData for testing; uses a mock DockingResult."""
    from dockmeow.core.docking import DockingResult, DockingConfig
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
        license_id="TEST-0001",
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        watermark=False,
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

    def test_watermark_version_produces_pdf(self, tmp_path, report_data):
        import dataclasses
        trial_data = dataclasses.replace(report_data, watermark=True)
        out = tmp_path / "trial_report.pdf"
        generate_pdf_report(trial_data, out, pose_screenshots=[])
        assert out.exists()
        assert out.read_bytes()[:4] == b"%PDF"

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
