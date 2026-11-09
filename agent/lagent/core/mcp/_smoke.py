import sys
sys.path.insert(0, r"L:\LY284\agent\lagent")

from core.mcp import load_mcp_servers, MCPClientManager, build_mcp_registry
from core.tools import ToolRegistry

servs = load_mcp_servers(path=r"L:\LY284\.mcp.json")
mgr = MCPClientManager(servs)
reg = ToolRegistry()
build_mcp_registry(reg, manager=mgr)

import json

def call(name, **kwargs):
    spec = reg.get(name)
    print("== EXECUTE", name, json.dumps(kwargs, ensure_ascii=False))
    print(reg.execute(name, json.dumps(kwargs)))

call("Bazi-MCP:getChineseCalendar", solarDatetime="2008-03-01T13:00:00+08:00")
print("----")
call("Bazi-MCP:getSolarTimes", bazi="甲子 乙丑 丙寅 丁卯")

mgr.close()
