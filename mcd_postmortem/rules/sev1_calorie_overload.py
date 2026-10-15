"""SEV1 · 单笔热量过载：订单合计 ≥ 1500 kcal."""
from mcd_postmortem.rules.base import Incident, Rule

KCAL_LIMIT = 1500


class CalorieOverloadRule(Rule):
    sev = "SEV1"
    rule_id = "SEV1-CALORIE-OVERLOAD"

    def check(self, orders, ctx):
        out = []
        for o in orders:
            kcal = ctx.kcal_of_order(o)
            if kcal and kcal >= KCAL_LIMIT:
                out.append(Incident(
                    sev=self.sev, rule_id=self.rule_id,
                    title=f"单笔热量过载（{kcal:.0f} kcal ≥ 阈值 {KCAL_LIMIT} kcal）",
                    detail=(
                        f"{o.create_time.strftime('%m-%d %H:%M')} 的变更 "
                        f"（{_names(o)}）按本次营养表计算的已知餐品负载为 {kcal:.0f} kcal，"
                        f"达到本项目趣味规则阈值 {KCAL_LIMIT} kcal。"
                        f"这是订单餐品合计，不代表个人实际摄入；缺失项未计入。"
                    ),
                    order_ids=[o.order_id],
                    evidence={"orderId": o.order_id, "kcal": kcal, "threshold": KCAL_LIMIT,
                              "createTime": o.create_time.isoformat(),
                              "coverage": ctx.coverage(o, "kcal")},
                ))
        return out


def _names(o) -> str:
    return "、".join(i["name"] for i in o.items)
