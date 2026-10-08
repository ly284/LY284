from typing import Optional, List
from protocol.meta import REQUIRED_META_FIELDS, SUPPORTED_PROTOCOL_VERSIONS

TOOL_HANDLERS = {}


def validate_meta(meta: dict) -> Optional[List[str]]:
    if not meta:
        return ["缺少必需的 _meta 字段"]
    errors = []
    for field in REQUIRED_META_FIELDS:
        if field not in meta:
            errors.append(f"缺少必需字段: {field}")
    protocol_version = meta.get("io.modelcontextprotocol/protocolVersion")
    if protocol_version and protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        errors.append(f"不支持的协议版本: {protocol_version}")
    return errors if errors else None


def build_error_response(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def build_success_response(request_id, result):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def register_tool(name, handler):
    TOOL_HANDLERS[name] = handler


def get_tool_handler(name):
    return TOOL_HANDLERS.get(name)
