import httpx
from config import API_BASE_URL


async def get_pets(**params) -> dict:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        response = await client.get("/api/v1/pets", params=params)
        response.raise_for_status()
        return response.json()


async def create_pet(pet_data: dict) -> dict:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        response = await client.post("/api/v1/pets", json=pet_data)
        response.raise_for_status()
        return response.json()
