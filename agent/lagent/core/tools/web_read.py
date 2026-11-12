"""网页读取工具：抓取静态网页并转成纯文本交给模型。

只依赖标准库：urllib 抓取（带 UA、超时、大小上限），正则做轻量
HTML → 文本转换（去 script/style、去标签、折叠空白）。不做 JS 渲染，
动态页面请改用搜索工具或其它手段。
"""

from __future__ import annotations

import html as html_module
import re
import urllib.error
import urllib.request

from .base import ToolError, ToolSpec

__all__ = ["build_read_webpage_tool"]

DEFAULT_TIMEOUT = 20.0
MAX_BYTES = 2_000_000        # 响应体大小上限（防大文件拖垮内存）
MAX_OUTPUT_CHARS = 6_000     # 交给模型的文本上限
_HEAD_CHARS = 4_000
_TAIL_CHARS = 1_500

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) lagent-readwebpage/1.0"
)

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|svg|head)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(
    r"</(p|div|section|article|li|tr|h[1-6]|br|table|ul|ol|blockquote|pre)>|<br\s*/?>",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def _html_to_text(raw: str) -> str:
    """轻量 HTML → 纯文本：去头/脚本/样式/注释/标签，保留块级换行。"""
    text = _SCRIPT_STYLE_RE.sub(" ", raw)
    text = _COMMENT_RE.sub(" ", text)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html_module.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return (
        f"{text[:_HEAD_CHARS]}\n\n...[内容过长，已截断，中间省略 "
        f"{len(text) - _HEAD_CHARS - _TAIL_CHARS} 字符]...\n\n{text[-_TAIL_CHARS:]}"
    )


def read_webpage(url: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    url = (url or "").strip()
    if not url:
        raise ToolError("缺少 url 参数：要读取的网页地址（http/https）")
    lowered = url.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise ToolError(f"仅支持 http/https 地址: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "html" not in content_type and "text" not in content_type and "xml" not in content_type:
                raise ToolError(f"不是文本类网页（Content-Type: {content_type}），已拒绝读取")
            body = resp.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ToolError(f"响应超过 {MAX_BYTES} 字节上限，已中止")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
            try:
                raw = body.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                raw = body.decode("utf-8", errors="replace")
            final_url = resp.geturl()
    except urllib.error.HTTPError as exc:
        raise ToolError(f"网页返回 HTTP {exc.code}: {exc.reason}（{url}）") from exc
    except urllib.error.URLError as exc:
        raise ToolError(f"无法访问网页: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ToolError(f"读取网页超时（{DEFAULT_TIMEOUT}s）") from exc

    text = _html_to_text(raw)
    if not text:
        raise ToolError(f"网页无可见文本内容（可能是纯脚本渲染的动态页面）: {url}")

    limit = max(200, min(int(max_chars or MAX_OUTPUT_CHARS), MAX_OUTPUT_CHARS))
    clipped = text[:limit]
    note = "" if len(text) <= limit else f"\n\n[网页全文约 {len(text)} 字符，已按 max_chars={limit} 截断]"
    return f"网页 {final_url} 内容如下:\n{_truncate(clipped)}{note}"


def build_read_webpage_tool() -> ToolSpec:
    return ToolSpec(
        name="readwebpage",
        description=(
            "读取一个静态网页并返回其可见文本内容（自动去掉脚本/样式/标签）。"
            "当需要查看某条搜索结果的正文、文档页、博客文章时使用。"
            "仅支持 http/https 地址；不做 JavaScript 渲染，动态页面可能拿不到内容。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要读取的网页地址，例如 https://example.com/article",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "最多返回的文本字符数（200~6000，默认 6000）",
                },
            },
            "required": ["url"],
        },
        handler=read_webpage,
    )
