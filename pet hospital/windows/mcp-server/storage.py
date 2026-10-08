from typing import Optional
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FOOD_FILE = os.path.join(DATA_DIR, "pet_food.json")


def _load() -> dict:
    if os.path.exists(FOOD_FILE):
        with open(FOOD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FOOD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_food(pet_id: str, foods: list) -> dict:
    data = _load()
    entry = {
        "petId": pet_id,
        "foods": foods,
        "updatedAt": datetime.now().isoformat(),
    }
    if pet_id in data:
        entry["createdAt"] = data[pet_id].get("createdAt", entry["updatedAt"])
    else:
        entry["createdAt"] = entry["updatedAt"]
    data[pet_id] = entry
    _save(data)
    return entry


def get_food(pet_id: str) -> Optional[dict]:
    data = _load()
    return data.get(pet_id)


def list_foods() -> list:
    data = _load()
    return list(data.values())
