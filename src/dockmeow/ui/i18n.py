"""Centralised Chinese UI strings.

All user-visible text must be retrieved through ``t()`` so it can be reviewed
and updated in one place without touching widget code.

Usage:
    from dockmeow.ui.i18n import t
    label.setText(t("receptor.drop_hint"))
"""

from __future__ import annotations

_STRINGS: dict[str, str] = {
    # --- Navigation labels ---
    "nav.receptor": "① 受体（蛋白）",
    "nav.ligand": "② 配体（小分子）",
    "nav.pocket": "③ 结合口袋",
    "nav.params": "④ 参数",
    "nav.run": "⑤ 对接",
    "nav.results": "⑥ 结果",
    "nav.prev": "上一步",
    "nav.next": "下一步",

    # --- Welcome page ---
    "welcome.title": "欢迎使用一键对接",
    "welcome.learn_more_btn": "了解更多",

    # --- Receptor page ---
    "receptor.drop_hint": "拖入 PDB 文件，或点此选择",

    # --- Ligand page ---
    "ligand.smiles_label": "输入 SMILES：",
    "ligand.file_hint": "拖入 SDF / MOL2 / MOL 文件",

    # --- Pocket page ---
    "pocket.blind_warning": "盲对接结果仅供参考，建议指定结合口袋",
    "pocket.custom_btn": "我要自己框",
    "pocket.recommended_suffix": "（推荐）",
    "pocket.blind_label": "全蛋白盲对接",

    # --- Params page ---
    "params.exhaustiveness_label": "搜索精度",
    "params.speed_fast": "快速（8）",
    "params.speed_standard": "标准（16）",
    "params.speed_fine": "精细（32）",
    "params.speed_ultra": "极精细（64）",
    "params.advanced_toggle": "高级参数",

    # --- Run page ---
    "run.cancel_btn": "取消",
    "run.status_docking": "对接中…",

    # --- Results page ---
    "results.affinity": "结合能 (kcal/mol)",
    "results.pose": "构象",
    "results.rmsd_lb": "RMSD lb",
    "results.rmsd_ub": "RMSD ub",
    "results.export_sdf": "导出 SDF 格式",
    "results.export_pdb": "导出 PDBQT 格式",
    "results.export_pdf": "生成 PDF 报告",
    "results.new_docking": "开始新对接",
    "results.ray_btn": "Ray 截图",
    "results.ray_bg_btn": "背景色",
    "results.ray_saved": "截图已保存：{path}",
    "results.ray_failed": "截图失败：{err}",

    # --- App / menu ---
    "app.title": "DockMeow 一键对接",
    "menu.file": "文件",
    "menu.help": "帮助",
    "menu.about": "关于",
    "menu.exit": "退出",

    # --- Receptor page extra ---
    "receptor.hetero_groups": "异质残基（HETATM）",
    "receptor.warnings": "处理提示",
    "receptor.preparing": "正在准备受体…",

    # --- Ligand page extra ---
    "ligand.tab_smiles": "SMILES",
    "ligand.tab_file": "文件",
    "ligand.tab_examples": "示例库",
    "ligand.parse_btn": "解析",
    "ligand.info_atoms": "原子数：{n}",
    "ligand.info_rotbonds": "可旋转键：{n}",
    "ligand.preparing": "正在准备配体…",

    # --- Pocket page extra ---
    "pocket.detecting": "检测口袋中…",
    "pocket.score": "评分：{score}",
    "pocket.center": "中心：{x}, {y}, {z}",
    "pocket.size": "盒子：{w} × {h} × {d} Å",

    # --- Params page extra ---
    "params.num_modes": "构象数",
    "params.energy_range": "能量窗口 (kcal/mol)",
    "params.seed": "随机种子",
    "params.start_btn": "开始对接",
    "params.estimate": "预计耗时：约 {minutes} 分钟",

    # --- Run page extra ---
    "run.title": "对接进行中",
    "run.cancelled": "已取消",
    "run.completed": "对接完成",

    # --- Results page extra ---
    "results.title": "结果",
    "results.no_pose": "暂无构象",

    # --- Results page: PyMOL integration ---
    "results.pymol_group": "PyMOL 导入",
    "results.pymol_path_label": "PyMOL 路径：",
    "results.pymol_path_hint": "选择 PyMOL 可执行文件，或点“自动搜索”",
    "results.pymol_browse": "浏览…",
    "results.pymol_browse_tip": "手动选择 PyMOL 可执行文件",
    "results.pymol_auto": "自动搜索",
    "results.pymol_auto_tip": "在常见安装位置与 PATH 中自动查找 PyMOL",
    "results.pymol_import": "导入 PyMOL",
    "results.pymol_import_tip": "在 PyMOL 中打开原始受体与全部构象（每个构象一个状态，可逐个切换）",
    "results.pymol_found": "已找到 PyMOL：\n{path}",
    "results.pymol_not_found": "未能自动找到 PyMOL。请点“浏览…”手动指定 PyMOL 可执行文件。",
    "results.pymol_bad_path": "PyMOL 路径无效或不可执行：\n{path}",
    "results.pymol_no_result": "请先完成对接，再导入 PyMOL。",
    "results.pymol_no_receptor": "缺少受体结构，无法导入 PyMOL。",
    "results.pymol_launch_failed": "启动 PyMOL 失败：{err}",
    "results.pymol_launched": (
        "已在 PyMOL 中打开受体与 {n} 个构象。\n"
        "用 PyMOL 右下角的帧滑块或方向键即可切换构象。"
    ),

    # --- Common dialogs ---
    "common.close": "关闭",
    "common.cancel": "取消",
    "common.ok": "确定",

    # --- About dialog ---
    "about.title": "关于 DockMeow",
    "about.version": "版本：{ver}",
    "about.tagline": "一键分子对接工具",
    "about.credits": "依赖：AutoDock Vina · RDKit · Meeko · fpocket · PySide6 · py3Dmol",
}


def t(key: str, **kwargs: str) -> str:
    """Look up a UI string by key, with optional str.format_map substitution.

    Args:
        key:    Dot-separated string key.
        kwargs: Format variables for ``{placeholder}`` patterns.

    Returns:
        Formatted Chinese string, or the raw key if not found (for debugging).
    """
    template = _STRINGS.get(key, key)
    if kwargs:
        return template.format_map(kwargs)
    return template
