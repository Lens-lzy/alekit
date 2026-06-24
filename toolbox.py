#!/usr/bin/env python3
"""集成工具箱 —— 左侧选择工具，右侧使用。

新增工具：实现一个 tools.base.Tool 子类，并在 tools/__init__.py 的 TOOLS 注册。
"""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import ttk

from tools import TOOLS

APP_NAME = "Alekit"
APP_VERSION = "1.0.1"
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"
REPO_URL = "https://github.com/Lens-lzy/alekit"
CONTACT_EMAIL = "ziyao.alek.liu@gmail.com"
SIDEBAR_BG = "#f0f0f3"
SIDEBAR_SEL = "#d8e6ff"
LINK_FG = "#2563eb"


class Toolbox:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("760x640")
        root.minsize(640, 560)

        self.tool_classes = list(TOOLS)
        self.tool_buttons: list[tk.Label] = []
        self.tool_frames: dict[int, ttk.Frame] = {}  # 懒加载并缓存
        self.tool_instances: dict[int, object] = {}
        self.current = -1

        self._build_ui()
        if self.tool_classes:
            self.select(0)

    def _build_ui(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        # 左侧栏
        sidebar = tk.Frame(outer, bg=SIDEBAR_BG, width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # 顶部品牌：名字大、版本号小
        brand = tk.Frame(sidebar, bg=SIDEBAR_BG)
        brand.pack(fill="x", padx=16, pady=(18, 12))
        tk.Label(
            brand, text=f"🧰 {APP_NAME}", bg=SIDEBAR_BG, fg="#222",
            font=("", 18, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            brand, text=f"v{APP_VERSION}", bg=SIDEBAR_BG, fg="#888",
            font=("", 10), anchor="w",
        ).pack(anchor="w")

        # 底部信息区（钉在左下角）
        self._build_info(sidebar)

        # 工具列表（占据中间剩余空间）
        for i, cls in enumerate(self.tool_classes):
            item = tk.Label(
                sidebar,
                text=f"  {cls.icon}  {cls.title}",
                bg=SIDEBAR_BG, fg="#333", anchor="w",
                font=("", 12), padx=8, pady=10, cursor="hand2",
            )
            item.pack(fill="x", padx=8, pady=2)
            item.bind("<Button-1>", lambda e, idx=i: self.select(idx))
            self.tool_buttons.append(item)

        # 右侧内容区
        right = ttk.Frame(outer)
        right.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(right)
        header.pack(fill="x", padx=16, pady=(14, 0))
        self.title_label = ttk.Label(header, text="", font=("", 16, "bold"))
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(header, text="", foreground="#777")
        self.subtitle_label.pack(anchor="w", pady=(2, 0))
        ttk.Separator(right, orient="horizontal").pack(fill="x", padx=16, pady=10)

        self.content = ttk.Frame(right)
        self.content.pack(fill="both", expand=True)

    def _build_info(self, sidebar: tk.Frame):
        """左下角信息区：版本号、GitHub 仓库、联系邮箱。"""
        info = tk.Frame(sidebar, bg=SIDEBAR_BG)
        info.pack(side="bottom", fill="x", padx=14, pady=(8, 14))

        tk.Frame(info, bg="#dcdce0", height=1).pack(fill="x", pady=(0, 8))

        def link(text, action, fg=LINK_FG):
            lbl = tk.Label(
                info, text=text, bg=SIDEBAR_BG, fg=fg, anchor="w",
                font=("", 10), cursor="hand2", justify="left",
            )
            lbl.pack(anchor="w")
            lbl.bind("<Button-1>", lambda e: action())
            return lbl

        tk.Label(
            info, text=f"关于 · 版本 v{APP_VERSION}", bg=SIDEBAR_BG, fg="#666",
            font=("", 10, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        link("↗ GitHub 仓库", lambda: webbrowser.open(REPO_URL))
        link(f"✉ {CONTACT_EMAIL}", lambda: webbrowser.open(f"mailto:{CONTACT_EMAIL}"), fg="#555")

    def select(self, idx: int):
        if idx == self.current:
            return
        self.current = idx
        for i, btn in enumerate(self.tool_buttons):
            btn.config(bg=SIDEBAR_SEL if i == idx else SIDEBAR_BG)

        # 隐藏其它工具的 frame
        for frame in self.tool_frames.values():
            frame.pack_forget()

        # 懒加载
        if idx not in self.tool_frames:
            frame = ttk.Frame(self.content)
            self.tool_frames[idx] = frame
            self.tool_instances[idx] = self.tool_classes[idx](frame)

        cls = self.tool_classes[idx]
        self.title_label.config(text=f"{cls.icon} {cls.title}")
        self.subtitle_label.config(text=cls.subtitle)
        self.tool_frames[idx].pack(fill="both", expand=True)


def main():
    root = tk.Tk()
    if os.uname().sysname == "Darwin":
        try:
            root.tk.call("tk::unsupported::MacWindowStyle", "style", root, "document", "")
        except tk.TclError:
            pass
        root.lift()
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    Toolbox(root)
    root.mainloop()


if __name__ == "__main__":
    main()
