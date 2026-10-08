TOOL_DEFINITION = {
    "name": "pet-hospital-set-pet-food",
    "description": "设置或更新宠物喜欢吃什么",
    "inputSchema": {
        "type": "object",
        "properties": {
            "petId": {"type": "string", "description": "宠物档案ID（如 PET-000001）"},
            "foods": {
                "type": "array",
                "items": {"type": "string"},
                "description": "喜欢的食物列表（如 [\"鸡胸肉\", \"三文鱼\"]）",
            },
        },
        "required": ["petId", "foods"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "petId": {"type": "string"},
            "foods": {"type": "array", "items": {"type": "string"}},
            "createdAt": {"type": "string"},
            "updatedAt": {"type": "string"},
        },
    },
}

TOOL_GET_DEFINITION = {
    "name": "pet-hospital-get-pet-food",
    "description": "查询宠物喜欢吃什么",
    "inputSchema": {
        "type": "object",
        "properties": {
            "petId": {"type": "string", "description": "宠物档案ID（如 PET-000001）"},
        },
        "required": ["petId"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "petId": {"type": "string"},
            "foods": {"type": "array", "items": {"type": "string"}},
            "createdAt": {"type": "string"},
            "updatedAt": {"type": "string"},
        },
    },
}


async def handle_set_pet_food(arguments: dict) -> dict:
    from storage import set_food
    try:
        pet_id = arguments.get("petId", "")
        foods = arguments.get("foods", [])
        if not pet_id or not foods:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": "petId 和 foods 不能为空"}],
                "isError": True,
            }
        entry = set_food(pet_id, foods)
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": f"已设置宠物 {pet_id} 喜欢吃：{', '.join(foods)}"}],
            "structuredContent": entry,
            "isError": False,
        }
    except Exception as e:
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": f"保存失败: {str(e)}"}],
            "isError": True,
        }


async def handle_get_pet_food(arguments: dict) -> dict:
    from storage import get_food
    try:
        pet_id = arguments.get("petId", "")
        if not pet_id:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": "petId 不能为空"}],
                "isError": True,
            }
        entry = get_food(pet_id)
        if entry:
            foods = entry.get("foods", [])
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": f"宠物 {pet_id} 喜欢吃：{', '.join(foods)}"}],
                "structuredContent": entry,
                "isError": False,
            }
        else:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": f"未找到宠物 {pet_id} 的食物记录"}],
                "isError": True,
            }
    except Exception as e:
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": f"查询失败: {str(e)}"}],
            "isError": True,
        }
