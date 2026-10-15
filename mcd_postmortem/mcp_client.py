"""麦当劳只读 MCP 客户端：限制为订单与营养查询，不携带写工具封装。"""
import json
import os
import time
import urllib.error
import urllib.request

MCP_URL = "https://mcp.mcd.cn"
TIMEOUT = 30
READ_TOOLS = frozenset({"order-list", "list-nutrition-foods"})


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, token: str | None = None, url: str = MCP_URL):
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        if not self.token:
            raise McpError("未找到 MCD_MCP_TOKEN。可先运行 mcd-postmortem demo。")
        self.url = url
        self._next_id = 0

    def _request(self, method, params):
        self._next_id += 1
        request_id = self._next_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        for attempt in range(3):
            req = urllib.request.Request(self.url, data=json.dumps(payload).encode(),
                                         headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise McpError(f"MCP 服务返回 HTTP {exc.code}") from None
            except (urllib.error.URLError, TimeoutError, UnicodeError):
                raise McpError("MCP 连接或响应解码失败，请检查网络后重试") from None
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            # Streamable HTTP 的 SSE 响应可包含通知/心跳；选取当前请求的 JSON-RPC 响应。
            body = None
            for event in raw.replace("\r\n", "\n").split("\n\n"):
                text = "\n".join(line[5:].lstrip() for line in event.splitlines()
                                 if line.startswith("data:"))
                try:
                    candidate = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and candidate.get("id") == request_id:
                    body = candidate
                    break
        if not isinstance(body, dict) or body.get("id") != request_id:
            raise McpError("MCP 响应格式或请求编号异常")
        if "error" in body:
            raise McpError("MCP 返回 JSON-RPC 错误")
        result = body.get("result")
        if not isinstance(result, dict):
            raise McpError("MCP result 格式异常")
        return result

    def call_tool(self, name, arguments=None):
        if name not in READ_TOOLS:
            raise McpError(f"本客户端仅允许只读工具：{', '.join(sorted(READ_TOOLS))}")
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise McpError(f"{name} 工具执行失败")
        payload = result.get("structuredContent")
        if not isinstance(payload, dict) or "success" not in payload:
            raw = "\n".join(c.get("text", "") for c in result.get("content", [])
                            if c.get("type") == "text")
            decoder, payload = json.JSONDecoder(), None
            for index, ch in enumerate(raw):
                if ch != "{":
                    continue
                try:
                    candidate, _ = decoder.raw_decode(raw[index:])
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and "success" in candidate:
                    payload = candidate
                    break
        if not isinstance(payload, dict):
            raise McpError(f"{name} 未返回可识别的业务结果")
        if payload.get("success") is not True:
            raise McpError(f"{name} 业务失败（响应内容已省略）")
        return payload.get("data")

    def order_list(self):
        return self.call_tool("order-list") or []
