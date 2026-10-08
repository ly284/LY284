import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer

from config import config
from anythingllm import AnythingLLMClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = MCPServer(name="AnythingLLM Server")

client = AnythingLLMClient(
    base_url=config.anythingllm_base_url,
    api_key=config.anythingllm_api_key
)

@server.tool()
async def query_workspace(message: str, mode: str = "query") -> dict:
    """
    从AnythingLLM工作区提取信息进行AI回答
    
    Args:
        message: 用户的问题
        mode: 查询模式 - "query" (仅基于文档回答) 或 "chat" (通用回答)
    
    Returns:
        AI的回答和来源信息
    """
    workspace_slug = config.anythingllm_default_workspace
    if not workspace_slug:
        workspaces = await client.list_workspaces()
        if not workspaces:
            return {"error": "No workspaces available"}
        workspace_slug = workspaces[0].get("slug", workspaces[0].get("name", ""))

    result = await client.chat(workspace_slug, message, mode)
    return result

@server.tool()
async def list_workspaces() -> str:
    """获取所有可用工作区列表"""
    workspaces = await client.list_workspaces()
    return str(workspaces)

if __name__ == "__main__":
    try:
        logger.info(f"Starting AnythingLLM MCP Server on {config.mcp_server_host}:{config.mcp_server_port}")
        server.run(transport="streamable-http", host=config.mcp_server_host, port=config.mcp_server_port)
    except KeyboardInterrupt:
        logger.info("Server stopped")
    finally:
        import asyncio
        asyncio.run(client.close())