"""SEV4 · 隐患告警：单笔钠 ≥ 2400mg（≈ 日推荐摄入量）."""
from mcd_postmortem.rules.base import Incident, Rule

SODIUM_LIMIT = 2400  # mg，成人每日推荐上限（中国营养学会）


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
                    title=f"钠负载告警（{sodium:.0f} mg ≥ 日推荐 {SODIUM_LIMIT} mg）",
                    detail=(
                        f"{o.create_time.strftime('%m-%d %H:%M')} 的变更 "
                        f"（{_names(o)}）钠负载 {sodium:.0f} mg，"
                        f"已达成人每日推荐上限（{SODIUM_LIMIT} mg）。"
                        f"容量规划（肾脏）已收到告警，建议后续变更关注减盐配置。"
                    ),
                    order_ids=[o.order_id],
                    evidence={"orderId": o.order_id, "sodiumMg": sodium,
                              "threshold": SODIUM_LIMIT},
                ))
        return out


def _names(o) -> str:
    return "、".join(i["name"] for i in o.items)
