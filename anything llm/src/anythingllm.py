import httpx
import logging

logger = logging.getLogger(__name__)

class AnythingLLMClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=timeout
        )

    async def chat(self, workspace_slug: str, message: str, mode: str = "query") -> dict:
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/workspace/{workspace_slug}/chat",
                json={"message": message, "mode": mode}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"AnythingLLM API error: {e}")
            raise

    async def list_workspaces(self) -> list:
        try:
            response = await self.client.get(f"{self.base_url}/v1/workspaces")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"AnythingLLM API error: {e}")
            raise

    async def upload_document(self, file_path: str, workspace_slug: str = "") -> dict:
        """上传本地文档到 AnythingLLM（可同时加入指定工作区）。"""
        import mimetypes
        import os

        path = os.path.abspath(file_path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"文件不存在: {path}")
        filename = os.path.basename(path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        data = {"metadata": "{}"}
        if workspace_slug:
            data["addToWorkspaces"] = workspace_slug
        try:
            # multipart 上传需要独立的 client（全局 client 的 Content-Type 是 JSON）
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=120.0,
            ) as upload_client:
                with open(path, "rb") as fh:
                    response = await upload_client.post(
                        f"{self.base_url}/v1/document/upload",
                        files={"file": (filename, fh, mime)},
                        data=data,
                    )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"AnythingLLM API error: {e}")
            raise

    async def embed_document(self, document_id: str) -> dict:
        """触发文档向量化（embed），返回嵌入任务结果。"""
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/document/embed",
                json={"documentId": document_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"AnythingLLM API error: {e}")
            raise

    async def close(self):
        await self.client.aclose()