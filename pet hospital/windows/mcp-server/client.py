import asyncio
import logging

import httpx

from config import API_BASE_URL

logger = logging.getLogger("pet-hospital-mcp.client")

MAX_RETRIES = 2          # 网络类错误最多重试次数（不含首次请求）
RETRY_BACKOFF_SECONDS = 0.5


async def _request_with_retry(method: str, path: str, **kwargs) -> dict:
    """带超时与简单重试的 REST 请求：仅对连接类错误重试，HTTP 4xx/5xx 不重试。"""
    last_exc: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.TransportError as exc:
            # 连接失败/超时等网络类错误：退避后重试
            last_exc = exc
            if attempt < MAX_RETRIES:
                logger.warning(
                    "REST %s %s 第 %d 次失败（%s），即将重试",
                    method, path, attempt + 1, type(exc).__name__,
                )
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
        except httpx.HTTPStatusError:
            # 上游明确返回错误状态：不重试，直接抛给工具层转结构化错误
            raise
    assert last_exc is not None
    raise last_exc


async def get_pets(**params) -> dict:
    return await _request_with_retry("GET", "/api/v1/pets", params=params)


async def create_pet(pet_data: dict) -> dict:
    return await _request_with_retry("POST", "/api/v1/pets", json=pet_data)
