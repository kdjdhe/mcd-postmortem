"""启动页与结果页。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from mcd_postmortem import service
from mcd_postmortem.gui import theme

MCP_CONSOLE = "https://open.mcd.cn/mcp"


def _font(size=14, weight="normal"):
    return ctk.CTkFont(family=theme.FONT_FAMILY, size=size, weight=weight)


class HomePage(ctk.CTkFrame):
    """两个入口：demo 体验与真实订单审计；高级选项默认折叠。"""

    def __init__(self, master, app):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.grid_columnconfigure(0, weight=1, uniform="card")
        self.grid_columnconfigure(1, weight=1, uniform="card")
        self._advanced_open = False
        self._build_cards()
        self._build_advanced()
        self._build_footer()

    def _build_footer(self):
        self.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(
            self,
            text="确定性规则 · 无需 LLM    ·    Token 仅在本次请求中使用，不写入磁盘"
                 "    ·    分享卡片自动隐藏订单号与门店",
            font=_font(11), text_color=theme.MUTED, anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="sw", pady=(12, 0))

    # ---------- 构建 ----------

    def _build_cards(self):
        demo = self._card(0, "无需 Token", "先看看效果", "用 7 笔虚构订单生成一份完整的 SRE 复盘和分享卡片。")
        ctk.CTkLabel(demo, text="· 覆盖全部 7 条规则\n· 终端报告 + 1000×1414 分享卡片",
                     font=_font(12), text_color=theme.MUTED, anchor="w",
                     justify="left").pack(anchor="w", padx=22, pady=(10, 0))
        self._primary_button(demo, "立即体验", self._start_demo)

        audit = self._card(1, "需要 MCP Token", "审计我的真实订单",
                           "从麦当劳官方 MCP 拉取历史订单，生成属于你的复盘。")
        token_row = ctk.CTkFrame(audit, fg_color="transparent")
        token_row.pack(fill="x", pady=(10, 6))
        self.token_entry = ctk.CTkEntry(token_row, show="•", height=38,
                                        placeholder_text="粘贴 MCD_MCP_TOKEN",
                                        font=_font(13), fg_color=theme.PAPER,
                                        border_color=theme.LINE)
        self.token_entry.pack(side="left", fill="x", expand=True)
        self.token_entry.bind("<Return>", lambda _event: self._start_audit())
        self.token_toggle = ctk.CTkButton(
            token_row, text="显示", width=52, height=38, font=_font(12),
            fg_color="transparent", hover_color=theme.ACCENT_SOFT,
            text_color=theme.MUTED, border_width=1, border_color=theme.LINE,
            command=self._toggle_token)
        self.token_toggle.pack(side="left", padx=(8, 0))

        link = ctk.CTkButton(audit, text="去 MCP 控制台申请 Token →", anchor="w",
                             fg_color="transparent", hover_color=theme.ACCENT_SOFT,
                             text_color=theme.ACCENT, font=_font(12), height=24,
                             command=lambda: webbrowser.open(MCP_CONSOLE))
        link.pack(fill="x", pady=(0, 6))

        self.error_label = ctk.CTkLabel(audit, text="", text_color=theme.ACCENT,
                                        font=_font(12), anchor="w", justify="left")
        self.error_label.pack(fill="x", pady=(0, 2))
        self._primary_button(audit, "开始审计", self._start_audit)

    def _card(self, column, tag, title, description):
        card = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=14,
                            border_width=1, border_color=theme.LINE)
        padx = (0, 12) if column == 0 else (12, 0)
        card.grid(row=0, column=column, sticky="nsew", padx=padx, pady=(4, 14))
        ctk.CTkLabel(card, text=tag, fg_color=theme.ACCENT_SOFT, corner_radius=6,
                     text_color=theme.ACCENT, font=_font(11, "bold"), height=24).pack(
            anchor="w", padx=22, pady=(20, 8), ipadx=8)
        ctk.CTkLabel(card, text=title, font=_font(21, "bold"), text_color=theme.INK,
                     anchor="w").pack(anchor="w", padx=22)
        ctk.CTkLabel(card, text=description, font=_font(12), text_color=theme.MUTED,
                     anchor="w", justify="left", wraplength=380).pack(
            anchor="w", padx=22, pady=(4, 0))
        return card

    def _primary_button(self, parent, text, command):
        ctk.CTkButton(parent, text=text, height=42, font=_font(15, "bold"),
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      text_color="#ffffff", command=command).pack(
            side="bottom", fill="x", padx=22, pady=(12, 20))

    def _build_advanced(self):
        self.toggle_button = ctk.CTkButton(
            self, text="▸ 高级选项", anchor="w", height=28, font=_font(13),
            fg_color="transparent", hover_color=theme.ACCENT_SOFT,
            text_color=theme.MUTED, command=self._toggle_advanced)
        self.toggle_button.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.advanced = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=12,
                                     border_width=1, border_color=theme.LINE)
        for col, weight in ((0, 0), (1, 1), (2, 0), (3, 1)):
            self.advanced.grid_columnconfigure(col, weight=weight)
        self.since_var = ctk.StringVar(value="全部")
        self.sev_var = ctk.StringVar(value="全部")
        self.combo_var = ctk.StringVar(value="不猜测（unknown）")

        self._advanced_label(0, 0, "时间范围")
        ctk.CTkOptionMenu(self.advanced, values=["全部", "最近 7 天", "最近 30 天", "最近 90 天"],
                          variable=self.since_var, width=150, font=_font(12),
                          fg_color=theme.PAPER, button_color=theme.LINE,
                          button_hover_color=theme.ACCENT_SOFT,
                          text_color=theme.INK).grid(row=0, column=1, sticky="w", padx=(8, 24), pady=10)
        self._advanced_label(0, 2, "严重级别")
        ctk.CTkOptionMenu(self.advanced, values=["全部", "SEV1", "SEV2", "SEV3", "SEV4", "SEV5", "INFO"],
                          variable=self.sev_var, width=110, font=_font(12),
                          fg_color=theme.PAPER, button_color=theme.LINE,
                          button_hover_color=theme.ACCENT_SOFT,
                          text_color=theme.INK).grid(row=0, column=3, sticky="w", padx=(8, 20), pady=10)

        self._advanced_label(1, 0, "套餐口径")
        ctk.CTkOptionMenu(self.advanced,
                          values=["不猜测（unknown）", "按份（per-parent）", "整单（per-order）"],
                          variable=self.combo_var, width=170, font=_font(12),
                          fg_color=theme.PAPER, button_color=theme.LINE,
                          button_hover_color=theme.ACCENT_SOFT,
                          text_color=theme.INK).grid(row=1, column=1, sticky="w", padx=(8, 24), pady=10)
        self._advanced_label(1, 2, "审计时间")
        self.at_entry = ctk.CTkEntry(self.advanced, height=32,
                                     placeholder_text="YYYY-MM-DD HH:MM，留空=当前",
                                     font=_font(12), fg_color=theme.PAPER,
                                     border_color=theme.LINE)
        self.at_entry.grid(row=1, column=3, sticky="ew", padx=(8, 20), pady=10)

        checks = ctk.CTkFrame(self.advanced, fg_color="transparent")
        checks.grid(row=2, column=0, columnspan=4, sticky="w", padx=16, pady=(0, 10))
        self.all_statuses = ctk.CTkCheckBox(checks, text="包含未完成/未知状态订单", font=_font(12),
                                            checkbox_width=18, checkbox_height=18,
                                            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                            text_color=theme.MUTED)
        self.all_statuses.pack(side="left", padx=(0, 24))
        self.refresh_nutrition = ctk.CTkCheckBox(checks, text="刷新营养缓存（仅 audit）",
                                                 font=_font(12), checkbox_width=18,
                                                 checkbox_height=18, fg_color=theme.ACCENT,
                                                 hover_color=theme.ACCENT_HOVER,
                                                 text_color=theme.MUTED)
        self.refresh_nutrition.pack(side="left")

    def _advanced_label(self, row, column, text):
        ctk.CTkLabel(self.advanced, text=text, font=_font(12), text_color=theme.MUTED,
                     anchor="w").grid(row=row, column=column, sticky="w", padx=(16, 0), pady=10)

    # ---------- 交互 ----------

    def _toggle_advanced(self):
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self.advanced.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            self.toggle_button.configure(text="▾ 高级选项")
        else:
            self.advanced.grid_remove()
            self.toggle_button.configure(text="▸ 高级选项")

    def _toggle_token(self):
        if self.token_entry.cget("show"):
            self.token_entry.configure(show="")
            self.token_toggle.configure(text="隐藏")
        else:
            self.token_entry.configure(show="•")
            self.token_toggle.configure(text="显示")

    def token(self):
        return self.token_entry.get().strip()

    def show_error(self, message):
        self.error_label.configure(text=message)

    def clear_error(self):
        self.error_label.configure(text="")

    def options(self) -> service.AuditOptions:
        since = {"全部": None, "最近 7 天": 7, "最近 30 天": 30,
                 "最近 90 天": 90}[self.since_var.get()]
        sev = None if self.sev_var.get() == "全部" else self.sev_var.get()
        combo = {"不猜测（unknown）": "unknown", "按份（per-parent）": "per-parent",
                 "整单（per-order）": "per-order"}[self.combo_var.get()]
        return service.AuditOptions(
            since_days=since, sev=sev, at=self._parse_at(),
            all_statuses=bool(self.all_statuses.get()),
            combo_quantities=combo,
            refresh_nutrition=bool(self.refresh_nutrition.get()))

    def _parse_at(self):
        text = self.at_entry.get().strip()
        if not text:
            return None
        value = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                value = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if value is None:
            try:
                value = datetime.fromisoformat(text)
            except ValueError:
                raise ValueError("审计时间格式应为 2026-10-15 12:00（留空则用当前时间）") from None
        if value.tzinfo:
            value = value.astimezone(service.SHANGHAI).replace(tzinfo=None)
        return value

    def _start_demo(self):
        self.clear_error()
        try:
            options = self.options()
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.app.start_demo(options)

    def _start_audit(self):
        self.clear_error()
        if not self.token():
            self.show_error("请先填入 MCD_MCP_TOKEN；也可以先点左侧「立即体验」")
            self.token_entry.focus_set()
            return
        try:
            options = self.options()
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.app.start_audit(options, self.token())


class ResultPage(ctk.CTkFrame):
    """卡片预览 + 详细报告 / JSON。"""

    def __init__(self, master, app):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.result = None
        self._ctk_image = None
        self._last_saved = None
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_body()
        self._build_status()

    # ---------- 构建 ----------

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=28, pady=(16, 8))
        ctk.CTkButton(bar, text="← 重新审计", width=110, height=34, font=_font(13),
                      fg_color="transparent", hover_color=theme.ACCENT_SOFT,
                      text_color=theme.MUTED, border_width=1, border_color=theme.LINE,
                      command=self.app.show_home).pack(side="left")
        self.save_button = ctk.CTkButton(
            bar, text="保存 PNG", width=100, height=34, font=_font(13, "bold"),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.save_png)
        self.save_button.pack(side="right")
        self.open_button = ctk.CTkButton(
            bar, text="打开文件夹", width=104, height=34, font=_font(13),
            fg_color="transparent", hover_color=theme.ACCENT_SOFT,
            text_color=theme.MUTED, border_width=1, border_color=theme.LINE,
            state="disabled", command=self.open_folder)
        self.open_button.pack(side="right", padx=8)
        self.copy_button = ctk.CTkButton(
            bar, text="复制 JSON", width=100, height=34, font=_font(13),
            fg_color="transparent", hover_color=theme.ACCENT_SOFT,
            text_color=theme.MUTED, border_width=1, border_color=theme.LINE,
            command=self.copy_json)
        self.copy_button.pack(side="right")

    def _build_body(self):
        preview_card = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=14,
                                    border_width=1, border_color=theme.LINE)
        preview_card.grid(row=1, column=0, sticky="ns", padx=(28, 12), pady=(0, 12))
        self.preview = ctk.CTkLabel(preview_card, text="", fg_color="transparent")
        self.preview.pack(padx=16, pady=(16, 6))
        ctk.CTkLabel(preview_card, text="分享版已隐藏订单号与门店", font=_font(11),
                     text_color=theme.MUTED).pack(pady=(0, 12))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=(12, 28), pady=(0, 12))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        self.summary_label = ctk.CTkLabel(right, text="", font=_font(15, "bold"),
                                          text_color=theme.INK, anchor="w", justify="left")
        self.summary_label.grid(row=0, column=0, sticky="ew")
        self.warn_label = ctk.CTkLabel(right, text="", font=_font(12), text_color=theme.ACCENT,
                                       anchor="w")
        self.warn_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.tabs = ctk.CTkTabview(
            right, fg_color=theme.SURFACE, border_width=1, border_color=theme.LINE,
            segmented_button_fg_color=theme.PAPER,
            segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.PAPER,
            text_color=theme.INK, corner_radius=12)
        self.tabs.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        report_tab = self.tabs.add("详细报告")
        json_tab = self.tabs.add("JSON")
        self.report_box = ctk.CTkTextbox(
            report_tab, fg_color=theme.SURFACE, border_width=0, wrap="word",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=13),
            text_color=theme.INK, scrollbar_button_color=theme.LINE)
        self.report_box.pack(fill="both", expand=True, padx=8, pady=8)
        self.json_box = ctk.CTkTextbox(
            json_tab, fg_color=theme.SURFACE, border_width=0, wrap="none",
            font=ctk.CTkFont(family=theme.MONO_FAMILY, size=12),
            text_color=theme.INK, scrollbar_button_color=theme.LINE)
        self.json_box.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_status(self):
        self.status = ctk.CTkLabel(self, text="", font=_font(12), text_color=theme.MUTED,
                                   anchor="w", justify="left")
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=30, pady=(0, 12))

    # ---------- 数据 ----------

    def load(self, result):
        self.result = result
        self._last_saved = None
        self.open_button.configure(state="disabled")

        image = Image.open(result.card_path)
        image.thumbnail((430, 580), Image.LANCZOS)
        self._ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
        self.preview.configure(image=self._ctk_image, text="")

        distribution = "  ".join(f"{sev} × {count}"
                                  for sev, count in result.summary["by_sev"].items())
        filtered = ""
        if result.summary.get("severityFilter"):
            filtered = (f"（全部 {result.summary['totalIncidentsBeforeFilter']} 起，"
                        f"当前仅显示 {result.summary['severityFilter']}）")
        self.summary_label.configure(
            text=f"订单 {len(result.orders)} 笔 · 事件 {len(result.incidents)} 起{filtered}"
                 + (f"\n{distribution}" if distribution else ""))

        if result.summary["ruleErrors"]:
            self.warn_label.configure(text="⚠ 部分规则执行失败，本次审计不完整（见 ENGINE-* 事件）")
        else:
            self.warn_label.configure(text="")

        self._set_text(self.report_box, result.report_text)
        self._set_text(self.json_box,
                       json.dumps(result.report_json, ensure_ascii=False, indent=2))
        self.tabs.set("详细报告")

        source = "合成演示数据" if result.summary["source"] == "demo" else "麦当劳官方 MCP"
        self.status.configure(
            text=f"审计时间 {result.at:%Y-%m-%d %H:%M}（北京时间） · 数据来源：{source} · "
                 f"卡片为临时文件，点击「保存 PNG」导出")

    @staticmethod
    def _set_text(box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.see("1.0")
        box.configure(state="disabled")

    # ---------- 动作 ----------

    def save_png(self):
        if not self.result or not self.result.card_path:
            return
        default = f"mcd-postmortem-{self.result.at:%Y%m%d-%H%M}.png"
        target = filedialog.asksaveasfilename(
            parent=self, title="保存分享卡片", defaultextension=".png",
            initialfile=default, filetypes=[("PNG 图片", "*.png")])
        if not target:
            return
        shutil.copyfile(self.result.card_path, target)
        self._last_saved = Path(target)
        self.open_button.configure(state="normal")
        self.status.configure(text=f"已保存：{target}")

    def open_folder(self):
        target = self._last_saved
        if target is None and self.result and self.result.card_path:
            target = Path(self.result.card_path)
        if target is None:
            return
        try:
            if sys.platform == "win32":
                os.startfile(target.parent)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target.parent)])
            else:
                subprocess.Popen(["xdg-open", str(target.parent)])
        except OSError as exc:
            messagebox.showerror("无法打开文件夹", str(exc), parent=self)

    def copy_json(self):
        if not self.result:
            return
        self.clipboard_clear()
        self.clipboard_append(json.dumps(self.result.report_json, ensure_ascii=False, indent=2))
        self.update_idletasks()
        self.status.configure(text="JSON 已复制到剪贴板")
