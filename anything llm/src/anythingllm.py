import httpx
import logging

logger = logging.getLogger(__name__)

class AnythingLLMClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
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

    async def close(self):
        await self.client.aclose()