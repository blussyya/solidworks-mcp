# solidworks-mcp (Claude Desktop)

An MCP server that lets Claude Desktop drive SolidWorks 2022 directly — sketching,
features (extrude/cut/revolve/fillet/chamfer/shell/patterns), driving
dimensions and equations, exporting, and inspecting mass properties.

**This only works on Windows**, and only on the machine where SolidWorks 2022
is actually installed and licensed. SolidWorks automation goes through
Windows COM (the same mechanism VBA macros use) — there's no way to drive it
remotely or from Linux/macOS. Run this alongside Claude Desktop on your
Windows box, the same way you've got your Blender and Fusion MCP connectors
set up.

## How it works

Unlike Blender (which needs an addon inside Blender exposing a socket),
SolidWorks exposes its entire API over COM natively. So this server *is* the
whole bridge — no separate addon to install inside SolidWorks. When a tool
calls `sw_connect`, the server attaches to a running SolidWorks 2022, or
launches one if none is open, using
[`pywin32`](https://github.com/mhammond/pywin32).

SolidWorks API enum constants (like "blind" vs "through all" for an extrude)
aren't hard-coded — they're pulled live from *your* installed SolidWorks 2022
type library via `win32com.gencache`, so they're guaranteed correct for your
install rather than a guess baked into this code.

## Setup

1. **Python on Windows.** 3.10+, installed on the same Windows machine as
   SolidWorks 2022 (not WSL — WSL can't reach Windows COM objects).
2. Open a terminal in this folder and install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. **Sanity-check the COM connection** before wiring it into Claude — open
   SolidWorks 2022, then run:
   ```
   python -c "import win32com.client; app = win32com.client.gencache.EnsureDispatch('SldWorks.Application'); print(app.RevisionNumber)"
   ```
   If that prints a version number, you're good. If it errors with something
   like "Class not registered", SolidWorks isn't installed/registered
   properly on this machine — reinstalling or repairing the SolidWorks
   installation fixes that.
4. **Register it with Claude Desktop.** Open (or create)
   `%APPDATA%\Claude\claude_desktop_config.json` and add an entry like the
   one in `claude_desktop_config.example.json`, pointing at your Python
   interpreter and this folder's `server.py`. Restart Claude Desktop.
5. In a chat, ask Claude to connect to SolidWorks — it'll call `sw_connect`
   and you should see the SolidWorks window come to the front (or launch).

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
value afterward — that's the point of doing this through the API rather than
just exporting a fixed mesh from a converter script.

## Known rough edges

I built this from SolidWorks's official API docs and real published macro
examples, cross-checked where I could, but **I don't have a live SolidWorks
install to test against** — so treat the first real run as the actual test
pass. In `tools/feature_tools.py` each tool is labeled by confidence:

- **VERIFIED** (`sw_feature_extrude_boss`, `sw_feature_extrude_cut`) — the
  exact positional call matches a real, working, published macro line for
  line. Should just work.
- **WELL-SOURCED** (`sw_feature_revolve`) — matches a real example closely.
- **BEST-EFFORT** (`sw_feature_chamfer`, `sw_feature_shell`,
  `sw_feature_linear_pattern`, `sw_feature_circular_pattern`) — built from
  general API knowledge of the method shape, not a verified example. If one
  of these throws or returns `None`, send me the exact error/traceback and
  the SolidWorks API help link in that tool's docstring, and I'll fix the
  call — these are usually one or two parameters out of order, not a
  fundamentally wrong approach.

Other things worth knowing:

- **Units**: every tool takes millimeters (or degrees for angles) and
  converts internally — the raw SolidWorks API always works in meters/radians
  regardless of your document's display units.
- **`sw_export_file`** uses the simplest `SaveAs` overload. If it errors on
  your install, `IModelDocExtension.SaveAs3` is the modern replacement (needs
  an `AdvancedSaveAsOptions` object) — the docstring links straight to the
  2022 API help page.
- **Edge/face selection** (fillet, chamfer, shell) works by passing an
  approximate XYZ point near the edge/face rather than a name — SolidWorks
  doesn't give edges friendly names the way it does planes. You'll generally
  want `sw_screenshot` or your own visual inspection to get coordinates, or
  use `all_edges=True` on fillet to just round everything.
- **Single-instance COM**: this server assumes one SolidWorks session and
  processes tool calls one at a time — that matches how you'd drive the UI
  yourself, and avoids COM's threading headaches.

## Extending it

Tool modules live in `tools/`, one file per rough category (sketching,
features, documents, parameters, inspection). Each exposes a `register(mcp)`
function. `connection.py`'s `get_const(name)` is the way to pull any
SolidWorks enum by name — add new tools there rather than hard-coding
integers. The full API reference is at
https://help.solidworks.com/2022/english/api/sldworksapi/welcome.htm.
