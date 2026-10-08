# Pet Hospital MCP Server 开发提示词

> 加载本文件后，按以下规范开发 Pet Hospital MCP Server。

---

## 一、项目概览

**项目**：宠物医院 · Pet Hospital REST API（`pethospital.exe`）

**MCP 目标**：将 REST API 数据通过 MCP 2026-07-28 协议暴露，供其他 Agent 的 MCP Client 消费。

**数据来源**：`pethospital.exe` 暴露的本地 HTTP 服务（默认 `127.0.0.1:8080`），数据库为 `data/pet.db`。

**开发语言**：Python 3.10+

**当前阶段**：MVP — 仅实现 `pet-hospital-list-pets` 工具

---

## 二、MCP 协议规范（2026-07-28）

### 2.1 协议核心：Stateless

- **移除 `initialize` / `notifications/initialized` 握手**，无 `Mcp-Session-Id` 头
- **每个请求自包含**：所有信息在请求体中，通过 `_meta` 携带协议版本和客户端能力
- **必须包含的 `_meta` 字段**：
  - `io.modelcontextprotocol/protocolVersion`：`"2026-07-28"`（必填）
  - `io.modelcontextprotocol/clientCapabilities`（必填）
  - `io.modelcontextprotocol/clientInfo`（建议）
  - `io.modelcontextprotocol/logLevel`（可选）
- **响应 `_meta`**：返回 `io.modelcontextprotocol/serverInfo`

### 2.2 Streamable HTTP 传输

- 每个请求是一个 HTTP POST 到 `/mcp`
- 请求头必须包含：`Mcp-Method`、`Mcp-Name`（SEP-2243）
- 服务器通过这些头路由，无需解析 JSON body
- 负载均衡器、WAF 可基于头路由/限流

### 2.3 消息格式

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { "name": "...", "arguments": { ... } },
  "_meta": {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": { ... },
    "io.modelcontextprotocol/clientInfo": { "name": "...", "version": "..." }
  }
}

// 成功响应
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resultType": "complete",
    "content": [...],
    "_meta": { "io.modelcontextprotocol/serverInfo": { ... } }
  }
}

