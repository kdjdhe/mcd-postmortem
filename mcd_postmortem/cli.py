"""mcd-postmortem 命令行入口.

命令：
  mcd-postmortem audit [--since 30d] [--sev SEV1] [--json] [--no-color]
  mcd-postmortem demo     # 合成订单数据，无需 Token
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from mcd_postmortem import __version__
from mcd_postmortem.engine import AuditEngine
from mcd_postmortem.mcp_client import McpClient, McpError
from mcd_postmortem.orders import fetch_orders, load_nutrition
from mcd_postmortem.report import render_report


def _engine(client=None) -> AuditEngine:
    if client is None:
        table = load_nutrition(None, use_cache=True) if os.path.exists(
            load_nutrition.__defaults__[-1] or "") else {}
    return AuditEngine(_nutrition_table(client))


def _nutrition_table(client):
    if os.path.exists(NUTRITION_CACHE):
        return load_nutrition(None, use_cache=True)
    if client is None:
        return {}
    return load_nutrition(client)


NUTRITION_CACHE = ".nutrition_cache.json"


def cmd_audit(args):
    try:
        client = McpClient()
    except McpError as e:
        print(f"❌ {e}")
        print("   提示：可以先跑 `mcd-postmortem demo` 看合成数据效果。")
        sys.exit(1)
    try:
        orders = fetch_orders(client)
        table = load_nutrition(client)
    except (McpError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)
    _run_audit(orders, table, args)


def cmd_demo(args):
    from mcd_postmortem.demo_data import demo_orders, demo_nutrition
    print("🧪 演示模式：使用合成订单数据（不调用 MCP）\n")
    _run_audit(demo_orders(), demo_nutrition(), args)


def _run_audit(orders, table, args):
    # --since 窗口过滤
    if args.since:
        orders = _filter_since(orders, args.since)

    engine = AuditEngine(table)
    incidents = engine.run(orders)
    if args.sev:
        incidents = [i for i in incidents if i.sev == args.sev.upper()]
    summary = engine.summary(orders, incidents)

    if args.json:
        print(json.dumps({
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "summary": summary,
            "incidents": [
                {"sev": i.sev, "ruleId": i.rule_id, "title": i.title,
                 "detail": i.detail, "orderIds": i.order_ids, "evidence": i.evidence}
                for i in incidents
            ],
        }, ensure_ascii=False, indent=1))
        return

    print(render_report(orders, incidents, summary))


def _filter_since(orders, since: str):
    m = {"d": "days", "w": "weeks", "m": None}
    try:
        if since.endswith("w"):
            delta = timedelta(weeks=int(since[:-1]))
        elif since.endswith("d"):
            delta = timedelta(days=int(since[:-1]))
        else:
            delta = timedelta(days=int(since))
    except ValueError:
        print(f"❌ --since 格式应为 30d / 2w，收到: {since}")
        sys.exit(1)
    cutoff = datetime.now() - delta
    return [o for o in orders if o.create_time >= cutoff]


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="mcd-postmortem",
        description="麦门彻查 · 把你的麦当劳历史订单审计成一份正经的 SRE 事故复盘报告 🍔📋")
    p.add_argument("--version", action="version", version=f"mcd-postmortem {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="审计真实历史订单（需 MCD_MCP_TOKEN）")
    a.add_argument("--since", help="审计窗口，如 30d / 2w（默认全部）")
    a.add_argument("--sev", choices=["SEV1", "SEV2", "SEV3", "SEV4", "SEV5", "INFO"],
                   help="只看某一级事故")
    a.add_argument("--json", action="store_true", help="输出结构化 JSON")
    a.set_defaults(func=cmd_audit)

    d = sub.add_parser("demo", help="合成数据演示（无需 Token）")
    d.add_argument("--since")
    d.add_argument("--sev")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
