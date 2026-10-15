"""合成演示数据：--demo 模式使用，让评测者无需 Token 即可体验完整审计.

数据为虚构订单，涵盖全部规则触发场景。
"""
from datetime import datetime, timedelta

from mcd_postmortem.orders import Nutrition, Order


def demo_nutrition() -> dict:
    items = [
        ("巨无霸", 551, 25, 33, 45, 1010, 250),
        ("麦辣鸡腿堡", 548, 26, 30, 47, 1030, 190),
        ("麦乐鸡5块", 213, 12, 12, 13, 422, 9),
        ("中薯条", 289, 4, 12, 38, 165, 18),
        ("大薯条", 379, 6, 16, 50, 216, 23),
        ("可乐中杯", 170, 0, 0, 42, 10, 5),
        ("零度可乐中杯", 0, 0, 0, 0, 10, 5),
        ("板烧鸡腿堡", 394, 26, 15, 39, 830, 150),
        ("麦香鱼", 331, 15, 12, 38, 690, 120),
        ("朱古力新地", 282, 5, 9, 44, 126, 182),
        ("麦旋风", 266, 5, 9, 40, 116, 185),
    ]
    return {k: Nutrition(name=k, kcal=v[1], kj=None, protein=v[2], fat=v[3],
                         carbohydrate=v[4], sodium=v[5], calcium=v[6])
            for k, v in ((n, (n, kcal, p, f, c, na, ca)) for n, kcal, p, f, c, na, ca in items)}


def demo_orders() -> list:
    now = datetime(2026, 10, 15, 12, 0, 0)
    rows = [
        # (天数前, 时间, 门店, [(名称, 数量, 子项)], 金额)
        (28, "12:31", "麦当劳上海福州路餐厅", [("巨无霸", 1, [])], 25.5),
        (27, "12:05", "麦当劳上海福州路餐厅", [("巨无霸", 1, [])], 25.5),
        (26, "12:18", "麦当劳上海福州路餐厅", [("巨无霸", 1, [("可乐中杯", 1)])], 32.0),
        (20, "02:47", "麦当劳上海南京西路餐厅",
         [("麦辣鸡腿堡", 2, []), ("大薯条", 1, []), ("麦乐鸡5块", 2, [])], 71.5),
        (14, "12:49", "麦当劳上海福州路餐厅", [("板烧鸡腿堡", 1, [])], 23.5),
        (14, "12:53", "麦当劳上海福州路餐厅", [("麦香鱼", 1, [])], 15.0),
        (7,  "18:22", "麦当劳上海悦荟广场餐厅",
         [("朱古力新地", 1, []), ("麦旋风", 1, []), ("大薯条", 2, [])], 46.0),
    ]
    orders = []
    for days_ago, hhmm, store, items, amount in rows:
        dt = now - timedelta(days=days_ago)
        dt = dt.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:5]))
        # code 从商品名生成（同名同码），模拟真实 productCode 的稳定性
        seen_names = {}
        order_items = []
        for n, q, subs in items:
            if n not in seen_names:
                seen_names[n] = f"9900{abs(hash(n)) % 10000:04d}"
            order_items.append({"name": n, "code": seen_names[n], "quantity": q,
                                "sub_items": [f"{s} x{sq}" for s, sq in subs]})
        orders.append(Order(
            order_id=f"DEMO{days_ago:03d}{hhmm.replace(':', '')}",
            create_time=dt, store_name=store, store_code="DEMO",
            order_status="订单已完成", order_type="1", be_type="1",
            total_amount=amount, items=order_items, raw={},
        ))
    orders.sort(key=lambda x: x.create_time)
    return orders
