#!/usr/bin/env python3
"""
solidworks_mcp_2011 — an MCP server exposing SolidWorks 2011 modeling
automation (sketching, features, dimensions, export, inspection) as MCP tools.

This is the SolidWorks 2011 server. It is pinned to the 2011 line and will
refuse to attach to anything newer, so it can run alongside the modern
server (claude/ or opencode/) without either one guessing which install it
got. Register it under its own name — "solidworks2011" — so the two sets of
tools stay separate calls.

This must run on the Windows machine where SolidWorks 2011 is installed —
SolidWorks automation only works over COM, which is Windows-only. See
README.md for setup and for how to point your client at this server.
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
    "solidworks_mcp_2011",
    instructions=(
        "Drive SolidWorks 2011 only through a stateful Windows COM session. Call "
        "sw_connect before modeling and sw_status when the active document or connection "
        "is uncertain. Build sketches before features, use returned names for later "
        "selections, rebuild after parameter changes, and inspect or save the model "
        "before reporting completion. Dimensions and coordinates are meters unless a "
        "tool explicitly says otherwise. Use the separate solidworks server for 2012+."
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
