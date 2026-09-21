#!/usr/bin/env python3
"""
solidworks_mcp — an MCP server exposing SolidWorks modeling automation
(sketching, features, dimensions, export, inspection) as MCP tools.

This server drives the modern SolidWorks line (2012 and newer, newest install
wins). SolidWorks 2011 has its own server in this repo under sw2011/, so that
neither has to guess which install it attached to.

This must run on the Windows machine where SolidWorks is installed —
SolidWorks automation only works over COM, which is Windows-only. See
README.md for setup and for how to point an MCP client at this server.
"""
from mcp.server.fastmcp import FastMCP

from tools import (
    session_tools,
    document_tools,
    sketch_tools,
    feature_tools,
    parameter_tools,
    inspection_tools,
)

mcp = FastMCP(
    "solidworks_mcp",
    instructions=(
        "Drive modern SolidWorks (2012+) through a stateful Windows COM session. "
        "Call sw_connect before modeling and sw_status when the active document or "
        "connection is uncertain. Build sketches before features, use returned names "
        "for later selections, rebuild after parameter changes, and inspect or save "
        "the model before reporting completion. Dimensions and coordinates are meters "
        "unless a tool explicitly says otherwise. This server never targets SolidWorks "
        "2011; use the separate solidworks2011 server for that release."
    ),
)

session_tools.register(mcp)
document_tools.register(mcp)
sketch_tools.register(mcp)
feature_tools.register(mcp)
parameter_tools.register(mcp)
inspection_tools.register(mcp)

if __name__ == "__main__":
    mcp.run()
