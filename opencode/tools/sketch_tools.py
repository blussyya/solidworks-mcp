"""Sketch tools: start/exit a sketch, draw primitives, dimension them.

Coordinate convention: all X/Y values are in the sketch's own 2D plane,
in millimeters (converted to meters internally, since the raw SolidWorks
API always works in meters/radians regardless of your document's display
units). Z is always 0 — every tool here draws on the active sketch plane,
not in free 3D space.
"""

import json
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from connection import sw, get_const

MM = 0.001  # SolidWorks API units are meters; we expose millimeters to the caller.


def _active_sketch_manager(model):
    sketch_mgr = model.SketchManager
    if sketch_mgr.ActiveSketch is None:
        raise RuntimeError(
            "No sketch is active. Call sw_new_sketch first (and don't call "
            "sw_sketch_exit until you're done drawing)."
        )
    return sketch_mgr


def register(mcp) -> None:
    class NewSketchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        plane: str = Field(
            default="Front Plane",
            description="Name of the plane or planar face to sketch on. Use "
            "'Front Plane', 'Top Plane', or 'Right Plane' for the standard "
            "reference planes, or the name of any other plane/face feature.",
        )

    @mcp.tool(
        name="sw_new_sketch",
        annotations={
            "title": "Start a new sketch",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_new_sketch(params: NewSketchInput) -> str:
        """Start a new 2D sketch on the given plane (or planar face) and make
        it the active sketch, ready for sw_sketch_line / sw_sketch_circle /
        sw_sketch_rectangle / sw_sketch_arc calls.

        Args:
            params (NewSketchInput): plane

        Returns:
            str: JSON confirmation with the plane name used.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        ok = model.Extension.SelectByID2(params.plane, "PLANE", 0, 0, 0, False, 0, None, 0)
        if not ok:
            # Fall back to FACE in case the caller passed a face name instead of a plane.
            ok = model.Extension.SelectByID2(params.plane, "FACE", 0, 0, 0, False, 0, None, 0)
        if not ok:
            raise RuntimeError(
                f"Could not select '{params.plane}' as a plane or face. Check the exact "
                "name shown in the SolidWorks FeatureManager tree."
            )
        model.SketchManager.InsertSketch(True)
        sw().last_entities = []
        return json.dumps({"sketch_started": True, "plane": params.plane})

    @mcp.tool(
        name="sw_sketch_exit",
        annotations={
            "title": "Exit the active sketch",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_sketch_exit() -> str:
        """Exit the currently active sketch, returning to normal part/assembly
        editing so features (extrude, etc.) can be created from it.

        Returns:
            str: JSON with the name SolidWorks assigned to the finished sketch
            (e.g. "Sketch3"), which you'll need for sw_feature_extrude_boss etc.
        """
        model = sw().active_doc()
        sketch_mgr = model.SketchManager
        if sketch_mgr.ActiveSketch is None:
            return json.dumps({"exited": False, "note": "No sketch was active."})
        # ActiveSketch.Name fails on late-bound ISketch; grab from feature tree instead
        name = None
        try:
            raw = sketch_mgr.ActiveSketch
            n = raw.Name
            if callable(n): n = n()
            name = n
        except (AttributeError, TypeError):
            pass
        if name is None:
            feat = model.FirstFeature()
            while feat is not None:
                try:
                    tname = feat.GetTypeName2()
                    if callable(tname): tname = tname()
                except (TypeError, AttributeError):
                    try:
                        tname = feat.GetTypeName()
                        if callable(tname): tname = tname()
                    except (TypeError, AttributeError):
                        tname = ''
                if tname == 'ProfileFeature':
                    n = feat.Name
                    if callable(n): n = n()
                    name = n
                    break
                feat = feat.GetNextFeature()
        if name is None:
            name = 'Sketch1'
        sketch_mgr.InsertSketch(True)
        return json.dumps({"exited": True, "sketch_name": name})

    class LineInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        x1: float = Field(..., description="Start point X, millimeters.")
        y1: float = Field(..., description="Start point Y, millimeters.")
        x2: float = Field(..., description="End point X, millimeters.")
        y2: float = Field(..., description="End point Y, millimeters.")

    @mcp.tool(
        name="sw_sketch_line",
        annotations={
            "title": "Draw a sketch line",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_sketch_line(params: LineInput) -> str:
        """Draw a straight line segment in the active sketch.

        Args:
            params (LineInput): x1, y1, x2, y2 (millimeters)

        Returns:
            str: JSON confirmation. The created segment becomes available to
            sw_sketch_add_dimension as entity_index 0.
        """
        model = sw().active_doc()
        sketch_mgr = _active_sketch_manager(model)
        seg = sketch_mgr.CreateLine(
            params.x1 * MM, params.y1 * MM, 0, params.x2 * MM, params.y2 * MM, 0
        )
        if seg is None:
            raise RuntimeError("SolidWorks did not create the line (CreateLine returned None).")
        sw().last_entities = [seg]
        return json.dumps({"created": "line", "start": [params.x1, params.y1], "end": [params.x2, params.y2]})

    class CircleInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        cx: float = Field(..., description="Center X, millimeters.")
        cy: float = Field(..., description="Center Y, millimeters.")
        radius: float = Field(..., gt=0, description="Radius, millimeters.")

    @mcp.tool(
        name="sw_sketch_circle",
        annotations={
            "title": "Draw a sketch circle",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_sketch_circle(params: CircleInput) -> str:
        """Draw a circle in the active sketch.

        Args:
            params (CircleInput): cx, cy, radius (millimeters)

        Returns:
            str: JSON confirmation. The created circle becomes available to
            sw_sketch_add_dimension as entity_index 0.
        """
        model = sw().active_doc()
        sketch_mgr = _active_sketch_manager(model)
        seg = sketch_mgr.CreateCircle(
            params.cx * MM, params.cy * MM, 0, (params.cx + params.radius) * MM, params.cy * MM, 0
        )
        if seg is None:
            raise RuntimeError("SolidWorks did not create the circle (CreateCircle returned None).")
        sw().last_entities = [seg]
        return json.dumps({"created": "circle", "center": [params.cx, params.cy], "radius": params.radius})

    class RectangleInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        x1: float = Field(..., description="First corner X, millimeters.")
        y1: float = Field(..., description="First corner Y, millimeters.")
        x2: float = Field(..., description="Opposite corner X, millimeters.")
        y2: float = Field(..., description="Opposite corner Y, millimeters.")
        centered: bool = Field(
            default=False,
            description="If True, (x1,y1) is the rectangle's center and "
            "(x2,y2) is one corner. If False (default), (x1,y1) and (x2,y2) "
            "are opposite corners.",
        )

    @mcp.tool(
        name="sw_sketch_rectangle",
        annotations={
            "title": "Draw a sketch rectangle",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_sketch_rectangle(params: RectangleInput) -> str:
        """Draw a rectangle (as 4 line segments) in the active sketch.

        Args:
            params (RectangleInput): x1, y1, x2, y2, centered (millimeters)

        Returns:
            str: JSON confirmation. The 4 created line segments become
            available to sw_sketch_add_dimension as entity_index 0-3, in the
            order SolidWorks creates them (not guaranteed to be a specific
            side — check the sketch visually if it matters which one you dimension).
        """
        model = sw().active_doc()
        sketch_mgr = _active_sketch_manager(model)
        args = (params.x1 * MM, params.y1 * MM, 0, params.x2 * MM, params.y2 * MM, 0)
        segs = sketch_mgr.CreateCenterRectangle(*args) if params.centered else sketch_mgr.CreateCornerRectangle(*args)
        if not segs:
            raise RuntimeError("SolidWorks did not create the rectangle.")
        sw().last_entities = list(segs)
        return json.dumps(
            {
                "created": "rectangle",
                "corner1": [params.x1, params.y1],
                "corner2": [params.x2, params.y2],
                "centered": params.centered,
                "segment_count": len(segs),
            }
        )

    class ArcInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        cx: float = Field(..., description="Center X, millimeters.")
        cy: float = Field(..., description="Center Y, millimeters.")
        radius: float = Field(..., gt=0, description="Radius, millimeters.")
        start_angle_deg: float = Field(..., description="Start angle, degrees, measured counterclockwise from +X.")
        end_angle_deg: float = Field(..., description="End angle, degrees, measured counterclockwise from +X.")
        clockwise: bool = Field(default=False, description="Direction of the arc sweep.")

    @mcp.tool(
        name="sw_sketch_arc",
        annotations={
            "title": "Draw a sketch arc",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_sketch_arc(params: ArcInput) -> str:
        """Draw a center-point arc in the active sketch.

        Args:
            params (ArcInput): cx, cy, radius, start_angle_deg, end_angle_deg, clockwise

        Returns:
            str: JSON confirmation. The created arc becomes available to
            sw_sketch_add_dimension as entity_index 0.
        """
        import math

        model = sw().active_doc()
        sketch_mgr = _active_sketch_manager(model)
        sx = params.cx + params.radius * math.cos(math.radians(params.start_angle_deg))
        sy = params.cy + params.radius * math.sin(math.radians(params.start_angle_deg))
        ex = params.cx + params.radius * math.cos(math.radians(params.end_angle_deg))
        ey = params.cy + params.radius * math.sin(math.radians(params.end_angle_deg))
        seg = sketch_mgr.CreateArc(
            params.cx * MM, params.cy * MM, 0,
            sx * MM, sy * MM, 0,
            ex * MM, ey * MM, 0,
            -1 if params.clockwise else 1,
        )
        if seg is None:
            raise RuntimeError("SolidWorks did not create the arc (CreateArc returned None).")
        sw().last_entities = [seg]
        return json.dumps({"created": "arc", "center": [params.cx, params.cy], "radius": params.radius})

    class DimensionInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        value: float = Field(..., description="Dimension value in millimeters (or degrees for an angular dimension).")
        entity_index: int = Field(
            default=0,
            description="Which entity from the most recent sketch tool call to dimension "
            "(0 for most primitives; a rectangle has 4, indexed 0-3).",
        )
        label_x: Optional[float] = Field(
            default=None, description="Where to place the dimension text, X in millimeters. Defaults near the entity."
        )
        label_y: Optional[float] = Field(
            default=None, description="Where to place the dimension text, Y in millimeters. Defaults near the entity."
        )

    @mcp.tool(
        name="sw_sketch_add_dimension",
        annotations={
            "title": "Dimension the most recently drawn sketch entity",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_sketch_add_dimension(params: DimensionInput) -> str:
        """Add a driving dimension to the entity created by the most recent
        sw_sketch_line / sw_sketch_circle / sw_sketch_rectangle / sw_sketch_arc
        call, and set it to the given value. This is what makes a sketch
        parametric instead of just reference geometry — do this for every
        measurement you want to be able to change later with sw_set_dimension.

        Args:
            params (DimensionInput): value, entity_index, label_x, label_y

        Returns:
            str: JSON with the dimension's SolidWorks name (e.g. "D1@Sketch1"),
            which you can pass to sw_set_dimension later to drive it.
        """
        conn = sw()
        model = conn.active_doc()
        entities = conn.last_entities
        if not entities or params.entity_index >= len(entities):
            raise RuntimeError(
                "No sketch entity available to dimension. Draw a line/circle/"
                "rectangle/arc first, then call this immediately after."
            )
        entity = entities[params.entity_index]
        model.ClearSelection2(True)
        entity.Select4(False, None)

        lx = params.label_x if params.label_x is not None else 0
        ly = params.label_y if params.label_y is not None else 0
        dim = model.AddDimension2(lx * MM, ly * MM, 0)
        if dim is None:
            raise RuntimeError(
                "SolidWorks could not create a dimension for this entity "
                "(AddDimension2 returned None)."
            )
        is_angle = "angle" in dim.Name.lower() if hasattr(dim, "Name") else False
        dim.SystemValue = params.value if is_angle else params.value * MM
        model.EditRebuild3()
        return json.dumps({"dimensioned": True, "name": dim.Name, "value": params.value})
