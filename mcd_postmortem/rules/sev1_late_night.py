"""SEV1 · 深夜变更未走审批：00:00–04:59 下单."""
from datetime import time

from mcd_postmortem.rules.base import Incident, Rule


class LateNightRule(Rule):
    sev = "SEV1"
    rule_id = "SEV1-LATE-NIGHT"

    def check(self, orders, ctx):
        out = []
        for o in orders:
            t = o.create_time.time()
            if time(0, 0) <= t < time(5, 0):
                total_kcal = ctx.kcal_of_order(o)
                detail = (
                    f"{o.create_time.strftime('%m-%d %H:%M')} 于 {o.store_name} "
                    f"发起生产环境变更（{o.order_status}），未走变更审批。"
                    f"变更内容：{_brief(o)}，实付 ¥{o.total_amount:.2f}。"
                    f"影响范围：次日的你。"
                )
                if total_kcal:
                    detail += f" 该变更携带 {total_kcal:.0f} kcal 负载。"
                out.append(Incident(
                    sev=self.sev, rule_id=self.rule_id,
                    title="深夜变更未走审批（00:00–05:00 生产操作）",
                    detail=detail, order_ids=[o.order_id],
                    evidence={"orderId": o.order_id,
                              "createTime": o.create_time.isoformat(),
                              "storeName": o.store_name},
                ))
        return out


def _brief(o) -> str:
    names = "、".join(i["name"] for i in o.items[:3])
    more = f" 等 {len(o.items)} 项" if len(o.items) > 3 else ""
    return f"{names}{more}"
