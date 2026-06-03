"""PDF report generation using ReportLab.

Report structure:
    1. Cover page  — project name, timestamp, software version
    2. Summary     — receptor / ligand / pocket metadata, score table
    3. 3D views    — up to 3 pose screenshots (PNG paths supplied by GUI layer)
    4. Parameters  — full DockingConfig dump
    5. Disclaimer  — standard scientific disclaimer

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from dockmeow.core.docking import DockingResult
from dockmeow.core.exceptions import DockMeowError
from dockmeow.core.ligand import LigandInfo
from dockmeow.core.pocket import Pocket
from dockmeow.core.receptor import ReceptorInfo
from dockmeow.utils.paths import fpocket_binary, resource_path
from dockmeow.version import __version__

_log = logging.getLogger(__name__)

_FONTS_REGISTERED = False


def _register_chinese_fonts() -> None:
    """Register NotoSansSC OTF fonts with ReportLab (idempotent)."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_dir = resource_path("bundled/fonts")
    regular = font_dir / "NotoSansSC-Regular.ttf"
    bold = font_dir / "NotoSansSC-Bold.ttf"

    if not regular.exists() or not bold.exists():
        _log.warning(
            "NotoSansSC fonts not found at %s — Chinese characters may not render",
            font_dir,
        )
        return

    pdfmetrics.registerFont(TTFont("NotoSansSC", str(regular)))
    pdfmetrics.registerFont(TTFont("NotoSansSC-Bold", str(bold)))
    # Map bold/italic aliases so ParagraphStyle lookups don't fall back to Helvetica
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily(
        "NotoSansSC",
        normal="NotoSansSC",
        bold="NotoSansSC-Bold",
        italic="NotoSansSC",
        boldItalic="NotoSansSC-Bold",
    )
    _FONTS_REGISTERED = True
    _log.debug("NotoSansSC fonts registered")

_DISCLAIMER_ZH = (
    "免责声明：本报告由一键对接（DockMeow）自动生成，仅供科研参考，不构成临床建议。"
    "分子对接结果受对接参数、力场精度及样本质量影响，不能替代实验验证。"
    "使用者应自行对结果的准确性及适用性负责。"
)


@dataclass
class ReportData:
    """All data required to render the PDF report."""

    project_name: str
    receptor: ReceptorInfo
    ligand: LigandInfo
    pocket: Pocket
    result: DockingResult
    user_email: str
    timestamp: str          # ISO-8601 string, pre-formatted by caller
    os_warning: str = ""    # Non-empty on Windows when fpocket is absent


