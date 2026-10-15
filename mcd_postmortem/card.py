"""PNG 报告卡片渲染：一张正经的「事故复盘报告」首页.

设计参考正式 Postmortem 文书：报告头（编号/等级/状态）→ 事故概述 →
SEV 分布 → 变更时间线 → 根因 → 归档红章。字体优先微软雅黑（Windows 自带），
缺失时提示设置 MCD_FONT，避免中文静默变成方框。
"""
import os
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from mcd_postmortem.rules.base import SEV_ORDER
from mcd_postmortem.presentation import (coverage_text, nutrient_text, period_text,
                                         report_id, share_detail, source_label, status_label, audit_now)
from mcd_postmortem.report import _root_cause

W, H = 1000, 1414  # A5 比例 @ ~120dpi
MARGIN = 64

# 配色：文件纸感
BG = "#f7f4ee"          # 米白纸底
INK = "#1f2328"         # 正文墨色
MUTED = "#8a8f98"       # 次要
RULE = "#d8d2c4"        # 分隔线
SEV_COLOR = {
    "SEV1": "#c62828", "SEV2": "#e65100", "SEV3": "#8e24aa",
    "SEV4": "#00838f", "SEV5": "#546e7a", "INFO": "#2e7d32",
}

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",   # 黑体
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def _font(size: int, bold: bool = False):
    candidates = ([os.environ["MCD_FONT"]] if os.environ.get("MCD_FONT") else [])
    candidates += _FONT_CANDIDATES if bold else _FONT_CANDIDATES[1:]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise RuntimeError("未找到中文字体，请安装 Noto CJK 或设置 MCD_FONT 为字体文件路径")


