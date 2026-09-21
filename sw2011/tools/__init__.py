"""Tool modules for the SolidWorks MCP server.

Each module exposes a `register(mcp)` function that defines and decorates
its tools against the shared FastMCP instance. Keeping registration as a
function (rather than decorating at import time against a module-level mcp
object) avoids circular imports between server.py and the tool modules.
"""
