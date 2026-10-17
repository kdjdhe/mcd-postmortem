"""桌面窗口入口：启动页 → 后台审计 → 结果页。

Tkinter 不是线程安全的：审计在 worker 线程执行，进度与结果通过队列回传，
由主线程的 after() 轮询消费。
"""
from __future__ import annotations

import queue
import tempfile
import threading
import uuid
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from mcd_postmortem import __version__, service
from mcd_postmortem.gui import pages, theme


def _font(size=14, weight="normal"):
    return ctk.CTkFont(family=theme.FONT_FAMILY, size=size, weight=weight)


class BusyOverlay(ctk.CTkFrame):
    """不确定进度指示；不阻塞主线程。"""

    def __init__(self, master):
        super().__init__(master, fg_color=theme.PAPER, corner_radius=16,
                         border_width=1, border_color=theme.LINE)
        self.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(self, text="正在审计…", font=_font(18, "bold"),
                                        text_color=theme.INK)
        self.title_label.grid(row=0, column=0, padx=42, pady=(26, 10))
        self.bar = ctk.CTkProgressBar(self, mode="indeterminate", width=300,
                                      progress_color=theme.ACCENT, fg_color=theme.LINE)
        self.bar.grid(row=1, column=0, padx=42, pady=(0, 10))
        self.stage = ctk.CTkLabel(self, text="", font=_font(12), text_color=theme.MUTED)
        self.stage.grid(row=2, column=0, padx=42, pady=(0, 24))

    def show(self, title):
        self.title_label.configure(text=title)
        self.stage.configure(text="")
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.lift()
        self.bar.start()

    def set_stage(self, message):
        self.stage.configure(text=message)

    def hide(self):
        self.bar.stop()
        self.place_forget()


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        super().__init__(fg_color=theme.BG)
        self.title("麦门彻查 · mcd-postmortem")
        self.geometry("1100x780")
        self.minsize(1000, 700)
        self._set_icon()
        self._busy = False
        self._queue = None
        self._build_header()

        container = ctk.CTkFrame(self, fg_color=theme.BG)
        container.pack(fill="both", expand=True)
        self.home = pages.HomePage(container, self)
        self.result_page = pages.ResultPage(container, self)
        self.overlay = BusyOverlay(self)
        self.show_home()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(20, 4))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="麦门彻查  ·  mcd-postmortem", font=_font(24, "bold"),
                     text_color=theme.INK, anchor="w").pack(anchor="w")
        ctk.CTkLabel(left, text="把你的麦当劳订单审计成一份 SRE 事故复盘",
                     font=_font(13), text_color=theme.MUTED, anchor="w").pack(anchor="w")
        ctk.CTkLabel(header, text=f"v{__version__}", font=_font(12),
                     text_color=theme.MUTED).pack(side="right", anchor="n")

    def _set_icon(self):
        icon = Path(__file__).with_name("icon.ico")
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except Exception:
                pass

    # ---------- 页面切换 ----------

    def show_home(self):
        self.result_page.pack_forget()
        self.home.pack(fill="both", expand=True, padx=32, pady=(8, 18))
        self.home.clear_error()

    def show_result(self, result):
        self.home.pack_forget()
        self.result_page.pack(fill="both", expand=True, padx=32, pady=(4, 14))
        self.result_page.load(result)

    # ---------- 任务 ----------

    def start_demo(self, options):
        options.card_path = self._temp_card()
        self._start(lambda progress: service.run_demo(options, progress=progress),
                    "正在生成演示报告…")

    def start_audit(self, options, token):
        options.card_path = self._temp_card()
        self._start(lambda progress: service.run_audit(options, token=token, progress=progress),
                    "正在审计真实订单…")

    @staticmethod
    def _temp_card():
        return Path(tempfile.gettempdir()) / f"mcd-postmortem-{uuid.uuid4().hex[:8]}.png"

    def _start(self, runner, title):
        if self._busy:
            return
        self._busy = True
        self._queue = queue.Queue()
        self.overlay.show(title)
        threading.Thread(target=self._work, args=(runner,), daemon=True).start()
        self.after(80, self._drain)

    def _work(self, runner):
        try:
            result = runner(lambda stage, message: self._queue.put(("progress", message)))
            self._queue.put(("done", result))
        except Exception as exc:  # 展示给用户的错误：保留原始中文提示
            self._queue.put(("error", str(exc) or exc.__class__.__name__))

    def _drain(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self.overlay.set_stage(item[1])
                elif kind == "done":
                    self._busy = False
                    self.overlay.hide()
                    self.show_result(item[1])
                    return
                elif kind == "error":
                    self._busy = False
                    self.overlay.hide()
                    messagebox.showerror("审计失败", item[1], parent=self)
                    return
        except queue.Empty:
            pass
        if self._busy:
            self.after(80, self._drain)


def main():
    ctk.set_appearance_mode("light")
    App().mainloop()


if __name__ == "__main__":
    main()
