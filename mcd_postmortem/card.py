"""PNG 报告卡片渲染：一张正经的「事故复盘报告」首页.

设计参考正式 Postmortem 文书：报告头（编号/等级/状态）→ 事故概述 →
SEV 分布 → 变更时间线 → 根因 → 归档红章。字体优先微软雅黑（Windows 自带），
缺失时退回系统默认。
"""
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from mcd_postmortem.rules.base import SEV_ORDER

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
STAMP_RED = "#c0392b"

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",   # 黑体
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int, bold: bool = False):
    candidates = _FONT_CANDIDATES if bold else _FONT_CANDIDATES[1:]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_card(orders, incidents, summary, out_path: str,
                generated_at: datetime | None = None) -> str:
    now = generated_at or datetime.now()
    inc_id = f"INC-{now.strftime('%Y%m%d')}-{max(1, len(incidents)):04d}"
    top_sev = _top_sev(incidents)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_h1 = _font(46, bold=True)
    f_h2 = _font(22, bold=True)
    f_body = _font(21)
    f_small = _font(17)
    f_tiny = _font(14)
    f_sev = _font(15, bold=True)
    f_stamp = _font(30, bold=True)

    x = MARGIN
    y = MARGIN

    # ── 报告头 ──
    d.text((x, y), "事故复盘报告", font=f_h1, fill=INK)
    d.text((x, y + 62), "INCIDENT POSTMORTEM", font=_font(18), fill=MUTED)
    # 报告编号（右上）
    d.text((W - MARGIN - 260, y + 8), inc_id, font=f_h2, fill=INK)
    d.text((W - MARGIN - 260, y + 40), now.strftime("%Y-%m-%d %H:%M 审计"),
           font=f_small, fill=MUTED)
    y += 120
    d.line((x, y, W - MARGIN, y), fill=INK, width=3)
    y += 18

    # ── 元信息行 ──
    meta = [
        ("等级", top_sev or "—"),
        ("状态", "已归档"),
        ("变更数", str(summary["orders"])),
        ("事故数", str(summary["incidents"])),
    ]
    bx = x
    for k, v in meta:
        d.text((bx, y), k, font=f_small, fill=MUTED)
        vx = bx + max(64, int(d.textlength(k, font=f_small)) + 14)
        if k == "等级" and top_sev:
            _sev_badge(d, vx, y - 6, top_sev, f_sev)
        else:
            d.text((vx, y - 6), v, font=f_h2, fill=INK)
        bx += 226
    y += 52
    d.line((x, y, W - MARGIN, y), fill=RULE, width=1)
    y += 24

    # ── 事故概述 ──
    y = _section(d, y, "一、事故概述", f_h2)
    if orders:
        first = orders[0]
        span_days = max(1, (now - first.create_time).days)
        lines = [
            f"自 {first.create_time.strftime('%Y-%m-%d')} 起，生产环境（你的胃）共受理"
            f"{summary['orders']} 次变更申请。",
            f"累计负载 {summary['kcal']:.0f} kcal，钠 {summary['sodium']:.0f} mg，"
            f"支出 ¥{summary['amount']:.2f}，观察窗口 {span_days} 天。",
            _headline(incidents),
        ]
        for ln in lines:
            y = _body_text(d, x, y, ln, f_body, W - 2 * MARGIN)
            y += 6
    else:
        y = _body_text(d, x, y, "观察窗口内没有生产变更记录。", f_body, W - 2 * MARGIN)
    y += 14

    # ── SEV 分布条 ──
    y = _section(d, y, "二、事故分级", f_h2)
    bx = x
    total = max(1, summary["incidents"])
    for sev in SEV_ORDER:
        n = summary["by_sev"].get(sev, 0)
        if not n:
            continue
        frac = n / total
        seg_w = int(frac * (W - 2 * MARGIN - 10))
        d.rounded_rectangle((bx, y, bx + seg_w, y + 30), radius=6, fill=SEV_COLOR[sev])
        d.text((bx + 8, y + 5), f"{sev}×{n}", font=f_sev, fill="#ffffff")
        bx += seg_w + 4
    if not summary["incidents"]:
        d.rounded_rectangle((bx, y, bx + 240, y + 30), radius=6, fill=SEV_COLOR["INFO"])
        d.text((bx + 8, y + 5), "未发现事故 ✓", font=f_sev, fill="#ffffff")
    y += 54

    # ── 变更时间线 ──
    y = _section(d, y, "三、变更时间线", f_h2)
    if orders:
        shown = orders[-6:] if len(orders) > 6 else orders
        if len(orders) > 6:
            pass
        for o in shown:
            stamp = o.create_time.strftime("%m-%d %H:%M")
            d.ellipse((x + 4, y + 12, x + 12, y + 20), fill=INK)
            if y + 44 < H - 160:
                d.line((x + 8, y + 20, x + 8, y + 44), fill=RULE, width=1)
            d.text((x + 28, y), stamp, font=f_small, fill=MUTED)
            names = "、".join(i["name"] for i in o.items)
            y = _body_text(d, x + 140, y, f"{names}  ¥{o.total_amount:.2f}",
                           f_body, W - MARGIN - (x + 140))
            y += 22
        if len(orders) > 6:
            d.text((x + 28, y), f"… 还有 {len(orders) - 6} 条更早的变更，见终端完整报告",
                   font=f_small, fill=MUTED)
            y += 30
    else:
        y = _body_text(d, x, y, "（无变更记录）", f_body, W - 2 * MARGIN)
    y += 14

    # ── 关键事故（前 2 条 SEV1/2/3）──
    key = [i for i in incidents if i.sev in ("SEV1", "SEV2", "SEV3")][:2]
    if key:
        y = _section(d, y, "四、关键事故", f_h2)
        for inc in key:
            _sev_badge(d, x, y, inc.sev, f_sev)
            ty = y
            title = inc.title
            if _text_w(title, f_body) > W - 2 * MARGIN - 84:
                title = _ellipsis(title, W - 2 * MARGIN - 84, f_body)
            d.text((x + 84, ty), title, font=f_body, fill=INK)
            ty += 30
            detail = _trim_detail(inc.detail, 110)
            ty = _body_text(d, x + 84, ty, detail, f_small, W - MARGIN - (x + 84))
            y = ty + 18

    # ── 根因分析（预留印章安全区，超出则压缩到两行内）──
    if y < H - 330:
        y = _section(d, y, "五、根因分析", f_h2)
        rc = _root_cause_line(orders, incidents)
        max_lines = 2 if y > H - 460 else 4
        for ln in _wrap(rc, W - 2 * MARGIN - 10, f_body)[:max_lines]:
            d.text((x, y), ln, font=f_body, fill=INK)
            y += 30

    # ── 页脚 ──
    d.line((x, H - 110, W - MARGIN, H - 110), fill=RULE, width=1)
    d.text((x, H - 92), "本报告由 mcd-postmortem 生成 · 数据源：麦当劳官方 MCP",
           font=f_small, fill=MUTED)
    d.text((x, H - 66), "结论仅供参考，不构成医疗或营养建议。餐品信息以官方渠道为准。",
           font=f_tiny, fill=MUTED)

    # ── 归档红章（右下，半透明盖印，旋转）──
    stamp = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    RED = (192, 57, 43, 130)  # 印泥半透明
    sd.ellipse((10, 10, 250, 250), outline=RED, width=5)
    sd.ellipse((28, 28, 232, 232), outline=RED, width=2)
    sd.text((52, 78), "麦门彻查", font=f_stamp, fill=RED)
    sd.text((64, 126), "已 归 档", font=f_stamp, fill=RED)
    sd.text((80, 178), now.strftime("%Y.%m.%d"), font=_font(18), fill=RED)
    stamp = stamp.rotate(18, expand=True, resample=Image.BICUBIC)
    # 印章盖在右下角，压住页脚分隔线上方空白区；正文区已按印章安全线截断
    stamp_x = W - 330
    stamp_y = H - 360
    img_rgba = img.convert("RGBA")
    img_rgba.alpha_composite(stamp, (stamp_x, stamp_y))
    img = img_rgba.convert("RGB")

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