def render_card(orders, incidents, summary, out_path: str,
                generated_at: datetime | None = None) -> str:
    now = generated_at or audit_now()
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_h1, f_h2 = _font(42, True), _font(23, True)
    f_body, f_small, f_tiny = _font(21), _font(18), _font(15)
    f_sev, f_stamp = _font(16, True), _font(30, True)
    x, width = MARGIN, W - 2 * MARGIN
    d.text((x, 60), "事故复盘报告", font=f_h1, fill=INK)
    d.text((x, 122), "INCIDENT POSTMORTEM", font=f_small, fill=MUTED)
    d.text((W - MARGIN - 325, 74), report_id(orders, summary, now), font=f_small, fill=INK)
    d.text((W - MARGIN - 325, 110), now.strftime("%Y-%m-%d %H:%M 北京时间"),
           font=f_tiny, fill=MUTED)
    d.line((x, 176, W - MARGIN, 176), fill=INK, width=3)
    top = _top_sev(incidents)
    for idx, (label, value) in enumerate((("等级", top or "—"), ("状态", "已归档"),
                                         ("订单数", str(len(orders))), ("事件数", str(len(incidents))))):
        bx = x + idx * 222
        d.text((bx, 201), label, font=f_small, fill=MUTED)
        if label == "等级" and top:
            _sev_badge(d, bx + 64, 196, top, f_sev)
        else:
            d.text((bx + 78, 196), value, font=f_h2, fill=INK)
    d.text((x, 243), source_label(summary) + " · 分享版已隐藏订单号与门店", font=f_small, fill=MUTED)
    status = status_label(summary)
    severity = summary.get("severityFilter") or "全部等级"
    excluded = sum(summary.get("excludedByStatus", {}).values())
    scope = f"{status} · {severity} · 按状态排除 {excluded} 笔"
    if summary.get("ruleErrors"):
        scope += " · 审计不完整（有规则失败）"
    d.text((x, 267), scope, font=f_tiny, fill=MUTED)
    y = _section(d, 288, "一、订单餐品统计", f_h2)
    for text in (f"{period_text(summary)} · {len(orders)} 笔订单，实付 ¥{summary['amount']:.2f}",
                 nutrient_text(summary)):
        d.text((x, y), _ellipsis(text, width, f_body), font=f_body, fill=INK)
        y += 32
    for text in coverage_text(summary).split("；"):
        d.text((x, y), _ellipsis(text, width, f_small), font=f_small, fill=MUTED)
        y += 27
    d.text((x, y), "仅计已知返回餐品；不代表个人实际摄入。", font=f_tiny, fill=MUTED)
    y += 42
    y = _section(d, y, "二、规则事件（含数据提示）", f_h2)
    bx = x
    for sev in SEV_ORDER:
        count = summary["by_sev"].get(sev, 0)
        if count:
            label = f"{sev} × {count}"
            seg_width = int(d.textlength(label, font=f_sev)) + 28
            d.rounded_rectangle((bx, y, bx + seg_width, y + 32), radius=5, fill=SEV_COLOR[sev])
            d.text((bx + 12, y + 5), label, font=f_sev, fill="white")
            bx += seg_width + 8
    if not incidents:
        d.text((x, y), "当前筛选下无规则事件", font=f_small, fill=MUTED)
    y += 52
    y = _section(d, y, "三、变更时间线", f_h2)
    for order in orders[-4:]:
        d.ellipse((x + 4, y + 10, x + 12, y + 18), fill=INK)
        d.text((x + 26, y), order.create_time.strftime("%m-%d %H:%M"), font=f_small, fill=MUTED)
        names = "、".join(f"{i['name']} ×{i['quantity']}" for i in order.items)
        label = f"{names}  ¥{order.total_amount:.2f}"
        d.text((x + 150, y), _ellipsis(label, width - 150, f_body), font=f_body, fill=INK)
        y += 38
    if len(orders) > 4:
        d.text((x + 26, y), f"另有 {len(orders) - 4} 条更早记录，见终端完整报告", font=f_tiny, fill=MUTED)
        y += 27
    if not orders:
        d.text((x, y), "所选范围无订单", font=f_small, fill=MUTED)
        y += 30
    y += 14
    key = [i for i in incidents if i.sev != "INFO"][:2]
    if key:
        y = _section(d, y, "四、关键事件", f_h2)
        for incident in key:
            _sev_badge(d, x, y, incident.sev, f_sev)
            d.text((x + 88, y), _ellipsis(incident.title, width - 88, f_body), font=f_body, fill=INK)
            y += 34
            detail = share_detail(incident.detail, orders)
            wrapped = _wrap(detail, width - 88, f_small)
            for idx, line in enumerate(wrapped[:2]):
                if idx == 1 and len(wrapped) > 2:
                    line = _ellipsis(line + "…", width - 88, f_small)
                d.text((x + 88, y), line, font=f_small, fill=INK)
                y += 26
            y += 16
    if y < H - 285:
        y = _section(d, y, "五、趣味解读", f_h2)
        for line in _wrap(_root_cause(orders, incidents), width - 290, f_small)[:2]:
            d.text((x, y), line, font=f_small, fill=MUTED)
            y += 27
    # 印章单独占据右下留白；最多四条时间线、两条事件保证正文不会压到页脚。
    stamp = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    red = (192, 57, 43, 130)
    sd.ellipse((10, 10, 250, 250), outline=red, width=5)
    sd.ellipse((28, 28, 232, 232), outline=red, width=2)
    sd.text((52, 78), "麦门彻查", font=f_stamp, fill=red)
    sd.text((64, 126), "已 归 档", font=f_stamp, fill=red)
    sd.text((80, 178), now.strftime("%Y.%m.%d"), font=_font(18), fill=red)
    stamp = stamp.rotate(18, expand=True, resample=Image.Resampling.BICUBIC)
    layer = img.convert("RGBA")
    layer.alpha_composite(stamp, (W - 330, H - 360))
    img = layer.convert("RGB")
    d = ImageDraw.Draw(img)
    d.line((x, H - 110, W - MARGIN, H - 110), fill=RULE, width=1)
    d.text((x, H - 90), f"规则 {summary['rulesetVersion']} · 营养版本 {summary['nutritionVersion'][:12]}",
           font=f_tiny, fill=MUTED)
    d.text((x, H - 62), "程序员事故复盘梗；趣味规则阈值不构成医疗或营养标准。", font=f_tiny, fill=MUTED)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


# ---------- 小部件 ----------

def _sev_badge(d, x, y, sev, font):
    color = SEV_COLOR.get(sev, INK)
    d.rounded_rectangle((x, y, x + 74, y + 30), radius=6, fill=color)
    d.text((x + 12, y + 5), sev, font=font, fill="#ffffff")


def _section(d, x_or_y, title, font):
    x, y = MARGIN, x_or_y
    d.rectangle((x, y + 4, x + 6, y + 26), fill=INK)
    d.text((x + 18, y), title, font=font, fill=INK)
    return y + 46


def _wrap(text, width, font):
    lines, cur = [], ""
    # 数值与英文单词作为整体换行，避免 1901 被拆成 19 / 01。
    for token in re.findall(r"[A-Za-z0-9]+(?:[.:-][A-Za-z0-9]+)*|.", text):
        if cur and _text_w(cur + token, font) > width:
            lines.append(cur.rstrip())
            cur = token.lstrip()
        else:
            cur += token
    if cur:
        lines.append(cur)
    return lines or [""]


def _text_w(text, font):
    box = font.getbbox(text or " ")
    return box[2] - box[0]


def _ellipsis(text, width, font):
    if _text_w(text, font) <= width:
        return text
    while text and _text_w(text + "…", font) > width:
        text = text[:-1]
    return text + "…"


def _top_sev(incidents):
    for sev in SEV_ORDER:
        if any(i.sev == sev for i in incidents):
            return sev
    return None
