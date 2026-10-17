"""service 层测试：CLI 与 GUI 共用的审计入口，全部离线。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from mcd_postmortem import service
from mcd_postmortem.demo_data import DEMO_TIME
from mcd_postmortem.orders import Nutrition, Order


def order(index, status="订单已完成"):
    return Order(str(index), DEMO_TIME + timedelta(minutes=index), "测试门店", "S", status,
                 "1", "1", 10, [{"name": "A", "code": "A", "quantity": 1, "sub_items": []}])


def table():
    return {"a": Nutrition("A", 100, 400, 1, 1, 1, 50, 1)}


class ServiceDemoTests(unittest.TestCase):
    def test_demo_result_has_report_json_and_text(self):
        result = service.run_demo()
        self.assertEqual(result.summary["orders"], 7)
        self.assertEqual(result.report_json["schemaVersion"], 1)
        self.assertEqual(len(result.report_json["incidents"]), 10)
        self.assertIsInstance(result.report_text, str)
        self.assertIn("事故复盘报告", result.report_text)

    def test_demo_progress_reports_stages_in_order(self):
        stages = []
        with tempfile.TemporaryDirectory() as folder:
            service.run_demo(
                service.AuditOptions(card_path=Path(folder) / "card.png"),
                progress=lambda stage, message: stages.append(stage))
        self.assertEqual(stages[0], "prepare")
        self.assertEqual(stages[-1], "card")

    def test_demo_card_is_generated(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.png"
            result = service.run_demo(service.AuditOptions(card_path=path))
            self.assertEqual(result.card_path, str(path))
            with Image.open(path) as image:
                self.assertEqual(image.size, (1000, 1414))

    def test_since_filter_uses_fixed_demo_time(self):
        result = service.run_demo(service.AuditOptions(since_days=7))
        self.assertEqual(result.summary["orders"], 1)

    def test_severity_filter_keeps_pre_filter_count(self):
        result = service.run_demo(service.AuditOptions(sev="SEV1"))
        self.assertTrue(all(i.sev == "SEV1" for i in result.incidents))
        self.assertEqual(result.summary["totalIncidentsBeforeFilter"], 10)

    def test_unknown_severity_is_rejected(self):
        with self.assertRaises(ValueError):
            service.run_demo(service.AuditOptions(sev="BAD"))


class ServiceAuditTests(unittest.TestCase):
    def test_audit_passes_token_and_returns_mcp_source(self):
        rows = [order(0), order(1, "已取消")]
        client = Mock()
        with patch("mcd_postmortem.service.McpClient", return_value=client) as factory, \
                patch("mcd_postmortem.service.fetch_orders", return_value=rows) as fetch, \
                patch("mcd_postmortem.service.load_nutrition", return_value=table()):
            result = service.run_audit(service.AuditOptions(), token="secret")
        factory.assert_called_once_with(token="secret")
        fetch.assert_called_once_with(client, combo_quantities="unknown")
        self.assertEqual(result.summary["source"], "mcp")
        self.assertEqual(result.summary["orders"], 1)
        self.assertEqual(result.summary["excludedByStatus"], {"已取消": 1})

    def test_audit_forwards_filters(self):
        rows = [order(0), order(1)]
        with patch("mcd_postmortem.service.McpClient"), \
                patch("mcd_postmortem.service.fetch_orders", return_value=rows), \
                patch("mcd_postmortem.service.load_nutrition", return_value=table()):
            result = service.run_audit(service.AuditOptions(
                all_statuses=True, combo_quantities="per-order"))
        self.assertEqual(result.summary["orders"], 2)
        self.assertEqual(result.summary["comboQuantityScope"], "per-order")

    def test_audit_result_json_is_serializable(self):
        rows = [order(0)]
        with patch("mcd_postmortem.service.McpClient"), \
                patch("mcd_postmortem.service.fetch_orders", return_value=rows), \
                patch("mcd_postmortem.service.load_nutrition", return_value=table()):
            result = service.run_audit(service.AuditOptions())
        text = json.dumps(result.report_json, ensure_ascii=False, allow_nan=False)
        self.assertIn("inputDigest", json.loads(text))


if __name__ == "__main__":
    unittest.main()
