"""INFO · 404 未建档：订单商品在官方营养表中无匹配条目.

匹配失败不算错误，计入 INFO 级「未纳管资产」，提示建立 CMDB 记录。
"""
from mcd_postmortem.rules.base import Incident, Rule
from mcd_postmortem.orders import components


class UntrackedAssetRule(Rule):
    sev = "INFO"
    rule_id = "INFO-404-UNTRACKED"

    def check(self, orders, ctx):
        seen = {}
        for o in orders:
            for i in components(o):
                if ctx.nutrition_of(i["name"]) is None:
                    key = i["code"] or i["name"]
                    seen.setdefault(key, {"item": i, "orders": []})
                    if o not in seen[key]["orders"]:
                        seen[key]["orders"].append(o)
        out = []
        for key, v in seen.items():
            item = v["item"]
            out.append(Incident(
                sev=self.sev, rule_id=self.rule_id,
                title=f"404 未建档：{item['name']}",
                detail=(
                    f"资产 {item['name']} 在本次营养数据中未检索到记录，"
                    f"出现 {len(v['orders'])} 次。"
                    f"未纳管资产无法参与容量与负载评估，建议纳入 CMDB（营养表）管理。"
                ),
                order_ids=[o.order_id for o in v["orders"]],
                evidence={"itemName": item["name"], "productCode": item["code"]},
            ))
        return out
