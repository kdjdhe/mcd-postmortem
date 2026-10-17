"""审计 CLI：稳定演示、可复现时间与纯 JSON 输出。具体审计逻辑在 service 层。"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from mcd_postmortem import __version__
from mcd_postmortem import service
from mcd_postmortem.mcp_client import McpError
from mcd_postmortem.rules.base import SEV_ORDER

SHANGHAI = timezone(timedelta(hours=8))


def _parse_at(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo:
            result = result.astimezone(SHANGHAI).replace(tzinfo=None)
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--at 应为 ISO 时间，如 2026-10-15T12:00:00+08:00") from exc


def _parse_since(value):
    match = re.fullmatch(r"([1-9][0-9]*)([dw]?)", value)
    if not match:
        raise argparse.ArgumentTypeError("--since 应为正整数天数或 30d / 2w")
    days = int(match[1]) * (7 if match[2] == "w" else 1)
    if days > 36500:
        raise argparse.ArgumentTypeError("--since 不得超过 36500 天")
    return days


def _options(args):
    return service.AuditOptions(
        since_days=args.since, sev=args.sev, at=args.at,
        all_statuses=args.all_statuses,
        # demo 子命令没有 --combo-quantities；保持历史 JSON 输出不变。
        combo_quantities=getattr(args, "combo_quantities", "per-parent"),
        refresh_nutrition=getattr(args, "refresh_nutrition", False),
        card_path=args.card)


def _emit(result, args):
    if result.card_path:
        print(f"报告卡片已生成: {result.card_path}", file=sys.stderr)
    if args.json:
        print(json.dumps(result.report_json, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(result.report_text)
    if result.summary["ruleErrors"]:
        print("部分规则失败，请检查 ENGINE-* 事件。", file=sys.stderr)
        raise SystemExit(2)


def cmd_audit(args):
    _emit(service.run_audit(_options(args)), args)


def cmd_demo(args):
    print("演示模式：合成订单与营养数据，无需 Token。", file=sys.stderr)
    _emit(service.run_demo(_options(args)), args)


def main(argv=None):
    # Windows 重定向默认可能使用 GBK；CLI 的文本和 JSON 统一为 UTF-8。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="mcd-postmortem", description="麦门彻查 · 订单事故复盘")
    parser.add_argument("--version", action="version", version=f"mcd-postmortem {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, func, help_text in (("audit", cmd_audit, "审计真实历史订单"),
                                  ("demo", cmd_demo, "无需 Token 的合成数据演示")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--since", type=_parse_since, help="最近 30d / 2w，默认全部返回记录")
        p.add_argument("--sev", type=str.upper, choices=SEV_ORDER, help="只显示指定级别")
        p.add_argument("--at", type=_parse_at, help="固定审计时间，默认北京时间；用于复现")
        p.add_argument("--json", action="store_true", help="标准输出仅写 JSON")
        p.add_argument("--card", metavar="PATH", help="生成隐藏门店/订单号的 PNG 卡片")
        p.add_argument("--all-statuses", action="store_true", help="包含未完成/未知状态，默认仅已完成")
        if name == "audit":
            p.add_argument("--refresh-nutrition", action="store_true", help="刷新七天营养缓存")
            p.add_argument("--combo-quantities", choices=service.QUANTITY_SCOPES,
                           default="unknown",
                           help="多份套餐子项数量：unknown 待确认 / per-parent 每份 / per-order 整单")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (McpError, ValueError, KeyError, TypeError, OSError, RuntimeError, OverflowError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("已中断。", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
