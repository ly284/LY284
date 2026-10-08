import os

API_BASE_URL = os.environ.get("PET_HOSPITAL_API_URL", "http://127.0.0.1:8081")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))
MCP_PATH = "/mcp"
PROTOCOL_VERSION = "2026-07-28"
SERVER_NAME = "pet-hospital-mcp"
SERVER_VERSION = "1.0.0"
SERVER_DESCRIPTION = "宠物医院数据 MCP 服务，提供宠物档案查询与管理"
TOOLS_LIST_TTL_MS = 60000
TOOLS_LIST_CACHE_SCOPE = "public"
