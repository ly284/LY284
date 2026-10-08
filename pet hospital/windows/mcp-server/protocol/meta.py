META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_SUBSCRIPTION_ID = "io.modelcontextprotocol/subscriptionId"

SERVER_INFO = {
    "name": "pet-hospital-mcp",
    "version": "1.0.0",
    "description": "宠物医院数据 MCP 服务，提供宠物档案查询与管理",
}

REQUIRED_META_FIELDS = [META_PROTOCOL_VERSION, META_CLIENT_CAPABILITIES]
SUPPORTED_PROTOCOL_VERSIONS = {"2026-07-28"}
