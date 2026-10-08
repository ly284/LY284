from protocol.meta import SERVER_INFO, REQUIRED_META_FIELDS, SUPPORTED_PROTOCOL_VERSIONS
from protocol.router import validate_meta, build_error_response, build_success_response, TOOL_HANDLERS, register_tool, get_tool_handler


async def handle_mcp_request(body: dict, headers: dict) -> dict:
    request_id = body.get("id", 1)
    method = body.get("method", "")
    params = body.get("params", {})
    meta = body.get("_meta", {})

    errors = validate_meta(meta)
    if errors:
        return build_error_response(request_id, -32602, "; ".join(errors))

    if method == "tools/list":
        return build_success_response(request_id, build_tools_list_result(meta))
    elif method == "tools/call":
        return await handle_tools_call(request_id, params, meta)
    else:
        return build_error_response(request_id, -32602, f"未知方法: {method}")


def build_tools_list_result(meta):
    from tools.list_pets import TOOL_DEFINITION as LIST_PETS_DEF
    from tools.create_pet import TOOL_DEFINITION as CREATE_PET_DEF
    from tools.pet_food import TOOL_DEFINITION as SET_FOOD_DEF, TOOL_GET_DEFINITION as GET_FOOD_DEF
    return {
        "resultType": "complete",
        "tools": [
            {
                "name": LIST_PETS_DEF["name"],
                "title": "宠物档案列表查询",
                "description": LIST_PETS_DEF["description"],
                "inputSchema": LIST_PETS_DEF["inputSchema"],
                "outputSchema": LIST_PETS_DEF["outputSchema"],
            },
            {
                "name": CREATE_PET_DEF["name"],
                "title": "新增宠物档案",
                "description": CREATE_PET_DEF["description"],
                "inputSchema": CREATE_PET_DEF["inputSchema"],
                "outputSchema": CREATE_PET_DEF["outputSchema"],
            },
            {
                "name": SET_FOOD_DEF["name"],
                "title": "设置宠物喜欢的食物",
                "description": SET_FOOD_DEF["description"],
                "inputSchema": SET_FOOD_DEF["inputSchema"],
                "outputSchema": SET_FOOD_DEF["outputSchema"],
            },
            {
                "name": GET_FOOD_DEF["name"],
                "title": "查询宠物喜欢的食物",
                "description": GET_FOOD_DEF["description"],
                "inputSchema": GET_FOOD_DEF["inputSchema"],
                "outputSchema": GET_FOOD_DEF["outputSchema"],
            },
        ],
        "_meta": {
            "io.modelcontextprotocol/serverInfo": SERVER_INFO,
        },
        "ttlMs": 60000,
        "cacheScope": "public",
    }


async def handle_tools_call(request_id, params, meta):
    from tools.list_pets import handle_list_pets
    from tools.create_pet import handle_create_pet
    from tools.pet_food import handle_set_pet_food, handle_get_pet_food
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    handlers = {
        "pet-hospital-list-pets": handle_list_pets,
        "pet-hospital-create-pet": handle_create_pet,
        "pet-hospital-set-pet-food": handle_set_pet_food,
        "pet-hospital-get-pet-food": handle_get_pet_food,
    }

    handler = handlers.get(tool_name)
    if handler:
        result = await handler(arguments)
        return build_success_response(request_id, result)
    else:
        return build_error_response(request_id, -32602, f"未知工具: {tool_name}")


async def handle_streamable_http(body: dict, headers: dict) -> dict:
    return await handle_mcp_request(body, headers)
