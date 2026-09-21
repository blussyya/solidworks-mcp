"""Inspection tools: mass properties, material, view control, screenshots."""

import json
import os

from pydantic import BaseModel, ConfigDict, Field

from connection import sw, get_const

_VIEW_CONSTANTS = {
    "front": "swFrontView",
    "back": "swBackView",
    "left": "swLeftView",
    "right": "swRightView",
    "top": "swTopView",
    "bottom": "swBottomView",
    "isometric": "swIsometricView",
    "trimetric": "swTrimetricView",
    "dimetric": "swDimetricView",
}


def register(mcp) -> None:
    @mcp.tool(
        name="sw_get_mass_properties",
        annotations={
            "title": "Get mass properties",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_get_mass_properties() -> str:
        """Compute mass, volume, surface area, and center of mass for the
        active document (uses whatever material is currently assigned;
        density defaults to 1 if no material is set).

        Returns:
            str: JSON with mass_g, volume_mm3, surface_area_mm2,
            center_of_mass_mm ([x, y, z]).
        """
        model = sw().active_doc()
        mp = model.Extension.CreateMassProperty()
        com = mp.CenterOfMass
        return json.dumps(
            {
                "mass_g": mp.Mass * 1000,
                "volume_mm3": mp.Volume * 1e9,
                "surface_area_mm2": mp.SurfaceArea * 1e6,
                "center_of_mass_mm": [com[0] * 1000, com[1] * 1000, com[2] * 1000],
            }
        )

    class SetMaterialInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        material_name: str = Field(..., description="Exact material name as it appears in the database, e.g. '1060 Alloy' or 'ABS'.")
        database_path: str = Field(
            default="",
            description="Full path to the .sldmat materials database. If left blank, "
            "tries the standard SOLIDWORKS 2022 install location — override this if "
            "your material lives in a custom database.",
        )
        configuration: str = Field(default="", description="Configuration name, or '' for all configurations.")

    @mcp.tool(
        name="sw_set_material",
        annotations={
            "title": "Assign a material",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_set_material(params: SetMaterialInput) -> str:
        """Assign a material to the active part.

        Args:
            params (SetMaterialInput): material_name, database_path, configuration

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        db_path = params.database_path
        if not db_path:
            app = sw().app
            exe_dir = os.path.dirname(app.GetExecutablePath() or "")
            db_path = os.path.join(exe_dir, "lang", "english", "sldmaterials", "SOLIDWORKS Materials.sldmat")
        model.SetMaterialPropertyName2(params.configuration, db_path, params.material_name)
        return json.dumps({"material_set": params.material_name, "database": db_path})

    class ScreenshotInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        path: str = Field(..., description="Output path, e.g. 'C:\\\\temp\\\\preview.bmp'. SolidWorks writes BMP.")
        width: int = Field(default=1024, gt=0, description="Image width in pixels.")
        height: int = Field(default=768, gt=0, description="Image height in pixels.")

    @mcp.tool(
        name="sw_screenshot",
        annotations={
            "title": "Save a screenshot of the current view",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_screenshot(params: ScreenshotInput) -> str:
        """Save the current graphics view as a BMP image — useful for showing
        Claude what the model looks like right now, or dropping into a report.

        Args:
            params (ScreenshotInput): path, width, height

        Returns:
            str: JSON with the output path.
        """
        model = sw().active_doc()
        os.makedirs(os.path.dirname(params.path) or ".", exist_ok=True)
        ok = model.SaveBMP(params.path, params.height, params.width)
        ok = ok[0] if isinstance(ok, tuple) else ok
        if not ok:
            raise RuntimeError(f"SaveBMP failed writing to '{params.path}'.")
        return json.dumps({"saved": True, "path": params.path})

    @mcp.tool(
        name="sw_set_view",
        annotations={
            "title": "Set the graphics view orientation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_set_view(view: str = "isometric") -> str:
        """Set the standard view orientation and zoom to fit.

        Args:
            view (str): One of front, back, left, right, top, bottom,
                isometric, trimetric, dimetric.

        Returns:
            str: JSON confirmation.
        """
        const_name = _VIEW_CONSTANTS.get(view.lower())
        if const_name is None:
            raise ValueError(f"Unknown view '{view}'. Choose one of: {', '.join(_VIEW_CONSTANTS)}.")
        model = sw().active_doc()
        model.ShowNamedView2(f"*{view.capitalize()}", get_const(const_name))
        model.ViewZoomtofit2()
        return json.dumps({"view_set": view})

    @mcp.tool(
        name="sw_zoom_to_fit",
        annotations={
            "title": "Zoom to fit",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_zoom_to_fit() -> str:
        """Zoom the graphics view to fit the whole model on screen.

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        model.ViewZoomtofit2()
        return json.dumps({"zoomed": True})
