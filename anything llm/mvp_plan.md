# AnythingLLM MCP Server MVP 开发计划

## 1. 项目概述

开发一个MCP Server，用于访问本机安装的AnythingLLM，实现从唯一一个工作区提取信息进行AI回答的功能。

### 1.1 技术栈
- **语言**: Python 3.10+
- **MCP框架**: 官方Python SDK (mcp) + FastMCP
- **Web框架**: Uvicorn + Starlette (支持Streamable HTTP)
- **HTTP客户端**: httpx (异步HTTP请求)
- **配置管理**: pydantic-settings

### 1.2 传输协议
- 使用 **Streamable HTTP** 传输协议 (非stdio)
- 端点: `http://localhost:8000/mcp`
- 支持MCP协议版本: 2025-03-26

## 2. AnythingLLM API 分析

### 2.1 认证方式
```
Authorization: Bearer <api_key>
```

### 2.2 核心端点 (MVP所需)
| 端点 | 方法 | 描述 |
|------|------|------|
| `/v1/workspace/:slug/chat` | POST | 同步聊天 (返回完整响应) |
| `/v1/workspace/:slug/stream-chat` | POST | 流式聊天 (SSE) |
| `/v1/workspaces` | GET | 获取所有工作区列表 |

### 2.3 Chat请求格式
```json
POST /v1/workspace/:slug/chat
Content-Type: application/json
Authorization: Bearer <api_key>

{
  "message": "用户的问题",
  "mode": "chat",  // 或 "query"
  "userId": "optional-user-id"
}
```

### 2.4 Chat响应格式
```json
{
  "id": "unique-response-id",
  "type": "chat",
  "sources": [...],
  "textResponse": "AI的回答",
  "metrics": {...}
}
```

## 3. MCP Server 设计

### 3.1 MCP工具 (Tools)
```python
@server.tool()
async def query_workspace(
    message: str,
    workspace_slug: str = None,
    mode: str = "chat"
) -> str:
    """
    从AnythingLLM工作区查询信息并获取AI回答
    
    Args:
        message: 用户的问题
        workspace_slug: 工作区slug (可选，默认使用配置的工作区)
        mode: 查询模式 - "chat" (通用回答) 或 "query" (仅基于文档)
    
    Returns:
        AI的回答文本
    """
```

### 3.2 MCP资源 (Resources)
```python
@server.resource("workspaces://list")
async def list_workspaces() -> str:
    """获取所有可用工作区列表"""
```

### 3.3 MCP提示 (Prompts)
```python
@server.prompt()
def ask_workspace(workspace_slug: str, question: str) -> str:
    """生成一个用于查询工作区的提示模板"""
```

## 4. 项目结构

```
anythingllm-mcp-server/
├── src/
│   ├── __init__.py
│   ├── server.py          # MCP Server主入口
│   ├── anythingllm.py     # AnythingLLM API客户端
│   ├── config.py          # 配置管理
│   └── tools/
│       ├── __init__.py
│       └── workspace.py   # 工作区相关工具
├── tests/
│   ├── __init__.py
│   └── test_tools.py      # 单元测试
├── requirements.txt       # 依赖项
├── pyproject.toml         # 项目配置
├── README.md              # 项目说明
└── .env.example           # 环境变量示例
```

## 5. 依赖项

```txt
# requirements.txt
mcp>=1.8.0
httpx>=0.27.0
pydantic>=2.0
pydantic-settings>=2.0
uvicorn>=0.30.0
python-dotenv>=1.0
```

## 6. 配置管理

### 6.1 环境变量
```bash
# .env
ANYTHINGLLM_BASE_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=KRY1Z4H-CPD4FFP-GEVVKDQ-Y0RF4WJ
ANYTHINGLLM_DEFAULT_WORKSPACE=your-workspace-slug
MCP_SERVER_PORT=8000
MCP_SERVER_HOST=0.0.0.0
```

### 6.2 配置类
```python
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    anythingllm_base_url: str = "http://localhost:3001"
    anythingllm_api_key: str
    anythingllm_default_workspace: str = None
    mcp_server_port: int = 8000
    mcp_server_host: str = "0.0.0.0"
```

## 7. 核心实现

### 7.1 AnythingLLM客户端
```python
import httpx

class AnythingLLMClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def chat(self, workspace_slug: str, message: str, mode: str = "chat") -> dict:
        response = await self.client.post(
            f"{self.base_url}/v1/workspace/{workspace_slug}/chat",
            json={"message": message, "mode": mode}
        )
        response.raise_for_status()
        return response.json()
    
    async def list_workspaces(self) -> list:
        response = await self.client.get(f"{self.base_url}/v1/workspaces")
        response.raise_for_status()
        return response.json()
```

### 7.2 MCP Server主入口
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("AnythingLLM Server")

@mcp.tool()
async def query_workspace(message: str, workspace_slug: str = None, mode: str = "chat") -> str:
    # 实现查询逻辑
    pass

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

## 8. 测试计划

### 8.1 单元测试
- 测试AnythingLLM客户端的chat方法
- 测试MCP工具的参数验证
- 测试配置加载

### 8.2 集成测试
- 测试MCP Server启动
- 测试Streamable HTTP通信
- 测试与AnythingLLM的实际连接

### 8.3 测试命令
```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_tools.py::test_query_workspace -v
```

## 9. 启动和使用

### 9.1 安装依赖
```bash
pip install -r requirements.txt
```

### 9.2 配置环境变量
```bash
cp .env.example .env
# 编辑.env文件，填入正确的配置
```

### 9.3 启动服务器
```bash
python -m src.server
# 或
uvicorn src.server:app --host 0.0.0.0 --port 8000
```

### 9.4 测试连接
```bash
# 列出MCP工具
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 调用query_workspace工具
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"query_workspace","arguments":{"message":"什么是机器学习?"}}}'
```

## 10. 后续扩展 (MVP后)

1. 支持多个工作区切换
2. 支持文档上传和管理
3. 支持流式响应
4. 添加更多MCP资源和提示
5. 支持认证中间件
6. 添加监控和日志

## 11. 开发时间估算

| 任务 | 预计时间 |
|------|----------|
| 项目结构搭建 | 1小时 |
| AnythingLLM客户端实现 | 2小时 |
| MCP工具实现 | 2小时 |
| 配置管理 | 1小时 |
| 单元测试 | 2小时 |
| 集成测试和调试 | 2小时 |
| **总计** | **10小时** |
