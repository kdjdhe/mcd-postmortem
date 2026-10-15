"""终端富文本渲染：Postmortem 报告（无第三方依赖，纯 ANSI）."""
import os
import sys
import unicodedata
from datetime import datetime

from mcd_postmortem.rules.base import SEV_ORDER, SEV_TITLES

# ANSI 颜色
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_WHITE = "\033[37m"

SEV_STYLE = {
    "SEV1": (_RED, "▓▒░"), "SEV2": (_YELLOW, "▒░ "), "SEV3": (_MAGENTA, "░  "),
    "SEV4": (_CYAN, "·  "), "SEV5": (_WHITE, "   "), "INFO": (_GREEN, "✓  "),
}

WIDTH = 72


def _color_enabled() -> bool:
    return sys.stdout.isatty() or os.environ.get("FORCE_COLOR")


def _c(code, text):
    return f"{code}{text}{_RESET}" if _color_enabled() else text


def render_report(orders, incidents, summary, generated_at: datetime | None = None) -> str:
    now = generated_at or datetime.now()
    inc_id = f"INC-{now.strftime('%Y%m%d')}-{max(1, len(incidents)):04d}"
    lines = []
    w = WIDTH

    def line(ch="─", color=_DIM):
        lines.append(_c(color, ch * w))

    def center(text, color=""):
        pad = max(0, (w - _disp_len(text)) // 2)
        lines.append(" " * pad + (_c(color, text) if color else text))

    def kv(k, v):
        lines.append(f"  {_c(_DIM, k.ljust(12))}{v}")

    line("╭" + "─" * (w - 2) + "╮", _DIM) if False else line("═", _CYAN)
    center("事 故 复 盘 报 告", _BOLD + _CYAN)
    center("Incident Postmortem · mcd-postmortem 自动生成", _DIM)
    line("═", _CYAN)
    kv("事故编号", inc_id)
    kv("审计时间", now.strftime("%Y-%m-%d %H:%M:%S"))
    kv("审计范围", f"近 30 天 {summary['orders']} 笔生产变更（订单）")
    kv("事故总数", f"{summary['incidents']} 起  "
       + "  ".join(f"{k}×{v}" for k, v in sorted(summary['by_sev'].items())))
    lines.append("")

    # ---- 概述 ----
    lines.append(_c(_BOLD, "▍事故概述"))
    if orders:
        first, last = orders[0], orders[-1]
        span_days = max(1, (now - first.create_time).days)
        lines.append(
            f"  自 {first.create_time.strftime('%Y-%m-%d')} 起，生产环境（你的胃）"
            f"共受理 {summary['orders']} 次变更申请，")
        lines.append(
            f"  累计负载 {summary['kcal']:.0f} kcal / 钠 {summary['sodium']:.0f} mg，"
            f"支出 ¥{summary['amount']:.2f}，观察窗口 {span_days} 天。")
        sev1 = [i for i in incidents if i.sev == "SEV1"]
        if sev1:
            lines.append(f"  {_c(_RED, '本次审计发现重大生产事故 %d 起，需管理层（你）立即知悉。' % len(sev1))}")
        elif incidents:
            lines.append(f"  本次审计发现一般事故 {len(incidents)} 起，均在可控范围内。")
        else:
            lines.append(_c(_GREEN, "  本次审计未发现事故。这本身就是一个奇迹，建议写进年报。"))
    else:
        lines.append("  观察窗口内没有生产变更记录。要么你很自律，要么你还没用 MCP 下过单。")
    lines.append("")

    # ---- 时间线 ----
    if orders:
        lines.append(_c(_BOLD, "▍变更时间线（Timeline）"))
        for o in orders:
            kcal = None
            stamp = o.create_time.strftime("%m-%d %H:%M")
            names = "、".join(i["name"] for i in o.items)
            lines.append(f"  {_c(_DIM, stamp)}  {names}  ¥{o.total_amount:.2f}  "
                         f"{_c(_DIM, o.store_name)}")
        lines.append("")

    # ---- 事故明细 ----
    if incidents:
        lines.append(_c(_BOLD, "▍事故明细（按严重度排序）"))
        lines.append("")
        for idx, inc in enumerate(incidents, 1):
            color, bar = SEV_STYLE.get(inc.sev, (_WHITE, ""))
            lines.append(f"  {bar}{_c(color + _BOLD, inc.sev)} {_c(_DIM, inc.rule_id)}"
                         f"  {inc.title}")
            for det in _wrap(inc.detail, w - 6):
                lines.append(f"      {det}")
            if inc.order_ids:
                oid = inc.order_ids[0]
                lines.append(f"      {_c(_DIM, '证据: orderId=' + oid[:18] + '…')}")
            lines.append("")
    else:
        lines.append(_c(_BOLD, "▍事故明细"))
        lines.append("  （无）")
        lines.append("")

    # ---- 根因 ----
    lines.append(_c(_BOLD, "▍根因分析（Root Cause）"))
    rc = _root_cause(orders, incidents)
    for det in _wrap(rc, w - 4):
        lines.append(f"  {det}")
    lines.append("")

    # ---- Action items ----
    lines.append(_c(_BOLD, "▍后续行动（Action Items）"))
    items = _action_items(incidents)
    for it in items:
        lines.append(f"  ☐ {it}")
    if not items:
        lines.append("  ☐ 继续保持。审计小组对你的表现表示赞许。")
    lines.append("")

    line("═", _CYAN)
    center("—— 本报告由 mcd-postmortem 生成 · 数据源：麦当劳官方 MCP ——", _DIM)
    center("结论仅供参考，不构成医疗、营养或投资建议。餐品信息以官方渠道为准。", _DIM)
    return "\n".join(lines)


def _root_cause(orders, incidents) -> str:
    if not orders:
        return "无变更记录，无根因可查。"
    noon = sum(1 for o in orders if 11 <= o.create_time.hour < 14)
    night = sum(1 for o in orders if o.create_time.hour < 5)
    mono = next((i for i in incidents if i.rule_id == "SEV2-MONO-DEPENDENCY"), None)
    parts = []
    if noon:
        parts.append(f"观察期 {noon}/{len(orders)} 次变更集中在午间决策疲劳窗口（11:00–14:00），"
                     "决策系统降级为「上次吃啥这次还吃啥」模式")
    if night:
        parts.append(f"{night} 次变更发生在凌晨，变更审批流程（理智）处于离线状态")
    if mono:
        parts.append(f"存在对 {mono.evidence.get('itemName', '特定单品')} 的路径依赖，"
                     "备选方案演练不足")
    if not parts:
        parts.append("变更流程整体健康，未发现系统性根因；个别事故归因于偶发流量（馋）")
    return "；".join(parts) + "。"


def _action_items(incidents) -> list:
    items = []
    if any(i.rule_id == "SEV1-LATE-NIGHT" for i in incidents):
        items.append("P0 为变更审批系统（理智）配置值班 schedule：00:00 后自动拒绝需求（Owner: 你）")
    if any(i.rule_id == "SEV2-MONO-DEPENDENCY" for i in incidents):
        items.append("P0 为关键单品引入冗余备份，完成至少 1 次灰度验证（点一次别的）")
    if any(i.rule_id == "SEV1-CALORIE-OVERLOAD" for i in incidents):
        items.append("P1 后续变更前核对官方营养表，单笔负载控制在 1500 kcal 以内")
    if any(i.rule_id == "SEV4-SODIUM-ALARM" for i in incidents):
        items.append("P1 关注减盐配置：同款变更存在低钠替代方案时优先采纳")
    if any(i.rule_id == "SEV5-PEAK-DEPLOY" for i in incidents):
        items.append("P2 午高峰变更换用预约发布（reservationDate）或错峰执行")
    if any(i.rule_id == "SEV2-RAPID-REDEPLOY" for i in incidents):
        items.append("P2 下单前增加冷静期（购物车放置 5 分钟）再提交变更")
    if not items:
        items.append("P3 输出最佳实践文档，供团队（朋友们）学习")
    return items


def _disp_len(s: str) -> int:
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _wrap(text: str, width: int) -> list:
    lines, cur, cur_len = [], [], 0
    for ch in text:
        ch_len = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if cur_len + ch_len > width:
            lines.append("".join(cur))
            cur, cur_len = [], 0
        cur.append(ch)
        cur_len += ch_len
    if cur:
        lines.append("".join(cur))
    return lines
