[![M8ven Live Monitored](https://m8ven.ai/badge/mcp/blussyya-solidworks-mcp-3oq9wh?variant=verified)](https://m8ven.ai/mcp/blussyya-solidworks-mcp-3oq9wh?variant=verified)
# solidworks-mcp

An MCP server that drives SolidWorks 2022 directly from AI assistants —
sketching, features (extrude/cut/revolve/fillet/chamfer/shell/patterns),
driving dimensions and equations, exporting, and inspecting mass properties.

**Windows only.** SolidWorks automation goes through Windows COM — this
must run on the same machine where SolidWorks 2022 is installed and licensed.

## Quick start (recommended)

Download the [latest release](https://github.com/blussyya/solidworks-mcp/releases/latest) and run `setup.bat` — it auto-detects your Python and SolidWorks installs, installs dependencies, and configures your client. Done in one click.

Or manually:
```
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## Client support

This repo ships the same MCP server for two AI clients:

| Client | Directory | Config format |
|--------|-----------|---------------|
| [Claude Desktop](https://claude.ai/download) | `claude/` | `claude_desktop_config.json` |
| [opencode](https://opencode.ai) | `opencode/` | `opencode.jsonc` |

Each directory has its own README with client-specific setup instructions
and the same Python source code underneath.

```
solidworks-mcp/
├── README.md                    ← you are here
├── claude/                      ← Claude Desktop
│   ├── README.md
│   ├── claude_desktop_config.example.json
│   ├── server.py
│   ├── connection.py
│   ├── requirements.txt
│   ├── diagnose.py
│   └── tools/
└── opencode/                    ← opencode
    ├── README.md
    ├── opencode_config.example.jsonc
    ├── server.py
    ├── connection.py
    ├── requirements.txt
    ├── diagnose.py
    └── tools/
```

## Quick start

Pick your client and follow its README:

- **Claude Desktop**: [`claude/README.md`](claude/README.md)
- **opencode**: [`opencode/README.md`](opencode/README.md)

Both require the same prerequisites: Python 3.10+ and SolidWorks 2022 on
Windows. Install dependencies with `pip install -r requirements.txt` in the
appropriate directory.

## How it works

SolidWorks exposes its entire API over COM natively — no addon required.
This server attaches to a running SolidWorks instance (or launches one)
via `pywin32`, and exposes ~30 tools covering the full modeling workflow.

API enum constants are pulled live from your installed SolidWorks type
library, so they're guaranteed correct for your install.

See the client-specific READMEs for the full tool list, example workflows,
and known rough edges.
