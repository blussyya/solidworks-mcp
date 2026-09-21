"""Feature tools: extrude, cut, revolve, fillet, chamfer, shell, patterns.

Confidence levels (see README "Known rough edges" for details):
  VERIFIED     — matches a real, published working macro example exactly.
  WELL-SOURCED — matches official API docs + a real example closely.
  BEST-EFFORT  — built from general SolidWorks API knowledge but not checked
                 against a real example. Most likely spots to need a small
                 fix once you run this against actual SolidWorks 2022 —
                 if one throws or returns None, tell me the exact error and
                 I'll correct it.
"""

import json
import math
from typing import List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from connection import sw, get_const

MM = 0.001
DEG = math.pi / 180.0


def _select_sketch(model, sketch_name: str) -> None:
    model.ClearSelection2(True)
    ok = model.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, None, 0)
    if not ok:
        raise RuntimeError(
            f"Could not select sketch '{sketch_name}'. Check the exact name in the "
            "FeatureManager tree (sw_sketch_exit returns the name SolidWorks assigned)."
        )


def _select_point_entity(model, entity_type: str, point_mm: Tuple[float, float, float], append: bool) -> bool:
    x, y, z = point_mm
    return bool(
        model.Extension.SelectByID2("", entity_type, x * MM, y * MM, z * MM, append, 0, None, 0)
    )


