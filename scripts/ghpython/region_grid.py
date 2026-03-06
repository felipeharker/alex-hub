# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - B (GH: B) | Rhino.Geometry.Curve | Absolute closed planar boundary region.
# - RadX (GH: RadX) | float | Cell radius in X direction.
# - RadY (GH: RadY) | float | Cell radius in Y direction; if 0, uses RadX.
# - Type (GH: Type) | bool | True=hex grid, False=rectangular grid.
# - MaxX (GH: MaxX) | float | Maximum panel extent in X (working plane units).
# - MaxY (GH: MaxY) | float | Maximum panel extent in Y (working plane units).
# - UseWorldXY (GH: UseWorldXY) | bool | If True, paneling/grid uses WorldXY.
# Outputs:
# - GridCells (GH: GridCells) | list[Rhino.Geometry.Curve] | Valid grid cells.
# - Panels (GH: Panels) | list[Rhino.Geometry.Curve] | Panel bounds in region.
# - R (GH: R) | Grasshopper.DataTree[object] | Grid cells grouped by rows.
# - C (GH: C) | Grasshopper.DataTree[object] | Grid cells grouped by columns.

"""GhPython: Region grid with integrated panel seams and max-size panelization."""

__author__ = "Alexandria Labs"
__version__ = "2.1.0"
__last_reviewed__ = "2026-02-24"

import math

import Rhino
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path
from Rhino.Geometry import Interval
from Rhino.Geometry import Point3d
from Rhino.Geometry import Polyline
from Rhino.Geometry import PolylineCurve
from Rhino.Geometry import Rectangle3d
from Rhino.Geometry.Intersect import Intersection


# ------------------
# Helpers
# ------------------
def _is_closed_planar(crv, tol):
    if crv is None:
        return False
    if not crv.IsClosed:
        return False
    ok, _ = crv.TryGetPlane(tol)
    return ok


def _curve_plane(crv, tol):
    ok, pln = crv.TryGetPlane(tol)
    return pln if ok else None


def _hex_pts_xy(cx, cy, rx, ry):
    """Pointy-top hex; rx stretches X and ry stretches Y."""
    points = []
    for k in range(6):
        ang = math.radians(30.0 + 60.0 * k)
        points.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return points


def _rect_pts_xy(cx, cy, rx, ry):
    """Axis-aligned rectangle; if rx==ry this is a square."""
    return [
        (cx - rx, cy - ry),
        (cx + rx, cy - ry),
        (cx + rx, cy + ry),
        (cx - rx, cy + ry),
    ]


def _poly_fully_inside(cell_crv, boundary, plane, tol):
    """Return True only when polygon is strictly interior (no boundary touch)."""
    ok, polyline = cell_crv.TryGetPolyline()
    if not ok:
        return False

    # All vertices must be inside or on boundary.
    for i in range(polyline.Count - 1):
        if (
            boundary.Contains(polyline[i], plane, tol)
            == Rhino.Geometry.PointContainment.Outside
        ):
            return False

    # Any curve-curve intersection (including touch) rejects strict containment.
    events = Intersection.CurveCurve(cell_crv, boundary, tol, tol)
    if events and events.Count > 0:
        return False

    return True


def _sizes_by_max(length, max_size, tol):
    """Split `length` into equal pieces where each piece is <= `max_size`."""
    if max_size is None:
        return [length]

    try:
        max_value = float(max_size)
    except Exception:
        return [length]

    if max_value <= tol:
        return [length]

    count = int(math.ceil(length / max_value)) if length > tol else 1
    count = max(1, count)
    step = length / float(count)
    return [step] * count


def _snap_values_to_grid(values, anchor, step, tol):
    """Snap seam coordinates to nearest center-line series: anchor + k*step."""
    if step <= tol:
        return values

    snapped = []
    for value in values:
        k = int(round((value - anchor) / step))
        snapped.append(anchor + k * step)
    return snapped


def _build_panels(
    bbox,
    plane,
    max_x,
    max_y,
    anchor_x,
    anchor_y,
    step_x,
    step_y,
    tol,
    snap_x=True,
    snap_y=True,
):
    """Create panel rectangles, optionally snapping internal seams to grid lines."""
    len_x = bbox.Max.X - bbox.Min.X
    len_y = bbox.Max.Y - bbox.Min.Y

    x_sizes = _sizes_by_max(len_x, max_x, tol)
    y_sizes = _sizes_by_max(len_y, max_y, tol)

    x_edges = [bbox.Min.X]
    for size in x_sizes:
        x_edges.append(x_edges[-1] + size)

    y_edges = [bbox.Min.Y]
    for size in y_sizes:
        y_edges.append(y_edges[-1] + size)

    # Keep outer boundary fixed; only wiggle internal seams.
    if len(x_edges) > 2 and snap_x:
        mids = _snap_values_to_grid(x_edges[1:-1], anchor_x, step_x, tol)
        x_edges = [x_edges[0]] + mids + [x_edges[-1]]
        x_edges = sorted(x_edges)

    if len(y_edges) > 2 and snap_y:
        mids = _snap_values_to_grid(y_edges[1:-1], anchor_y, step_y, tol)
        y_edges = [y_edges[0]] + mids + [y_edges[-1]]
        y_edges = sorted(y_edges)

    panels = []
    for i in range(len(x_edges) - 1):
        x0 = x_edges[i]
        x1 = x_edges[i + 1]
        if x1 - x0 <= tol:
            continue

        for j in range(len(y_edges) - 1):
            y0 = y_edges[j]
            y1 = y_edges[j + 1]
            if y1 - y0 <= tol:
                continue

            rect = Rectangle3d(plane, Interval(x0, x1), Interval(y0, y1))
            panels.append(rect.ToNurbsCurve())

    return panels


