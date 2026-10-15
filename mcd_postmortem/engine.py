"""审计引擎：加载规则 → 计算每单证据（热量/钠）→ 产出事故列表.

确定性保证：同一份订单数据跑两遍，结果一字不差。
"""
import importlib
import pkgutil
from dataclasses import dataclass

from mcd_postmortem.orders import match_nutrition
from mcd_postmortem.rules.base import SEV_ORDER


@dataclass
class AuditContext:
    """规则共享的查询接口：订单热量/钠、营养匹配."""

    nutrition_table: dict

    def nutrition_of(self, item_name: str):
        """营养核算用精确匹配：套餐/组合名不得蹭用单品的营养（子项另计）."""
        return match_nutrition(item_name, self.nutrition_table, exact_only=True)

    def kcal_of_order(self, order) -> float | None:
        return self._sum_order(order, "kcal")

    def sodium_of_order(self, order) -> float | None:
        return self._sum_order(order, "sodium")

    def _sum_order(self, order, attr) -> float | None:
        """按「主商品 + 套餐子项」两级汇总营养.

        套餐本身在营养表常无条目（如 XX套餐/五选一），但其子项（汉堡/饮料）有——
        两级都计入，避免套餐订单营养被记 0。
        """
        names = []
        for i in order.items:
            names.append((i["name"], i["quantity"]))
            for sub in i.get("sub_items") or []:
                # 子项格式 "可乐中杯 x1"
                if " x" in sub:
                    sname, sq = sub.rsplit(" x", 1)
                    try:
                        names.append((sname, int(sq)))
                    except ValueError:
                        names.append((sname, 1))
                else:
                    names.append((sub, 1))
        total, matched_any = 0.0, False
        for name, qty in names:
            n = self.nutrition_of(name)
            if n is not None and getattr(n, attr) is not None:
                total += getattr(n, attr) * qty
                matched_any = True
        return total if matched_any else None


class AuditEngine:
    def __init__(self, nutrition_table: dict):
        self.ctx = AuditContext(nutrition_table)
        self.rules = self._load_rules()

    @staticmethod
    def _load_rules():
        """自动发现 mcd_postmortem/rules/ 下所有规则的 Rule 子类."""
        import mcd_postmortem.rules as pkg
        rules = []
        for m in pkgutil.iter_modules(pkg.__path__):
            if m.name in ("base", "__init__"):
                continue
            mod = importlib.import_module(f"mcd_postmortem.rules.{m.name}")
            for attr in vars(mod).values():
                if (isinstance(attr, type) and issubclass(attr, Rule.__mro__[-2])
                        and attr is not Rule):
                    rules.append(attr())
        return rules

    def run(self, orders) -> list:
        """执行全部规则，返回按严重度排序的事故列表."""
        incidents = []
        for rule in self.rules:
            try:
                incidents.extend(rule.check(orders, self.ctx))
            except Exception as e:  # 单条规则失败不影响整体审计
                incidents.append(_rule_error_incident(rule, e))
        sev_rank = {s: i for i, s in enumerate(SEV_ORDER)}
        incidents.sort(key=lambda x: sev_rank.get(x.sev, 99))
        return incidents

    def summary(self, orders, incidents) -> dict:
        """报告头统计."""
        kcal_total = sum(filter(None, (self.ctx.kcal_of_order(o) for o in orders)))
        sodium_total = sum(filter(None, (self.ctx.sodium_of_order(o) for o in orders)))
        amount_total = sum(o.total_amount for o in orders)
        by_sev = {}
        for i in incidents:
            by_sev[i.sev] = by_sev.get(i.sev, 0) + 1
        return {
            "orders": len(orders),
            "kcal": round(kcal_total, 1) if kcal_total else 0,
            "sodium": round(sodium_total, 1) if sodium_total else 0,
            "amount": round(amount_total, 2),
            "incidents": len(incidents),
            "by_sev": by_sev,
        }


from mcd_postmortem.rules.base import Rule  # noqa: E402  (避免循环导入放底部)


def _rule_error_incident(rule, exc) -> "object":
    from mcd_postmortem.rules.base import Incident
    return Incident(
        sev="INFO", rule_id=f"ENGINE-{rule.rule_id}",
        title=f"规则 {rule.rule_id} 执行失败",
        detail=f"该规则在审计中抛出异常已跳过：{exc}",
    )
