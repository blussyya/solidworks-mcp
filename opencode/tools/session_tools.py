"""Connection/session tools: sw_connect, sw_status, sw_disconnect."""

import json

from pydantic import BaseModel, ConfigDict, Field

from connection import sw


def _val(x):
    """RevisionNumber (and a few other zero-arg members) come back as a
    bound method when we have a typed wrapper, or as a plain value when
    running on the late-bound fallback (where attribute access alone
    already invoked it). Normalize both to a plain value."""
    return x() if callable(x) else x


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible: bool = Field(
        default=True,
        description="Whether the SolidWorks window should be visible on screen. "
        "Keep True so you can watch it work; set False for headless batch runs.",
    )
    launch_if_needed: bool = Field(
        default=True,
        description="If SolidWorks 2022 is not already running, launch it. "
        "Set False if you only want to attach to an already-running instance.",
    )


def register(mcp) -> None:
    @mcp.tool(
        name="sw_connect",
        annotations={
            "title": "Connect to SolidWorks",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_connect(params: ConnectInput) -> str:
        """Attach to a running SolidWorks 2022 instance, or launch one.

        Call this once at the start of a session before any other sw_* tool.
        Safe to call again later — if already connected it just verifies the
        connection is alive.

        Args:
            params (ConnectInput): visible, launch_if_needed

        Returns:
            str: JSON with connection status and SolidWorks version info.
        """
        conn = sw()
        app = conn.connect(visible=params.visible, launch_if_needed=params.launch_if_needed)
        try:
            version = _val(app.RevisionNumber)
        except Exception:
            version = "unknown"
        return json.dumps({"connected": True, "solidworks_revision": version})

    @mcp.tool(
        name="sw_status",
        annotations={
            "title": "Check SolidWorks connection status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_status() -> str:
        """Report whether the server is connected to SolidWorks and which
        document (if any) is currently active.

        Returns:
            str: JSON with `connected` (bool) and, if a document is open,
            `active_document` with its title, path, and document type
            ("PART", "ASSEMBLY", "DRAWING", or "UNKNOWN").
        """
        conn = sw()
        if conn.sw_app is None:
            return json.dumps({"connected": False})
        try:
            rev = _val(conn.sw_app.RevisionNumber)
            if not rev:
                raise RuntimeError("empty revision")
        except Exception:
            return json.dumps({"connected": False, "note": "Stale handle; call sw_connect again."})

        model = conn.wrap_model(conn.sw_app.ActiveDoc)
        if model is None:
            return json.dumps({"connected": True, "active_document": None})

        type_names = {1: "PART", 2: "ASSEMBLY", 3: "DRAWING"}
        doc_type = type_names.get(model.GetType(), "UNKNOWN")
        return json.dumps(
            {
                "connected": True,
                "active_document": {
                    "title": model.GetTitle(),
                    "path": model.GetPathName(),
                    "type": doc_type,
                },
            }
        )

    @mcp.tool(
        name="sw_disconnect",
        annotations={
            "title": "Disconnect from SolidWorks",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_disconnect(close_solidworks: bool = False) -> str:
        """Release the COM connection. Open documents and unsaved changes are
        left exactly as they are unless close_solidworks is True.

        Args:
            close_solidworks (bool): If True, also quits the SolidWorks
                application itself (any unsaved work is lost). Defaults to
                False, which just releases this server's handle.

        Returns:
            str: JSON confirmation.
        """
        sw().disconnect(close_solidworks=close_solidworks)
        return json.dumps({"disconnected": True, "solidworks_closed": close_solidworks})