def generate_pdf_report(
    data: ReportData,
    output_path: Path,
    pose_screenshots: list[Path],
) -> Path:
    """Render and save the PDF report.

    Args:
        data:             All report content.
        output_path:      Destination PDF path.
        pose_screenshots: Up to 3 PNG files (top poses) captured by the GUI layer.
                          May be empty (CLI mode); report is still generated.

    Returns:
        Resolved path of the written PDF.

    Raises:
        DockMeowError: on rendering failure.
    """
    _register_chinese_fonts()

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import (
        HRFlowable,
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = A4
    margin = 2 * cm

    _F = "NotoSansSC"
    _FB = "NotoSansSC-Bold"

    # ---- Styles ----
    title_style = ParagraphStyle(
        "title",
        fontName=_FB,
        fontSize=22,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=0.3 * cm,
    )
    h1_style = ParagraphStyle(
        "h1",
        fontName=_FB,
        fontSize=14,
        leading=18,
        spaceBefore=0.5 * cm,
        spaceAfter=0.2 * cm,
    )
    small_style = ParagraphStyle(
        "small",
        fontName=_F,
        fontSize=8,
        leading=11,
        textColor=colors.grey,
    )
    warn_style = ParagraphStyle(
        "warn",
        fontName=_F,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#B22222"),
    )

    # ---- Page callback ----
    def _on_page(canvas: Canvas, doc) -> None:
        # Footer
        canvas.saveState()
        canvas.setFont(_F, 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(margin, 1.2 * cm, f"一键对接 DockMeow v{__version__}")
        canvas.drawRightString(W - margin, 1.2 * cm, f"第 {doc.page} 页")
        canvas.restoreState()

    # ---- Build content ----
    story = []

    # --- Cover ---
    story.append(Spacer(1, 1 * cm))

    # Logo on cover page
    logo_path = resource_path("ui/resources/icons/logo_256.png")
    if logo_path.exists():
        logo_img = Image(str(logo_path), width=3 * cm, height=3 * cm)
        logo_img.hAlign = "CENTER"
        story.append(logo_img)
        story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("一键对接 · DockMeow", title_style))
    story.append(Paragraph("分子对接分析报告", title_style))
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2E86AB")))
    story.append(Spacer(1, 0.4 * cm))

    cover_data = [
        ["项目名称", data.project_name],
        ["生成时间", data.timestamp],
        ["软件版本", f"DockMeow v{__version__}"],
        ["用户", data.user_email],
    ]
    cover_table = Table(cover_data, colWidths=[4 * cm, 12 * cm])
    cover_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _F),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), _FB),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(cover_table)
    story.append(PageBreak())

    # --- Summary ---
    story.append(Paragraph("1. 摘要", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.3 * cm))

    summary_rows = [
        ["类别", "参数", "值"],
        ["受体", "PDB 文件", data.receptor.pdb_path.name],
        ["", "链", ", ".join(data.receptor.chains) or "—"],
        ["", "残基数", str(data.receptor.n_residues)],
        ["配体", "名称", data.ligand.name],
        ["", "重原子数", str(data.ligand.n_atoms)],
        ["", "可旋转键", str(data.ligand.n_rotatable)],
        ["", "SMILES", _truncate(data.ligand.smiles, 60)],
        ["口袋", "来源", data.pocket.source],
        ["", "中心 (Å)", (
            f"{data.pocket.center[0]:.2f}, "
            f"{data.pocket.center[1]:.2f}, "
            f"{data.pocket.center[2]:.2f}"
        )],
        ["", "大小 (Å)", (
            f"{data.pocket.size[0]:.1f} × "
            f"{data.pocket.size[1]:.1f} × "
            f"{data.pocket.size[2]:.1f}"
        )],
    ]
    sum_table = Table(summary_rows, colWidths=[3 * cm, 4 * cm, 9 * cm])
    sum_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _FB),
        ("FONTNAME", (0, 1), (-1, -1), _F),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E86AB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("SPAN", (0, 1), (0, 3)),  # receptor rows
        ("SPAN", (0, 4), (0, 7)),  # ligand rows
        ("SPAN", (0, 8), (0, 10)), # pocket rows
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 0.5 * cm))

    # --- Score table ---
    story.append(Paragraph("2. 对接结果", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.3 * cm))

    score_rows = [["构象", "结合能 (kcal/mol)", "RMSD lb (Å)", "RMSD ub (Å)"]]
    for i, (score, lb, ub) in enumerate(
        zip(data.result.scores, data.result.rmsd_lb, data.result.rmsd_ub), start=1
    ):
        score_rows.append([str(i), f"{score:.2f}", f"{lb:.3f}", f"{ub:.3f}"])

    score_table = Table(score_rows, colWidths=[3 * cm, 5 * cm, 5 * cm, 5 * cm])
    score_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _FB),
        ("FONTNAME", (0, 1), (-1, -1), _F),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E86AB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        f"对接耗时：{data.result.runtime_seconds:.1f} 秒", small_style
    ))

    # --- Screenshots ---
    valid_screens = [p for p in pose_screenshots[:3] if p.exists()]
    if valid_screens:
        story.append(PageBreak())
        story.append(Paragraph("3. 3D 结构视图", h1_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.3 * cm))
        for i, img_path in enumerate(valid_screens, start=1):
            try:
                available_w = W - 2 * margin
                # Preserve the PNG's actual aspect ratio to avoid stretching.
                # Clamp height to ~60% of the available page height so the image
                # never spills onto the next page.
                try:
                    from PIL import Image as _PILImage
                    with _PILImage.open(str(img_path)) as _pil:
                        _pw, _ph = _pil.size
                    _aspect = _ph / _pw if _pw else 0.5625
                except Exception:
                    _aspect = 0.5625  # 16:9 fallback
                max_h = (H - 2 * margin) * 0.6
                img_h = min(available_w * _aspect, max_h)
                img = Image(str(img_path), width=available_w, height=img_h)
                story.append(img)
                story.append(Paragraph(f"图 {i}：构象 {i} 3D 视图", small_style))
                story.append(Spacer(1, 0.5 * cm))
            except Exception as exc:
                _log.warning("Cannot embed screenshot %s: %s", img_path, exc)

    # --- Parameters ---
    story.append(PageBreak())
    story.append(Paragraph("4. 详细参数", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.3 * cm))

    # Windows platform notice (shown when pocket source is not cocrystal)
    if data.os_warning:
        win_warn_style = ParagraphStyle(
            "win_warn",
            fontName=_F,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#78350F"),
            backColor=colors.HexColor("#FEF3C7"),
            borderPadding=(4, 8, 4, 8),
            borderWidth=1,
            borderColor=colors.HexColor("#FCD34D"),
            borderRadius=3,
            spaceAfter=0.3 * cm,
        )
        story.append(Paragraph(data.os_warning, win_warn_style))

    cfg = data.result.config
    if cfg:
        param_rows = [
            ["参数", "值"],
            ["搜索精度 (exhaustiveness)", str(cfg.exhaustiveness)],
            ["最大构象数 (num_modes)", str(cfg.num_modes)],
            ["能量范围 (energy_range)", f"{cfg.energy_range} kcal/mol"],
            ["随机种子 (seed)", str(cfg.seed)],
            ["CPU 线程 (cpu)", str(cfg.cpu) if cfg.cpu > 0 else "自动"],
            ["盒子中心 X", f"{cfg.center[0]:.3f} Å"],
            ["盒子中心 Y", f"{cfg.center[1]:.3f} Å"],
            ["盒子中心 Z", f"{cfg.center[2]:.3f} Å"],
            ["盒子大小 X", f"{cfg.size[0]:.1f} Å"],
            ["盒子大小 Y", f"{cfg.size[1]:.1f} Å"],
            ["盒子大小 Z", f"{cfg.size[2]:.1f} Å"],
        ]
        param_table = Table(param_rows, colWidths=[8 * cm, 8 * cm])
        param_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), _FB),
            ("FONTNAME", (0, 1), (-1, -1), _F),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444444")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(param_table)

    # --- Disclaimer ---
    story.append(PageBreak())
    story.append(Paragraph("5. 免责声明", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(_DISCLAIMER_ZH, warn_style))

    # ---- Build PDF ----
    try:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=2 * cm,
        )
        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    except Exception as exc:
        raise DockMeowError(
            f"ReportLab build failed: {exc}",
            "PDF 报告生成失败。",
            "请检查磁盘空间是否充足，或联系技术支持。",
        ) from exc

    _log.info("PDF report written: %s", output_path)
    return output_path.resolve()


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 3] + "..."


