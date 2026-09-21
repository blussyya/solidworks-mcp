"""Parameter tools: read/drive dimensions, manage equations.

This is what makes the model genuinely parametric from Claude's side —
sw_set_dimension lets you go back and change a value (e.g. "make that boss
20mm instead of 15mm") without recreating the sketch/feature.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from connection import sw

MM = 0.001


def register(mcp) -> None:
    @mcp.tool(
        name="sw_list_dimensions",
        annotations={
            "title": "List all dimensions in the active document",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_list_dimensions() -> str:
        """List every dimension in the active document (sketch dimensions and
        feature dimensions like extrude depth), with their current values and
        the full name you'd pass to sw_set_dimension.

        Returns:
            str: JSON array of {name, value_mm, feature}. Angular dimensions
            report value_deg instead of value_mm.
        """
        model = sw().active_doc()
        out = []
        feat = model.FirstFeature()
        while feat is not None:
            disp_dim = feat.GetFirstDisplayDimension()
            while disp_dim is not None:
                try:
                    dim = disp_dim.GetDimension()
                except (TypeError, AttributeError):
                    disp_dim = feat.GetNextDisplayDimension(disp_dim)
                    continue
                if dim is None:
                    disp_dim = feat.GetNextDisplayDimension(disp_dim)
                    continue
                try:
                    full_name = dim.FullName
                    if callable(full_name): full_name = full_name()
                except Exception:
                    try:
                        dname = dim.Name
                        if callable(dname): dname = dname()
                        fname = feat.Name
                        if callable(fname): fname = fname()
                        full_name = f"{dname}@{fname}"
                    except Exception:
                        disp_dim = feat.GetNextDisplayDimension(disp_dim)
                        continue
                try:
                    dname = dim.Name
                    if callable(dname): dname = dname()
                    is_angle = "angle" in dname.lower()
                except Exception:
                    is_angle = False
                fname = feat.Name
                if callable(fname): fname = fname()
                entry = {"name": full_name, "feature": fname}
                try:
                    val = dim.SystemValue
                    if callable(val): val = val()
                except (TypeError, AttributeError):
                    disp_dim = feat.GetNextDisplayDimension(disp_dim)
                    continue
                if is_angle:
                    entry["value_deg"] = val * 180.0 / 3.14159265358979
                else:
                    entry["value_mm"] = val / MM
                out.append(entry)
                disp_dim = feat.GetNextDisplayDimension(disp_dim)
            feat = feat.GetNextFeature()
        return json.dumps(out)

    class SetDimensionInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name: str = Field(..., description="Full dimension name, e.g. 'D1@Sketch1' or 'D1@Boss-Extrude1'. See sw_list_dimensions.")
        value: float = Field(..., description="New value: millimeters, or degrees if this is an angular dimension.")
        rebuild: bool = Field(default=True, description="Rebuild the model immediately after setting the value.")

    @mcp.tool(
        name="sw_set_dimension",
        annotations={
            "title": "Drive a dimension to a new value",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_set_dimension(params: SetDimensionInput) -> str:
        """Change the value of an existing dimension and rebuild the model —
        this is how you edit a parametric model without recreating features.

        Args:
            params (SetDimensionInput): name, value, rebuild

        Returns:
            str: JSON confirmation with the new value.
        """
        model = sw().active_doc()
        dim = model.Parameter(params.name)
        if dim is None:
            raise RuntimeError(
                f"No dimension named '{params.name}' was found. Call sw_list_dimensions "
                "for the exact names available in this document."
            )
        is_angle = "angle" in params.name.lower()
        dim.SystemValue = params.value * (3.14159265358979 / 180.0) if is_angle else params.value * MM
        if params.rebuild:
            model.EditRebuild3()
        return json.dumps({"set": True, "name": params.name, "value": params.value})

    class AddEquationInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        equation: str = Field(
            ...,
            description='Equation text exactly as SolidWorks displays it, e.g. '
            '\'"D1@Sketch2" = "D1@Sketch1" * 2\'.',
        )

    @mcp.tool(
        name="sw_add_equation",
        annotations={
            "title": "Add a global equation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_add_equation(params: AddEquationInput) -> str:
        """Add a global equation linking two dimensions (or a dimension to a
        constant/formula), so one drives the other automatically from then on.

        Args:
            params (AddEquationInput): equation

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        eq_mgr = model.GetEquationMgr()
        index = eq_mgr.Add3(-1, params.equation, True, 0)
        if index < 0:
            raise RuntimeError(
                f"SolidWorks rejected the equation: {params.equation!r}. Check the exact "
                "dimension names with sw_list_dimensions and match SolidWorks' own quoting "
                'syntax (dimension names in double quotes).'
            )
        return json.dumps({"added": True, "index": index, "equation": params.equation})

    @mcp.tool(
        name="sw_list_equations",
        annotations={
            "title": "List global equations",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_list_equations() -> str:
        """List every global equation defined in the active document.

        Returns:
            str: JSON array of equation strings.
        """
        model = sw().active_doc()
        eq_mgr = model.GetEquationMgr()
        count = eq_mgr.GetCount()
        return json.dumps([eq_mgr.Equation(i) for i in range(count)])
