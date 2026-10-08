from config import MCP_HOST, MCP_PORT, MCP_PATH, API_BASE_URL

TOOL_DEFINITION = {
    "name": "pet-hospital-list-pets",
    "description": "查询宠物档案列表，支持根据种类、医生、状态、疾病、主人姓名等参数进行筛选，支持排序和分页",
    "inputSchema": {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "全文检索关键词"},
            "species": {"type": "string", "description": "按种类筛选（如 犬、猫）"},
            "doctor": {"type": "string", "description": "按医生筛选"},
            "status": {"type": "string", "description": "按就诊状态筛选（如 待就诊、就诊中、已康复）"},
            "disease": {"type": "string", "description": "按疾病筛选"},
            "ownerName": {"type": "string", "description": "按主人姓名筛选"},
            "min": {"type": "number", "description": "最低总花费"},
            "max": {"type": "number", "description": "最高总花费"},
            "sortBy": {"type": "string", "description": "排序字段（如 name、totalCost、createdAt）"},
            "order": {"type": "string", "enum": ["asc", "desc"], "description": "排序方向"},
            "page": {"type": "integer", "minimum": 1, "default": 1, "description": "页码"},
            "pageSize": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20, "description": "每页条数"},
        },
        "additionalProperties": False,
    },
    "outputSchema": {"type": "object", "properties": {"total": {"type": "integer"}, "page": {"type": "integer"}, "pageSize": {"type": "integer"}, "pets": {"type": "array"}}},
}


async def handle_list_pets(arguments: dict) -> dict:
    from client import get_pets
    params = {}
    for key in ["q", "species", "doctor", "status", "disease", "ownerName", "sortBy", "order"]:
        if key in arguments and arguments[key] is not None:
            params[key] = arguments[key]
    if "min" in arguments and arguments["min"] is not None:
        params["min"] = arguments["min"]
    if "max" in arguments and arguments["max"] is not None:
        params["max"] = arguments["max"]
    if "page" in arguments and arguments["page"] is not None:
        params["page"] = arguments["page"]
    if "pageSize" in arguments and arguments["pageSize"] is not None:
        params["pageSize"] = arguments["pageSize"]

    try:
        data = await get_pets(**params)
        if isinstance(data, dict) and data.get("code") == 200:
            api_data = data.get("data", {})
            return {
                "resultType": "complete",
                "content": [
                    {
                        "type": "text",
                        "text": f"共 {api_data.get('total', 0)} 条记录",
                    }
                ],
                "structuredContent": api_data,
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