// 错误响应
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": { "code": -32602, "message": "..." }
}
```

### 2.4 所有结果必须包含 `resultType`

- `"complete"`：普通完整结果
- `"input_required"`：MRTR 中间结果，需客户端补充输入

### 2.5 列表结果缓存

- `tools/list`、`resources/list`、`prompts/list` 响应必须包含 `ttlMs` 和 `cacheScope`
- `cacheScope`：`"public"` 或 `"private"`

### 2.6 订阅与通知（Subscribe and Notify）

- 客户端通过 `subscriptions/listen` 订阅通知流
- 服务器推送 `notifications/tools/list_changed`、`notifications/resources/updated`
- 通知携带 `io.modelcontextprotocol/subscriptionId`

### 2.7 已弃用功能

- `roots/list`、`sampling/createMessage`、`elicitation/create` 已移入 MRTR 模式
- Tasks 移入 `io.modelcontextprotocol/tasks` 扩展

### 2.8 JSON Schema 规范

- 默认使用 JSON Schema 2020-12
- `inputSchema` 必须是有效的 JSON Schema object（不能为 null）
- 无参数工具使用 `{ "type": "object", "additionalProperties": false }`

---

## 三、MCP Server 架构设计

### 3.1 Server 信息

```json
{
  "name": "pet-hospital-mcp",
  "version": "1.0.0",
  "description": "宠物医院数据 MCP 服务，提供宠物档案查询与管理"
}
```

### 3.2 声明的能力（Capabilities）

```json
{
  "capabilities": {
    "tools": { "listChanged": true },
    "resources": { "listChanged": true, "subscribe": true },
    "prompts": { "listChanged": true }
  }
}
```

### 3.3 传输层

- **主运输**：Streamable HTTP，监听 `127.0.0.1:8080/mcp`
- 复用 `pethospital.exe` 已有 HTTP 服务通道，在 `/mcp` 路径新增 MCP 端点
- 所有 MCP 请求的 `_meta` 从 HTTP 请求头或 JSON-RPC body 中提取

---

## 四、MCP Tool 设计（仅 MVP）

### `pet-hospital-list-pets` — MVP 唯一 Tool

- **描述**：查询宠物档案列表，支持根据种类、医生、状态、疾病、主人姓名等参数进行筛选，支持排序和分页
- **inputSchema**：
  ```json
  {
    "type": "object",
    "properties": {
      "q": { "type": "string", "description": "全文检索关键词" },
      "species": { "type": "string", "description": "按种类筛选（如 犬、猫）" },
      "doctor": { "type": "string", "description": "按医生筛选" },
      "status": { "type": "string", "description": "按就诊状态筛选（如 待就诊、就诊中、已康复）" },
      "disease": { "type": "string", "description": "按疾病筛选" },
      "ownerName": { "type": "string", "description": "按主人姓名筛选" },
      "min": { "type": "number", "description": "最低总花费" },
      "max": { "type": "number", "description": "最高总花费" },
      "sortBy": { "type": "string", "description": "排序字段（如 name、totalCost、createdAt）" },
      "order": { "type": "string", "enum": ["asc", "desc"], "description": "排序方向" },
      "page": { "type": "integer", "minimum": 1, "default": 1, "description": "页码" },
      "pageSize": { "type": "integer", "minimum": 1, "maximum": 100, "default": 20, "description": "每页条数" }
    },
    "additionalProperties": false
  }
  ```
- **outputSchema**：`{ "total": integer, "page": integer, "pageSize": integer, "pets": array }`
- **REST 映射**：`GET /api/v1/pets?...`（将所有 inputSchema 参数透传为查询字符串）
- **输出格式**：REST API 返回的 JSON 数据原样返回，结构化内容（structuredContent）中包含解析后的宠物列表

---

## 五、Python 技术栈

### 5.1 依赖

```
mcp>=1.0.0          # MCP SDK（Anthropic 官方）
httpx>=0.27.0       # 异步 HTTP 客户端，调用 pethospital.exe REST API
uvicorn>=0.30.0     # ASGI 服务器（如使用 FastAPI 风格）
```

或使用更轻量的方案：
```
mcp>=1.0.0          # MCP SDK
httpx>=0.27.0       # HTTP 客户端
```

### 5.2 项目结构

```text
mcp-server/
├── main.py              # 入口：启动 MCP Server
├── config.py            # 配置（API 基地址、端口等）
├── client.py            # 封装对 pethospital.exe REST API 的调用
├── tools/
│   └── list_pets.py     # pet-hospital-list-pets 工具实现
├── protocol/
│   ├── __init__.py      # MCP 协议层：Streamable HTTP transport、/mcp 端点
│   ├── meta.py          # _meta 注入逻辑
│   └── router.py        # MCP 请求路由（method → handler）
└── requirements.txt
```

### 5.3 核心实现要点

1. **MCP SDK 集成**：使用 `mcp` 库创建 MCP Server，注册 tool、resource、prompt
2. **REST API 调用**：使用 `httpx` 异步调用 `pethospital.exe` 的 REST 接口
3. **Streamable HTTP**：实现 `/mcp` 端点，处理 POST 请求，根据 `Mcp-Method` 和 `Mcp-Name` 头路由
4. **_meta 处理**：从请求头或 JSON-RPC body 提取 `io.modelcontextprotocol/*` 字段，验证协议版本
5. **错误处理**：REST API 错误转换为 `isError: true` 的 tool 执行错误；协议错误返回 JSON-RPC error `-32602`

---

## 六、开发步骤

1. **搭建项目骨架**：创建目录结构，初始化 `requirements.txt`，安装依赖
2. **实现 REST API 客户端**（`client.py`）：封装 `GET /api/v1/pets` 调用，参数透传
3. **实现 MCP 协议层**（`protocol/`）：Streamable HTTP transport，`/mcp` 端点，`_meta` 验证
4. **实现 `pet-hospital-list-pets` Tool**（`tools/list_pets.py`）：注册 tool，定义 inputSchema，调用 REST API
5. **注册 `tools/list`**：返回包含 `pet-hospital-list-pets` 的工具列表，包含 `ttlMs` 和 `cacheScope`
6. **启动 Server**：监听 Streamable HTTP 端口，处理请求
7. **测试**：用 `curl` 或 MCP Client 验证 `tools/list` 和 `tools/call`

---

## 七、错误处理规范

### 7.1 协议错误
- 未知 Tool → JSON-RPC error `-32602`
- 缺少必需 `_meta` 字段 → JSON-RPC error `-32602`
- 不支持的协议版本 → JSON-RPC error `-32602`

### 7.2 工具执行错误
- REST API 返回错误 → `resultType: "complete"`, `isError: true`
- 包含可操作的错误信息供 LLM 自纠正

### 7.3 MRTR 支持（预留）
- 需要用户输入时 → `resultType: "input_required"` + `inputRequests`

---

## 八、数据模型参考

### Pet 主档字段
- `id` (string, 如 PET-000001)
- `name`, `species`, `breed`, `gender`, `ageMonths`, `color`, `chipNumber`
- `ownerName`, `ownerPhone`, `ownerAddress`
- `doctor`, `disease`, `status`
- `allergyHistory`, `notes`, `hasChip`
- `records[]` (历史病历), `charges[]` (消费明细)
- `totalCost` (派生), `visitCount` (派生)

### REST API `GET /api/v1/pets` 查询参数
- `q` — 全文检索
- `species` — 按种类
- `doctor` — 按医生
- `status` — 按就诊状态
- `disease` — 按疾病
- `ownerName` — 按主人姓名
- `min` / `max` — 总花费区间
- `sortBy` / `order` — 排序
- `page` / `pageSize` — 分页

返回格式：
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "total": 100,
    "page": 1,
    "pageSize": 20,
    "pets": [...]
  },
  "time": "2025-01-01T00:00:00+08:00"
}
```

---

## 九、开发约束

1. **Python 3.10+**：使用 Python 开发
2. **端口复用**：MCP Server 运行在 `pethospital.exe` 的 HTTP 服务上（默认 8080），在 `/mcp` 路径处理 MCP 协议
3. **内嵌网页**：已有网页界面不受 MCP Server 影响
4. **无鉴权**：MCP Server 仅监听本机，如需安全加固请在部署层处理
5. **数据库路径**：`data/pet.db`，与主程序共享
6. **MVP 范围**：本次仅实现 `pet-hospital-list-pets` 一个 Tool，不做其他功能
7. **异步优先**：使用 `async/await` 和 `httpx` 异步调用 REST API

---

## 十、关键参考

- REST API 完整文档：`README.md`（同目录）
- Windows 运行说明：`README-Windows.md`（同目录）
- MCP 2026-07-28 规范：`https://modelcontextprotocol.io/specification/2026-07-28`
- MCP 变更日志：`https://modelcontextprotocol.io/specification/2026-07-28/changelog`
- MCP Python SDK：https://github.com/modelcontextprotocol/python-sdk
