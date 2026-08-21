#!/usr/bin/env python3
"""
solidworks_mcp — an MCP server exposing SolidWorks 2022 modeling automation
(sketching, features, dimensions, export, inspection) as tools Claude can call.

This must run on the Windows machine where SolidWorks 2022 is installed —
SolidWorks automation only works over COM, which is Windows-only. See
README.md for setup and for how to point Claude Desktop at this server.
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

mcp = FastMCP("solidworks_mcp")

session_tools.register(mcp)
document_tools.register(mcp)
sketch_tools.register(mcp)
feature_tools.register(mcp)
parameter_tools.register(mcp)
inspection_tools.register(mcp)

if __name__ == "__main__":
    mcp.run()
