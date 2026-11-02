"""网络搜索工具：调用百度千帆 AI 搜索 API，返回搜索摘要与来源。"""

from __future__ import annotations

import json
import urllib.error 
import urllib.request
from typing import Any, Dict, List, Optional

from .base import ToolError, ToolSpec

__all__ = ["SearchClient", "build_search_tool"]

DEFAULT_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
DEFAULT_RESULTS = 10


class SearchClient:
    """百度千帆 AI 搜索客户端：负责鉴权与请求/解析。"""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 30.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("缺少百度千帆搜索 api_key")
        self._api_key = api_key.strip()
        self._endpoint = endpoint
        self._timeout = timeout

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - 尽力读取错误体
                pass
            raise ToolError(
                f"百度搜索接口返回 HTTP {exc.code}: {exc.reason or ''} {detail}".strip()
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            raise ToolError(f"无法连接百度搜索服务: {reason}") from exc
        except TimeoutError as exc:
            raise ToolError(f"请求百度搜索服务超时（{self._timeout}s）") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolError(f"百度搜索返回了非 JSON 内容: {raw[:300]}") from exc
        return data

    def _check_error(self, data: Dict[str, Any]) -> None:
        code = data.get("code")
        # 成功响应没有 code；API 返回错误码时抛出清晰信息
        if code is not None:
            message = data.get("message") or "未知错误"
            request_id = data.get("requestId") or data.get("request_id") or ""
            prefix = f"（requestId: {request_id}）" if request_id else ""
            raise ToolError(f"百度搜索接口返回错误 code={code}{prefix}，{message}")

    def search(self, query: str, top_k: int = DEFAULT_RESULTS) -> Dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ToolError("搜索关键词 query 不能为空")
        if not (1 <= int(top_k) <= 50):
            raise ToolError("top_k 必须在 1 到 50 之间")

        payload = {
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": int(top_k)}],
        }
        data = self._post(payload)
        self._check_error(data)
        references = data.get("references")
        if not isinstance(references, list):
            raise ToolError(f"百度搜索响应缺少 references 字段: {data}")
        return {"request_id": data.get("request_id", ""), "references": references}


def _format_reference(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    title = item.get("title") or ""
    url = item.get("url") or ""
    # 摘要优先 snippet，其次 content，最后为空
    snippet = (
        item.get("snippet")
        or item.get("content")
        or ""
    )
    website = item.get("website") or ""
    parts = []
    if title:
        parts.append(f"标题：{title}")
    if website:
        parts.append(f"来源：{website}")
    if url:
        parts.append(f"链接：{url}")
    if snippet:
        parts.append(f"摘要：{snippet.strip()}")
    return "\n".join(parts)


def _search_and_format(
    client: SearchClient, query: str, top_k: int = DEFAULT_RESULTS
) -> str:
    result = client.search(query, top_k=top_k)
    refs = result["references"]
    if not refs:
        return f"未搜索到与“{query}”相关的网页结果"

    lines = [f"搜索“{query}”共返回 {len(refs)} 条结果："]
    for i, item in enumerate(refs, start=1):
        lines.append(f"\n[{i}]\n{_format_reference(item)}")
    return "\n".join(lines)


def build_search_tool(
    api_key: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 30.0,
) -> ToolSpec:
    """构造 searchWeb 工具声明。

    若未提供 api_key，返回的工具在执行时会对 LLM 返回清晰错误信息，
    不影响 Agent 正常启动与其它工具使用。
    """
    client = None
    if api_key and api_key.strip():
        try:
            client = SearchClient(api_key, endpoint=endpoint, timeout=timeout)
        except ValueError:
            client = None

    def handler(query: str, top_k: int = DEFAULT_RESULTS) -> str:  # noqa: ANN001
        if client is None:
            return (
                "百度搜索未启用：缺少配置 [search] 段中的 api_key。"
                "请检查 config.ini 是否正确配置后重试。"
            )
        try:
            return _search_and_format(client, query, top_k=top_k)
        except ToolError as exc:
            return f"搜索失败: {exc}"

    return ToolSpec(
        name="searchWeb",
        description=(
            "搜索互联网获取最新信息。向百度搜索引擎发起检索，返回搜索结果摘要、"
            "来源标题与链接。当问题涉及实时新闻、最新动态或需要网络资料时使用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或问题，例如“今日百度搜索最新资讯”。",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的搜索结果条数，1~50，默认 10。",
                },
            },
            "required": ["query"],
        },
        handler=handler,
    )
