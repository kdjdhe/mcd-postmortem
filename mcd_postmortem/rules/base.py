"""事故规则基类.

每条规则一个模块，暴露 INCIDENT 实例（check 函数 + 元数据）。
社区 PR 新规则 = 往 rules/ 加一个文件，engine 自动发现。
"""
from dataclasses import dataclass, field


@dataclass
class Incident:
    sev: str                 # SEV1..SEV5 / INFO
    rule_id: str             # 如 SEV1-LATE-NIGHT
    title: str               # 一句话事故标题
    detail: str              # 证据与说明（含真实字段值）
    order_ids: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)  # 可溯源字段


SEV_ORDER = ["SEV1", "SEV2", "SEV3", "SEV4", "SEV5", "INFO"]
SEV_TITLES = {
    "SEV1": "重大生产事故",
    "SEV2": "单点故障",
    "SEV3": "资损事故",
    "SEV4": "隐患告警",
    "SEV5": "流程瑕疵",
    "INFO": "优秀实践",
}


class Rule:
    """规则基类：子类实现 check(orders, ctx) -> list[Incident]."""

    sev = "INFO"
    rule_id = "BASE"

    def check(self, orders, ctx) -> list[Incident]:
        raise NotImplementedError
