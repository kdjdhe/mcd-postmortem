"""SEV5 · 流程瑕疵：午高峰（11:30–13:00）到店自取变更.

高峰期发起到店自取，取餐排队即「变更排队」，建议错峰或预约。
"""
from datetime import time

from mcd_postmortem.rules.base import Incident, Rule


class PeakHourRule(Rule):
    sev = "SEV5"
    rule_id = "SEV5-PEAK-DEPLOY"

    def check(self, orders, ctx):
        out = []
        for o in orders:
            t = o.create_time.time()
            to_store = o.order_type == "1"
            if to_store and time(11, 30) <= t < time(13, 0):
                out.append(Incident(
                    sev=self.sev, rule_id=self.rule_id,
                    title="午高峰窗口发起到店变更",
                    detail=(
                        f"{o.create_time.strftime('%m-%d %H:%M')} 处于午高峰（11:30–13:00），"
                        f"仍选择到店自取（{_names(o)}）。"
                        f"高峰期变更需进入发布队列（排队取餐），"
                        f"建议错峰部署或使用预约发布（reservationDate）。"
                    ),
                    order_ids=[o.order_id],
                    evidence={"orderId": o.order_id, "createTime": o.create_time.isoformat()},
                ))
        return out


def _names(o) -> str:
    return "、".join(i["name"] for i in o.items)
