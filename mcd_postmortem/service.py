"""供 CLI 与 GUI 共用的审计服务层：不打印、不退出进程，由调用方决定输出方式。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from mcd_postmortem.engine import AuditEngine
from mcd_postmortem.mcp_client import McpClient
from mcd_postmortem.orders import (COMPLETED_STATUSES, QUANTITY_SCOPES, fetch_orders,
                                   load_nutrition, normalize_orders)
from mcd_postmortem.presentation import audit_now, input_digest
from mcd_postmortem.report import render_report
from mcd_postmortem.rules.base import SEV_ORDER

SHANGHAI = timezone(timedelta(hours=8))

# progress(stage, message)：stage 为稳定的机器标识，message 为展示文案。
ProgressCallback = Callable[[str, str], None]


@dataclass
class AuditOptions:
    since_days: int | None = None
    sev: str | None = None
    at: datetime | None = None
    all_statuses: bool = False
    combo_quantities: str = "unknown"
    refresh_nutrition: bool = False
    card_path: str | Path | None = None


@dataclass
class AuditResult:
    orders: list
    incidents: list
    summary: dict
    at: datetime
    report_text: str
    report_json: dict
    card_path: str | None = None


def _notify(progress: ProgressCallback | None, stage: str, message: str) -> None:
    if progress is not None:
        progress(stage, message)


def run_demo(options: AuditOptions | None = None,
             progress: ProgressCallback | None = None) -> AuditResult:
    """使用合成数据运行完整审计，不访问网络、不需要 Token。"""
    from mcd_postmortem.demo_data import DEMO_TIME, demo_nutrition, demo_orders
    options = options or AuditOptions()
    at = options.at or DEMO_TIME
    _notify(progress, "prepare", "正在准备合成演示数据…")
    return _audit(demo_orders(at), demo_nutrition(), options, at, "demo", progress)


def run_audit(options: AuditOptions | None = None, token: str | None = None,
              progress: ProgressCallback | None = None) -> AuditResult:
    """从麦当劳 MCP 拉取真实订单并审计。"""
    options = options or AuditOptions()
    at = options.at or audit_now()
    _notify(progress, "connect", "正在连接麦当劳 MCP…")
    client = McpClient(token=token)
    _notify(progress, "orders", "正在拉取历史订单…")
    orders = fetch_orders(client, combo_quantities=options.combo_quantities)
    _notify(progress, "nutrition", "正在加载营养表…")
    table = load_nutrition(client, use_cache=not options.refresh_nutrition)
    _notify(progress, "rules", "正在运行审计规则…")
    return _audit(orders, table, options, at, "mcp", progress)


def _audit(orders, table, options: AuditOptions, at: datetime, source: str,
           progress: ProgressCallback | None) -> AuditResult:
    if options.sev is not None and options.sev not in SEV_ORDER:
        raise ValueError(f"未知的严重级别：{options.sev}")

    orders = normalize_orders(orders)
    if options.since_days:
        cutoff = at - timedelta(days=options.since_days)
        orders = [o for o in orders if cutoff <= o.create_time <= at]
    else:
        orders = [o for o in orders if o.create_time <= at]
    excluded = {}
    if not options.all_statuses:
        selected = []
        for order in orders:
            if order.order_status.strip().lower() in COMPLETED_STATUSES:
                selected.append(order)
            else:
                excluded[order.order_status] = excluded.get(order.order_status, 0) + 1
        orders = selected

    engine = AuditEngine(table)
    incidents = engine.run(orders)
    all_count = len(incidents)
    rule_errors = sum(i.rule_id.startswith("ENGINE-") for i in incidents)
    if options.sev:
        incidents = [i for i in incidents if i.sev == options.sev]
    summary = engine.summary(orders, incidents)
    summary.update({"source": source, "excludedByStatus": dict(sorted(excluded.items())),
                    "statusScope": "all" if options.all_statuses else "completed",
                    "sinceDays": options.since_days, "severityFilter": options.sev,
                    "totalIncidentsBeforeFilter": all_count,
                    "ruleErrors": rule_errors,
                    "comboQuantityScope": options.combo_quantities})

    _notify(progress, "render", "正在生成报告…")
    report_json = {
        "schemaVersion": 1,
        "generatedAt": at.isoformat(timespec="seconds") + "+08:00",
        "inputDigest": input_digest(orders, summary),
        "summary": summary,
        "incidents": [{"sev": i.sev, "ruleId": i.rule_id, "title": i.title,
                       "detail": i.detail, "orderIds": i.order_ids,
                       "evidence": i.evidence} for i in incidents],
    }
    report_text = render_report(orders, incidents, summary, generated_at=at)

    card_path = None
    if options.card_path:
        from mcd_postmortem.card import render_card
        _notify(progress, "card", "正在渲染分享卡片…")
        card_path = render_card(orders, incidents, summary, str(options.card_path),
                                generated_at=at)

    return AuditResult(orders=orders, incidents=incidents, summary=summary, at=at,
                       report_text=report_text, report_json=report_json,
                       card_path=str(card_path) if card_path else None)