# ------------------
# Main
# ------------------
GridCells = []
Panels = []
R = DataTree[object]()
C = DataTree[object]()

if B is None or RadX is None:
    GridCells = []
    Panels = []
else:
    tol = (
        Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        if Rhino.RhinoDoc.ActiveDoc
        else 1e-6
    )

    rx = float(RadX)
    if rx <= 0.0:
        GridCells = []
        Panels = []
    else:
        # Critical rule: if RadY == 0 -> regular polygons.
        if RadY is None:
            ry = rx
        else:
            ry_in = float(RadY)
            ry = rx if abs(ry_in) <= tol else ry_in

        if not _is_closed_planar(B, tol):
            GridCells = []
            Panels = []
        else:
            base_plane = _curve_plane(B, tol)
            work_plane = Rhino.Geometry.Plane.WorldXY if UseWorldXY else base_plane

            xform_w2p = Rhino.Geometry.Transform.ChangeBasis(
                work_plane, Rhino.Geometry.Plane.WorldXY
            )
            xform_p2w = Rhino.Geometry.Transform.ChangeBasis(
                Rhino.Geometry.Plane.WorldXY, work_plane
            )

            boundary_xy = B.DuplicateCurve()
            boundary_xy.Transform(xform_w2p)

            bbox = boundary_xy.GetBoundingBox(True)
            center = bbox.Center
            use_hex = bool(Type)

            if use_hex:
                step_x = math.sqrt(3.0) * rx
                step_y = 1.5 * ry
            else:
                step_x = 2.0 * rx
                step_y = 2.0 * ry

            # Hex row parity offsets make X snapping ambiguous; keep X unsnapped.
            panels_xy = _build_panels(
                bbox,
                Rhino.Geometry.Plane.WorldXY,
                MaxX,
                MaxY,
                center.X,
                center.Y,
                step_x,
                step_y,
                tol,
                snap_x=(not use_hex),
                snap_y=True,
            )

            Panels = []
            for panel in panels_xy:
                panel_world = panel.DuplicateCurve()
                panel_world.Transform(xform_p2w)
                Panels.append(panel_world)

            minx = bbox.Min.X - 2.0 * step_x
            maxx = bbox.Max.X + 2.0 * step_x
            miny = bbox.Min.Y - 2.0 * step_y
            maxy = bbox.Max.Y + 2.0 * step_y

            j_min = int(math.floor((miny - center.Y) / step_y)) - 1
            j_max = int(math.ceil((maxy - center.Y) / step_y)) + 1
            i_min = int(math.floor((minx - center.X) / step_x)) - 1
            i_max = int(math.ceil((maxx - center.X) / step_x)) + 1

            cells_by_row = {}
            cells_by_col = {}

            for j in range(j_min, j_max + 1):
                y = center.Y + j * step_y
                row_offset = 0.5 * step_x if (use_hex and (j & 1)) else 0.0

                for i in range(i_min, i_max + 1):
                    x = center.X + i * step_x + row_offset
                    center_pt = Point3d(x, y, 0.0)

                    if (
                        boundary_xy.Contains(center_pt, Rhino.Geometry.Plane.WorldXY, tol)
                        == Rhino.Geometry.PointContainment.Outside
                    ):
                        continue

                    # Candidate must belong to exactly one panel by center point.
                    owner_count = 0
                    for panel in panels_xy:
                        if (
                            panel.Contains(center_pt, Rhino.Geometry.Plane.WorldXY, tol)
                            != Rhino.Geometry.PointContainment.Outside
                        ):
                            owner_count += 1
                            if owner_count > 1:
                                break
                    if owner_count != 1:
                        continue

                    verts = (
                        _hex_pts_xy(x, y, rx, ry)
                        if use_hex
                        else _rect_pts_xy(x, y, rx, ry)
                    )
                    points = [Point3d(vx, vy, 0.0) for (vx, vy) in verts]
                    points.append(points[0])

                    polyline = Polyline(points)
                    if not polyline.IsValid:
                        continue

                    cell_xy = PolylineCurve(polyline)

                    if not _poly_fully_inside(
                        cell_xy, boundary_xy, Rhino.Geometry.Plane.WorldXY, tol
                    ):
                        continue

                    # Cell must fully fit inside exactly one panel seam region.
                    panel_fit_count = 0
                    for panel in panels_xy:
                        if _poly_fully_inside(
                            cell_xy, panel, Rhino.Geometry.Plane.WorldXY, tol
                        ):
                            panel_fit_count += 1
                            if panel_fit_count > 1:
                                break

                    if panel_fit_count != 1:
                        continue

                    cell_world = cell_xy.DuplicateCurve()
                    cell_world.Transform(xform_p2w)

                    GridCells.append(cell_world)
                    cells_by_row.setdefault(j, []).append((i, cell_world))
                    cells_by_col.setdefault(i, []).append((j, cell_world))

            # Rows -> R (branches ordered by j, items ordered by i).
            row_keys = sorted(cells_by_row.keys())
            for row_index, j in enumerate(row_keys):
                path = GH_Path(row_index)
                for (_, curve) in sorted(cells_by_row[j], key=lambda item: item[0]):
                    R.Add(curve, path)

            # Cols -> C (branches ordered by i, items ordered by j).
            col_keys = sorted(cells_by_col.keys())
            for col_index, i in enumerate(col_keys):
                path = GH_Path(col_index)
                for (_, curve) in sorted(cells_by_col[i], key=lambda item: item[0]):
                    C.Add(curve, path)
