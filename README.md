# 🧰 Alek 的锦囊（Alekit）

一个集成的桌面小工具箱：左侧选工具，右侧用。基于 Python + tkinter，跨平台。

> Alekit = **Alek** + **kit**（工具箱）

## 内置工具

| 工具 | 说明 |
|---|---|
| 📄 文档格式转换器 | 基于 pandoc，在 Word / Markdown / HTML / EPUB / RTF 等格式间互转 |
| 🗜️ PPT 压缩 | 智能重压幻灯片图片（按显示尺寸降分辨率），可选视频转码；滑块控制档位 + 真实大小预览 |

### PPT 压缩说明
- **只在更小时才替换，绝不把文件改大**；文字 / 排版 / 动画 / 母版 / 嵌入字体完全不动。
- 图片压缩纯 [Pillow](https://python-pillow.org/)，零外部依赖。
- 视频压缩需要 [ffmpeg](https://ffmpeg.org/)，可在界面里按需自动下载（不打进安装包）。
- 损失：图片清晰度按档位下降（不可逆）；勾选视频压缩后视频清晰度下降。

## 运行（开发模式）

```bash
pip install -r requirements.txt
# 文档转换需要 pandoc：brew install pandoc
python3 toolbox.py
```

macOS 也可直接双击 `启动工具箱.command`。

## 免安装包

每次打 `v*` 标签（如 `v1.0.0`）或在 Actions 页手动触发，GitHub Actions 会自动构建：

- `Alekit-windows.zip` —— 单个 `Alekit.exe`，双击即用
- `Alekit-macos-arm64.zip` —— `Alekit.app`（Apple 芯片）
- `Alekit-macos-intel.zip` —— `Alekit.app`（Intel Mac）

无需安装 Python，解压即用。ffmpeg 首次压缩视频时按需下载。

## 加新工具

实现一个 `tools.base.Tool` 子类，在 `tools/__init__.py` 的 `TOOLS` 注册即可出现在侧栏。
