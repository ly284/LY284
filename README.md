# LY284

基于本地 **LM Studio** 大模型的对话与工具调用实验项目，全部服务运行在本机，不依赖任何云端模型 API。

项目由三个子模块组成：

| 模块 | 说明 | 技术栈 |
|------|------|--------|
| `anything llm` | AnythingLLM 的 MCP Server，把本地知识库工作区封装为 MCP 工具供 Agent 调用 | Python 3.10+ / MCP SDK / httpx |
| `pet hospital` | 宠物医院管理系统（Go 单文件可执行 + 内嵌网页 + REST API），并附带将其数据暴露为 MCP 服务的 Python 服务 | Go 标准库 / Python aiohttp |
| `agent` | LM Studio OpenAI 兼容接口的对话练习：命令行流式问答 | Python / openai |
| `anythingllm-web` | 极简的 AnythingLLM 文档上传页面（单 HTML 文件） | 原生 HTML / JS |

## 目录结构

```text
LY284/
├── README.md
│
├── agent/                            # LM Studio 对话练习
│   └── practice01/
│       ├── mian.py                   # 流式对话入口
│       └── config.ini                # 模型与 base_url 配置
│
├── anything llm/                     # AnythingLLM MCP Server
│   ├── src/
│   │   ├── __init__.py
│   │   ├── server.py                 # MCP Server 入口（Streamable HTTP）
│   │   ├── anythingllm.py            # AnythingLLM REST API 客户端
│   │   └── config.py                 # pydantic-settings 配置
│   ├── .env.example                  # 环境变量示例
│   ├── pyproject.toml                # 依赖声明
│   ├── mvp_plan.md                   # MVP 设计文档
│   └── opencode.json
│
├── anythingllm-web/
│   └── upload.html                   # 文档上传页面
│
└── pet hospital/                     # 宠物医院项目
    └── windows/
        ├── pethospital.exe           # Go 主程序（网页 + REST API 已内嵌）
        ├── data/
        │   ├── pet.db                # 单文件数据库
        │   └── pet_food.json
        ├── mcp-server/               # 宠物医院 MCP Server（Python）
        │   ├── main.py               # 入口：aiohttp 监听 /mcp
        │   ├── config.py             # 端口、协议版本等配置
        │   ├── client.py             # REST API 调用封装
        │   ├── storage.py
        │   ├── protocol/             # MCP 协议层（meta / router）
        │   ├── tools/                # list_pets / create_pet / pet_food
        │   └── requirements.txt
        ├── README.md                 # REST API 完整文档
        ├── README-Windows.md         # Windows 使用说明
        ├── AGENTS.md                 # Agent 开发上下文
        ├── MCP_DEV_PROMPTS.md
        └── LICENSE
```

## 环境准备

- **LM Studio**：启动本地模型服务，默认地址 `http://localhost:1234/v1`（本项目无需真实 API Key）
- **Python** 3.10+
- **Go** 1.21+（仅在需要从源码重新编译 `pethospital.exe` 时）
- **AnythingLLM**（可选）：本地实例，默认地址 `http://localhost:3001`

## 运行说明

### 1. agent — LM Studio 流式对话

```bash
cd agent/practice01
python mian.py
```

按提示输入问题即可流式输出回答。模型与地址可在 `config.ini` 中调整：

```ini
[llm]
base_url = http://127.0.0.1:1234
model    = deepseek-r1-distill-qwen-1.5b
```

### 2. anything llm — AnythingLLM MCP Server

```bash
cd "anything llm"

# 安装依赖
pip install -e .          # 或 pip install -r requirements.txt / 按 pyproject.toml 安装

# 配置环境变量
copy .env.example .env    # Windows；Linux/macOS 用 cp
# 编辑 .env，填写 ANYTHINGLLM_BASE_URL / API_KEY / 默认工作区

# 启动（Streamable HTTP，默认 0.0.0.0:8000，端点 /mcp）
python src/server.py
```

提供的 MCP 工具：

- `query_workspace(message, mode)` — 向工作区提问，`mode` 为 `query`（仅基于文档）或 `chat`（通用对话）
- `list_workspaces()` — 列出所有可用工作区

### 3. pet hospital — 宠物医院 REST API + MCP Server

**启动主程序**（网页与 REST API 同端口，默认 `127.0.0.1:8080`）：

```bash
cd "pet hospital/windows"
pethospital.exe                      # 或双击运行
# 浏览器访问 http://127.0.0.1:8080/
```

**启动 MCP Server**（独立进程，依赖 `pethospital.exe` 先运行）：

```bash
cd "pet hospital/windows/mcp-server"
pip install -r requirements.txt
python main.py
# MCP 端点：http://127.0.0.1:<MCP_PORT>/mcp
# 健康检查：http://127.0.0.1:<MCP_PORT>/health
```

可通过环境变量覆盖默认值：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PET_HOSPITAL_API_URL` | REST API 基地址 | `http://127.0.0.1:8081` |
| `MCP_HOST` / `MCP_PORT` | MCP Server 监听地址与端口 | `127.0.0.1` / `8080` |

> 若主程序已占用 8080，请用 `set MCP_PORT=8081` 指定其他端口，并保证 `PET_HOSPITAL_API_URL` 指向主程序实际端口。

MCP 工具（MVP）：`pet-hospital-list-pets` —— 按关键词、种类、医生、状态、花费区间筛选宠物档案，支持排序与分页。

### 4. anythingllm-web — 文档上传页面

先启动本地 AnythingLLM（`http://localhost:3001`），浏览器直接打开 `anythingllm-web/upload.html` 选择文件上传即可。

## 典型使用流程

```text
LM Studio (localhost:1234)
    ├── agent/practice01          → 直接对话（流式）
    ├── pet hospital              → REST API 数据 + MCP 工具 → Agent 查询宠物档案
    └── AnythingLLM (localhost:3001)
            └── anything llm      → MCP 工具 → Agent 基于知识库问答
```

## 说明

- 所有数据与模型均保存在本地，仅供学习、演示与开发调试使用。
- 各子模块的详细文档见对应目录：`pet hospital/windows/README.md`、`anything llm/mvp_plan.md`。
