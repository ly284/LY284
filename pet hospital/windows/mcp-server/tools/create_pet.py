TOOL_DEFINITION = {
    "name": "pet-hospital-create-pet",
    "description": "新增一条宠物档案，id 自动生成，无需填写",
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "宠物姓名"},
            "species": {"type": "string", "description": "种类（如 犬、猫、兔）"},
            "breed": {"type": "string", "description": "品种（如 金毛、布偶）"},
            "gender": {"type": "string", "enum": ["公", "母", "未知"], "description": "性别"},
            "ageMonths": {"type": "integer", "minimum": 0, "description": "月龄"},
            "color": {"type": "string", "description": "毛色"},
            "chipNumber": {"type": "string", "description": "芯片号"},
            "ownerName": {"type": "string", "description": "主人姓名"},
            "ownerPhone": {"type": "string", "description": "主人电话"},
            "ownerAddress": {"type": "string", "description": "主人住址"},
            "doctor": {"type": "string", "description": "主治医生"},
            "disease": {"type": "string", "description": "疾病"},
            "status": {"type": "string", "description": "就诊状态（如 待就诊、就诊中、已康复）"},
            "allergyHistory": {"type": "string", "description": "过敏史"},
            "notes": {"type": "string", "description": "备注"},
            "hasChip": {"type": "boolean", "description": "是否植入芯片"},
        },
        "required": ["name", "species", "ownerName", "ownerPhone"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "新生成的宠物档案ID"},
            "name": {"type": "string"},
            "species": {"type": "string"},
        },
    },
}


async def handle_create_pet(arguments: dict) -> dict:
    from client import create_pet
    try:
        data = await create_pet(arguments)
        if isinstance(data, dict) and data.get("code") in (200, 201):
            created = data.get("data", {})
            return {
                "resultType": "complete",
                "content": [
                    {
                        "type": "text",
                        "text": f"新增成功，档案ID：{created.get('id', '未知')}",
                    }
                ],
                "structuredContent": created,
                "isError": False,
            }
        else:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": f"API 返回异常: {data}"}],
                "isError": True,
            }
    except Exception as e:
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": f"调用 REST API 失败: {str(e)}"}],
            "isError": True,
        }
