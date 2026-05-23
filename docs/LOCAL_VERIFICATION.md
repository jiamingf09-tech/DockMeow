# DockMeow — 上线前本地验证流程

> **用途**：每次发新版本前，按此文档自测一遍完整链路（编译 → 签发 → 安装 → 激活 → 验收）。  
> **时间**：约 15–20 分钟（含编译时间）。

---

## 前置检查（每次验证前先跑）

```bash
cd /path/to/DockMeow

# 1. 私钥存在
ls -lh dockmeow_private.pem

# 2. 签发工具正常
PYTHONPATH=src .venv/bin/python tools/issue_license.py --help

# 3. 机器指纹工具正常
PYTHONPATH=src .venv/bin/python tools/get_machine_id.py
```

所有输出无报错即可继续。

---

## 步骤 1：编译 .dmg

> 在 macOS 上编译目标平台的安装包。

```bash
cd /path/to/DockMeow

# 激活 build venv（含 PyInstaller、PySide6 6.7.x）
source .venv-build/bin/activate

# 注入构建元数据（commit hash + 文件校验和）
python tools/inject_build_info.py

# PyInstaller 打包
pyinstaller packaging/dockmeow.spec --clean --noconfirm

# 生成 DMG
VERSION=$(python -c "import sys; sys.path.insert(0,'src'); \
    from dockmeow.version import __version__; print(__version__)")
ARCH=$(python -c "import platform; print('arm64' if platform.machine()=='arm64' else 'x86_64')")
DMG_NAME="DockMeow-${VERSION}-${ARCH}.dmg"

mkdir -p dist/installers
hdiutil create \
    -volname DockMeow \
    -srcfolder dist/DockMeow.app \
    -ov \
    -format UDZO \
    "dist/installers/${DMG_NAME}"

echo "✅ DMG: dist/installers/${DMG_NAME}"
deactivate
```

**预期输出**：`dist/installers/DockMeow-x.x.x-arm64.dmg`（约 200–400 MB）

---

## 步骤 2：获取本机指纹

在**目标机器**（将要安装 DockMeow 的机器）上运行：

```bash
# 开发机自测时直接运行：
PYTHONPATH=src .venv/bin/python tools/get_machine_id.py
```

**示例输出**：
```
============================================
  DockMeow 机器指纹
============================================
  指纹 ID:  DM-853caa58-9fd8639c-a3e827c6

  完整因子（请发送以下内容给客服）:
    mb=853caa58ae67e9fe
    cpu=9fd8639cece7f8a5
    mac=a3e827c63db90fb1
```

日常签发只需要记下 `指纹 ID` 这一串 `DM-...` 设备码，用于步骤 3。
旧版三因子 `mb=`, `cpu=`, `mac=` 仍可用于兼容排查。

---

## 步骤 3：签发许可证

### 方式 A — 交互式（推荐日常使用）

```bash
PYTHONPATH=src .venv/bin/python tools/quick_issue.py
```

按提示输入：
1. 许可证类型：`perpetual` 或 `trial`
2. 用户邮箱
3. 设备 ID（粘贴步骤 2 的 `DM-xxxxxxxx-yyyyyyyy-zzzzzzzz`）
4. 备注（可选，如订单号）

### 方式 B — 命令行（批量/脚本化）

```bash
PYTHONPATH=src .venv/bin/python tools/quick_issue.py \
    --type perpetual \
    --email user@example.com \
    --machine-id "DM-853caa58-9fd8639c-a3e827c6" \
    --note "Stripe inv_xxx / 自测"
```

旧版完整因子仍可使用 `--machine-factors "mb=...,cpu=...,mac=..."`。

### 方式 C — 原始签发工具（无 DB 记录）

```bash
PYTHONPATH=src .venv/bin/python tools/issue_license.py \
    --type perpetual \
    --email user@example.com \
    --machine-id "DM-853caa58-9fd8639c-a3e827c6"
```

**预期输出**：
```
✅ 签发成功
  文件: issued/DM-2026-00001.dmlic
  编号: DM-2026-00001
  ...
（文件路径已复制到剪贴板，Finder 已弹出位置）
```

签发的 `.dmlic` 文件在 `issued/` 目录，**不进 git**（已 gitignore）。

---

## 步骤 4：安装 DMG + 解除隔离

```bash
# 挂载 DMG
open dist/installers/DockMeow-*.dmg

# 在 Finder 中将 DockMeow.app 拖入 /Applications

# 解除 macOS 隔离标记（首次启动必须）
xattr -cr /Applications/DockMeow.app

# 启动 App
open /Applications/DockMeow.app
```

