import os
import re
import json
import locale
import shutil
import mimetypes
import subprocess
import configparser
from openai import OpenAI

# 读取同目录下的 config.ini
cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")
sec = cfg["llm"]
model = sec.get("model")
api_key = sec.get("api_key")
base_url = sec.get("base_url")

client = OpenAI(api_key="sk-ttwguxojcefnzmrnsnplmueyqcprpntwwmxtfetanvebzrnu", base_url="https://api.siliconflow.cn/v1")



# 删除 <think> 和 </think> 之间的思考内容
# 传入累积的原始文本，流式时标签被拆到不同 chunk 也能正确过滤
def strip_think(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    i = text.rfind('<think>')
    if i != -1:                              # 标签还没闭合，思考内容先不输出
        text = text[:i]
    j = text.rfind('<')
    if j != -1 and '>' not in text[j:]:      # 末尾是半个标签，等下一段再判断
        text = text[:j]
    return text


# ---------------- function call tool ----------------

# 按顺序尝试解码，兼容 Windows GBK 控制台与 UTF-8 输出
def decode_cmd(data):
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not enc:
            continue
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


# getdate：调用本机 date 命令获取日期和时间，不用 python 代码拼时间
def getdate():
    if os.name == "nt":                      # Windows：date 命令不加 /t 会等待输入，用 /t 直接输出
        cmd = ["cmd", "/c", "date /t & time /t"]
    else:                                    # Linux / macOS：date 直接输出，stdin 传空避免挂起
        cmd = ["date"]
    proc = subprocess.run(cmd, input=b"", capture_output=True, timeout=10)
    text = decode_cmd(proc.stdout).strip() or decode_cmd(proc.stderr).strip()
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


# isleapyear：用 python 代码计算某年是否为闰年
def isleapyear(year):
    y = int(year)
    leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
    return f"{y}年{'是' if leap else '不是'}闰年"


# ---------------- 本地文件操作工具 ----------------

# 按 UTF-8 / GBK 顺序尝试解码纯文本字节，出现二进制特征直接报错
def decode_text(data, path):
    if b"\x00" in data:
        raise ValueError(f"检测到二进制内容，仅支持纯文本文件: {path}")
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法以 UTF-8 / GBK 解码，可能是二进制文件: {path}")


# getcwd：获取当前工作目录
def getcwd():
    return os.getcwd()


# list_dir：列出指定目录下的所有文件和子目录
def list_dir(path="."):
    if not os.path.isdir(path):
        raise NotADirectoryError(f"目录不存在: {path}")
    items = []
    with os.scandir(path) as it:
        for entry in it:
            kind = "目录" if entry.is_dir() else "文件"
            size = "" if entry.is_dir() else f"，{entry.stat().st_size} 字节"
            items.append(f"[{kind}] {entry.name}{size}")
    if not items:
        return f"目录 {os.path.abspath(path)} 为空"
    return f"目录 {os.path.abspath(path)} 共 {len(items)} 项:\n" + "\n".join(items)


# get_file_type：获取指定文件的文件类型
def get_file_type(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"路径不存在: {path}")
    if os.path.isdir(path):
        return f"{path} 是目录"
    mime, _ = mimetypes.guess_type(path)
    ext = os.path.splitext(path)[1] or "(无扩展名)"
    return f"{path} 是文件，扩展名 {ext}，MIME 类型 {mime or '未知'}"


# read_text_file：读取指定纯文本文件的内容
def read_text_file(path):
    if os.path.isdir(path):
        raise IsADirectoryError(f"这是目录，不是文件: {path}")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "rb") as f:
        text = decode_text(f.read(), path)
    return f"{path} 内容如下:\n{text}"


# create_file：根据目录和文件名创建新文件，父目录不存在时一并创建
def create_file(path, content="", overwrite=False):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"文件已存在: {path}，如需覆盖请设置 overwrite")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content or "")
    return f"已创建文件: {os.path.abspath(path)}"


# edit_file：编辑纯文本文件内容，支持 append / prepend / replace 三种模式
def edit_file(path, content, mode="append"):
    if os.path.isdir(path):
        raise IsADirectoryError(f"这是目录，不是文件: {path}")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    if mode == "prepend":
        with open(path, "rb") as f:
            old = decode_text(f.read(), path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write((content or "") + old)
    elif mode == "replace":
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content or "")
    elif mode == "append":
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(content or "")
    else:
        raise ValueError(f"不支持的模式: {mode}，可选 append / prepend / replace")
    return f"已用 {mode} 模式更新文件: {path}"


# create_directory：创建新目录，父目录不存在时一并创建
def create_directory(path):
    if os.path.isdir(path):
        return f"目录已存在: {os.path.abspath(path)}"
    os.makedirs(path)
    return f"已创建目录: {os.path.abspath(path)}"


# remove_directory：删除目录及其全部内容（非空目录也能删除）
def remove_directory(path):
    if not os.path.isdir(path):
        raise NotADirectoryError(f"目录不存在: {path}")
    shutil.rmtree(path)
    return f"已删除目录及其全部内容: {path}"


# delete_file：删除指定文件
def delete_file(path):
    if os.path.isdir(path):
        raise IsADirectoryError(f"这是目录，请改用删除目录工具: {path}")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    os.remove(path)
    return f"已删除文件: {path}"


# rename_path：重命名或移动文件、目录
def rename_path(src, dst):
    if not os.path.exists(src):
        raise FileNotFoundError(f"源路径不存在: {src}")
    if os.path.exists(dst):
        raise FileExistsError(f"目标路径已存在: {dst}")
    parent = os.path.dirname(os.path.abspath(dst))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    shutil.move(src, dst)
    return f"已将 {src} 重命名为 {dst}"


