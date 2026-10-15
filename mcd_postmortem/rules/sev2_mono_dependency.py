"""SEV2 · 单点依赖：同一餐品连续 ≥ 3 单重复出现.

「服务一旦下架将导致早午餐不可用」。
"""
from collections import Counter

from mcd_postmortem.rules.base import Incident, Rule

MIN_STREAK = 3


class MonoDependencyRule(Rule):
    sev = "SEV2"
    rule_id = "SEV2-MONO-DEPENDENCY"

    def check(self, orders, ctx):
        if len(orders) < MIN_STREAK:
            return []
        counter = Counter()
        last_seen = {}
        for o in orders:  # orders 已按时间升序
            for i in o.items:
                key = i["code"] or i["name"]
                counter[key] += 1
                last_seen[key] = (o, i)
        out = []
        for key, n in counter.items():
            if n < MIN_STREAK:
                continue
            o, item = last_seen[key]
            out.append(Incident(
                sev=self.sev, rule_id=self.rule_id,
                title=f"单点依赖：{item['name']} 已出现 {n} 次（阈值 {MIN_STREAK}）",
                detail=(
                    f"关键服务 {item['name']} 在观察期 {len(orders)} 次变更中出现 {n} 次，"
                    f"构成单点依赖。该服务一旦下架，早/午餐可用性将受到直接影响。"
                    f"建议引入冗余备份（另选 1–2 个替代单品并完成灰度验证）。"
                ),
                order_ids=[o.order_id],
                evidence={"itemName": item["name"], "productCode": item["code"],
                          "occurrences": n, "windowOrders": len(orders)},
            ))
        return out