def register(mcp) -> None:
    # -- Extrude boss (VERIFIED against a published FeatureExtrusion3 macro) --

    class ExtrudeBossInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        sketch_name: str = Field(..., description="Name of the finished sketch to extrude, e.g. 'Sketch1'.")
        depth_mm: float = Field(..., gt=0, description="Extrude depth, millimeters.")
        both_directions: bool = Field(default=False, description="Extrude symmetrically in both directions.")
        depth2_mm: float = Field(default=0, description="Depth in the second direction, if both_directions is True.")
        reverse: bool = Field(default=False, description="Reverse the extrude direction.")
        draft_angle_deg: float = Field(default=0, description="Draft angle, degrees. 0 for no draft.")
        merge: bool = Field(default=True, description="Merge with existing bodies (multibody parts).")

    @mcp.tool(
        name="sw_feature_extrude_boss",
        annotations={
            "title": "Extrude a sketch into a boss/base feature",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_extrude_boss(params: ExtrudeBossInput) -> str:
        """Extrude a finished sketch to add material (Boss/Base Extrude).

        Args:
            params (ExtrudeBossInput): sketch_name, depth_mm, both_directions,
                depth2_mm, reverse, draft_angle_deg, merge

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        _select_sketch(model, params.sketch_name)
        has_draft = params.draft_angle_deg != 0
        feat = model.FeatureManager.FeatureExtrusion3(
            not params.both_directions,      # Sd: True = single direction
            False,                            # Flip
            params.reverse,                   # Dir
            get_const("swEndCondBlind"),      # T1
            get_const("swEndCondBlind"),      # T2
            params.depth_mm * MM,              # D1
            params.depth2_mm * MM,             # D2
            has_draft, False,                  # Dchk1, Dchk2
            False, False,                      # Ddir1, Ddir2
            params.draft_angle_deg * DEG, 0,   # Dang1, Dang2
            False, False,                      # OffsetReverse1, OffsetReverse2
            False, False,                      # TranslateSurface1, TranslateSurface2
            params.merge,                      # Merge
            True, True,                        # UseFeatScope, UseAutoSelect
            get_const("swStartSketchPlane"),   # T0
            0,                                  # StartOffset
            False,                              # FlipStartOffset
        )
        if feat is None:
            raise RuntimeError(
                "FeatureExtrusion3 returned None — the extrude failed. Common causes: "
                "the sketch isn't closed/valid for a solid extrude, or it's already "
                "used by another feature."
            )
        return json.dumps({"created": "extrude_boss", "feature_name": feat.Name})

    # -- Extrude cut (VERIFIED against a published FeatureCut4 macro) --

    class ExtrudeCutInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        sketch_name: str = Field(..., description="Name of the finished sketch to cut with, e.g. 'Sketch2'.")
        depth_mm: float = Field(default=10, gt=0, description="Cut depth, millimeters. Ignored if through_all is True.")
        through_all: bool = Field(default=False, description="Cut all the way through the part.")
        reverse: bool = Field(default=False, description="Reverse the cut direction.")
        both_directions: bool = Field(default=False, description="Cut symmetrically in both directions.")

    @mcp.tool(
        name="sw_feature_extrude_cut",
        annotations={
            "title": "Extrude-cut material from a sketch",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_extrude_cut(params: ExtrudeCutInput) -> str:
        """Extrude a finished sketch to remove material (Extruded Cut).

        Args:
            params (ExtrudeCutInput): sketch_name, depth_mm, through_all, reverse, both_directions

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        _select_sketch(model, params.sketch_name)
        end_cond = get_const("swEndCondThroughAll") if params.through_all else get_const("swEndCondBlind")
        feat = model.FeatureManager.FeatureCut4(
            not params.both_directions,          # Sd
            params.reverse,                       # Flip
            False,                                  # Dir
            end_cond, 0,                            # T1, T2
            params.depth_mm * MM, params.depth_mm * MM,  # D1, D2
            False, False, False, False,             # Dchk1, Dchk2, Ddir1, Ddir2
            0, 0,                                    # Dang1, Dang2
            False, False,                            # OffsetReverse1, OffsetReverse2
            False, False,                            # TranslateSurface1, TranslateSurface2
            False,                                    # NormalCut
            True, True,                               # UseFeatScope, UseAutoSelect
            True, True,                               # AssemblyFeatureScope, AutoSelectComponents
            False,                                     # PropagateFeatureToParts
            get_const("swStartSketchPlane"),           # T0
            0, False,                                   # StartOffset, FlipStartOffset
            False,                                       # (trailing param — see FeatureCut4 docs if this errors)
        )
        if feat is None:
            raise RuntimeError(
                "FeatureCut4 returned None — the cut failed. Common causes: the sketch "
                "doesn't intersect any material, or isn't closed."
            )
        return json.dumps({"created": "extrude_cut", "feature_name": feat.Name})

    # -- Revolve (WELL-SOURCED against a published FeatureRevolve2 macro) --

    class RevolveInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        sketch_name: str = Field(..., description="Name of the finished sketch (profile + one construction-line axis).")
        angle_deg: float = Field(default=360, gt=0, le=360, description="Revolve angle, degrees.")
        cut: bool = Field(default=False, description="False = adds material (Revolved Boss/Base), True = removes it (Revolved Cut).")
        reverse: bool = Field(default=False, description="Reverse the revolve direction.")

    @mcp.tool(
        name="sw_feature_revolve",
        annotations={
            "title": "Revolve a sketch around an axis",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_revolve(params: RevolveInput) -> str:
        """Revolve a sketch profile around a construction-line axis in the same
        sketch (Revolved Boss/Base, or Revolved Cut if cut=True).

        Args:
            params (RevolveInput): sketch_name, angle_deg, cut, reverse

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        _select_sketch(model, params.sketch_name)
        feat = model.FeatureManager.FeatureRevolve2(
            True, not params.cut, False, params.cut, params.reverse, False,
            get_const("swEndCondBlind"), get_const("swEndCondBlind"),
            params.angle_deg * DEG, 0,
            False, False,
            0, 0,
            0,
            0, 0,
            True, False, True,
        )
        if feat is None:
            raise RuntimeError(
                "FeatureRevolve2 returned None — the revolve failed. Make sure the "
                "sketch has exactly one construction-line axis and a closed profile."
            )
        return json.dumps({"created": "revolve", "feature_name": feat.Name})

    # -- Fillet (reasonably confident: modern, well-documented 6-param FeatureFillet3) --

    class FilletInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        radius_mm: float = Field(..., gt=0, description="Fillet radius, millimeters.")
        all_edges: bool = Field(default=False, description="Fillet every edge of every solid body in the part.")
        edge_points_mm: Optional[List[Tuple[float, float, float]]] = Field(
            default=None,
            description="Instead of all_edges, a list of [x,y,z] points (millimeters, "
            "model space) each near one edge you want to fillet.",
        )

    @mcp.tool(
        name="sw_feature_fillet",
        annotations={
            "title": "Round (fillet) edges",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_fillet(params: FilletInput) -> str:
        """Add a constant-radius fillet to one or more edges.

        Args:
            params (FilletInput): radius_mm, all_edges, edge_points_mm

        Returns:
            str: JSON with the new feature's name and how many edges were selected.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        count = 0

        if params.all_edges:
            bodies = model.GetBodies2(get_const("swSolidBody") if _has_const("swSolidBody") else 0, True) or []
            for body in bodies:
                for edge in body.GetEdges() or []:
                    if edge.Select4(True, None):
                        count += 1
        elif params.edge_points_mm:
            for pt in params.edge_points_mm:
                if _select_point_entity(model, "EDGE", pt, append=True):
                    count += 1
        else:
            raise ValueError("Provide either all_edges=True or a non-empty edge_points_mm list.")

        if count == 0:
            raise RuntimeError("No edges were selected — nothing to fillet.")

        feat = model.FeatureManager.FeatureFillet3(
            0,                       # Options bitmask (swFilletOptions_e), 0 = defaults
            params.radius_mm * MM,   # R1: default radius
            params.radius_mm * MM,   # R2: second radius (same for constant radius)
            0,                       # Rho: conic rho (unused for constant radius)
            0,                       # Ftyp: 0 = constant radius fillet
            0,                       # OverflowType
            0,                       # ConicRhoType
            None,                    # Radii (array of per-edge radii, None = use default)
            None,                    # Dist2Arr
            None,                    # RhoArr
            None,                    # SetBackDistances
            None,                    # PointRadiusArray
            None,                    # PointDist2Array
            None,                    # PointRhoArray
        )
        if feat is None:
            raise RuntimeError("FeatureFillet3 returned None — the fillet failed (radius too large for the geometry?).")
        return json.dumps({"created": "fillet", "feature_name": feat.Name, "edges_selected": count})

    # -- Chamfer (BEST-EFFORT — verify against your SolidWorks 2022 before relying on it) --

    class ChamferInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        distance_mm: float = Field(..., gt=0, description="Chamfer distance, millimeters.")
        edge_points_mm: List[Tuple[float, float, float]] = Field(
            ..., description="List of [x,y,z] points (millimeters, model space) each near one edge to chamfer."
        )
        angle_deg: float = Field(default=45, description="Chamfer angle, degrees (distance-angle chamfer).")

    @mcp.tool(
        name="sw_feature_chamfer",
        annotations={
            "title": "Chamfer edges (best-effort — verify against SolidWorks 2022)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_chamfer(params: ChamferInput) -> str:
        """Add a distance-angle chamfer to one or more edges.

        BEST-EFFORT implementation — InsertFeatureChamfer's exact parameter
        order has shifted across SolidWorks versions more than most feature
        methods. If this errors, check
        https://help.solidworks.com/2022/english/api/sldworksapi/
        solidworks.interop.sldworks~solidworks.interop.sldworks.ifeaturemanager~insertfeaturechamfer.html
        and tell me the signature it shows — I'll fix the call.

        Args:
            params (ChamferInput): distance_mm, edge_points_mm, angle_deg

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        count = 0
        for pt in params.edge_points_mm:
            if _select_point_entity(model, "EDGE", pt, append=True):
                count += 1
        if count == 0:
            raise RuntimeError("No edges were selected — nothing to chamfer.")

        feat = model.FeatureManager.InsertFeatureChamfer(
            0,                        # Options
            get_const("swChamferAngleDistance") if _has_const("swChamferAngleDistance") else 1,  # Type
            params.distance_mm * MM,   # Width / D1
            params.angle_deg * DEG,     # Angle
            0, 0, 0, 0,                  # OtherDist / vertex-chamfer distances (unused here)
        )
        if feat is None:
            raise RuntimeError("InsertFeatureChamfer returned None — see the tool description for how to fix this.")
        return json.dumps({"created": "chamfer", "feature_name": feat.Name, "edges_selected": count})

    # -- Shell (BEST-EFFORT) --

    class ShellInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        thickness_mm: float = Field(..., gt=0, description="Wall thickness, millimeters.")
        face_points_mm: List[Tuple[float, float, float]] = Field(
            ..., description="List of [x,y,z] points (millimeters, model space) each near one face to remove/open up."
        )

    @mcp.tool(
        name="sw_feature_shell",
        annotations={
            "title": "Shell out a part (best-effort — verify against SolidWorks 2022)",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_shell(params: ShellInput) -> str:
        """Hollow out the part, removing the given faces to leave an open shell.

        BEST-EFFORT implementation — verify against your SolidWorks 2022. If it
        errors, check
        https://help.solidworks.com/2022/english/api/sldworksapi/
        solidworks.interop.sldworks~solidworks.interop.sldworks.ifeaturemanager~insertfeatureshell2.html

        Args:
            params (ShellInput): thickness_mm, face_points_mm

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        count = 0
        for pt in params.face_points_mm:
            if _select_point_entity(model, "FACE", pt, append=True):
                count += 1
        if count == 0:
            raise RuntimeError("No faces were selected — nothing to remove.")

        feat = model.FeatureManager.InsertFeatureShell(params.thickness_mm * MM, False)
        if feat is None:
            raise RuntimeError("InsertFeatureShell returned None — see the tool description for how to fix this.")
        return json.dumps({"created": "shell", "feature_name": feat.Name, "faces_removed": count})

    # -- Patterns (BEST-EFFORT) --

    class LinearPatternInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        feature_name: str = Field(..., description="Name of the feature to pattern, e.g. 'Boss-Extrude1'.")
        spacing_mm: float = Field(..., gt=0, description="Distance between instances, millimeters.")
        count: int = Field(..., gt=1, description="Total number of instances including the original.")
        direction_point_mm: Tuple[float, float, float] = Field(
            ..., description="[x,y,z] point (millimeters) near a linear edge that defines the pattern direction."
        )
        reverse: bool = Field(default=False, description="Reverse the pattern direction.")

    @mcp.tool(
        name="sw_feature_linear_pattern",
        annotations={
            "title": "Linear pattern a feature (best-effort — verify against SolidWorks 2022)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_linear_pattern(params: LinearPatternInput) -> str:
        """Repeat a feature along a straight direction at a fixed spacing.

        BEST-EFFORT implementation. If it errors, check
        https://help.solidworks.com/2022/english/api/sldworksapi/
        solidworks.interop.sldworks~solidworks.interop.sldworks.ifeaturemanager~featurelinearpattern4.html

        Args:
            params (LinearPatternInput): feature_name, spacing_mm, count, direction_point_mm, reverse

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        feat_to_pattern = model.FeatureByName(params.feature_name)
        if feat_to_pattern is None:
            raise RuntimeError(f"No feature named '{params.feature_name}' found.")
        feat_to_pattern.Select2(False, 0)
        if not _select_point_entity(model, "EDGE", params.direction_point_mm, append=True):
            raise RuntimeError("Could not select a direction edge near direction_point_mm.")

        feat = model.FeatureManager.FeatureLinearPattern4(
            params.count, params.spacing_mm * MM, 1, 0,
            params.reverse, False,
            True, False,
            "", "",
            False, False,
            True, True,
        )
        if feat is None:
            raise RuntimeError("FeatureLinearPattern4 returned None — see the tool description for how to fix this.")
        return json.dumps({"created": "linear_pattern", "feature_name": feat.Name})

    class CircularPatternInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        feature_name: str = Field(..., description="Name of the feature to pattern, e.g. 'Boss-Extrude1'.")
        angle_deg: float = Field(default=360, gt=0, le=360, description="Total angle to spread instances across.")
        count: int = Field(..., gt=1, description="Total number of instances including the original.")
        axis_point_mm: Tuple[float, float, float] = Field(
            ..., description="[x,y,z] point (millimeters) near a cylindrical face, axis, or edge to rotate around."
        )
        equal_spacing: bool = Field(default=True, description="Space instances evenly across angle_deg.")

    @mcp.tool(
        name="sw_feature_circular_pattern",
        annotations={
            "title": "Circular pattern a feature (best-effort — verify against SolidWorks 2022)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sw_feature_circular_pattern(params: CircularPatternInput) -> str:
        """Repeat a feature in a circular arrangement around an axis.

        BEST-EFFORT implementation. If it errors, check
        https://help.solidworks.com/2022/english/api/sldworksapi/
        solidworks.interop.sldworks~solidworks.interop.sldworks.ifeaturemanager~featurecircularpattern5.html

        Args:
            params (CircularPatternInput): feature_name, angle_deg, count, axis_point_mm, equal_spacing

        Returns:
            str: JSON with the new feature's name.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        if not _select_point_entity(model, "EDGE", params.axis_point_mm, append=False):
            _select_point_entity(model, "FACE", params.axis_point_mm, append=False)
        feat_to_pattern = model.FeatureByName(params.feature_name)
        if feat_to_pattern is None:
            raise RuntimeError(f"No feature named '{params.feature_name}' found.")
        feat_to_pattern.Select2(True, 0)

        feat = model.FeatureManager.FeatureCircularPattern5(
            params.count, params.angle_deg * DEG, params.equal_spacing,
            "", False, False, True, True, False,
        )
        if feat is None:
            raise RuntimeError("FeatureCircularPattern5 returned None — see the tool description for how to fix this.")
        return json.dumps({"created": "circular_pattern", "feature_name": feat.Name})

    # -- Inspection / management --

    @mcp.tool(
        name="sw_list_features",
        annotations={
            "title": "List the feature tree",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_list_features() -> str:
        """List every feature in the active document's FeatureManager tree.

        Returns:
            str: JSON array of {name, type, suppressed}.
        """
        model = sw().active_doc()
        out = []
        feat = model.FirstFeature()
        while feat is not None:
            fname = feat.Name
            if callable(fname): fname = fname()
            try:
                ftype = feat.GetTypeName2()
                if callable(ftype): ftype = ftype()
            except (TypeError, AttributeError):
                ftype = feat.GetTypeName()
                if callable(ftype): ftype = ftype()
            suppressed = feat.IsSuppressed2(0)
            if callable(suppressed): suppressed = suppressed()
            out.append({"name": fname, "type": ftype, "suppressed": bool(suppressed)})
            feat = feat.GetNextFeature()
        return json.dumps(out)

    @mcp.tool(
        name="sw_delete_feature",
        annotations={
            "title": "Delete a feature",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sw_delete_feature(feature_name: str) -> str:
        """Delete a feature (and, by default, anything that depends on it) by name.

        Args:
            feature_name (str): Exact feature name, e.g. 'Fillet3'. See sw_list_features.

        Returns:
            str: JSON confirmation.
        """
        model = sw().active_doc()
        model.ClearSelection2(True)
        ok = model.Extension.SelectByID2(feature_name, "BODYFEATURE", 0, 0, 0, False, 0, None, 0)
        if not ok:
            ok = model.Extension.SelectByID2(feature_name, "SKETCH", 0, 0, 0, False, 0, None, 0)
        if not ok:
            raise RuntimeError(f"Could not select '{feature_name}' to delete. Check sw_list_features for the exact name.")
        model.EditDelete()
        return json.dumps({"deleted": feature_name})


def _has_const(name: str) -> bool:
    try:
        get_const(name)
        return True
    except Exception:
        return False
