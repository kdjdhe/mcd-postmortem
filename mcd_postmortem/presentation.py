"""报告与卡片共用的数据口径和编号。"""
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone


def audit_now():
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def status_label(summary):
    return {"all": "全部状态", "completed": "仅已完成订单"}.get(
        summary.get("statusScope"), "调用方提供订单（状态未筛选）")


def input_digest(orders, summary):
    rows = []
    for order in orders:
        row = asdict(order)
        row.pop("raw", None)
        row["create_time"] = order.create_time.isoformat()
        rows.append(row)
    data = {"orders": rows, "rules": summary["rulesetVersion"],
            "nutrition": summary["nutritionVersion"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def report_id(orders, summary, at):
    return f"INC-{at:%Y%m%d}-{input_digest(orders, summary)[:8].upper()}"


def source_label(summary):
    return {"demo": "合成演示数据", "mcp": "麦当劳官方 MCP 返回数据"}.get(
        summary.get("source"), "调用方提供数据（来源未标注）")


def nutrient_text(summary):
    def value(key):
        n = summary[key]
        return "未知" if n is None else f"{n:.0f}"
    return f"已知餐品合计 {value('kcal')} kcal / 钠 {value('sodium')} mg"


def coverage_text(summary):
    parts = []
    for key, name in (("kcal", "热量"), ("sodium", "钠")):
        row = summary["nutrition"][key]
        parts.append(f"{name}匹配 {row['matched']}/{row['total']} 项"
                     f"（缺失 {row['missing']}，数量待确认 {row['ambiguous']}）")
    return "；".join(parts)


def period_text(summary):
    if not summary["periodStart"]:
        return "所选范围无订单"
    return f"{summary['periodStart'][:10]} 至 {summary['periodEnd'][:10]}"


def share_detail(text, orders):
    # 分享卡片隐藏具体门店与真实订单号；终端/JSON 保留本地可追溯证据。
    replacements = {o.store_name: "某门店" for o in orders if o.store_name}
    replacements.update({o.order_id: "[订单已隐藏]" for o in orders if o.order_id})
    for original in sorted(replacements, key=len, reverse=True):
        text = text.replace(original, replacements[original])
    return text