> **注**：如果 Gatekeeper 弹出"无法验证开发者"，执行 `xattr -cr` 后再 `open`。

---

## 步骤 5：激活授权

1. 打开 DockMeow（等待约 3–5 秒加载完成）
2. 点击顶部菜单 **文件 → 激活授权**（或状态栏的"未激活"提示）
3. 在弹出的激活对话框中：
   - 点击"从文件导入"按钮
   - 选择步骤 3 签发的 `.dmlic` 文件（路径在剪贴板里，直接粘贴）
4. 激活成功后，状态栏显示：`已激活：user@example.com`

---

## 步骤 6：完整功能验收

依次完成以下操作，逐项打勾：

### 受体加载
- [ ] 拖入 `examples/1AKE_with_ATP.pdb`
- [ ] 3D 视图显示蛋白质卡通图（cartoon + spectrum 配色）
- [ ] "异质残基"列表出现 ATP

### 口袋检测
- [ ] 点击"下一步"进入口袋页
- [ ] 出现至少 1 个口袋卡片（来源：cocrystal 或 fpocket）
- [ ] 3D 视图显示蓝色虚线框叠加在蛋白上

### 配体输入
- [ ] 输入 SMILES：`CC(=O)Oc1ccccc1C(=O)O`（阿司匹林）
- [ ] 配体名称、重原子数显示正常

### 对接执行
- [ ] 设置 `exhaustiveness=4`（快速测试）
- [ ] 点击运行，进度圈走完（约 30–120 秒）
- [ ] 结果页出现 ≥3 个构象和亲和力数值

### 结果验收
- [ ] 点击构象 1，3D 视图显示受体 cartoon + 配体 stick（greenCarbon）
- [ ] 亲和力最佳值在 -5 ~ -9 kcal/mol 范围内（合理）
- [ ] **导出 SDF** 按钮可正常下载
- [ ] **导出 PDF** → 等待 2–3 秒 → 保存对话框出现
- [ ] 打开 PDF：
  - [ ] 第 1 页：封面，项目名称、时间、版本、许可证 ID 正确
  - [ ] 第 2 页：摘要表格，受体/配体/口袋参数完整
  - [ ] **第 3 页：3D 结构视图 — 必须包含配体 stick 模型嵌入受体** ✅
  - [ ] 第 4 页：对接参数表（详细参数）
  - [ ] 第 5 页：免责声明

---

## 快速 Dry-Run（不需要完整编译，仅验证签发链路）

```bash
# 验证签发工具和 DB 链路（不写真实文件）
PYTHONPATH=src .venv/bin/python tools/quick_issue.py \
    --dry-run \
    --type trial \
    --email dryrun@test.com \
    --machine-id "DM-00000000-11111111-22222222"
```

---

## 客户台账查询

```bash
# 查看所有已签发记录
sqlite3 customers.db "SELECT recorded_at, license_no, license_type, email, expires_at FROM customers ORDER BY id DESC LIMIT 20;"

# 查询特定邮箱
sqlite3 customers.db "SELECT * FROM customers WHERE email LIKE '%@example.com';"
```

---

## 故障排查

| 现象 | 原因 | 解决方案 |
|------|------|----------|
| "已损坏，无法打开" | Gatekeeper 隔离 | `xattr -cr /Applications/DockMeow.app` |
| 激活失败"机器不匹配" | 在不同机器上运行 | 重新获取目标机器指纹重新签发 |
| 激活失败"签名无效" | `.dmlic` 文件损坏 | 重新签发 |
| PDF 第 3 页空白 | WebGL 未渲染完成 | 关闭省电模式；等待 3D 视图加载后再导出 |
| 口袋检测无结果 | fpocket 二进制缺失 | 检查 `src/dockmeow/bundled/fpocket/` |
| `issue_license.py` 找不到私钥 | `dockmeow_private.pem` 不在 repo 根目录 | 将私钥放到 repo 根目录（**不要 git add**）|

---

## 文件路径速查

```
DockMeow/
├── dockmeow_private.pem    ← 私钥（gitignored，永远不提交）
├── dockmeow_public.pem     ← 公钥（备份用，已嵌入 _keystore.py）
├── issued/                 ← 签发的 .dmlic 文件（gitignored）
├── customers.db            ← 客户台账（gitignored）
├── tools/
│   ├── quick_issue.py      ← 本文档步骤 3 使用
│   ├── issue_license.py    ← 底层签发工具
│   └── get_machine_id.py   ← 步骤 2 获取指纹
└── dist/installers/        ← 编译输出（gitignored）
```