# 模型可调用的工具清单
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getdate",
            "description": "获取当前电脑的日期和时间，通过调用系统 date 命令得到",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isleapyear",
            "description": "计算某一年是否是闰年",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，例如 2024",
                    },
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getcwd",
            "description": "获取当前工作目录的完整路径",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出指定目录下的所有文件和子目录，不填 path 时列出当前目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，例如 D:/test 或相对路径 .",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_type",
            "description": "获取指定文件的文件类型（扩展名与 MIME 类型），目录会单独说明",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要判断类型的文件路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "读取指定纯文本文件的内容，二进制文件会拒绝读取",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的纯文本文件路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "根据目录和文件名创建新文件，父目录不存在时会一并创建",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要创建的文件完整路径，例如 D:/test/a.txt",
                    },
                    "content": {
                        "type": "string",
                        "description": "写入文件的文本内容，默认空字符串",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "文件已存在时是否覆盖，默认 false",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑指定纯文本文件的内容，支持追加、前置、整体替换",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的纯文本文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "prepend", "replace"],
                        "description": "编辑模式：append 追加到末尾，prepend 插入到开头，replace 整体替换，默认 append",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "创建新目录，父目录不存在时会一并创建",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要创建的目录路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_directory",
            "description": "删除指定目录及其全部内容，非空目录也能删除",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的目录路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除指定文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_path",
            "description": "重命名或移动文件、目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {
                        "type": "string",
                        "description": "原文件或目录路径",
                    },
                    "dst": {
                        "type": "string",
                        "description": "新的文件或目录路径",
                    },
                },
                "required": ["src", "dst"],
            },
        },
    },
]


# 分发工具调用，执行结果返回给模型
def run_tool(name, arguments):
    try:
        if name == "getdate":
            return getdate()
        if name == "isleapyear":
            args = json.loads(arguments or "{}")
            return isleapyear(args.get("year"))
        if name == "getcwd":
            return getcwd()
        args = json.loads(arguments or "{}")
        if name == "list_dir":
            return list_dir(args.get("path") or ".")
        if name == "get_file_type":
            return get_file_type(args.get("path"))
        if name == "read_text_file":
            return read_text_file(args.get("path"))
        if name == "create_file":
            return create_file(args.get("path"), args.get("content") or "", bool(args.get("overwrite")))
        if name == "edit_file":
            return edit_file(args.get("path"), args.get("content") or "", args.get("mode") or "append")
        if name == "create_directory":
            return create_directory(args.get("path"))
        if name == "remove_directory":
            return remove_directory(args.get("path"))
        if name == "delete_file":
            return delete_file(args.get("path"))
        if name == "rename_path":
            return rename_path(args.get("src"), args.get("dst"))
        return f"未找到工具: {name}"
    except Exception as e:
        return f"工具执行失败: {e}"


# 流式请求，边打印回答边收集 tool_calls，返回 (已输出文本, 工具调用列表)
def stream_answer():
    raw = ""                    # 本轮收到的原始文本，用来判断标签是否闭合
    printed = ""                # 已经输出的内容
    pending = {}                # index -> {id, name, arguments}，流式时工具调用分多段到达

    stream = client.chat.completions.create(
        model=model, messages=messages, tools=TOOLS, stream=True)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        for tc in (getattr(delta, "tool_calls", None) or []):
            slot = pending.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            fn = tc.function
            if fn is not None:
                if fn.name:
                    slot["name"] = fn.name
                if fn.arguments:
                    slot["arguments"] += fn.arguments

        if not delta.content:
            continue
        raw += delta.content
        now = strip_think(raw).strip()   # 过滤思考过程，去掉首尾空格换行
        if now.startswith(printed):      # 只输出新增的部分
            print(now[len(printed):], end="", flush=True)
        else:
            print(now, end="", flush=True)
        printed = now

    calls = [
        {
            "id": pending[i]["id"] or f"call_{i}",
            "type": "function",
            "function": {
                "name": pending[i]["name"],
                "arguments": pending[i]["arguments"] or "{}",
            },
        }
        for i in sorted(pending)
    ]
    if printed or calls:
        print()
    return printed, calls


MAX_ROUNDS = 5              # 单个问题最多连续调用工具的轮数，防止死循环

# 对话历史，不加 system 提示词（DeepSeek-R1 对 system 角色支持不好）
messages = []

print("已连接 LM Studio，输入 exit 退出")

while True:
    question = input("\n请输入问题: ").strip()
    if question == "exit":      # 退出程序
        break
    if not question:
        continue

    start = len(messages)       # 本轮开始位置，出错时整体回滚
    messages.append({"role": "user", "content": question})

    try:
        for _ in range(MAX_ROUNDS):
            printed, calls = stream_answer()

            if not calls:                      # 没有工具调用，本轮回答结束
                messages.append({"role": "assistant", "content": printed})
                break

            # 把工具调用记入历史，再把执行结果交给模型继续回答
            messages.append({
                "role": "assistant",
                "content": printed or None,
                "tool_calls": calls,
            })
            for call in calls:
                fn = call["function"]
                result = run_tool(fn["name"], fn["arguments"])
                print(f"[tool] {fn['name']} -> {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })
        else:
            print("工具调用轮数超限，本轮已终止")
    except Exception as e:
        print()
        print("请检查 LM Studio 是否已启动")
        print(f"connection error: {e}")
        del messages[start:]    # 本轮失败，回滚，避免污染上下文
        continue

print("程序已安全退出")
