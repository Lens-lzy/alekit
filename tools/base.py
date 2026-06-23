"""工具基类。

每个工具是一个类，把自己的界面 build 到给定的父 Frame 里。
工具箱负责左侧导航与切换，工具只管自己的内容区。
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk


class Tool:
    # 子类覆盖这些
    id: str = "tool"
    title: str = "工具"
    icon: str = "🔧"          # 侧栏图标（emoji）
    subtitle: str = ""        # 内容区顶部的一句话说明

    def __init__(self, parent: ttk.Frame):
        self.parent = parent
        self.root = parent.winfo_toplevel()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.build(parent)
        self._poll_log()

    # 子类实现：把界面搭进 parent
    def build(self, parent: ttk.Frame) -> None:  # pragma: no cover
        raise NotImplementedError

    # ---- 通用日志（子类可调用 self.log，需自备名为 log_text 的 Text 控件）----
    def log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _poll_log(self) -> None:
        widget = getattr(self, "log_text", None)
        if widget is not None:
            try:
                while True:
                    msg = self.log_queue.get_nowait()
                    widget.config(state="normal")
                    widget.insert(tk.END, msg + "\n")
                    widget.see(tk.END)
                    widget.config(state="disabled")
            except queue.Empty:
                pass
        self.root.after(100, self._poll_log)
