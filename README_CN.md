# 一键对接 · DockMeow

分子对接一站式桌面工具。

---

## macOS 首次启动

由于内测版未做苹果代码签名，首次启动会提示"DockMeow 已损坏，无法打开"。

请打开终端，执行以下命令（**一次性，之后无需重复**）：

```bash
xattr -cr /Applications/DockMeow.app
```

然后正常双击启动即可。

> **说明**：此命令仅移除 macOS 的隔离标记（quarantine flag），不会修改软件本身。正式发布版将通过苹果公证（notarization），届时无需此步骤。

---

## Windows 首次启动

下载 `DockMeow-Setup-x.x.x-x64.exe` 后双击安装，安装完成后可从开始菜单启动。

首次启动时，Windows SmartScreen 可能弹出蓝色警告框"Windows 已保护你的电脑"：

1. 点击"**更多信息**"（左下角小字）
2. 点击"**仍要运行**"

> **原因**：内测版未经 Microsoft 代码签名认证。正式发布版将通过签名，届时不再出现此提示。

---

## Linux 启动

下载 `DockMeow-x.x.x-x86_64.AppImage` 后：

```bash
# 添加执行权限（仅首次）
chmod +x DockMeow-*.AppImage

# 直接运行
./DockMeow-*.AppImage
```

若提示 3D 视图黑屏或崩溃，可尝试加 `--no-sandbox` 参数（部分容器化环境需要）：

```bash
./DockMeow-*.AppImage --no-sandbox
```

> **系统要求**：Ubuntu 22.04 / Debian 12 或同等 glibc 2.35+ 发行版；需 libfuse2（`sudo apt install libfuse2`）。

---

## 已知平台差异

| 功能 | macOS (arm64 / x64) | Windows | Linux |
|------|---------------------|---------|-------|
| 自动口袋检测（fpocket） | ✅ 支持 | ✅ 支持 | ✅ 支持 |
| AutoDock Vina 对接 | ✅ | ✅ | ✅ |
| 3D 可视化 | ✅ | ✅ | ✅ |
| PDF 报告导出 | ✅ | ✅ | ✅ |
| 代码签名 / 公证 | ❌ 内测版未签名 | ❌ 内测版未签名 | — |

**Windows 说明**：新版 Windows 安装包已内置 fpocket 二进制，可自动检测口袋。只有在安装包缺少该组件时，软件才会提示改用共结晶口袋、全蛋白盲对接盒子或手动指定坐标。

---

## 系统要求

| 平台 | 最低系统 | 架构 | 磁盘 |
|------|---------|------|------|
| macOS | 12.0 (Monterey) | arm64 / x86_64 | ~400 MB |
| Windows | 10 / 11 (64-bit) | x86_64 | ~350 MB |
| Linux | Ubuntu 22.04 / glibc 2.35+ | x86_64 | ~400 MB |

---

## 快速上手

**macOS**：将 `DockMeow.app` 拖入 `/Applications/`，首次运行执行 `xattr -cr` 命令（见上）。  
**Windows**：运行安装程序，按向导完成安装，从开始菜单启动。  
**Linux**：添加执行权限后直接运行 AppImage（见上）。

1. 打开软件，在「文件 → 激活授权」中输入许可证密钥
2. 依次完成：受体 → 配体 → 口袋 → 参数 → 运行 → 结果

---

## 许可证激活

- 打开软件后，点击菜单 **文件 → 激活授权**
- 输入购买后收到的许可证密钥（格式：`DM-XXXX-XXXX-XXXX`）
- 激活成功后，状态栏显示「已激活：your@email.com」

---

## 常见问题

**Q：（macOS）提示"已损坏，无法打开"怎么办？**  
A：执行 `xattr -cr /Applications/DockMeow.app` 后重试。

**Q：（Windows）SmartScreen 警告怎么办？**  
A：点"更多信息" → "仍要运行"即可。

**Q：（Linux）AppImage 无法运行，提示缺少 FUSE？**  
A：执行 `sudo apt install libfuse2` 后重试。

**Q：口袋页提示“当前安装包未检测到可用 fpocket 自动口袋检测组件”？**  
A：请使用新版 Windows 安装包；若当前安装包确实缺少该组件，可选择“全蛋白盲对接”、手动指定坐标，或上传含共结晶配体的原始 PDB。

**Q：3D 视图空白或无法加载？**  
A：macOS 需 12+，开启硬件加速；Linux 可加 `--no-sandbox`；Windows 需 DirectX 11+。

**Q：对接速度很慢？**  
A：在「参数」页面降低 `exhaustiveness`（默认 8，可调至 4 快速预览）。

---

© 2026 DockMeow
