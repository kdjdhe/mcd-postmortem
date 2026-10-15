"""订单拉取与清洗、营养表解析、订单商品 ↔ 营养条目映射.

数据源（麦当劳官方 MCP）:
- order-list           → 近 30 天订单
- list-nutrition-foods → 160 项餐品营养表（纯文本表格，解析后离线缓存）
"""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

CACHE_FILE = ".nutrition_cache.json"


@dataclass
class Order:
    order_id: str
    create_time: datetime
    store_name: str
    store_code: str
    order_status: str
    order_type: str          # 1 到店 / 2 外送
    be_type: str             # 1 到店取餐 / 2 麦乐送 / 5 得来速 / 6 团餐
    total_amount: float      # 实付（元）
    items: list              # [{name, code, quantity, sub_items: [str]}]
    raw: dict = field(default_factory=dict)


@dataclass
class Nutrition:
    name: str
    kcal: float | None
    kj: float | None
    protein: float | None
    fat: float | None
    carbohydrate: float | None
    sodium: float | None
    calcium: float | None


def fetch_orders(client) -> list[Order]:
    """拉取历史订单并清洗为 Order 结构."""
    data = client.order_list()
    rows = data.get("list") if isinstance(data, dict) else data
    orders = []
    for o in rows or []:
        items = []
        for p in o.get("orderProductList") or []:
            subs = [
                f"{s.get('name', '?')} x{s.get('quantity', 1)}"
                for s in p.get("comboItemList") or []
            ]
            items.append({
                "name": p.get("productName", "?"),
                "code": p.get("productCode", ""),
                "quantity": int(p.get("quantity", 1)),
                "sub_items": subs,
            })
        try:
            amount = float(o.get("realTotalAmount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        orders.append(Order(
            order_id=str(o.get("orderId", "")),
            create_time=datetime.strptime(o["createTime"], "%Y-%m-%d %H:%M:%S"),
            store_name=o.get("storeName", "?"),
            store_code=str(o.get("storeCode", "")),
            order_status=o.get("orderStatus", "?"),
            order_type=str(o.get("orderType", "")),
            be_type=str(o.get("beType", "")),
            total_amount=amount,
            items=items,
            raw=o,
        ))
    orders.sort(key=lambda x: x.create_time)
    return orders


def load_nutrition(client, use_cache: bool = True) -> dict[str, Nutrition]:
    """解析营养表 → {规范化名称: Nutrition}. 结果落盘缓存（营养表是静态数据）."""
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                raw = json.load(f)
            return {k: Nutrition(**v) for k, v in raw.items()}
        except Exception:
            pass

    data = client.call_tool("list-nutrition-foods")
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    table = _parse_nutrition_text(text)
    if not table:
        raise RuntimeError("营养表解析失败：未得到任何条目")

    if use_cache:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({k: vars(v) for k, v in table.items()}, f, ensure_ascii=False)
    return table


def _parse_nutrition_text(text: str) -> dict[str, Nutrition]:
    """解析官方返回的表格文本.

    格式: "[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,
    carbohydrate,sodium,calcium}:\\n  猪柳麦满分,null,1288,308,16,16,24,781,213\\n ..."
    """
    m = re.search(r"\{([^}]*)\}\s*:", text)
    if not m:
        return {}
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("{") or "," not in line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        rows.append(parts)
    table = {}
    for p in rows:
        def num(s):
            try:
                v = float(s)
                return v
            except (TypeError, ValueError):
                return None
        name = _normalize(p[0])
        table[name] = Nutrition(
            name=p[0],
            kj=num(p[2]), kcal=num(p[3]), protein=num(p[4]), fat=num(p[5]),
            carbohydrate=num(p[6]), sodium=num(p[7]), calcium=num(p[8]),
        )
    return table


def _normalize(name: str) -> str:
    return re.sub(r"[\s·・（）()【】\[\]「」-]+", "", name or "").lower()


def match_nutrition(item_name: str, table: dict[str, Nutrition],
                    exact_only: bool = False) -> Nutrition | None:
    """订单商品名 → 营养条目.

    exact_only=False: 规范化完全相等 > 规范化包含（长名优先），用于单品查询。
    exact_only=True: 仅规范化完全相等，用于营养核算——
        「巨无霸套餐」不是「巨无霸」，套餐营养由其子项（comboItemList）构成，
        模糊蹭用单品的营养会造成重复/错误计量。
    匹配失败返回 None。
    """
    key = _normalize(item_name)
    if not key:
        return None
    if key in table:
        return table[key]
    if exact_only:
        return None
    contains = [(len(k), v) for k, v in table.items() if k and (k in key or key in k)]
    if not contains:
        return None
    contains.sort(key=lambda x: x[0])
    return contains[0][1]
