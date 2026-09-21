# solidworks-mcp (Codex)

Codex supports the same local STDIO MCP servers as the other clients. The
desktop app, CLI, and IDE extension share `~/.codex/config.toml` on the same
host.

## Configure

Install the dependencies from the repository root:

```powershell
python -m pip install -r requirements.txt
```

Then register the modern server:

```powershell
codex mcp remove solidworks
codex mcp add solidworks -- python C:\path\to\solidworks-mcp\claude\server.py
```

If SolidWorks 2011 is installed, register its separate server too:

```powershell
codex mcp remove solidworks2011
codex mcp add solidworks2011 -- python C:\path\to\solidworks-mcp\sw2011\server.py
```

The equivalent TOML is in [`codex_config.example.toml`](codex_config.example.toml).
Use absolute paths. Restart the Codex desktop app after changing MCP
configuration, then use `/mcp` or `codex mcp list` to confirm both servers.

The server uses STDIO, so it must not print ordinary output to stdout. Python
logging and diagnostics should go to stderr.

