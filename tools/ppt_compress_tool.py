"""PPT 压缩工具 —— 智能图片重压（+ 可选视频转码），滑块控制档位 + 真实大小预览。

图片压缩纯 Pillow、零外部依赖；视频压缩需要 ffmpeg，可在界面里按需下载。
不动文字/排版/动画/嵌入字体，最大限度保留原 PPT 的观看体验。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import ppt_compress_engine as engine
import video
from tools.base import Tool

PILLOW_OK = True
try:
    import PIL  # noqa: F401
except Exception:
    PILLOW_OK = False


class PptCompressTool(Tool):
    id = "ppt_compress"
    title = "PPT 压缩"
    icon = "🗜️"
    subtitle = "智能重压幻灯片里的图片，体积大幅下降、观看体验基本不变"

    def build(self, parent: ttk.Frame) -> None:
        self.files: list[Path] = []
        self.analyses: dict[Path, engine.AnalyzeResult] = {}
        self.total_original = 0
        self.tier_var = tk.IntVar(value=engine.DEFAULT_TIER)
        self.output_dir: Path | None = None
        self._preview_job = None
        self._busy = False
        self.has_video = False
        self.video_size = 0
        self.compress_video_var = tk.BooleanVar(value=False)
        self.ffmpeg = video.find_ffmpeg()

        pad = {"padx": 12, "pady": 6}

        if not PILLOW_OK:
            warn = ttk.Label(
                parent,
                text="⚠️ 未检测到 Pillow，图片压缩不可用。请先运行：pip3 install Pillow python-pptx",
                foreground="#b00",
            )
            warn.pack(fill="x", **pad)

        # 1. 选择文件
        input_frame = ttk.LabelFrame(parent, text="1. 选择 PPT 文件（.pptx）")
        input_frame.pack(fill="both", expand=False, **pad)
        list_frame = ttk.Frame(input_frame)
        list_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.file_listbox = tk.Listbox(list_frame, height=4, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, command=self.file_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=scroll.set)

        btn_row = ttk.Frame(input_frame)
        btn_row.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Button(btn_row, text="添加 PPT…", command=self.on_add_files).pack(side="left")
        ttk.Button(btn_row, text="移除选中", command=self.on_remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="清空", command=self.on_clear).pack(side="left")

        self.analysis_label = ttk.Label(input_frame, text="尚未选择文件", foreground="#666")
        self.analysis_label.pack(fill="x", padx=8, pady=(0, 8))

        # 2. 压缩档位
        tier_frame = ttk.LabelFrame(parent, text="2. 压缩档位（向右更小，向左更清晰）")
        tier_frame.pack(fill="x", **pad)

        self.scale = ttk.Scale(
            tier_frame,
            from_=0,
            to=len(engine.QUALITY_TIERS) - 1,
            orient="horizontal",
            command=self.on_scale_move,
        )
        self.scale.pack(fill="x", padx=10, pady=(10, 2))
        self.scale.bind("<ButtonRelease-1>", lambda e: self.schedule_preview())

        ticks = ttk.Frame(tier_frame)
        ticks.pack(fill="x", padx=10)
        for label, *_ in engine.QUALITY_TIERS:
            ttk.Label(ticks, text=label, font=("", 9)).pack(side="left", expand=True)

        self.tier_desc = ttk.Label(tier_frame, text="", foreground="#333", wraplength=560, justify="left")
        self.tier_desc.pack(fill="x", padx=10, pady=(6, 10))

        # 2.5 视频压缩（可选，需要 ffmpeg）
        video_frame = ttk.LabelFrame(parent, text="视频压缩（可选）")
        video_frame.pack(fill="x", **pad)
        vrow = ttk.Frame(video_frame)
        vrow.pack(fill="x", padx=10, pady=(8, 2))
        self.video_check = ttk.Checkbutton(
            vrow,
            text="同时压缩视频（需要 ffmpeg）",
            variable=self.compress_video_var,
            command=self.on_toggle_video,
            state="disabled",
        )
        self.video_check.pack(side="left")
        self.ffmpeg_status = ttk.Label(vrow, text="", foreground="#666")
        self.ffmpeg_status.pack(side="right")
        self.video_hint = ttk.Label(
            video_frame, text="选择含视频的 PPT 后这里会给出说明。",
            foreground="#777", wraplength=560, justify="left",
        )
        self.video_hint.pack(fill="x", padx=10, pady=(0, 8))
        self._refresh_ffmpeg_status()

        # 3. 预览
        preview_frame = ttk.LabelFrame(parent, text="3. 压缩后大小预览（真实试压，不改原文件）")
        preview_frame.pack(fill="x", **pad)
        prow = ttk.Frame(preview_frame)
        prow.pack(fill="x", padx=10, pady=8)
        self.preview_label = ttk.Label(prow, text="原始 —  →  压缩后 —", font=("", 13, "bold"))
        self.preview_label.pack(side="left")
        self.preview_btn = ttk.Button(prow, text="刷新预览", command=self.schedule_preview)
        self.preview_btn.pack(side="right")
        self.preview_progress = ttk.Progressbar(preview_frame, mode="indeterminate")

        # 4. 输出 + 操作
        out_frame = ttk.Frame(parent)
        out_frame.pack(fill="x", **pad)
        ttk.Label(out_frame, text="输出目录:").pack(side="left")
        self.output_dir_label = ttk.Label(out_frame, text="（与源文件同目录，文件名加 _compressed）", foreground="#666")
        self.output_dir_label.pack(side="left", padx=8)
        ttk.Button(out_frame, text="选择…", command=self.on_choose_output_dir).pack(side="left")
        ttk.Button(out_frame, text="重置", command=self.on_reset_output_dir).pack(side="left", padx=4)

        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", **pad)
        self.compress_btn = ttk.Button(action_frame, text="开始压缩并保存", command=self.on_compress)
        self.compress_btn.pack(side="left")
        self.progress = ttk.Progressbar(action_frame, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)

        # 说明 + 日志
        bottom = ttk.Frame(parent)
        bottom.pack(fill="both", expand=True, **pad)

        note = ttk.LabelFrame(bottom, text="压缩会损失什么？")
        note.pack(fill="x")
        note_text = (
            "• 文字、排版、动画、切换、母版、嵌入字体完全不动。\n"
            "• 图片清晰度按所选档位降低（投影/屏幕一般看不出，放大或打印可能变糊，且不可逆）。\n"
            "• 视频默认保留原样；勾选“同时压缩视频”后会转码（清晰度下降、不可逆，需 ffmpeg）。\n"
            "• 始终只在“压得更小”时才替换，绝不会把文件改大。"
        )
        ttk.Label(note, text=note_text, justify="left", foreground="#444").pack(fill="x", padx=10, pady=8)

        log_frame = ttk.LabelFrame(bottom, text="日志")
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=5, state="disabled", wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.log_text.config(yscrollcommand=log_scroll.set)

        self.scale.set(engine.DEFAULT_TIER)  # 此时 tier_desc 已存在，回调安全
        self._update_tier_desc()

    # ---------- 档位 ----------
    def _tier_index(self) -> int:
        return max(0, min(len(engine.QUALITY_TIERS) - 1, round(float(self.scale.get()))))

    def on_scale_move(self, _value):
        # 拖动时只更新文字说明；松手才真正试压（见 ButtonRelease 绑定）
        self._update_tier_desc()

    def _update_tier_desc(self):
        label, dpi, q, desc = engine.QUALITY_TIERS[self._tier_index()]
        self.tier_desc.config(text=f"【{label}】{desc}（目标 {dpi} DPI，JPEG 质量 {q}）")

    # ---------- 文件 ----------
    def on_add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 PPT 文件", filetypes=[("PowerPoint 演示文稿", "*.pptx"), ("所有文件", "*.*")]
        )
        added = 0
        for p in paths:
            path = Path(p)
            if path.suffix.lower() != ".pptx":
                self.log(f"跳过（仅支持 .pptx）：{path.name}")
                continue
            if path not in self.files:
                self.files.append(path)
                self.file_listbox.insert(tk.END, str(path))
                added += 1
        if added:
            self._refresh_analysis()

    def on_remove_selected(self):
        sel = list(self.file_listbox.curselection())
        for idx in reversed(sel):
            self.file_listbox.delete(idx)
            del self.files[idx]
        self._refresh_analysis()

    def on_clear(self):
        self.file_listbox.delete(0, tk.END)
        self.files.clear()
        self.analyses.clear()
        self.total_original = 0
        self.analysis_label.config(text="尚未选择文件", foreground="#666")
        self.preview_label.config(text="原始 —  →  压缩后 —")
        self.has_video = False
        self.video_size = 0
        self.compress_video_var.set(False)
        self.video_check.config(state="disabled")
        self.video_hint.config(text="选择含视频的 PPT 后这里会给出说明。", foreground="#777")

    def on_choose_output_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir = Path(d)
            self.output_dir_label.config(text=str(self.output_dir), foreground="black")

    def on_reset_output_dir(self):
        self.output_dir = None
        self.output_dir_label.config(text="（与源文件同目录，文件名加 _compressed）", foreground="#666")

    # ---------- 分析 ----------
    def _refresh_analysis(self):
        if not self.files:
            self.on_clear()
            return
        self.analysis_label.config(text="正在分析…", foreground="#666")
        threading.Thread(target=self._analyze_worker, args=(list(self.files),), daemon=True).start()

    def _analyze_worker(self, files):
        results = {}
        for f in files:
            try:
                results[f] = engine.analyze(f)
            except Exception as e:
                self.log(f"分析失败 {f.name}: {e}")
        self.root.after(0, lambda: self._analyze_done(results))

    def _analyze_done(self, results):
        self.analyses = results
        self.total_original = sum(r.total_size for r in results.values())
        img = sum(r.image_count for r in results.values())
        img_sz = sum(r.image_size for r in results.values())
        vid = sum(r.video_count for r in results.values())
        vid_sz = sum(r.video_size for r in results.values())
        fonts = any(r.has_embedded_fonts for r in results.values())

        parts = [
            f"共 {len(results)} 个文件，原始 {engine.human_size(self.total_original)}",
            f"图片 {img} 张 / {engine.human_size(img_sz)}（可压缩）",
        ]
        if vid:
            parts.append(f"视频 {vid} 个 / {engine.human_size(vid_sz)}")
        if fonts:
            parts.append("含嵌入字体（不处理）")
        self.analysis_label.config(text="  ·  ".join(parts), foreground="#333")
        self.preview_label.config(
            text=f"原始 {engine.human_size(self.total_original)}  →  压缩后 ?（点“刷新预览”）"
        )

        # 视频区状态
        self.has_video = vid > 0
        self.video_size = vid_sz
        self._update_video_hint(vid, vid_sz)

        self.schedule_preview()

    def _update_video_hint(self, vid_count, vid_sz):
        if not self.has_video:
            self.compress_video_var.set(False)
            self.video_check.config(state="disabled")
            self.video_hint.config(text="本 PPT 未检测到视频，无需此选项。", foreground="#777")
            return
        self.video_check.config(state="normal")
        # 不压缩视频时的体积下限 ≈ 原始 - 图片可省的部分；视频原样保留是硬地板
        floor_hint = (
            f"检测到视频 {vid_count} 个 / 共 {engine.human_size(vid_sz)}。"
            f"不压缩视频时，体积下限约为视频本身的大小 {engine.human_size(vid_sz)}（再小压不动了）。"
            f"勾选“同时压缩视频”可进一步缩小，但视频清晰度会下降。"
        )
        self.video_hint.config(text=floor_hint, foreground="#444")

    # ---------- ffmpeg / 视频 ----------
    def _refresh_ffmpeg_status(self):
        self.ffmpeg = video.find_ffmpeg()
        if self.ffmpeg:
            self.ffmpeg_status.config(text="✓ ffmpeg 已就绪", foreground="#2a7")
        else:
            self.ffmpeg_status.config(text="未安装 ffmpeg", foreground="#b80")

    def on_toggle_video(self):
        if not self.compress_video_var.get():
            self.schedule_preview()
            return
        # 想开启视频压缩：没有 ffmpeg 就询问是否下载
        if not self.ffmpeg:
            hint = video.download_hint()
            if not video.can_download():
                messagebox.showinfo(
                    "需要 ffmpeg",
                    "压缩视频需要 ffmpeg，但当前系统不支持自动下载，请手动安装后重试。",
                )
                self.compress_video_var.set(False)
                return
            yes = messagebox.askyesno(
                "需要 ffmpeg",
                f"压缩视频需要 ffmpeg（{hint}）。\n是否现在自动下载？\n\n"
                "不下载也可以使用——只是无法压缩视频，文件只能压到“视频本身大小”这个下限。",
            )
            if not yes:
                self.compress_video_var.set(False)
                return
            self._download_ffmpeg()
            return
        self.schedule_preview()

    def _download_ffmpeg(self):
        self._busy = True
        self.video_check.config(state="disabled")
        self.preview_btn.config(state="disabled")
        self.compress_btn.config(state="disabled")
        self.ffmpeg_status.config(text="正在下载 ffmpeg…", foreground="#888")
        self.preview_progress.pack(fill="x", padx=10, pady=(0, 8))
        self.preview_progress.start(10)
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            video.download_ffmpeg(progress_cb=None, log=self.log)
            self.root.after(0, lambda: self._download_done(True))
        except Exception as e:
            self.log(f"ffmpeg 下载失败: {e}")
            self.root.after(0, lambda: self._download_done(False))

    def _download_done(self, ok):
        self.preview_progress.stop()
        self.preview_progress.pack_forget()
        self._busy = False
        self.video_check.config(state="normal")
        self.preview_btn.config(state="normal")
        self.compress_btn.config(state="normal")
        self._refresh_ffmpeg_status()
        if ok and self.ffmpeg:
            self.compress_video_var.set(True)
            messagebox.showinfo("完成", "ffmpeg 已就绪，现在可以压缩视频了。")
            self.schedule_preview()
        else:
            self.compress_video_var.set(False)
            messagebox.showerror("下载失败", "未能自动安装 ffmpeg，请检查网络或手动安装。详见日志。")

    # ---------- 真实预览 ----------
    def schedule_preview(self):
        if not self.files or self._busy:
            return
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(300, self._start_preview)

    def _start_preview(self):
        self._preview_job = None
        if not self.files:
            return
        tier = self._tier_index()
        self._busy = True
        self.preview_btn.config(state="disabled")
        self.compress_btn.config(state="disabled")
        self.preview_progress.pack(fill="x", padx=10, pady=(0, 8))
        self.preview_progress.start(10)
        self.preview_label.config(text=f"原始 {engine.human_size(self.total_original)}  →  正在试压…")
        cv = self.compress_video_var.get() and bool(self.ffmpeg)
        threading.Thread(
            target=self._preview_worker, args=(list(self.files), tier, cv), daemon=True
        ).start()

    def _preview_worker(self, files, tier, compress_video):
        total_new = 0
        ok = True
        for f in files:
            try:
                r = engine.estimate(f, tier, compress_video=compress_video, ffmpeg=self.ffmpeg)
                total_new += r.new_size
            except Exception as e:
                ok = False
                self.log(f"预览失败 {f.name}: {e}")
        self.root.after(0, lambda: self._preview_done(total_new, ok, tier, compress_video))

    def _preview_done(self, total_new, ok, tier, compress_video):
        self.preview_progress.stop()
        self.preview_progress.pack_forget()
        self._busy = False
        self.preview_btn.config(state="normal")
        self.compress_btn.config(state="normal")
        if not ok:
            self.preview_label.config(text="预览出错，详见日志")
            return
        saved = max(0, self.total_original - total_new)
        ratio = (saved / self.total_original * 100) if self.total_original else 0
        label = engine.QUALITY_TIERS[tier][0]
        vtag = "含视频" if compress_video else ("仅图片，视频保留" if self.has_video else "")
        suffix = f"，{vtag}" if vtag else ""
        self.preview_label.config(
            text=f"原始 {engine.human_size(self.total_original)}  →  "
            f"压缩后 {engine.human_size(total_new)}  （省 {ratio:.0f}%，档位：{label}{suffix}）"
        )

    # ---------- 压缩保存 ----------
    def on_compress(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加 PPT 文件")
            return
        if not PILLOW_OK:
            messagebox.showerror("缺少依赖", "未检测到 Pillow，请先运行：pip3 install Pillow python-pptx")
            return
        tier = self._tier_index()
        self._busy = True
        self.compress_btn.config(state="disabled")
        self.preview_btn.config(state="disabled")
        cv = self.compress_video_var.get() and bool(self.ffmpeg)
        if cv:
            self.log("已开启视频压缩，转码较慢，请耐心等待…")
        self.progress.config(value=0, maximum=len(self.files))
        threading.Thread(
            target=self._compress_worker, args=(list(self.files), tier, cv), daemon=True
        ).start()

    def _compress_worker(self, files, tier, compress_video):
        ok = fail = 0
        for i, f in enumerate(files):
            try:
                dst_dir = self.output_dir if self.output_dir else f.parent
                dst_dir.mkdir(parents=True, exist_ok=True)
                dst = dst_dir / f"{f.stem}_compressed.pptx"
                self.log(f"→ 压缩: {f.name}")
                r = engine.compress_file(
                    f, dst, tier, compress_video=compress_video, ffmpeg=self.ffmpeg
                )
                extra = f"，视频 {r.videos_shrunk}/{r.videos_processed} 个转码" if r.videos_processed else ""
                note = ""
                if r.skipped_video_size:
                    note = f"（含未压缩视频 {engine.human_size(r.skipped_video_size)}）"
                self.log(
                    f"  ✓ {engine.human_size(r.original_size)} → {engine.human_size(r.new_size)} "
                    f"省 {r.ratio*100:.0f}%，图片 {r.images_shrunk}/{r.images_processed} 张缩小{extra} {note}"
                )
                self.log(f"    输出: {dst}")
                ok += 1
            except Exception as e:
                self.log(f"  ✗ 失败: {e}")
                fail += 1
            self.root.after(0, lambda v=i + 1: self.progress.config(value=v))
        self.log(f"完成。成功 {ok}，失败 {fail}")
        self.root.after(0, self._compress_done)

    def _compress_done(self):
        self._busy = False
        self.compress_btn.config(state="normal")
        self.preview_btn.config(state="normal")
