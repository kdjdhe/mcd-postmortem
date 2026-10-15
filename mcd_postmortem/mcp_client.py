"""麦当劳 MCP Server 客户端.

Streamable HTTP + Bearer Token，单次部署调用数 ≤ 6，远低于官方 600 req/min 限流；
遇到 429 时指数退避重试。
"""
import json
import os
import time
import urllib.error
import urllib.request

MCP_URL = "https://mcp.mcd.cn"
TIMEOUT = 30


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, token: str | None = None, url: str = MCP_URL):
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        if not self.token:
            raise McpError(
                "未找到 MCP Token。请先在 https://open.mcd.cn/mcp 控制台申请，"
                "并 export MCD_MCP_TOKEN=..."
            )
        self.url = url
        self._next_id = 0

    def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        delay = 1.0
        for attempt in range(3):
            req = urllib.request.Request(
                self.url, data=json.dumps(payload).encode("utf-8"),
                headers=headers, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise McpError(f"MCP 服务返回 HTTP {e.code}") from e
            except urllib.error.URLError as e:
                raise McpError(f"无法连接 MCP 服务 {self.url}: {e.reason}") from e
        else:
            raise McpError("MCP 请求重试耗尽")

        if "error" in body:
            raise McpError(f"MCP 错误: {body['error']}")
        return body.get("result", {})

    def call_tool(self, name: str, arguments: dict | None = None):
        """调用一个 MCP Tool，返回解析后的业务 JSON（data 部分）."""
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        texts = [
            c.get("text", "")
            for c in result.get("content", [])
            if c.get("type") == "text"
        ]
        raw = "\n".join(texts)
        # 服务端返回内容为「给 LLM 的说明文字 + JSON + 可能的尾注」的拼接，
        # 用增量解码器取出第一个完整 JSON 对象
        start = raw.find('{"success"')
        if start < 0:
            raise McpError(f"{name} 返回格式异常: {raw[:200]}")
        try:
            payload, _ = json.JSONDecoder().raw_decode(raw[start:])
        except json.JSONDecodeError as e:
            raise McpError(f"{name} 返回 JSON 解析失败: {e}") from e
        if not payload.get("success"):
            raise McpError(f"{name} 业务失败: {payload.get('code')} {payload.get('message')}")
        return payload.get("data")

    # ---- 流水线用到的 Tool 封装 ----

    def time_info(self) -> dict:
        return self.call_tool("now-time-info")

    def nearby_stores(self, city: str, keyword: str, be_type: int = 1) -> list:
        return self.call_tool("query-nearby-stores", {
            "beType": be_type, "searchType": 2, "city": city, "keyword": keyword,
        }) or []

    def meals(self, store_code: str, order_type: int = 1, be_type: int = 1) -> dict:
        return self.call_tool("query-meals", {
            "storeCode": store_code, "orderType": order_type, "beType": be_type,
        }) or {}

    def my_coupons(self) -> list:
        data = self.call_tool("query-my-coupons")
        if isinstance(data, dict):
            return data.get("coupons") or data.get("list") or []
        return data or []

    def calculate_price(self, store_code: str, items: list, order_type: int = 1,
                        be_type: int = 1) -> dict:
        return self.call_tool("calculate-price", {
            "storeCode": store_code, "orderType": order_type, "beType": be_type,
            "items": items,
        }) or {}

    def create_order(self, store_code: str, items: list, take_way_code: str,
                     order_type: int = 1, be_type: int = 1) -> dict:
        return self.call_tool("create-order", {
            "storeCode": store_code, "orderType": order_type, "beType": be_type,
            "takeWayCode": take_way_code, "items": items,
        }) or {}

    def query_order(self, order_id: str) -> dict:
        return self.call_tool("query-order", {"orderId": order_id}) or {}

    def cancel_order(self, order_id: str, reason_code: str = "1") -> dict:
        return self.call_tool("cancel-order", {
            "orderId": order_id, "cancelReasonCode": reason_code,
        }) or {}

    def order_list(self) -> list:
        return self.call_tool("order-list") or []

    def available_coupons(self) -> list:
        return self.call_tool("available-coupons") or []

    def claim_coupons(self) -> dict:
        return self.call_tool("auto-bind-coupons") or {}
