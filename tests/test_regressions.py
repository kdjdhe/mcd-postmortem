"""针对误判、缺失数据、可复现性和 CLI 协议的回归测试。全部离线。"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from mcd_postmortem.cli import main
from mcd_postmortem.demo_data import DEMO_TIME, demo_nutrition, demo_orders
from mcd_postmortem.engine import AuditEngine
from mcd_postmortem.mcp_client import McpClient, McpError
from mcd_postmortem.orders import (Nutrition, Order, _parse_nutrition_text,
                                   fetch_orders, load_nutrition, normalize_orders)
from mcd_postmortem.report import render_report
from mcd_postmortem.presentation import share_detail


def order(index, name="A", quantity=1, subs=None, scope="per-parent"):
    return Order(str(index), DEMO_TIME + timedelta(minutes=index), "私密门店", "S", "订单已完成",
                 "1", "1", 10, [{"name": name, "code": name, "quantity": quantity,
                                  "sub_items": subs or [], "sub_quantity_scope": scope}])


def table():
    return {"a": Nutrition("A", 100, 400, 1, 1, 1, 50, 1),
            "b": Nutrition("B", 200, 800, 1, 1, 1, 100, 1)}


def cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        main(list(args))
    return stdout.getvalue(), stderr.getvalue()


class ConsecutiveTests(unittest.TestCase):
    def mono(self, orders):
        return [i for i in AuditEngine(table()).run(orders) if "MONO" in i.rule_id]

    def test_interrupted_repeat_is_not_streak(self):
        self.assertEqual(self.mono([order(i, n) for i, n in enumerate("ABABA")]), [])

    def test_long_streak_reports_once_with_all_evidence(self):
        rows = [order(i) for i in range(5)]
        result = self.mono(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].order_ids, [str(i) for i in range(5)])
        self.assertEqual(result[0].evidence["occurrences"], 5)

    def test_two_streaks_remain_separate(self):
        result = self.mono([order(i, n) for i, n in enumerate("AAABAAA")])
        self.assertEqual([r.order_ids for r in result], [["0", "1", "2"], ["4", "5", "6"]])

    def test_duplicate_item_rows_are_one_order(self):
        rows = [order(i) for i in range(3)]
        rows[0].items *= 3
        self.assertEqual(self.mono(rows)[0].evidence["occurrences"], 3)

    def test_quantity_is_not_number_of_orders(self):
        self.assertEqual(self.mono([order(0, quantity=3), order(1, "B"), order(2, "B")]), [])

    def test_order_input_order_does_not_change_results(self):
        engine = AuditEngine(table())
        rows = [order(i) for i in range(3)]
        self.assertEqual(engine.run(rows), engine.run(list(reversed(rows))))

    def test_duplicate_orders_do_not_create_streak(self):
        row = order(0)
        self.assertEqual(self.mono([row, row, row]), [])

    def test_conflicting_duplicate_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_orders([order(0), order(0, "B")])


class NutritionTests(unittest.TestCase):
    def setUp(self):
        self.engine = AuditEngine(table())
        self.ctx = self.engine.ctx

    def test_per_parent_quantities_multiply(self):
        self.assertEqual(self.ctx.kcal_of_order(order(0, "combo", 2, ["A x3"])), 600)

    def test_per_order_quantities_do_not_multiply(self):
        self.assertEqual(self.ctx.kcal_of_order(order(0, "combo", 2, ["A x3"], "per-order")), 300)

    def test_unknown_multiple_combo_quantities_are_not_guessed(self):
        row = self.ctx.coverage(order(0, "combo", 2, ["A x3"], "unknown"), "kcal")
        self.assertIsNone(row["value"])
        self.assertEqual(row["ambiguous"], ["A"])
        self.assertFalse(row["complete"])

    def test_single_parent_unknown_scope_is_unambiguous(self):
        self.assertEqual(self.ctx.kcal_of_order(order(0, "combo", 1, ["A x3"], "unknown")), 300)

    def test_structured_subitems_are_supported(self):
        self.assertEqual(self.ctx.kcal_of_order(order(0, "combo", 2,
                         [{"name": "A", "quantity": 2}])), 400)

    def test_parent_and_children_are_not_double_counted(self):
        self.assertEqual(self.ctx.kcal_of_order(order(0, "A", 1, ["A x1", "B x1"])), 300)

    def test_partial_and_unknown_totals_are_explicit(self):
        row = order(0)
        row.items += order(1, "unknown").items
        coverage = self.ctx.coverage(row, "kcal")
        self.assertEqual(coverage["value"], 100)
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["missing"], ["unknown"])
        summary = self.engine.summary([order(1, "unknown")], [])
        self.assertIsNone(summary["kcal"])

    def test_zero_nutrients_are_known_values(self):
        self.ctx.nutrition_table["a"].kcal = 0
        coverage = self.ctx.coverage(order(0), "kcal")
        self.assertEqual(coverage["value"], 0)
        self.assertTrue(coverage["complete"])

    def test_untracked_checks_children_not_combo_wrapper(self):
        incidents = self.engine.run([order(0, "combo", 1, ["A x1", "unknown x1"])])
        names = [i.evidence["itemName"] for i in incidents if "UNTRACKED" in i.rule_id]
        self.assertEqual(names, ["unknown"])

    def test_negative_or_fractional_quantity_is_rejected(self):
        for qty in (-1, 0, True, 1.5):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                self.ctx.kcal_of_order(order(0, quantity=qty))

    def test_csv_handles_commas_in_descriptions_and_null(self):
        text = ('[1]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,'
                'carbohydrate,sodium,calcium}:\n  A,"foo, bar",400,100,null,1,2,50,1')
        result = _parse_nutrition_text(text)
        self.assertEqual(result["a"].kcal, 100)
        self.assertIsNone(result["a"].protein)

    def test_invalid_nutrient_is_unknown(self):
        text = '[1]{productName,energyKcal,sodium}:\n A,NaN,-1'
        row = _parse_nutrition_text(text)["a"]
        self.assertIsNone(row.kcal)
        self.assertIsNone(row.sodium)

    def test_identical_food_duplicates_merge_but_conflicts_are_rejected(self):
        text = '[2]{productName,energyKcal,sodium}:\n A,100,50\n A,100,50'
        self.assertEqual(len(_parse_nutrition_text(text)), 1)
        with self.assertRaises(RuntimeError):
            _parse_nutrition_text(text.replace('A,100,50', 'A,200,50', 1))


class InputAndCacheTests(unittest.TestCase):
    def test_fetch_preserves_structured_children_and_uncertain_scope(self):
        client = Mock()
        client.order_list.return_value = {"orders": [{"orderId": "O1", "createTime": "2026-10-15 12:00:00",
            "orderProductList": [{"productName": "套餐", "quantity": 2,
                "comboItemList": [{"name": "A", "quantity": 1, "productCode": "A"}]}]}]}
        rows = fetch_orders(client)
        self.assertEqual(rows[0].items[0]["sub_items"][0]["code"], "A")
        self.assertEqual(rows[0].items[0]["sub_quantity_scope"], "unknown")

    def test_fresh_expired_and_forced_cache(self):
        client = Mock()
        client.call_tool.return_value = [{"productName": "A", "energyKcal": 100}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.json"
            with patch("mcd_postmortem.orders.cache_path", return_value=path):
                with patch("mcd_postmortem.orders.time.time", return_value=1_000_000):
                    load_nutrition(client)
                    load_nutrition(client)
                    self.assertEqual(client.call_tool.call_count, 1)
                    load_nutrition(client, use_cache=False)
                    self.assertEqual(client.call_tool.call_count, 2)
                with patch("mcd_postmortem.orders.time.time", return_value=2_000_000):
                    load_nutrition(client)
                    self.assertEqual(client.call_tool.call_count, 3)

    def test_corrupt_cache_is_refetched(self):
        client = Mock()
        client.call_tool.return_value = [{"productName": "A", "energyKcal": 100}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.json"
            path.write_text("broken", encoding="utf-8")
            with patch("mcd_postmortem.orders.cache_path", return_value=path):
                self.assertEqual(load_nutrition(client)["a"].kcal, 100)
                client.call_tool.assert_called_once()

    def test_cache_with_invalid_numbers_is_refetched(self):
        client = Mock()
        client.call_tool.return_value = [{"productName": "A", "energyKcal": 100}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.json"
            food = asdict(table()["a"])
            food["kcal"] = -100
            path.write_text(json.dumps({"schemaVersion": 1, "fetchedAt": 1_000_000,
                                        "foods": {"a": food}}), encoding="utf-8")
            with patch("mcd_postmortem.orders.cache_path", return_value=path), \
                    patch("mcd_postmortem.orders.time.time", return_value=1_000_000):
                self.assertEqual(load_nutrition(client)["a"].kcal, 100)
                client.call_tool.assert_called_once()


class CliTests(unittest.TestCase):
    def test_time_window_includes_boundaries_and_excludes_future(self):
        rows = [order(i) for i in range(4)]
        rows[0].create_time = DEMO_TIME - timedelta(days=1, seconds=1)
        rows[1].create_time = DEMO_TIME - timedelta(days=1)
        rows[2].create_time = DEMO_TIME
        rows[3].create_time = DEMO_TIME + timedelta(seconds=1)
        with patch("mcd_postmortem.cli.McpClient"), patch("mcd_postmortem.cli.fetch_orders", return_value=rows), \
                patch("mcd_postmortem.cli.load_nutrition", return_value=table()):
            result = json.loads(cli("audit", "--json", "--since", "1d", "--at", DEMO_TIME.isoformat())[0])
        self.assertEqual(result["summary"]["orders"], 2)

    def test_rule_failure_is_nonzero_even_when_filtered_out(self):
        from mcd_postmortem.rules.base import Rule

        class BrokenRule(Rule):
            rule_id = "BROKEN"

            def check(self, orders, ctx):
                raise RuntimeError("private response must not leak")

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(AuditEngine, "_load_rules", return_value=[BrokenRule()]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as caught:
            main(["demo", "--sev", "SEV1", "--json"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["summary"]["ruleErrors"], 1)
        self.assertNotIn("private response", stdout.getvalue())

    def test_share_text_removes_private_identifiers(self):
        row = order(123)
        self.assertEqual(share_detail("订单123于私密门店下单", [row]),
                         "订单[订单已隐藏]于某门店下单")

    def test_json_stdout_is_parseable(self):
        stdout, stderr = cli("demo", "--json")
        result = json.loads(stdout)
        self.assertEqual(result["summary"]["source"], "demo")
        self.assertIn("合成", stderr)

    def test_severity_filter_is_validated_in_demo(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["demo", "--sev", "BAD"])
        self.assertEqual(caught.exception.code, 2)

    def test_since_uses_fixed_reference_and_has_no_future_orders(self):
        result = json.loads(cli("demo", "--since", "7d", "--json")[0])
        self.assertEqual(result["summary"]["orders"], 1)
        self.assertIn("+08:00", result["generatedAt"])

    def test_since_and_at_validation(self):
        for args in (["--since", "-1d"], ["--since", "0"], ["--since", "2m"], ["--at", "bad"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["demo", *args])

    def test_aware_time_is_converted_to_shanghai(self):
        result = json.loads(cli("demo", "--json", "--at", "2026-10-15T04:00:00Z")[0])
        self.assertEqual(result["generatedAt"], "2026-10-15T12:00:00+08:00")

    def test_stable_demo_across_processes(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        command = [sys.executable, "-B", "-m", "mcd_postmortem.cli", "demo", "--json"]
        one = subprocess.run(command, capture_output=True, check=True, env=env).stdout
        two = subprocess.run(command, capture_output=True, check=True, env=env).stdout
        self.assertEqual(one, two)

    def test_windows_redirect_is_utf8_even_when_default_is_gbk(self):
        env = dict(os.environ, PYTHONIOENCODING="gbk")
        result = subprocess.run([sys.executable, "-B", "-m", "mcd_postmortem.cli", "demo", "--json"],
                                capture_output=True, check=True, env=env)
        self.assertEqual(json.loads(result.stdout.decode("utf-8"))["summary"]["orders"], 7)

    def test_status_filter_and_failure_stderr(self):
        rows = [order(0), order(1), order(2)]
        rows[0].create_time = DEMO_TIME - timedelta(minutes=2)
        rows[1].create_time = DEMO_TIME - timedelta(minutes=1)
        rows[2].create_time = DEMO_TIME
        rows[1].order_status = "已取消"
        rows[2].order_status = "未知状态"
        with patch("mcd_postmortem.cli.McpClient"), patch("mcd_postmortem.cli.fetch_orders", return_value=rows), \
                patch("mcd_postmortem.cli.load_nutrition", return_value=table()):
            result = json.loads(cli("audit", "--json", "--at", DEMO_TIME.isoformat())[0])
            self.assertEqual(result["summary"]["orders"], 1)
            self.assertEqual(result["summary"]["excludedByStatus"], {"已取消": 1, "未知状态": 1})
            result = json.loads(cli("audit", "--json", "--at", DEMO_TIME.isoformat(), "--all-statuses")[0])
            self.assertEqual(result["summary"]["orders"], 3)

    def test_missing_token_has_clean_stdout(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MCD_MCP_TOKEN": ""}), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["audit", "--json"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("MCD_MCP_TOKEN", stderr.getvalue())

    def test_card_and_json_can_be_combined(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.png"
            result = json.loads(cli("demo", "--json", "--card", str(path))[0])
            self.assertEqual(result["summary"]["orders"], 7)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1000, 1414))

    def test_empty_card_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            result = json.loads(cli("demo", "--since", "1d", "--json", "--card",
                                    str(Path(folder) / "empty.png"))[0])
            self.assertEqual(result["summary"]["orders"], 0)
            self.assertIsNone(result["summary"]["kcal"])

    def test_fixed_report_is_reproducible_and_not_fixed_30_days(self):
        engine = AuditEngine(demo_nutrition())
        rows = demo_orders()
        incidents = engine.run(rows)
        summary = engine.summary(rows, incidents)
        one = render_report(rows, incidents, summary, DEMO_TIME)
        self.assertEqual(one, render_report(rows, incidents, summary, DEMO_TIME))
        self.assertNotIn("近 30 天", one)
        self.assertIn("匹配", one)


class ClientTests(unittest.TestCase):
    def test_write_tool_rejected_before_network(self):
        client = McpClient("test")
        with patch.object(client, "_request") as request, self.assertRaises(McpError):
            client.call_tool("create-order")
        request.assert_not_called()

    def test_business_json_can_have_whitespace_and_prefix(self):
        client = McpClient("test")
        result = {"content": [{"type": "text", "text": '说明 { "data": [1], "success": true } 尾注'}]}
        with patch.object(client, "_request", return_value=result):
            self.assertEqual(client.order_list(), [1])

    def test_tool_error_and_business_failure_do_not_echo_private_data(self):
        client = McpClient("secret-test-value")
        for result in ({"isError": True}, {"structuredContent": {"success": False, "message": "secret-test-value"}}):
            with patch.object(client, "_request", return_value=result), self.assertRaises(McpError) as caught:
                client.order_list()
            self.assertNotIn("secret-test-value", str(caught.exception))

    def test_sse_response_and_request_id_validation(self):
        client = McpClient("test")
        response = Mock()
        response.read.return_value = (b': heartbeat\n\n'
            b'data: {"jsonrpc":"2.0","method":"notification"}\n\n'
            b'data: {"jsonrpc":"2.0","id":1,"result":{"content":[]}}\n\n')
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(client._request("tools/call", {}), {"content": []})


if __name__ == "__main__":
    unittest.main()
