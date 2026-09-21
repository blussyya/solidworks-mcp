"""Document lifecycle tools: new part/assembly/drawing, open, close, save, export."""

import glob
import json
import os
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from connection import sw, get_const

_DOC_TYPE_NAMES = {1: "PART", 2: "ASSEMBLY", 3: "DRAWING"}
_EXT_TO_DOC_TYPE = {
    ".sldprt": "swDocPART",
    ".prt": "swDocPART",
    ".sldasm": "swDocASSEMBLY",
    ".asm": "swDocASSEMBLY",
    ".slddrw": "swDocDRAWING",
    ".drw": "swDocDRAWING",
}


def _unwrap(result):
    """win32com returns a tuple when a COM method has [out] byref params
    alongside its return value. Normalize both shapes to a plain tuple."""
    if isinstance(result, tuple):
        return result
    return (result,)


def _guess_default_template(extension: str) -> str:
    """Best-effort search of SolidWorks' standard ProgramData templates
    folder for the top-level (non-MBD-subfolder) template of the given
    extension, e.g. '.asmdot' or '.drwdot'. There's no reliable no-argument
    API call to ask SolidWorks for this path directly without a verified
    swUserPreferenceStringValue_e enum ordinal, so this looks at the
    standard install location instead. Returns "" if nothing is found —
    callers should fall back to asking for template_path explicitly.
    """
    patterns = [
        rf"C:\ProgramData\SOLIDWORKS\SOLIDWORKS*\templates\*{extension}",
        rf"C:\ProgramData\SolidWorks\SOLIDWORKS*\templates\*{extension}",
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    # Prefer the shallowest path (skip MBD/ and other subfolders) so we get
    # the plain default template, not a size-specific MBD variant.
    top_level = [c for c in candidates if os.path.dirname(c).lower().endswith("templates")]
    chosen = sorted(top_level or candidates)
    return chosen[0] if chosen else ""


def register(mcp) -> None:
    @mcp.tool(
        name="sw_new_part",
        annotations={
            "title": "Create new part document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_new_part() -> str:
        """Create a new part document from your default part template and
        make it active.

        Returns:
            str: JSON with the new document's title.
        """
        conn = sw()
        app = conn.app
        model = conn.wrap_model(app.NewPart())
        if model is None:
            template = _guess_default_template(".prtdot")
            if not template:
                raise RuntimeError(
                    "SolidWorks did not create a new part (NewPart returned None), and "
                    "no default part template could be located automatically. Check "
                    "Tools > Options > Default Templates in SolidWorks."
                )
            model = conn.wrap_model(app.NewDocument(template, 0, 0, 0))
        if model is None:
            raise RuntimeError("SolidWorks did not create a new part.")
        return json.dumps({"created": True, "type": "PART", "title": model.GetTitle()})

    class NewFromTemplateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        template_path: str = Field(
            default="",
            description="Full path to a .asmdot/.drwdot template file. If left "
            "blank, tries to auto-locate your SolidWorks default template — if "
            "that fails, open Tools > Options > Default Templates in SolidWorks, "
            "copy the path shown there, and pass it explicitly.",
        )

    @mcp.tool(
        name="sw_new_assembly",
        annotations={
            "title": "Create new assembly document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_new_assembly(params: NewFromTemplateInput) -> str:
        """Create a new assembly document and make it active.

        Args:
            params (NewFromTemplateInput): template_path (optional)

        Returns:
            str: JSON with the new document's title.
        """
        conn = sw()
        template = params.template_path or _guess_default_template(".asmdot")
        if not template:
            raise RuntimeError(
                "Couldn't determine a default assembly template automatically. "
                "Open Tools > Options > Default Templates in SolidWorks, copy the "
                "assembly template path shown there, and pass it as template_path."
            )
        model = conn.wrap_model(conn.app.NewDocument(template, 0, 0, 0))
        if model is None:
            raise RuntimeError(f"SolidWorks did not create a new assembly from template '{template}'.")
        return json.dumps({"created": True, "type": "ASSEMBLY", "title": model.GetTitle()})

    @mcp.tool(
        name="sw_new_drawing",
        annotations={
            "title": "Create new drawing document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_new_drawing(params: NewFromTemplateInput) -> str:
        """Create a new drawing document and make it active.

        Args:
            params (NewFromTemplateInput): template_path (optional)

        Returns:
            str: JSON with the new document's title.
        """
        conn = sw()
        template = params.template_path or _guess_default_template(".drwdot")
        if not template:
            raise RuntimeError(
                "Couldn't determine a default drawing template automatically. "
                "Open Tools > Options > Default Templates in SolidWorks, copy the "
                "drawing template path shown there, and pass it as template_path."
            )
        model = conn.wrap_model(conn.app.NewDocument(template, 0, 0, 0))
        if model is None:
            raise RuntimeError(f"SolidWorks did not create a new drawing from template '{template}'.")
        return json.dumps({"created": True, "type": "DRAWING", "title": model.GetTitle()})

    class OpenDocumentInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        path: str = Field(..., description="Full path to a .sldprt, .sldasm, or .slddrw file.")
        read_only: bool = Field(default=False, description="Open read-only (viewer mode).")

    @mcp.tool(
        name="sw_open_document",
        annotations={
            "title": "Open a SolidWorks document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_open_document(params: OpenDocumentInput) -> str:
        """Open an existing part, assembly, or drawing file and make it active.

        Args:
            params (OpenDocumentInput): path, read_only

        Returns:
            str: JSON with title, path, and document type. Raises if the file
            doesn't exist or SolidWorks reports an error/warning code.
        """
        if not os.path.isfile(params.path):
            raise FileNotFoundError(f"No such file: {params.path}")

        ext = os.path.splitext(params.path)[1].lower()
        const_name = _EXT_TO_DOC_TYPE.get(ext)
        if const_name is None:
            raise ValueError(f"Unrecognized SolidWorks file extension: {ext}")
        doc_type = get_const(const_name)

        options = get_const("swOpenDocOptions_ReadOnly") if params.read_only else 0
        conn = sw()
        result = _unwrap(conn.app.OpenDoc6(params.path, doc_type, options, "", 0, 0))
        model = conn.wrap_model(result[0])
        if model is None:
            errors = result[1] if len(result) > 1 else "unknown"
            raise RuntimeError(
                f"SolidWorks failed to open '{params.path}' (error code: {errors}). "
                "Check the path and that the file isn't already open elsewhere."
            )
        return json.dumps(
            {
                "opened": True,
                "title": model.GetTitle(),
                "path": model.GetPathName(),
                "type": _DOC_TYPE_NAMES.get(model.GetType(), "UNKNOWN"),
            }
        )

    class CloseDocumentInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        save: bool = Field(default=False, description="Save changes before closing.")

    @mcp.tool(
        name="sw_close_active_document",
        annotations={
            "title": "Close the active document",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_close_active_document(params: CloseDocumentInput) -> str:
        """Close the currently active document.

        Args:
            params (CloseDocumentInput): save (bool) — save before closing.

        Returns:
            str: JSON confirmation with the title of the closed document.
        """
        conn = sw()
        model = conn.active_doc()
        title = model.GetTitle()
        if params.save:
            model.Save3(0, 0, 0)
        conn.app.CloseDoc(title)
        return json.dumps({"closed": True, "title": title, "saved": params.save})

    @mcp.tool(
        name="sw_save",
        annotations={
            "title": "Save the active document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_save() -> str:
        """Save the active document to its current path (overwrites in place).
        For a new, never-saved document, use sw_export_file instead to give it
        a path.

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        ok = model.Save3(0, 0, 0)
        result = ok[0] if isinstance(ok, tuple) else ok
        return json.dumps({"saved": bool(result), "path": model.GetPathName()})

    class ExportInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        path: str = Field(
            ...,
            description="Full output path including extension, e.g. "
            "'C:\\\\parts\\\\bracket.step'. The extension determines the format "
            "(.sldprt/.sldasm/.slddrw, .step/.stp, .stl, .iges/.igs, .pdf, .dxf, "
            ".dwg, .x_t/.x_b (Parasolid), .3mf, .obj).",
        )

    @mcp.tool(
        name="sw_export_file",
        annotations={
            "title": "Export/Save As the active document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_export_file(params: ExportInput) -> str:
        """Save/export the active document to a new path, in whatever format
        the file extension implies (STEP, STL, PDF, IGES, DXF, Parasolid, ...).

        Reference: https://help.solidworks.com/2022/english/api/sldworksapi/
        solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldocextension~saveas.html
        If this errors on your install, that page documents the exact
        overload SolidWorks 2022 expects — SaveAs has been through several
        revisions (SaveAs/SaveAs2/SaveAs3) across SolidWorks versions.

        Args:
            params (ExportInput): path

        Returns:
            str: JSON confirmation with the output path.
        """
        model = sw().active_doc()
        os.makedirs(os.path.dirname(params.path) or ".", exist_ok=True)
        result = _unwrap(model.Extension.SaveAs(params.path, 0, 0, None, 0, 0))
        ok = result[0]
        if not ok:
            raise RuntimeError(
                f"Export to '{params.path}' failed. Common causes: an unsupported "
                "combination of source document / target extension, or the target "
                "file is open/locked elsewhere."
            )
        return json.dumps({"exported": True, "path": params.path})

    class CustomPropertyInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name: str = Field(..., description="Custom property name, e.g. 'Material' or 'PartNumber'.")
        value: str = Field(..., description="Value to store (SolidWorks stores custom properties as text).")
        configuration: str = Field(
            default="",
            description="Configuration name for a config-specific property, or '' for a document-level property.",
        )

    @mcp.tool(
        name="sw_set_custom_property",
        annotations={
            "title": "Set a custom property",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_set_custom_property(params: CustomPropertyInput) -> str:
        """Set (or overwrite) a custom property on the active document, e.g.
        for BOM/title-block fields like Material, PartNumber, Description.

        Args:
            params (CustomPropertyInput): name, value, configuration

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        cpm = model.Extension.CustomPropertyManager(params.configuration)
        cpm.Add3(
            params.name,
            get_const("swCustomInfoText"),
            params.value,
            get_const("swCustomPropertyReplaceValue"),
        )
        return json.dumps({"set": True, "name": params.name, "value": params.value})

    @mcp.tool(
        name="sw_get_custom_properties",
        annotations={
            "title": "List custom properties",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_get_custom_properties(configuration: str = "") -> str:
        """List all custom properties on the active document.

        Args:
            configuration (str): Configuration name for config-specific
                properties, or '' (default) for document-level properties.

        Returns:
            str: JSON object mapping property name -> value.
        """
        model = sw().active_doc()
        cpm = model.Extension.CustomPropertyManager(configuration)
        names = cpm.GetNames()
        props = {}
        if names:
            for name in names:
                got = _unwrap(cpm.Get4(name, False, "", ""))
                # Get4 out params: (retval, valOut, resolvedValOut) once unwrapped
                value = got[1] if len(got) > 1 else None
                props[name] = value
        return json.dumps(props)

    @mcp.tool(
        name="sw_rebuild",
        annotations={
            "title": "Rebuild the active document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_rebuild(force: bool = False) -> str:
        """Force-rebuild the active document. Call this after changing a
        dimension or equation so the model updates before you inspect or
        export it.

        Args:
            force (bool): True forces a full rebuild of every feature
                (slower); False lets SolidWorks rebuild only what changed.

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        if force:
            model.ForceRebuild3(True)
        else:
            model.EditRebuild3()
        return json.dumps({"rebuilt": True, "forced": force})
