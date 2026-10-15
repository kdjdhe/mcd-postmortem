"""终端报告：事实、数据覆盖率与趣味解读分开呈现。"""
import os
import sys
import unicodedata

from mcd_postmortem.presentation import (coverage_text, nutrient_text, period_text,
                                         report_id, source_label, status_label, audit_now)

_RESET, _BOLD, _CYAN = "\033[0m", "\033[1m", "\033[36m"
WIDTH = 78


def _color_enabled():
    if "NO_COLOR" in os.environ:
        return False
    return bool(os.environ.get("FORCE_COLOR")) or sys.stdout.isatty()


def _c(code, text):
    return f"{code}{text}{_RESET}" if _color_enabled() else text


def render_report(orders, incidents, summary, generated_at=None):
    now = generated_at or audit_now()
    lines = [_c(_CYAN, "═" * WIDTH), _c(_BOLD, "事故复盘报告 · Incident Postmortem"),
             f"事故编号：{report_id(orders, summary, now)}",
             f"审计时间：{now:%Y-%m-%d %H:%M:%S}（北京时间）",
             f"数据来源：{source_label(summary)}",
             f"订单范围：{period_text(summary)}，共 {summary['orders']} 笔",
             f"状态口径：{status_label(summary)}",
             f"规则版本：{summary['rulesetVersion']}；营养版本：{summary['nutritionVersion'][:12]}"]
    if summary.get("sinceDays"):
        lines.append(f"筛选条件：审计时间之前 {summary['sinceDays']} 天（含边界）")
    if summary.get("excludedByStatus"):
        lines.append("状态排除：" + "、".join(f"{s} {n} 笔" for s, n in summary["excludedByStatus"].items()))
    if summary.get("severityFilter"):
        lines.append(f"等级筛选：{summary['severityFilter']}；全部规则事件 "
                     f"{summary['totalIncidentsBeforeFilter']} 起，本页展示 {len(incidents)} 起")
    lines.extend(["", "▍订单餐品统计", nutrient_text(summary), coverage_text(summary),
                  f"订单实付合计 ¥{summary['amount']:.2f}；餐品总量不代表个人实际摄入。",
                  "", "▍变更时间线（Timeline）"])
    for order in orders:
        names = "、".join(f"{i['name']} ×{i['quantity']}" for i in order.items)
        lines.append(f"{order.create_time:%Y-%m-%d %H:%M}  {names}  ¥{order.total_amount:.2f}")
    if not orders:
        lines.append("所选范围无订单，无法进行行为判断。")
    lines.extend(["", f"▍规则事件：{len(incidents)} 起（含数据提示）"])
    for incident in incidents:
        lines.append(f"[{incident.sev}] {incident.rule_id}  {incident.title}")
        lines.extend("  " + line for line in _wrap(incident.detail, WIDTH - 4))
        if incident.order_ids:
            lines.append("  证据订单：" + "、".join(incident.order_ids))
    if not incidents:
        lines.append("当前筛选下没有规则事件；不代表营养完整或健康结论。")
    if summary["ruleErrors"]:
        lines.append("审计不完整：有规则执行失败，请查看 ENGINE-* 事件。")
    lines.extend(["", "▍趣味解读（非事实根因）", _root_cause(orders, incidents),
                  "", "▍后续行动（Action Items）"])
    lines.extend("☐ " + item for item in _action_items(incidents))
    lines.extend(["", "═" * WIDTH, "本报告使用程序员事故复盘梗；规则阈值不构成医疗或营养标准。"])
    return "\n".join(lines)


def _root_cause(orders, incidents):
    if not orders:
        return "暂无订单样本，审计小组暂时下班。"
    parts = []
    if any(i.rule_id == "SEV2-MONO-DEPENDENCY" for i in incidents):
        parts.append("菜单备份演练欠费，决策系统一直复用上个版本")
    if any(i.rule_id == "SEV1-LATE-NIGHT" for i in incidents):
        parts.append("深夜审批系统（理智）可能已经离线")
    return "；".join(parts or ["审计小组已阅；以上事件仅供趣味回顾，真实动机未知"]) + "。"


def _action_items(incidents):
    items = []
    ids = {i.rule_id for i in incidents}
    if "SEV2-MONO-DEPENDENCY" in ids:
        items.append("为常点单品准备一个菜单备选，完成一次灰度尝鲜。")
    if "SEV2-RAPID-REDEPLOY" in ids:
        items.append("下单前复核购物车，减少遗漏后补单。")
    if "INFO-404-UNTRACKED" in ids:
        items.append("核对未匹配餐品与官方营养表，补齐数据后再看总量。")
    if any(i.startswith("ENGINE-") for i in ids):
        items.append("修复失败规则后重新运行审计。")
    return items or ["核对数据口径，按自己的需要安排下一次点餐。"]


def _disp_len(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _wrap(text, width):
    rows, current, size = [], [], 0
    for ch in text:
        length = _disp_len(ch)
        if size + length > width:
            rows.append("".join(current))
            current, size = [], 0
        current.append(ch)
        size += length
    if current:
        rows.append("".join(current))
    return rows
