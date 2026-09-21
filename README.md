# solidworks-mcp

An MCP server that drives SolidWorks directly from AI assistants —
sketching, features (extrude/cut/revolve/fillet/chamfer/shell/patterns),
driving dimensions and equations, exporting, and inspecting mass properties.

**Windows only.** SolidWorks automation goes through Windows COM — this
must run on the same machine where SolidWorks is installed and licensed.

Two servers ship here, and they are **separate calls**: one for the modern
line (2012 and newer) and one for SolidWorks 2011, which needs different
API signatures. Pick a server and you have picked a version — there is no
runtime sniffing, and neither server will attach to a version it does not
target.

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

Plus a separate server for SolidWorks 2011, usable from either client:

| Version | Directory | Registered as | Notes |
|---------|-----------|---------------|-------|
| SolidWorks 2012+ | `claude/`, `opencode/` | `solidworks` | Newest install wins |
| SolidWorks 2011 | `sw2011/` | `solidworks2011` | Older API signatures (`FeatureExtrusion2`, `SelectByID2` variant arguments) |

Register both if you want both — because they use different server names,
their tools stay distinct and you choose a version per conversation rather
than hoping the server guessed right.

Each directory has its own README with client-specific setup instructions
and the same Python source code underneath.

```
solidworks-mcp/
├── README.md                    ← you are here
├── claude/                      ← Claude Desktop (SW2012+)
│   ├── README.md
│   ├── claude_desktop_config.example.json
│   ├── server.py
│   ├── connection.py
│   ├── requirements.txt
│   ├── diagnose.py
│   └── tools/
├── opencode/                    ← opencode (SW2012+)
│   ├── README.md
│   ├── opencode_config.example.jsonc
│   ├── server.py
│   ├── connection.py
│   ├── requirements.txt
│   ├── diagnose.py
│   └── tools/
└── sw2011/                      ← SolidWorks 2011 (either client)
    ├── README.md
    ├── claude_desktop_config.example.json
    ├── opencode_config.example.jsonc
    ├── server.py
    ├── connection.py
    ├── requirements.txt
    ├── diagnose.py
    └── tools/
```

## Per-directory setup

Pick your client and follow its README:

- **Claude Desktop**: [`claude/README.md`](claude/README.md)
- **opencode**: [`opencode/README.md`](opencode/README.md)
- **SolidWorks 2011**: [`sw2011/README.md`](sw2011/README.md)

All require the same prerequisites: Python 3.10+ and SolidWorks on
Windows. Install dependencies with `pip install -r requirements.txt` in the
appropriate directory.

## How it works

SolidWorks exposes its entire API over COM natively — no addon required.
This server attaches to a running SolidWorks instance (or launches one)
via `pywin32`, and exposes ~30 tools covering the full modeling workflow.

API enum constants are pulled live from your installed SolidWorks type
library, so they're guaranteed correct for your install.

### Which install a server attaches to

Each server resolves a **version-specific** ProgID — `SldWorks.Application.<major>`,
where `major` maps to the release year as `year = 1992 + major` (19 → 2011,
30 → 2022) — and dispatches only that.

The bare `SldWorks.Application` ProgID is deliberately never used. It belongs
to whichever install registered it last, which is not necessarily the newest:
on a machine with 2011 and 2022 side by side it was observed resolving to
**2011**, so a server that believed it was driving 2022 silently drove 2011
instead. Nothing errors when that happens — the interface names are identical,
so you just get a different application quietly building your geometry. The
same hazard applies to the type library, so each server loads the
`sldworks.tlb` sitting next to the executable that actually answered rather
than the one the registry's generic pointer names.

`sw_connect` and `sw_status` report the ProgID, executable path and release
year of whatever they attached to, so you can confirm at a glance.

To force a specific install, set `SOLIDWORKS_MCP_PROGID` (e.g.
`SldWorks.Application.30`) before launching the server.

See the client-specific READMEs for the full tool list, example workflows,
and known rough edges.
