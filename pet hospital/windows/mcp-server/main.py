import logging

from aiohttp import web

from protocol import handle_streamable_http
from config import MCP_HOST, MCP_PORT, MCP_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pet-hospital-mcp")


async def mcp_handler(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    headers = dict(request.headers)
    method = (body or {}).get("method", "?")
    logger.info("MCP 请求: method=%s", method)
    result = await handle_streamable_http(body, headers)
    if "error" in result:
        logger.warning(
            "MCP 请求出错: method=%s code=%s msg=%s",
            method,
            result["error"].get("code"),
            result["error"].get("message"),
        )
    return web.json_response(result)


async def health_handler(request):
    return web.json_response({"status": "ok", "service": "pet-hospital-mcp"})


def main():
    app = web.Application()
    app.router.add_post(MCP_PATH, mcp_handler)
    app.router.add_get("/health", health_handler)
    logger.info("MCP Server 启动: http://%s:%s%s", MCP_HOST, MCP_PORT, MCP_PATH)
    logger.info("健康检查: http://%s:%s/health", MCP_HOST, MCP_PORT)
    web.run_app(app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
