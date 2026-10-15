"""规则引擎单测：确定性 + 各规则触发场景 + 营养映射."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_postmortem.engine import AuditEngine
from mcd_postmortem.orders import Nutrition, Order


def nutrition_table():
    items = [
        ("巨无霸", 551, 1010),
        ("麦辣鸡腿堡", 548, 1030),
        ("中薯条", 289, 165),
        ("可乐中杯", 170, 10),
        ("零度可乐中杯", 0, 10),
        ("麦乐鸡5块", 213, 422),
        ("朱古力新地", 282, 126),
    ]
    return {n: Nutrition(name=n, kcal=kcal, kj=None, protein=None, fat=None,
                         carbohydrate=None, sodium=na, calcium=None)
            for n, kcal, na in items}


def make_order(order_id, dt, items, amount=30.0, store="测试餐厅", order_type="1"):
    return Order(
        order_id=order_id, create_time=dt, store_name=store, store_code="S1",
        order_status="订单已完成", order_type=order_type, be_type="1",
        total_amount=amount,
        items=[{"name": n, "code": c, "quantity": q, "sub_items": subs}
               for n, c, q, subs in items],
        raw={},
    )


NOW = datetime(2026, 10, 15, 12, 0, 0)


class TestNutritionMatch(unittest.TestCase):
    def test_exact_match(self):
        engine = AuditEngine(nutrition_table())
        self.assertIsNotNone(engine.ctx.nutrition_of("巨无霸"))

    def test_fuzzy_match_ignores_spaces(self):
        engine = AuditEngine(nutrition_table())
        self.assertIsNotNone(engine.ctx.nutrition_of("麦乐鸡 5块"))

    def test_miss_returns_none(self):
        engine = AuditEngine(nutrition_table())
        self.assertIsNone(engine.ctx.nutrition_of("麦门神秘汉堡"))

    def test_combo_subitems_counted(self):
        """套餐主项无营养条目时，子项应被计入（回归：套餐营养记 0 问题）."""
        engine = AuditEngine(nutrition_table())
        order = make_order("O1", NOW, [("巨无霸套餐", "P1", 1, ["中薯条 x1", "可乐中杯 x1"])])
        kcal = engine.ctx.kcal_of_order(order)
        expected = 289 + 170  # 中薯条 + 可乐中杯（套餐本身无条目）
        self.assertAlmostEqual(kcal, expected, places=0)


class TestRules(unittest.TestCase):
    def setUp(self):
        self.engine = AuditEngine(nutrition_table())

    def test_late_night_triggers(self):
        o = make_order("O1", NOW.replace(hour=2, minute=47),
                       [("麦辣鸡腿堡", "C1", 1, [])])
        incidents = self.engine.run([o])
        self.assertTrue(any(i.rule_id == "SEV1-LATE-NIGHT" for i in incidents))

    def test_daytime_no_late_night(self):
        o = make_order("O1", NOW.replace(hour=12, minute=0),
                       [("麦辣鸡腿堡", "C1", 1, [])])
        incidents = self.engine.run([o])
        self.assertFalse(any(i.rule_id == "SEV1-LATE-NIGHT" for i in incidents))

    def test_calorie_overload(self):
        o = make_order("O1", NOW, [("麦辣鸡腿堡", "C1", 2, []), ("中薯条", "C2", 2, [])])
        incidents = self.engine.run([o])
        over = [i for i in incidents if i.rule_id == "SEV1-CALORIE-OVERLOAD"]
        self.assertTrue(over)
        self.assertAlmostEqual(over[0].evidence["kcal"], 548 * 2 + 289 * 2, places=0)

    def test_calorie_below_threshold_no_trigger(self):
        o = make_order("O1", NOW, [("麦辣鸡腿堡", "C1", 2, []), ("中薯条", "C2", 1, [])])
        incidents = self.engine.run([o])
        self.assertFalse(any(i.rule_id == "SEV1-CALORIE-OVERLOAD" for i in incidents))

    def test_mono_dependency_three_streak(self):
        orders = [
            make_order(f"O{i}", NOW - timedelta(days=i), [("巨无霸", "A1", 1, [])])
            for i in range(3)
        ]
        incidents = self.engine.run(orders)
        mono = [i for i in incidents if i.rule_id == "SEV2-MONO-DEPENDENCY"]
        self.assertTrue(mono)
        self.assertEqual(mono[0].evidence["occurrences"], 3)

    def test_mono_dependency_two_no_trigger(self):
        orders = [
            make_order(f"O{i}", NOW - timedelta(days=i), [("巨无霸", "A1", 1, [])])
            for i in range(2)
        ]
        incidents = self.engine.run(orders)
        self.assertFalse(any(i.rule_id == "SEV2-MONO-DEPENDENCY" for i in incidents))

    def test_rapid_redeploy(self):
        t = NOW.replace(hour=12)
        orders = [
            make_order("O1", t, [("巨无霸", "A1", 1, [])]),
            make_order("O2", t + timedelta(minutes=4), [("中薯条", "A2", 1, [])]),
        ]
        incidents = self.engine.run(orders)
        self.assertTrue(any(i.rule_id == "SEV2-RAPID-REDEPLOY" for i in incidents))

    def test_sodium_alarm(self):
        o = make_order("O1", NOW, [("麦辣鸡腿堡", "C1", 2, []), ("巨无霸", "C2", 1, [])])
        incidents = self.engine.run([o])
        alarm = [i for i in incidents if i.rule_id == "SEV4-SODIUM-ALARM"]
        self.assertTrue(alarm)
        self.assertAlmostEqual(alarm[0].evidence["sodiumMg"], 1030 * 2 + 1010, places=0)

    def test_peak_deploy(self):
        o = make_order("O1", NOW.replace(hour=12, minute=49),
                       [("巨无霸", "C1", 1, [])], order_type="1")
        incidents = self.engine.run([o])
        self.assertTrue(any(i.rule_id == "SEV5-PEAK-DEPLOY" for i in incidents))

    def test_untracked_asset(self):
        o = make_order("O1", NOW, [("麦门神秘新品", "X1", 1, [])])
        incidents = self.engine.run([o])
        self.assertTrue(any(i.rule_id == "INFO-404-UNTRACKED" for i in incidents))

    def test_incidents_sorted_by_severity(self):
        orders = [
            make_order("O1", NOW.replace(hour=2, minute=0), [("麦辣鸡腿堡", "C1", 3, [])]),
        ]
        incidents = self.engine.run(orders)
        sevs = [i.sev for i in incidents]
        self.assertEqual(sevs, sorted(sevs, key=["SEV1", "SEV2", "SEV3", "SEV4", "SEV5", "INFO"].index))


class TestDeterminism(unittest.TestCase):
    """同一输入跑两遍结果完全一致（核心理念：规则确定性，非 LLM 幻觉）."""

    def test_same_input_same_output(self):
        orders = [
            make_order("O1", NOW.replace(hour=2, minute=47), [("麦辣鸡腿堡", "C1", 2, [])]),
            make_order("O2", NOW.replace(hour=12, minute=49), [("巨无霸", "C2", 1, [])]),
            make_order("O3", NOW.replace(hour=12, minute=53), [("巨无霸", "C2", 1, [])]),
        ]
        e1 = AuditEngine(nutrition_table())
        e2 = AuditEngine(nutrition_table())
        r1 = [(i.sev, i.rule_id, i.title, i.detail, tuple(i.order_ids)) for i in e1.run(orders)]
        r2 = [(i.sev, i.rule_id, i.title, i.detail, tuple(i.order_ids)) for i in e2.run(orders)]
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
