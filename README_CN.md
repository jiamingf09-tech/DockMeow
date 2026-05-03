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

## 系统要求

- macOS 12.0 (Monterey) 及以上
- Apple Silicon (arm64) 或 Intel (x64)
- 约 400 MB 磁盘空间

---

## 快速上手

1. 将 `DockMeow.app` 拖入 `/Applications/` 文件夹
2. 首次启动执行上述 `xattr` 命令（仅一次）
3. 双击打开，在「文件 → 激活授权」中输入许可证密钥
4. 依次完成：受体 → 配体 → 口袋 → 参数 → 运行 → 结果

---

## 许可证激活

- 打开软件后，点击菜单 **文件 → 激活授权**
- 输入购买后收到的许可证密钥（格式：`DM-XXXX-XXXX-XXXX`）
- 激活成功后，状态栏显示「已激活：your@email.com」

---

## 常见问题

**Q：提示"已损坏，无法打开"怎么办？**  
A：执行 `xattr -cr /Applications/DockMeow.app` 后重试。

**Q：3D 视图空白或无法加载？**  
A：需要 macOS 12+ 且开启硬件加速（系统偏好设置 → 电池 → 关闭「低能耗模式」）。

**Q：对接速度很慢？**  
A：在「参数」页面降低 `exhaustiveness`（默认 8，可调至 4 快速预览）。

---

© 2026 DockMeow
