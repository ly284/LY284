import sys
sys.path.insert(0, r"L:\LY284\agent\lagent")
from core import create_agent
from core.events import ToolCallStarted, ToolCallFinished, TurnFinished, ErrorEvent

engine = create_agent(config_path=r"L:\LY284\agent\lagent\config.ini")
seen_mcp = []

def run(q):
    print("Q:", q)
    for ev in engine.ask(q):
        if isinstance(ev, ToolCallStarted):
            print("  [tool call]", ev.name, ev.arguments[:120])
            if ":" in ev.name:
                seen_mcp.append(ev.name)
        elif isinstance(ev, ToolCallFinished):
            print("  [tool result]", ev.result[:220].replace("\n", " ")[:220])
        elif isinstance(ev, TurnFinished):
            t = ev.text.replace("\n", " ")
            print("  [final]", t[:260])
        elif isinstance(ev, ErrorEvent):
            print("  [ERROR]", ev.message, ev.detail)
    print("=" * 40)

run("请用八字排盘，帮我分析一位2008年3月1日13时出生的男命：公历时间，给出四柱八字。")
print("MCP TOOL USED:", seen_mcp)
engine.close()
