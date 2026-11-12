# LY284

基于本地 **LM Studio** 大模型的对话与工具调用实验项目，全部服务运行在本机，不依赖任何云端模型 API。

项目由四个子模块组成：

| 模块 | 说明 | 技术栈 |
|------|------|--------|
| `agent` | 完整的定制 Agent（`lagent`）：工具调用主循环、技能系统、MCP 客户端、AGENTS.md 指引、上下文压缩与 TUI；另含两个流式对话练习 `practice01/02` | Python / openai / mcp / textual |
| `anything llm` | AnythingLLM 的 MCP Server，把本地知识库工作区封装为 MCP 工具供 Agent 调用 | Python 3.10+ / MCP SDK v2 / httpx |
| `pet hospital` | 宠物医院管理系统（Go 单文件可执行 + 内嵌网页 + REST API，课程发行包），并附带将其数据暴露为 MCP 服务的 Python 服务 | Go 标准库 / Python aiohttp |
| `anythingllm-web` | 极简的 AnythingLLM 文档上传页面（单 HTML 文件，密钥由用户在页面填写） | 原生 HTML / JS |

> 仓库中的 `officecli/` 是本地 Office 命令行工具发行包（供 `agent/lagent` 的 officecli 技能使用）；
> `work space/` 是 Agent 工作区里的第三方技能包存档，非本项目代码。

## 目录结构

```text
LY284/
├── README.md
│
├── agent/                            # 定制 Agent 与对话练习
│   ├── lagent/                       # 完整 Agent（详见 agent/lagent/README.md）
│   │   ├── main.py                   # 入口：组装 core 并启动 TUI
│   │   ├── core/
│   │   │   ├── agent/engine.py       # 主循环：提问 → 工具调用 → 继续回答
│   │   │   ├── llm/client.py         # OpenAI 兼容流式客户端
│   │   │   ├── tools/                # 内置工具（文件/时间/搜索/网页/CLI/技能）
│   │   │   ├── mcp/                  # MCP 客户端（stdio + Streamable HTTP）
│   │   │   ├── skills/               # 技能发现与按需加载
│   │   │   └── session_store.py      # 会话持久化
│   │   ├── tui/                      # Textual 终端界面
│   │   ├── .mcp.json.example         # MCP 服务器配置模板
│   │   └── README.md                 # lagent 使用文档
│   ├── practice01/                   # 流式对话练习（含工具调用）
│   │   ├── mian.py                   # 入口（config.ini.example 提供配置模板）
│   │   └── config.ini.example
│   └── practice02/                   # 同上（第二份练习）
│
├── anything llm/                     # AnythingLLM MCP Server
│   ├── src/
│   │   ├── server.py                 # MCP Server 入口（Streamable HTTP）
│   │   ├── anythingllm.py            # AnythingLLM REST API 客户端
│   │   └── config.py                 # pydantic-settings 配置（密钥仅从 .env 注入）
│   ├── .env.example                  # 环境变量示例（不含真实密钥）
│   ├── pyproject.toml                # 依赖声明
│   └── mvp_plan.md                   # MVP 设计文档
│
├── anythingllm-web/
│   └── upload.html                   # 文档上传页面（密钥运行时输入）
│
└── pet hospital/                     # 宠物医院项目
    └── windows/
        ├── pethospital.exe           # Go 主程序（网页 + REST API 已内嵌）
        ├── data/
        │   ├── pet.db                # 单文件数据库
        │   └── pet_food.json
        ├── mcp-server/               # 宠物医院 MCP Server（Python，自实现协议）
        │   ├── main.py               # 入口：aiohttp 监听 /mcp
        │   ├── client.py             # REST API 调用封装（超时+重试）
        │   ├── protocol/             # MCP 协议层（initialize / meta / router）
        │   ├── tools/                # list_pets / create_pet / set_food / get_food
        │   └── README.md             # 本模块文档
        ├── README.md                 # REST API 完整文档
        ├── README-Windows.md         # Windows 使用说明
        └── LICENSE
```

## 环境准备