def _body_text(d, x, y, text, font, width):
    lines = _wrap(text, width, font)
    # 孤行 rebalance：末行只剩 1–2 个字符时，把上一行末字符挪下来
    if len(lines) >= 2 and len(lines[-1]) <= 2:
        lines[-1] = lines[-2][-1] + lines[-1]
        lines[-2] = lines[-2][:-1]
    for ln in lines:
        d.text((x, y), ln, font=font, fill=INK)
        y += 30
    return y


def _wrap(text, width, font):
    lines, cur = [], ""
    for ch in text:
        if _text_w(cur + ch, font) > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
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


def _trim_detail(text, limit):
    """按整句截断，避免孤字/孤标点悬在行尾."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # 在最近的句号/分号处收尾，保证截断后仍是完整句子
    for p in ("。", "；"):
        idx = cut.rfind(p)
        if idx > limit * 0.5:
            return cut[:idx + 1]
    return cut.rstrip("，、： ") + "…"


def _top_sev(incidents):
    for sev in SEV_ORDER:
        if any(i.sev == sev for i in incidents):
            return sev
    return None


def _headline(incidents):
    sev1 = [i for i in incidents if i.sev == "SEV1"]
    if sev1:
        return f"本次审计发现重大生产事故 {len(sev1)} 起，需管理层（你）立即知悉。"
    if incidents:
        return f"本次审计发现事故 {len(incidents)} 起，均在可控范围内。"
    return "本次审计未发现事故。这本身就是一个奇迹，建议写进年报。"


def _root_cause_line(orders, incidents) -> str:
    if not orders:
        return "无变更记录，无根因可查。"
    noon = sum(1 for o in orders if 11 <= o.create_time.hour < 14)
    night = sum(1 for o in orders if o.create_time.hour < 5)
    mono = next((i for i in incidents if i.rule_id == "SEV2-MONO-DEPENDENCY"), None)
    parts = []
    if noon:
        parts.append(f"{noon}/{len(orders)} 次变更集中在午间决策疲劳窗口，"
                     "决策系统降级为「上次吃啥这次还吃啥」模式")
    if night:
        parts.append(f"{night} 次变更发生在凌晨，变更审批流程（理智）处于离线状态")
    if mono:
        parts.append(f"存在对 {mono.evidence.get('itemName', '特定单品')} 的路径依赖，"
                     "备选方案演练不足")
    if not parts:
        parts.append("变更流程整体健康，未发现系统性根因；个别事故归因于偶发流量（馋）")
    return "；".join(parts) + "。"
