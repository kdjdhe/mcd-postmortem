"""同一餐品连续至少三笔订单；中断后重新计数，每段只报一次。"""
from mcd_postmortem.rules.base import Incident, Rule

MIN_STREAK = 3


class MonoDependencyRule(Rule):
    sev = "SEV2"
    rule_id = "SEV2-MONO-DEPENDENCY"

    def check(self, orders, ctx):
        active, out = {}, []

        def finish(key, state):
            rows, name = state
            if len(rows) < MIN_STREAK:
                return
            out.append(Incident(
                sev=self.sev, rule_id=self.rule_id,
                title=f"单点依赖：{name} 连续 {len(rows)} 单出现",
                detail=(f"关键服务 {name} 连续 {len(rows)} 次变更均被选中，达到趣味规则阈值 "
                        f"{MIN_STREAK}。建议为菜单引入冗余备份，试试别的单品。"),
                order_ids=[o.order_id for o in rows],
                evidence={"itemName": name, "productCode": key,
                          "occurrences": len(rows), "threshold": MIN_STREAK,
                          "startTime": rows[0].create_time.isoformat(),
                          "endTime": rows[-1].create_time.isoformat(),
                          "windowOrders": len(orders)},
            ))

        for order in orders:
            current = {i["code"] or i["name"]: i["name"] for i in order.items}
            for key in sorted(set(active) - set(current)):
                finish(key, active.pop(key))
            for key, name in sorted(current.items()):
                active.setdefault(key, ([], name))[0].append(order)
        for key, state in sorted(active.items()):
            finish(key, state)
        return out
