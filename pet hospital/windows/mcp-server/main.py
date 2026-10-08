import asyncio
from aiohttp import web
from protocol import handle_streamable_http
from config import MCP_HOST, MCP_PORT, MCP_PATH


async def mcp_handler(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    headers = dict(request.headers)
    result = await handle_streamable_http(body, headers)
    return web.json_response(result)


async def health_handler(request):
    return web.json_response({"status": "ok", "service": "pet-hospital-mcp"})


def main():
    app = web.Application()
    app.router.add_post(MCP_PATH, mcp_handler)
    app.router.add_get("/health", health_handler)
    print(f"MCP Server 启动: http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}")
    print(f"健康检查: http://{MCP_HOST}:{MCP_PORT}/health")
    web.run_app(app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
