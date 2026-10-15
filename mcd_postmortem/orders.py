"""订单清洗、套餐数量口径与可刷新的营养表缓存。"""
import csv
import io
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CACHE_MAX_AGE = 7 * 24 * 3600
COMPLETED_STATUSES = {"订单已完成", "已完成", "已取餐", "已送达", "completed", "finished"}
QUANTITY_SCOPES = ("unknown", "per-parent", "per-order")


@dataclass
class Order:
    order_id: str
    create_time: datetime
    store_name: str
    store_code: str
    order_status: str
    order_type: str
    be_type: str
    total_amount: float
    items: list
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


def _quantity(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)) or int(value) < 1:
        raise ValueError("餐品数量必须为正整数")
    return int(value)


def normalize_orders(orders):
    """统一顺序并去重；同订单号出现冲突内容时拒绝静默挑选。"""
    unique = {}
    for order in orders:
        if not order.order_id:
            raise ValueError("订单缺少 orderId")
        if order.order_id in unique and unique[order.order_id] != order:
            raise ValueError("同一 orderId 存在不同内容，请检查输入")
        unique[order.order_id] = order
    return sorted(unique.values(), key=lambda o: (o.create_time, o.order_id))


def fetch_orders(client, combo_quantities="unknown"):
    """保留结构化子项；官方多份套餐数量含义未确认时默认不猜测。"""
    if combo_quantities not in QUANTITY_SCOPES:
        raise ValueError("未知的套餐数量口径")
    data = client.order_list()
    rows = (data.get("list", data.get("orders", [])) if isinstance(data, dict) else data)
    if not isinstance(rows, list):
        raise ValueError("历史订单返回格式应为列表")
    orders = []
    for row in rows:
        items = []
        for product in row.get("orderProductList") or []:
            subs = [{"name": sub.get("name") or sub.get("productName") or "?",
                     "code": str(sub.get("productCode") or ""),
                     "quantity": _quantity(sub.get("quantity", 1))}
                    for sub in product.get("comboItemList") or []]
            items.append({"name": product.get("productName") or "?",
                          "code": str(product.get("productCode") or ""),
                          "quantity": _quantity(product.get("quantity", 1)),
                          "sub_items": subs, "sub_quantity_scope": combo_quantities})
        amount = float(row.get("realTotalAmount") or 0)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("订单金额必须为有限非负数")
        orders.append(Order(
            order_id=str(row.get("orderId") or ""),
            create_time=datetime.strptime(row["createTime"], "%Y-%m-%d %H:%M:%S"),
            store_name=row.get("storeName") or "?", store_code=str(row.get("storeCode") or ""),
            order_status=str(row.get("orderStatus") or "未知"),
            order_type=str(row.get("orderType") or ""), be_type=str(row.get("beType") or ""),
            total_amount=amount, items=items, raw=row,
        ))
    return normalize_orders(orders)


def components(order):
    """有子项时只计子项，防止套餐与子项双计。旧字符串子项按每份定义。"""
    for item in order.items:
        parent_qty = _quantity(item.get("quantity", 1))
        subs = item.get("sub_items") or []
        if not subs:
            yield {"name": item["name"], "code": item.get("code", ""), "quantity": parent_qty}
            continue
        scope = item.get("sub_quantity_scope", "per-parent")
        if scope not in QUANTITY_SCOPES:
            raise ValueError("未知的套餐数量口径")
        for sub in subs:
            if isinstance(sub, str):
                name, sep, qty = sub.rpartition(" x")
                part = {"name": name if sep else sub, "code": "",
                        "quantity": _quantity(qty) if sep else 1}
            else:
                part = {"name": sub["name"], "code": sub.get("code", ""),
                        "quantity": _quantity(sub.get("quantity", 1))}
            if scope == "unknown" and parent_qty != 1:
                part["quantity"] = None
            elif scope != "per-order":
                part["quantity"] *= parent_qty
            yield part


def cache_path():
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    return Path(root or Path.home() / ".cache") / "mcd-postmortem" / "nutrition-v1.json"


def load_nutrition(client, use_cache=True):
    path = cache_path()
    if use_cache and path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - cached["fetchedAt"]
            if cached["schemaVersion"] == 1 and 0 <= age < CACHE_MAX_AGE:
                table = {k: Nutrition(**v) for k, v in cached["foods"].items()}
                for food in table.values():
                    if not isinstance(food.name, str):
                        raise ValueError("营养缓存名称异常")
                    for key, value in vars(food).items():
                        if key != "name" and value is not None and (
                                isinstance(value, bool) or not isinstance(value, (int, float))
                                or not math.isfinite(value) or value < 0):
                            raise ValueError("营养缓存数值异常")
                if table:
                    return table
        except (ValueError, TypeError, KeyError, AttributeError, OSError):
            pass
    if client is None:
        raise RuntimeError("营养缓存缺失、已过期或损坏，请联网刷新")
    data = client.call_tool("list-nutrition-foods")
    if isinstance(data, dict) and isinstance(data.get("list"), list):
        data = data["list"]
    if isinstance(data, list):
        table = _nutrition_rows(data)
    elif isinstance(data, str):
        table = _parse_nutrition_text(data)
    else:
        raise RuntimeError("无法识别营养表结构")
    if not table:
        raise RuntimeError("营养表解析失败：未得到任何条目")
    # --refresh 会绕过读取，但仍保存新缓存；失败的写入不影响已取得的数据。
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schemaVersion": 1, "fetchedAt": time.time(),
                   "foods": {k: vars(v) for k, v in table.items()}}
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False, suffix=".tmp") as stream:
            tmp = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
        try:
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return table


def _nutrition_rows(rows):
    def number(value):
        try:
            n = float(value)
            return n if math.isfinite(n) and n >= 0 else None
        except (TypeError, ValueError):
            return None
    table = {}
    for row in rows:
        name = row.get("productName")
        if not isinstance(name, str) or not _normalize(name):
            continue
        food = Nutrition(
            name=name, kj=number(row.get("energyKj")), kcal=number(row.get("energyKcal")),
            protein=number(row.get("protein")), fat=number(row.get("fat")),
            carbohydrate=number(row.get("carbohydrate")), sodium=number(row.get("sodium")),
            calcium=number(row.get("calcium")),
        )
        key = _normalize(name)
        if key in table and any(getattr(table[key], field) != getattr(food, field)
                                for field in vars(food) if field != "name"):
            raise RuntimeError("营养表存在同名但数值不同的记录，无法确定计量口径")
        table[key] = food
    return table


def _parse_nutrition_text(text):
    match = re.search(r"\{([^}]*)\}\s*:", text)
    if not match:
        return {}
    headers = next(csv.reader([match.group(1)]))
    rows = []
    for values in csv.reader(io.StringIO(text[match.end():].strip()), skipinitialspace=True):
        if len(values) == len(headers):
            rows.append(dict(zip(headers, values)))
    return _nutrition_rows(rows)


def _normalize(name):
    return re.sub(r"[\s·・（）()【】\[\]「」-]+", "", name or "").lower()


def match_nutrition(item_name, table, exact_only=False):
    key = _normalize(item_name)
    if not key:
        return None
    normalized = {_normalize(k): v for k, v in table.items()}
    if key in normalized:
        return normalized[key]
    if exact_only:
        return None
    matches = [(len(k), k, v) for k, v in normalized.items() if k and (k in key or key in k)]
    return sorted(matches, key=lambda x: (-x[0], x[1]))[0][2] if matches else None
