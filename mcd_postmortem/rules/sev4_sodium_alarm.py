"""SEV4 · 隐患告警：订单已知餐品钠 ≥ 2400mg（趣味规则阈值）."""
from mcd_postmortem.rules.base import Incident, Rule

SODIUM_LIMIT = 2400  # mg，仅为项目规则阈值，不代表个人健康标准


class SodiumAlarmRule(Rule):
    sev = "SEV4"
    rule_id = "SEV4-SODIUM-ALARM"

    def check(self, orders, ctx):
        out = []
        for o in orders:
            sodium = ctx.sodium_of_order(o)
            if sodium and sodium >= SODIUM_LIMIT:
                out.append(Incident(
                    sev=self.sev, rule_id=self.rule_id,
                    title=f"钠负载告警（{sodium:.0f} mg ≥ 规则阈值 {SODIUM_LIMIT} mg）",
                    detail=(
                        f"{o.create_time.strftime('%m-%d %H:%M')} 的变更 "
                        f"（{_names(o)}）钠负载 {sodium:.0f} mg，"
                        f"达到本项目趣味规则阈值 {SODIUM_LIMIT} mg。"
                        f"这不是个人摄入量或健康风险判断；未匹配项未计入。"
                    ),
                    order_ids=[o.order_id],
                    evidence={"orderId": o.order_id, "sodiumMg": sodium,
                              "threshold": SODIUM_LIMIT,
                              "createTime": o.create_time.isoformat(),
                              "coverage": ctx.coverage(o, "sodium")},
                ))
        return out


def _names(o) -> str:
    return "、".join(i["name"] for i in o.items)
