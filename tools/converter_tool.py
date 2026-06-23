"""文档格式转换器 —— 基于 pandoc 的 GUI 包装。

后期扩展格式：在 INPUT_FORMATS / OUTPUT_FORMATS 中加一行即可。
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tools.base import Tool

# ============ 格式配置（要加新格式只改这里） ============
# (显示名, 文件扩展名, pandoc 输入格式名 / None 表示让 pandoc 自动识别)
INPUT_FORMATS = [
    ("Word 文档 (.docx)", ".docx", None),
    ("Markdown (.md)", ".md", None),
    ("HTML (.html)", ".html", None),
    ("EPUB (.epub)", ".epub", None),
    ("RTF (.rtf)", ".rtf", None),
]

# (显示名, 文件扩展名, pandoc 输出格式名, 额外参数列表)
OUTPUT_FORMATS = [
    ("Markdown (.md)", ".md", "gfm", ["--wrap=none"]),
    ("HTML (.html)", ".html", "html", ["--standalone"]),
    ("纯文本 (.txt)", ".txt", "plain", ["--wrap=none"]),
    ("EPUB (.epub)", ".epub", "epub", []),
    ("RTF (.rtf)", ".rtf", "rtf", ["--standalone"]),
    ("Word 文档 (.docx)", ".docx", "docx", []),
    # PDF 需另装 LaTeX（如 mactex / basictex），按需启用：
    # ("PDF (.pdf)", ".pdf", "pdf", []),
]


class ConverterTool(Tool):
    id = "converter"
    title = "文档格式转换器"
    icon = "📄"
    subtitle = "基于 pandoc，在 Word / Markdown / HTML / EPUB / RTF 等格式间互转"

    def build(self, parent: ttk.Frame) -> None:
        self.files: list[Path] = []
        self.output_dir: Path | None = None
        self.extract_media = tk.BooleanVar(value=True)
        pad = {"padx": 12, "pady": 6}

        # 输入区
        input_frame = ttk.LabelFrame(parent, text="1. 选择输入文件")
        input_frame.pack(fill="both", expand=False, **pad)

        list_frame = ttk.Frame(input_frame)
        list_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.file_listbox = tk.Listbox(list_frame, height=6, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, command=self.file_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=scroll.set)

        btn_row = ttk.Frame(input_frame)
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_row, text="添加文件…", command=self.on_add_files).pack(side="left")
        ttk.Button(btn_row, text="移除选中", command=self.on_remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="清空", command=self.on_clear).pack(side="left")

        # 选项区
        opt_frame = ttk.LabelFrame(parent, text="2. 转换选项")
        opt_frame.pack(fill="x", **pad)

        row1 = ttk.Frame(opt_frame)
        row1.pack(fill="x", padx=8, pady=6)
        ttk.Label(row1, text="输出格式:").pack(side="left")
        self.format_var = tk.StringVar(value=OUTPUT_FORMATS[0][0])
        self.format_combo = ttk.Combobox(
            row1,
            textvariable=self.format_var,
            values=[f[0] for f in OUTPUT_FORMATS],
            state="readonly",
            width=24,
        )
        self.format_combo.pack(side="left", padx=8)

        row2 = ttk.Frame(opt_frame)
        row2.pack(fill="x", padx=8, pady=6)
        ttk.Label(row2, text="输出目录:").pack(side="left")
        self.output_dir_label = ttk.Label(row2, text="（与源文件同目录）", foreground="#666")
        self.output_dir_label.pack(side="left", padx=8)
        ttk.Button(row2, text="选择…", command=self.on_choose_output_dir).pack(side="left")
        ttk.Button(row2, text="重置", command=self.on_reset_output_dir).pack(side="left", padx=4)

        row3 = ttk.Frame(opt_frame)
        row3.pack(fill="x", padx=8, pady=6)
        ttk.Checkbutton(
            row3,
            text="提取文档中的图片到 media/ 子目录（仅 docx 等含图片的格式有效）",
            variable=self.extract_media,
        ).pack(side="left")

        # 操作区
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", **pad)
        self.convert_btn = ttk.Button(action_frame, text="开始转换", command=self.on_convert)
        self.convert_btn.pack(side="left")
        self.progress = ttk.Progressbar(action_frame, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)

        # 日志区
        log_frame = ttk.LabelFrame(parent, text="日志")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(log_frame, height=8, state="disabled", wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.log_text.config(yscrollcommand=log_scroll.set)

    # ---------- 事件 ----------
    def on_add_files(self):
        types = [("支持的文档", " ".join(f"*{f[1]}" for f in INPUT_FORMATS)),
                 ("所有文件", "*.*")]
        paths = filedialog.askopenfilenames(title="选择要转换的文档", filetypes=types)
        added = 0
        for p in paths:
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
                self.file_listbox.insert(tk.END, str(path))
                added += 1
        if added:
            self.log(f"已添加 {added} 个文件")

    def on_remove_selected(self):
        sel = list(self.file_listbox.curselection())
        for idx in reversed(sel):
            self.file_listbox.delete(idx)
            del self.files[idx]

    def on_clear(self):
        self.file_listbox.delete(0, tk.END)
        self.files.clear()

    def on_choose_output_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir = Path(d)
            self.output_dir_label.config(text=str(self.output_dir), foreground="black")

    def on_reset_output_dir(self):
        self.output_dir = None
        self.output_dir_label.config(text="（与源文件同目录）", foreground="#666")

    def on_convert(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加要转换的文件")
            return
        if not shutil.which("pandoc"):
            messagebox.showerror("缺少依赖", "未检测到 pandoc，请先运行 `brew install pandoc`。")
            return

        fmt_idx = [f[0] for f in OUTPUT_FORMATS].index(self.format_var.get())
        _, out_ext, pandoc_to, extra = OUTPUT_FORMATS[fmt_idx]

        self.convert_btn.config(state="disabled")
        self.progress.start(10)
        thread = threading.Thread(
            target=self._run_conversions,
            args=(list(self.files), out_ext, pandoc_to, extra),
            daemon=True,
        )
        thread.start()

    # ---------- 转换核心 ----------
    def _run_conversions(self, files, out_ext, pandoc_to, extra):
        ok, fail = 0, 0
        for src in files:
            try:
                dst_dir = self.output_dir if self.output_dir else src.parent
                dst_dir.mkdir(parents=True, exist_ok=True)
                dst = dst_dir / (src.stem + out_ext)

                cmd = ["pandoc", str(src), "-t", pandoc_to, "-o", str(dst), *extra]
                if self.extract_media.get():
                    media_dir = dst_dir / f"{src.stem}_media"
                    cmd += [f"--extract-media={media_dir}"]

                self.log(f"→ 转换: {src.name}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.log(f"  ✓ 输出: {dst}")
                    if result.stderr.strip():
                        self.log(f"  (pandoc 提示) {result.stderr.strip()}")
                    ok += 1
                else:
                    self.log(f"  ✗ 失败: {result.stderr.strip() or '未知错误'}")
                    fail += 1
            except Exception as e:
                self.log(f"  ✗ 异常: {e}")
                fail += 1

        self.log(f"完成。成功 {ok}，失败 {fail}")
        self.root.after(0, self._on_conversion_done)

    def _on_conversion_done(self):
        self.progress.stop()
        self.convert_btn.config(state="normal")
