"""SEV2 · 决策窗口拥塞：连续两单间隔 < 10 分钟（决策系统反复变更）."""
from mcd_postmortem.rules.base import Incident, Rule


class RapidRedeployRule(Rule):
    sev = "SEV2"
    rule_id = "SEV2-RAPID-REDEPLOY"

    def check(self, orders, ctx):
        out = []
        for prev, curr in zip(orders, orders[1:]):
            gap = (curr.create_time - prev.create_time).total_seconds() / 60
            if 0 < gap < 10:
                out.append(Incident(
                    sev=self.sev, rule_id=self.rule_id,
                    title=f"10 分钟内连续变更（间隔 {gap:.0f} 分钟）",
                    detail=(
                        f"{prev.create_time.strftime('%m-%d %H:%M')} 部署 {_names(prev)} 后，"
                        f"仅 {gap:.0f} 分钟又于 {curr.store_name} 部署 {_names(curr)}。"
                        f"首次部署未经过充分评审即被回滚替换，属于典型的变更管理失控。"
                    ),
                    order_ids=[prev.order_id, curr.order_id],
                    evidence={"gapMinutes": round(gap, 1),
                              "prev": prev.order_id, "curr": curr.order_id},
                ))
        return out


def _names(o) -> str:
    return "、".join(i["name"] for i in o.items) or "空变更"
