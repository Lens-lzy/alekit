#!/usr/bin/env python3
"""集成工具箱 —— 左侧选择工具，右侧使用。

新增工具：实现一个 tools.base.Tool 子类，并在 tools/__init__.py 的 TOOLS 注册。
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from tools import TOOLS

APP_TITLE = "Alek 的锦囊"
SIDEBAR_BG = "#f0f0f3"
SIDEBAR_SEL = "#d8e6ff"


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
        sidebar = tk.Frame(outer, bg=SIDEBAR_BG, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="🧰 Alek 的锦囊", bg=SIDEBAR_BG, fg="#222",
            font=("", 15, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(18, 12))

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
