MCP 2026-07-28 协议实现，不依赖 mcp 库。
使用 aiohttp 作为 HTTP 服务器，httpx 作为 REST API 客户端。

运行方式：
1. 确保 pethospital.exe 在 8080 端口运行（或设置 PET_HOSPITAL_API_URL 环境变量）
2. python main.py
3. 访问 http://127.0.0.1:8081/mcp 发送 MCP 请求
