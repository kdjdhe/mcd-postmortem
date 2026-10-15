"""确定性规则判定与营养覆盖率；只汇总可确认的订单餐品数据。"""
import hashlib
import importlib
import json
import pkgutil
from dataclasses import asdict, dataclass

from mcd_postmortem.orders import components, match_nutrition, normalize_orders
from mcd_postmortem.rules.base import Incident, Rule, SEV_ORDER

RULESET_VERSION = "2026.10.15.2"


@dataclass
class AuditContext:
    nutrition_table: dict

    def nutrition_of(self, name):
        return match_nutrition(name, self.nutrition_table, exact_only=True)

    def coverage(self, order, attr):
        total, matched, missing, ambiguous = 0.0, 0, [], []
        parts = list(components(order))
        for part in parts:
            if part["quantity"] is None:
                ambiguous.append(part["name"])
                continue
            nutrition = self.nutrition_of(part["name"])
            value = getattr(nutrition, attr) if nutrition else None
            if value is None:
                missing.append(part["name"])
            else:
                total += value * part["quantity"]
                matched += 1
        return {"value": total if matched else None, "matched": matched,
                "total": len(parts), "missing": missing, "ambiguous": ambiguous,
                "complete": bool(parts) and matched == len(parts)}

    def kcal_of_order(self, order):
        return self.coverage(order, "kcal")["value"]

    def sodium_of_order(self, order):
        return self.coverage(order, "sodium")["value"]


class AuditEngine:
    def __init__(self, nutrition_table):
        self.ctx = AuditContext(nutrition_table)
        self.rules = self._load_rules()

    @staticmethod
    def _load_rules():
        import mcd_postmortem.rules as pkg
        rules = []
        for module in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
            if module.name == "base":
                continue
            mod = importlib.import_module(f"mcd_postmortem.rules.{module.name}")
            for cls in vars(mod).values():
                if (isinstance(cls, type) and issubclass(cls, Rule) and cls is not Rule
                        and cls.__module__ == mod.__name__):
                    rules.append(cls())
        if len({r.rule_id for r in rules}) != len(rules):
            raise ValueError("规则 ID 重复")
        return sorted(rules, key=lambda r: r.rule_id)

    def run(self, orders):
        orders = normalize_orders(orders)
        incidents = []
        for rule in self.rules:
            try:
                incidents.extend(rule.check(orders, self.ctx))
            except Exception as exc:
                incidents.append(Incident(
                    sev="INFO", rule_id=f"ENGINE-{rule.rule_id}",
                    title=f"规则 {rule.rule_id} 执行失败",
                    detail=f"该规则已跳过（{type(exc).__name__}）；本次审计不完整。",
                ))
        rank = {sev: i for i, sev in enumerate(SEV_ORDER)}
        order_rank = {o.order_id: idx for idx, o in enumerate(orders)}
        return sorted(incidents, key=lambda i: (
            rank.get(i.sev, 99), i.rule_id,
            min((order_rank.get(oid, len(orders)) for oid in i.order_ids), default=len(orders)),
            tuple(i.order_ids), i.title))

    def summary(self, orders, incidents):
        orders = normalize_orders(orders)
        nutrition = {}
        for attr in ("kcal", "sodium"):
            rows = [self.ctx.coverage(o, attr) for o in orders]
            matched = sum(r["matched"] for r in rows)
            nutrition[attr] = {
                "value": round(sum(r["value"] or 0 for r in rows), 1) if matched else None,
                "matched": matched, "total": sum(r["total"] for r in rows),
                "missing": sum(len(r["missing"]) for r in rows),
                "ambiguous": sum(len(r["ambiguous"]) for r in rows),
                "complete": bool(rows) and all(r["complete"] for r in rows),
            }
        table = {k: asdict(v) for k, v in sorted(self.ctx.nutrition_table.items())}
        fingerprint = hashlib.sha256(json.dumps(
            table, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        return {
            "orders": len(orders), "kcal": nutrition["kcal"]["value"],
            "sodium": nutrition["sodium"]["value"],
            "amount": round(sum(o.total_amount for o in orders), 2),
            "incidents": len(incidents),
            "by_sev": {sev: sum(i.sev == sev for i in incidents)
                       for sev in SEV_ORDER if any(i.sev == sev for i in incidents)},
            "nutrition": nutrition, "rulesetVersion": RULESET_VERSION,
            "nutritionVersion": fingerprint,
            "periodStart": orders[0].create_time.isoformat() if orders else None,
            "periodEnd": orders[-1].create_time.isoformat() if orders else None,
            "ruleErrors": sum(i.rule_id.startswith("ENGINE-") for i in incidents),
        }
