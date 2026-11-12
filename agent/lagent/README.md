# lagent — 带工具调用能力的终端 Agent

基于 **LM Studio / 任意 OpenAI 兼容接口**的本地终端 Agent：
流式对话 + Function Calling 工具循环 + 技能（Skills）动态加载 +
外部 MCP 服务器接入 + AGENTS.md 项目指引注入 + 上下文压缩。

## 架构分层

```text
lagent/
├── main.py                  # 入口：解析命令行 → 组装 core → 启动 TUI
├── core/                    # 与界面无关的业务核心
│   ├── config.py            # config.ini 配置加载（支持环境变量/命令行覆盖）
│   ├── events.py            # core → 界面的事件契约
│   ├── llm/client.py        # OpenAI 兼容流式客户端（多 provider 可切换）
│   ├── tools/               # 模型可调用的本地工具（见下表）
│   ├── mcp/                 # MCP 客户端：stdio / Streamable HTTP 双传输
│   ├── skills/              # 技能发现与按需加载
│   ├── session.py           # 会话消息历史与失败回滚
│   ├── session_store.py     # 会话持久化（.agents/sessions/*.jsonl）
│   ├── context.py           # Token 估算 / 历史归档 / 上下文压缩
│   └── agent/engine.py      # 主循环：提问 → 流式回答 → 工具调用 → 继续回答
└── tui/                     # Textual 终端界面（流式渲染 / 侧边栏 / 斜杠命令）
```

## 内置工具一览

| 工具 | 能力 |
|---|---|
| `getdate` / `isleapyear` | 取本机日期时间（系统命令）、判断闰年 |
| `getcwd` / `list_dir` / `get_file_type` | 工作目录、列目录、路径类型 |
| `read_text_file` / `create_file` / `edit_file` | 读写编辑纯文本文件（二进制拒绝、可覆盖控制） |
| `create_directory` / `remove_directory` / `delete_file` / `rename_path` | 目录/文件增删改名（删除目录需 `confirm=true`，受保护目录拒删） |
| `searchWeb` | 百度千帆 AI 搜索（需在 `[search]` 配 api_key，未配置时优雅提示） |
| `readwebpage` | 抓取静态网页正文（去脚本/样式，超时与大小上限） |
| `RunCLI` | 运行本地命令行程序（参数列表执行、输出截断、可中断） |
| `createskill` / `loadSkill` | 技能创建与按需加载 |
| `recallContext` | 检索压缩前归档的历史上下文 |
| `beatra_*` | 已安装 beatra 技能的媒体生成能力（可选） |
| MCP 工具 | `.mcp.json` 中配置的外部服务器工具，以 `服务器名:工具名` 暴露 |

## 快速开始

```bash
cd agent/lagent
pip install -r requirements.txt
python main.py            # 首次运行会自动生成 config.ini 模板，填好后重启
```

`config.ini` 关键配置（完整模板见 `core/config.py` 中的 `DEFAULT_CONFIG_TEMPLATE`）：

```ini
[llm]
base_url = http://127.0.0.1:1234/v1   ; LM Studio 或任意 OpenAI 兼容服务
model = your-model
api_key = your-api-key                ; 也可用环境变量 LAGENT_API_KEY

[search]
api_key =                              ; 百度千帆 AI 搜索（可留空）

[agent]
max_rounds = 5                         ; 每轮模型-工具循环上限
compress_threshold = 0.6               ; 上下文占用阈值（触发 /compact 提示）
agents_file =                          ; 工作指引文件名（默认兼容 AGENTS.md / AGENT.md）
```

密钥也可通过环境变量提供：`LAGENT_API_KEY` / `LAGENT_BASE_URL` / `LAGENT_MODEL`，
命令行参数 `--api-key` / `--base-url` / `--model` 优先级最高。

## 项目工作指引（AGENTS.md / AGENT.md）

在**启动目录**放置 `AGENTS.md`（或 `AGENT.md`，或在配置里指定 `agents_file`），
Agent 首次加载时会把它作为一条消息注入对话历史，作为长期项目规则：

- 只注入一次，会话保存/恢复时会自动剔除并重新注入，保持行为一致；
- 内容超过 8000 字符会截断并标注；
- 文件不存在不影响启动。

## 技能系统（Agent Skills）

技能是放在 `.agents/skills/<name>/SKILL.md`（或 `skills/` 目录）的说明文件，
开头用 YAML Frontmatter 声明 `name` 与 `description`：

```markdown
---
name: my-skill
description: 这个技能做什么、什么时候用
---
（正文：操作步骤、注意事项…）
```

- **发现与注入**：启动时扫描技能目录，只把名称与描述注入系统提示（渐进加载）；
- **按需加载**：模型通过 `loadSkill` 读取全文，附件文件限定在技能目录内，超长自动截断；
- **创建**：模型通过 `createskill` 落盘新技能（校验命名与 frontmatter，同名拒绝覆盖）。

## 接入外部 MCP 服务器

复制 `.mcp.json.example` 为 `.mcp.json`（已被 .gitignore 忽略，不会入库）：

```json
{
  "mcpServers": {
    "my-server": { "command": "uvx", "args": ["mcp-server-fetch"] },
    "remote":   { "url": "http://127.0.0.1:8000/mcp", "timeout": 60 }
  }
}
```

- `command` 型走本地进程管道（stdio），`url` 型走 Streamable HTTP；
- 启动后**后台线程异步连接**，不阻塞界面，侧边栏实时显示每台服务器状态；
- 单台连接失败只跳过该服务器，错误可见，不影响其它工具。

## 会话与上下文

| 命令 | 作用 |
|---|---|
| `/new` / `/save` / `/resume` | 新建 / 保存 / 恢复会话（`.agents/sessions/*.jsonl`，可列出切换） |
| `/compact` | 上下文压缩：原始上下文归档 → LLM 生成摘要替换历史 |
| `/clear` / `/exit` / `/help` | 清空 / 退出 / 帮助 |

上下文占用达到阈值（默认 60%）会锁定输入并提示 `/compact`；
压缩后可用 `recallContext` 工具检索归档原文。

## 自测脚本

```bash
python core/mcp/_smoke.py   # MCP 客户端连通性冒烟（需先配好 .mcp.json）
python core/mcp/_e2e.py     # 端到端：配置引擎 → 提问 → 观察 MCP 工具调用
```

## 已知约束

- `RunCLI` 面向受控教学环境，无命令白名单，以当前用户权限执行，请勿在生产环境使用；
- MCP 传输依赖 `mcp>=2.0.0`（Python SDK v2）。
