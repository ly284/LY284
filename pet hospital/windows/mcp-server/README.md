# 宠物医院 MCP Server

基于 **MCP 2026-07-28 协议**自行实现的 MCP Server（不依赖 mcp 库）。
使用 aiohttp 作为 HTTP 服务器（Streamable HTTP，POST `/mcp` 端点），
httpx 作为上游 REST API 客户端（带 30s 超时与连接错误自动重试）。

## 提供的 MCP 工具

| 工具名 | 说明 |
|---|---|
| `pet-hospital-list-pets` | 按关键词、种类、医生、状态、花费区间筛选宠物档案，支持排序与分页 |
| `pet-hospital-create-pet` | 新增宠物档案（name/species/ownerName/ownerPhone 必填） |
| `pet-hospital-set-pet-food` | 设置宠物喜欢的食物（写入本地 `data/pet_food.json`） |
| `pet-hospital-get-pet-food` | 查询宠物喜欢的食物 |

## 运行方式

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 确保 `pethospital.exe`（REST API + 网页）已在本机运行，
   默认上游地址 `http://127.0.0.1:8081`，可用环境变量 `PET_HOSPITAL_API_URL` 覆盖；
   MCP Server 自身监听地址与端口用 `MCP_HOST` / `MCP_PORT` 覆盖（默认 `127.0.0.1:8080`）。
3. 启动：

   ```bash
   python main.py
   ```

## 健康检查与调用示例

健康检查：`GET http://127.0.0.1:8080/health`

工具枚举（tools/list）：

```bash
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}'
```

调用工具（tools/call）：

```bash
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"pet-hospital-list-pets","arguments":{"species":"犬","page":1,"pageSize":5}},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}'
```

initialize 握手：

```bash
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2026-07-28","capabilities":{},"clientInfo":{"name":"demo","version":"0.1"}}}'
```

## 错误语义

- 参数校验失败 / 未知方法 / 未知工具：JSON-RPC `-32602` 错误 + 可读信息
- 上游 REST 失败（连接拒绝、超时、非 200）：工具结果以 `isError: true` 的
  结构化文本返回（含失败原因），不会透传上游 HTML 错误页
- 上游连接类错误自动重试 2 次（0.5s/1s 退避），4xx/5xx 不重试
