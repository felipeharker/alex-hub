# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - SheetWidth (GH: SheetX) | float | Full sheet width
# - SheetHeight (GH: SheetY) | float | Full sheet height
# - EdgeMargin (GH: EdgeMargin) | float | Inset keep-out margin
# - SheetSpacing (GH: SheetSpacing) | float | Display spacing metadata
# Outputs:
# - SheetCurve (GH: SheetCurve) | Rhino.Geometry.Curve | Full sheet boundary
# - UsableCurve (GH: UsableCurve) | Rhino.Geometry.Curve | Inset usable boundary
# - SheetData (GH: SheetData) | dict | Structured sheet metadata

"""GhPython Component: Sheet Utility (Nest-ready rectangular sheet)

Purpose:
- Build a single rectangular sheet curve in World XY.
- Apply an edge margin (inset keep-out) so the nesting solver can pack inside the usable area.
- Store sheet spacing metadata for downstream visual layout (handled by the nesting tool).
- Output "nest-ready" sheet curves and a structured SheetData payload.

Inputs (Grasshopper):
    SheetX        (float)  full sheet width (X)
    SheetY        (float)  full sheet height (Y)
    EdgeMargin    (float)  inset margin from all edges (keep-out), same units
    SheetSpacing  (float)  spacing between displayed sheets (metadata only)

Outputs:
    SheetCurve    (Rhino.Geometry.Curve)   full sheet rectangle (World XY)
    UsableCurve   (Rhino.Geometry.Curve)   usable (inset) rectangle (World XY)
    SheetData     (dict)                   structured info for downstream nesting
                                           (dims, margins, usable area, spacing)
"""

import Rhino
from Rhino.Geometry import Plane, Rectangle3d, Interval

# -----------------------------
# Inputs (defensive defaults)
# -----------------------------
sx = 0.0 if SheetX is None else float(SheetX)
sy = 0.0 if SheetY is None else float(SheetY)
edge = 0.0 if EdgeMargin is None else float(EdgeMargin)
gap  = 0.0 if SheetSpacing is None else float(SheetSpacing)

sx = max(0.0, sx)
sy = max(0.0, sy)
edge = max(0.0, edge)
gap = max(0.0, gap)

# -----------------------------
# Initialize outputs
# -----------------------------
SheetCurve = None
UsableCurve = None
SheetData = {}

tol = 1e-9

# -----------------------------
# Validate dimensions
# -----------------------------
if sx > tol and sy > tol:
    usable_w = sx - 2.0 * edge
    usable_h = sy - 2.0 * edge
    has_usable = (usable_w > tol and usable_h > tol)

    plane = Plane.WorldXY

    # Full sheet rectangle
    full_rect = Rectangle3d(
        plane,
        Interval(0.0, sx),
        Interval(0.0, sy)
    )
    SheetCurve = full_rect.ToNurbsCurve()

    # Usable (inset) rectangle
    usable_rect = None
    if has_usable:
        usable_rect = Rectangle3d(
            plane,
            Interval(edge, sx - edge),
            Interval(edge, sy - edge)
        )
        UsableCurve = usable_rect.ToNurbsCurve()

    # Structured payload for nesting tool
    SheetData = {
        "plane": plane,
        "full_width": sx,
        "full_height": sy,
        "edge_margin": edge,
        "sheet_spacing": gap,
        "usable_width": usable_w if has_usable else 0.0,
        "usable_height": usable_h if has_usable else 0.0,
        "full_rect": full_rect,
        "usable_rect": usable_rect,
        "full_curve": SheetCurve,
        "usable_curve": UsableCurve
    }
