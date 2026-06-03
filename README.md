<div align="center">

<img src="examples/DockMeow.png" alt="DockMeow Logo" width="160"/>

# DockMeow &nbsp;·&nbsp; 一键对接

**A desktop GUI for molecular docking — no command line required.**

[![CI](https://github.com/jiamingf09-tech/DockMeow/actions/workflows/ci.yml/badge.svg)](https://github.com/jiamingf09-tech/DockMeow/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey.svg)](#installation)

[English](#english) &nbsp;|&nbsp; [中文](#中文)

</div>

---

## English

DockMeow is an open-source, cross-platform desktop application for **molecular docking**, built with Python and PySide6. It wraps the [AutoDock Vina](https://vina.scripps.edu/) engine in a clean step-by-step wizard, so computational chemists and pharmacology students can run docking experiments without touching the command line.

### Features

| | |
|---|---|
| 🧬 **Receptor preparation** | Auto-clean PDB with PDBFixer (add missing atoms, fix residues) |
| 💊 **Ligand preparation** | Load SDF/MOL2/SMILES → 3D coordinates via RDKit + Meeko |
| 🎯 **Pocket detection** | Automatic binding-site prediction with fpocket |
| ⚙️ **Docking** | AutoDock Vina with configurable exhaustiveness, modes, energy range |
| 🔬 **3D viewer** | Interactive py3Dmol viewer — rotate, zoom, switch poses |
| 📸 **Ray capture** | Export current 3D view as PNG with custom background |
| 📄 **PDF report** | One-click report with receptor info, scores table, and 3D screenshot |
| 📦 **Export** | Download result SDF or PDBQT for downstream analysis |

### Installation

#### macOS (Apple Silicon & Intel)

Download the latest `.dmg` from [Releases](https://github.com/jiamingf09-tech/DockMeow/releases), open it, and drag **DockMeow.app** to your Applications folder.

> **First launch:** macOS may show a Gatekeeper warning. Right-click the app → Open to bypass.

#### Windows (x64)

Download the latest `DockMeow-Setup-*-x64.exe` from [Releases](https://github.com/jiamingf09-tech/DockMeow/releases) and run the installer.

#### From source

```bash
# 1. Clone
git clone https://github.com/jiamingf09-tech/DockMeow.git
cd DockMeow

# 2. Create a Python 3.11 environment
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install runtime deps
#    macOS arm64: vina must come from conda-forge (no PyPI wheel)
#    conda install -c conda-forge vina boost-cpp
pip install -e ".[dev]"

# 4. Run
python -m dockmeow
```

### Usage

The wizard guides you through six steps:

1. **Receptor** — load a PDB file; DockMeow will clean and prepare it automatically.
2. **Ligand** — load an SDF/MOL2 file or paste a SMILES string.
3. **Pocket** — choose a predicted binding site or draw a custom docking box.
4. **Parameters** — set exhaustiveness, number of poses, random seed.
5. **Run** — watch real-time docking progress.
6. **Results** — explore poses in 3D, export SDF/PDBQT, generate a PDF report.

### Development

```bash
# Lint
python -m ruff check src/ tests/

# Test (fast, excludes slow e2e)
python -m pytest tests/ -q

# Test (including slow pipeline tests)
python -m pytest tests/ -m slow -q

# Build macOS DMG
./packaging/macos/build_dmg.sh

# Build Windows installer (run from CMD on Windows)
packaging\windows\build_win.bat
```

### CI / CD

| Workflow | Trigger | What it does |
|---|---|---|
| **CI** | push / PR | Lint + test on macOS arm64, Windows x64, Ubuntu |
| **Build & Release** | tag `v*` | PyInstaller → DMG / Inno Setup EXE / AppImage → GitHub Release |

### Project structure

```
src/dockmeow/
├── core/          # receptor.py, ligand.py, pocket.py, docking.py, report.py
├── ui/
│   ├── pages/     # ReceptorPage, LigandPage, PocketPage, ParamsPage, RunPage, ResultsPage
│   ├── widgets/   # Viewer3D (py3Dmol + QWebEngineView)
│   └── dialogs/   # AboutDialog, CustomBoxDialog
└── utils/         # paths.py, config.py, subprocess.py
packaging/
├── dockmeow.spec  # PyInstaller spec (shared macOS + Windows)
├── macos/         # build_dmg.sh, entitlements.plist
└── windows/       # build_win.bat, installer.iss, requirements-build-win.txt
```

### Contributing

Pull requests are welcome. Please:
1. Fork the repo and create a feature branch.
2. Add or update tests for any changed behaviour.
3. Run `ruff check` and `pytest` before opening the PR.
4. Keep commits focused; one logical change per commit.

### License

[MIT](LICENSE) — free to use, modify, and distribute.

---

## 中文

DockMeow（一键对接）是一款开源跨平台**分子对接**桌面应用，基于 Python + PySide6 构建，底层使用 [AutoDock Vina](https://vina.scripps.edu/) 引擎。无需命令行，六步向导即可完成从 PDB 到对接结果的全流程。

### 功能

| | |
|---|---|
| 🧬 **受体准备** | 自动用 PDBFixer 清洗 PDB（补全缺失原子、修复残基）|
| 💊 **配体准备** | 支持 SDF/MOL2/SMILES，通过 RDKit + Meeko 生成 3D 构象 |
| 🎯 **口袋检测** | 调用 fpocket 自动预测结合位点 |
| ⚙️ **分子对接** | AutoDock Vina，可调穷举性、构象数、能量窗口 |
| 🔬 **3D 可视化** | 内嵌 py3Dmol，可旋转缩放、切换对接构象 |
| 📸 **Ray 截图** | 导出当前 3D 视图为 PNG，支持自定义背景色 |
| 📄 **PDF 报告** | 一键生成包含受体信息、打分表和 3D 截图的报告 |
| 📦 **结果导出** | 下载 SDF 或 PDBQT 供下游分析 |

### 安装

#### macOS（Apple Silicon / Intel）

从 [Releases](https://github.com/jiamingf09-tech/DockMeow/releases) 下载最新 `.dmg`，打开后将 **DockMeow.app** 拖入「应用程序」文件夹。

> **首次启动**：macOS 可能弹出 Gatekeeper 警告，右键点击 → 打开 即可绕过。

#### Windows（x64）

从 [Releases](https://github.com/jiamingf09-tech/DockMeow/releases) 下载最新 `DockMeow-Setup-*-x64.exe` 并运行安装程序。

#### 从源码运行

```bash
git clone https://github.com/jiamingf09-tech/DockMeow.git
cd DockMeow

# macOS arm64：vina 需从 conda-forge 安装
# conda install -c conda-forge vina boost-cpp

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m dockmeow
```

### 使用步骤

1. **受体** — 加载 PDB 文件，软件自动完成清洗
2. **配体** — 加载 SDF/MOL2 或输入 SMILES
3. **口袋** — 选择预测位点或手动定义对接盒子
4. **参数** — 设置穷举性、构象数、随机种子
5. **对接** — 实时查看对接进度
6. **结果** — 3D 浏览构象、导出文件、生成 PDF 报告

### 开发

```bash
python -m ruff check src/ tests/   # 代码检查
python -m pytest tests/ -q         # 快速测试
python -m pytest tests/ -m slow -q # 含完整流程测试
./packaging/macos/build_dmg.sh     # 构建 macOS DMG
packaging\windows\build_win.bat    # 构建 Windows 安装包（在 Windows CMD 中运行）
```

### 许可证

[MIT License](LICENSE)
