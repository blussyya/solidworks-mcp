# solidworks-mcp

An MCP server that lets agents drive SolidWorks 2022 directly,
sketching features (extrude/cut/revolve/fillet/chamfer/shell/patterns),
driving dimensions and equations, exporting, and inspecting mass properties.

**This only works on Windows**, and only on the machine where SolidWorks 2022
is actually installed. SolidWorks automation goes through Windows COM.

## How it works

SolidWorks exposes its entire API over COM natively. So this server *is* the
whole bridge, no separate addon to install inside SolidWorks. When a tool
calls `sw_connect`, the server attaches to a running SolidWorks or
launches one if none is open using [`pywin32`](https://github.com/mhammond/pywin32).

SolidWorks API enum constants (like "blind" vs "through all" for an extrude)
aren't hard-coded, they're pulled live from *your* installed SolidWorks type library via `win32com.gencache`,
so they're guaranteed to be correct for your install rather than a guess.

## Setup

**Windows only.** Install SolidWorks and Python 3.10+ (Python 3.11–3.13 are reasonable choices), then run `setup.bat` from the repository folder. No Python dependencies are installed globally: the installer creates/reuses `.venv`, installs `requirements.txt`, and verifies the MCP and COM imports before registering clients.

The installer detects compatible Python interpreters (including the Windows Python launcher), reports incompatible versions, detects registered SolidWorks versions, and configures **detected** MCP clients. Supported clients: Claude Desktop, Claude Code CLI, OpenAI Codex CLI, Cursor, OpenCode, Windsurf, Gemini CLI and VS Code (GitHub Copilot MCP). It registers `solidworks` for modern SolidWorks and/or `solidworks2011` for SolidWorks 2011. Multiple detected SolidWorks versions can be registered together.

Existing JSON settings are retained and backed up before changes. If an existing JSONC config has comments or trailing commas that PowerShell cannot safely parse, setup **skips that config** instead of overwriting it. Codex and Claude Code are configured using their own CLI commands; they must be on `PATH` for automatic registration. A Codex desktop installation without the CLI is detected but cannot be configured automatically by this installer.

PowerShell options (run from the repository folder):

```powershell
.\setup.ps1                        # auto-detect versions and clients
.\setup.ps1 -Server Modern         # modern SolidWorks only
.\setup.ps1 -Server 2011           # SolidWorks 2011 only
.\setup.ps1 -Server Both           # register separate modern/2011 servers
.\setup.ps1 -Clients cursor        # configure Cursor explicitly
.\setup.ps1 -AllClients            # attempt every supported client (including absent ones)
```

`setup.bat` passes arguments through to the PowerShell installer. The MCP command uses the absolute path to this repository's `.venv\Scripts\python.exe`. Keep the repository in place afterward; moving it requires rerunning setup. Restart the configured client and approve/enable its MCP server if prompted.

**Manual alternative:** create a Python 3.10+ virtual environment, install `requirements.txt` there, and configure your client with the environment's `python.exe` and this repository's root `server.py` (or `sw2011\server.py`).

## Example workflow

"Make a 60x40x10mm plate with a 5mm hole in the middle and round the top
edges" would roughly become:

1. `sw_new_part`
2. `sw_new_sketch` (Front Plane)
3. `sw_sketch_rectangle` (centered, 60x40)
4. `sw_sketch_add_dimension` on each side you want fixed (or drive it via
   `sw_add_equation` later)
5. `sw_sketch_exit` → returns e.g. `"Sketch1"`
6. `sw_feature_extrude_boss` (sketch_name="Sketch1", depth_mm=10)
7. `sw_new_sketch` on the top face, `sw_sketch_circle` (r=2.5), `sw_sketch_exit`
8. `sw_feature_extrude_cut` (through_all=True)
9. `sw_feature_fillet` (all_edges=True, radius_mm=1) — or pass specific
   `edge_points_mm` if you only want certain edges
10. `sw_export_file` to a `.step` or `.sldprt` path

`sw_list_dimensions` / `sw_set_dimension` let you go back and change any
value afterward, that's the point of doing this through the API rather than
just exporting a fixed mesh from a converter script.

## Other things worth knowing:

- **Units**: every tool takes millimeters (or degrees for angles) and
  converts internally, the raw SolidWorks API always works in meters/radians
  regardless of your document's display units.
- **`sw_export_file`** uses the simplest `SaveAs` overload. If it errors on
  your install, `IModelDocExtension.SaveAs3` is the modern replacement (needs
  an `AdvancedSaveAsOptions` object), the docstring links straight to the
  API help page.
- **Edge/face selection** (fillet, chamfer, shell) works by passing an
  approximate XYZ point near the edge/face rather than a name, SolidWorks
  doesn't give edges friendly names the way it does planes. You'll generally
  want `sw_screenshot` or your own visual inspection to get coordinates, or
  use `all_edges=True` on fillet to just round everything.
- **Single-instance COM**: this server assumes one SolidWorks session and
  processes tool calls one at a time, that matches how you'd drive the UI
  yourself, and avoids COM's threading headaches.

## Extending it

Tool modules live in `tools/`, one file per rough category (sketching,
features, documents, parameters, inspection). Each exposes a `register(mcp)`
function. `connection.py`'s `get_const(name)` is the way to pull any
SolidWorks enum by name, add new tools there rather than hard-coding
integers. The full API reference is at
https://help.solidworks.com/2022/english/api/sldworksapi/welcome.htm.