def _pocket_source_from_config(cfg) -> str:
    return str(getattr(cfg, "pocket_source", "") or "config")


def _windows_fpocket_notice(pocket: Pocket) -> str:
    if sys.platform != "win32":
        return ""
    if pocket.source in {"cocrystal", "fpocket"}:
        return ""
    try:
        if fpocket_binary().exists():
            return ""
    except Exception:  # noqa: BLE001
        pass
    return (
        "⚠️ 平台说明：本报告在 Windows 上生成。"
        "当前安装包未检测到可用 fpocket 自动口袋检测组件，"
        f'本次对接使用口袋来源："{pocket.source}"。'
    )


def generate_report(
    receptor_info,
    ligand_info,
    result,
    output_path: Path,
    *,
    screenshot_path: Path | None = None,
    project_name: str = "DockMeow Project",
    user_email: str = "",
) -> Path:
    """Simplified entry point used by the GUI export button and capture script.

    Builds ReportData from individual fields and delegates to generate_pdf_report.
    """
    import datetime

    from dockmeow.core.pocket import Pocket

    cfg = result.config
    if cfg is not None:
        pocket = Pocket(
            pocket_id=1,
            center=cfg.center,
            size=cfg.size,
            score=0.0,
            source=_pocket_source_from_config(cfg),
        )
    else:
        pocket = Pocket(
            pocket_id=1, center=(0.0, 0.0, 0.0),
            size=(20.0, 20.0, 20.0), score=0.0, source="unknown",
        )

    _os_warning = _windows_fpocket_notice(pocket)

    data = ReportData(
        project_name=project_name,
        receptor=receptor_info,
        ligand=ligand_info,
        pocket=pocket,
        result=result,
        user_email=user_email,
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        os_warning=_os_warning,
    )

    screens = [screenshot_path] if screenshot_path and screenshot_path.exists() else []
    return generate_pdf_report(data, Path(output_path), screens)
