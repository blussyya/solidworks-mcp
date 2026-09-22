# SolidWorks 2011 MCP Server

MCP server for **SolidWorks 2011**. Uses the older API methods
(FeatureExtrusion2, FeatureCut3, FeatureRevolve, etc.) that the SW2011 COM
interface expects.

This is a **separate server from the modern one**, registered under its own
name (`solidworks2011`), so its tools are separate calls. It is pinned to
the 2011 line and will refuse to attach to anything newer — no fallback,
because silently attaching to a different version is the failure this split
exists to prevent. The modern line (2012+) is served by `claude/` and
`opencode/` in this repo.

Both can be registered at the same time; you pick the version by which
server you call.

## Prerequisites

- Windows with SolidWorks 2011 installed
- Python 3.10+
- The SolidWorks 2011 crack must be applied (setup folder copied to SW
  install dir, FlexNet services running)

## Setup

```powershell
pip install -r requirements.txt
```

## Running

**Claude Desktop** — in `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "solidworks2011": {
      "command": "C:\\path\\to\\python.exe",
      "args": ["C:\\path\\to\\solidworks-mcp\\sw2011\\server.py"]
    }
  }
}
```

**opencode** — in `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    "solidworks2011": {
      "type": "local",
      "command": ["python", "C:\\path\\to\\solidworks-mcp\\sw2011\\server.py"],
      "cwd": "C:\\path\\to\\solidworks-mcp\\sw2011",
      "enabled": true
    }
  }
}
```

Run `setup.bat` in the repository root to auto-detect the installed SolidWorks version and MCP clients. For only this server, use `powershell -ExecutionPolicy Bypass -File setup.ps1 -Server 2011` in the repository root. The installer creates a `.venv` and configures supported clients without requiring manual config edits.

## Which install it attaches to

This server dispatches `SldWorks.Application.19` and nothing else. If no
2011 install is registered it fails with a message telling you so, rather
than falling back to the bare `SldWorks.Application` ProgID — that ProgID
belongs to whichever install registered it last and can easily be a
different version.

`sw_connect` reports the ProgID, executable path and release year it
attached to, so you can confirm you're on 2011. To override the target,
set `SOLIDWORKS_MCP_PROGID` before launching.

## SW2011-specific differences

| Feature | SW2022 | SW2011 |
|---------|--------|--------|
| Extrude boss | FeatureExtrusion3 | FeatureExtrusion2 |
| Extrude cut | FeatureCut4 | FeatureCut3 |
| Revolve | FeatureRevolve2 | FeatureRevolve |
| Fillet | FeatureFillet3 | FeatureFillet2 |
| Linear pattern | FeatureLinearPattern4 | FeatureLinearPattern2 |
| Circular pattern | FeatureCircularPattern5 | FeatureCircularPattern2 |
| Save | Save3 | Save2 / Save |
| Rebuild | ForceRebuild3 | ForceRebuild2 / ForceRebuild |
| New part | NewPart() | NewDocument(template) |
| SelectByID2 Callout | None | VT_DISPATCH(None) |
| Boolean params | True/False | 0/1 (integers) |