- **LM Studio**：启动本地模型服务，默认地址 `http://localhost:1234/v1`（对话练习无需真实 API Key，lagent 走云端兼容服务时需要）
- **Python** 3.10+；lagent 的 MCP 客户端依赖 `mcp>=2.0.0`
- **Go** 1.21+（仅在需要从源码重新编译 `pethospital.exe` 时）
- **AnythingLLM**（可选）：本地实例，默认地址 `http://localhost:3001`

## 运行说明

### 1. agent/lagent — 定制 Agent

```bash
cd agent/lagent
pip install -r requirements.txt
python main.py        # 首次运行自动生成 config.ini 模板，填写后重启
```

配置、技能、MCP 接入、AGENTS.md 指引等完整说明见 **`agent/lagent/README.md`**。

### 2. agent/practice01 / practice02 — 流式对话练习

```bash
cd agent/practice01
copy config.ini.example config.ini   # 填写 base_url / model / api_key
python mian.py
```

### 3. anything llm — AnythingLLM MCP Server

```bash
cd "anything llm"

# 安装依赖
pip install -e .

# 配置环境变量（真实密钥不入库）
copy .env.example .env    # Windows；Linux/macOS 用 cp
# 编辑 .env，填写 ANYTHINGLLM_API_KEY（及可选的默认工作区）

# 启动（Streamable HTTP，默认 0.0.0.0:8000，端点 /mcp）
python src/server.py
```

提供的 MCP 工具：

- `query_workspace(message, mode)` — 向工作区提问，`mode` 为 `query`（仅基于文档）或 `chat`（通用对话）
- `list_workspaces()` — 列出所有可用工作区
- `upload_document(file_path, workspace_slug)` — 上传本地文档到 AnythingLLM 并可加入工作区
- `embed_document(document_id)` — 触发文档向量化，使其可用于检索问答

调用示例（tools/list）：

```bash
curl -X POST http://127.0.0.1:8000/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

失败场景：缺少 `ANYTHINGLLM_API_KEY` 时启动即报错提示配置方法；上游不可达时工具返回错误信息，不会静默。

### 4. pet hospital — 宠物医院 REST API + MCP Server

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

MCP 工具（4 个）：

- `pet-hospital-list-pets` — 按关键词、种类、医生、状态、花费区间筛选宠物档案，支持排序与分页
- `pet-hospital-create-pet` — 新增宠物档案（name/species/ownerName/ownerPhone 必填）
- `pet-hospital-set-pet-food` / `pet-hospital-get-pet-food` — 设置/查询宠物喜欢的食物

调用示例与 initialize 握手示例见 **`pet hospital/windows/mcp-server/README.md`**。

### 5. anythingllm-web — 文档上传页面

先启动本地 AnythingLLM（`http://localhost:3001`），浏览器打开 `anythingllm-web/upload.html`，
在页面中填写 **API Key**（仅保存在浏览器 sessionStorage，不写入代码与文件）、
确认服务地址与工作区 ID 后选择文件上传即可。

## 典型使用流程

```text
LM Studio (localhost:1234)
    ├── agent/practice01          → 直接对话（流式）
    ├── agent/lagent              → 工具调用 Agent（技能 + MCP + 上下文压缩）
    ├── pet hospital              → REST API 数据 + MCP 工具 → Agent 查询宠物档案
    └── AnythingLLM (localhost:3001)
            ├── anything llm      → MCP 工具 → Agent 基于知识库问答
            └── anythingllm-web   → 浏览器上传文档并加入工作区
```

## 说明

- 所有数据与模型均保存在本地，仅供学习、演示与开发调试使用。
- **密钥安全**：真实 API Key 只通过 `.env` / `config.ini` / `.mcp.json` 注入（三者均已被 .gitignore 忽略），仓库内只保留 `*.example` 模板。若历史提交中曾泄露过密钥，请立即吊销更换。
- 各子模块的详细文档见对应目录：`agent/lagent/README.md`、`anything llm/mvp_plan.md`、`pet hospital/windows/README.md`、`pet hospital/windows/mcp-server/README.md`。
