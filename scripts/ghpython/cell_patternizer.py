# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - Cells (GH: Cells) | list[Rhino.Geometry.Polyline] | Input cells
# - Mode (GH: Mode) | str | Pattern mode
# - Inset (GH: Inset) | float | Inset factor
# - Steps (GH: Steps) | int | Pattern steps/intensity
# - Rotate (GH: Rotate) | float | Rotation in degrees
# Outputs:
# - Curves (GH: Curves) | list[Rhino.Geometry.Curve] | Primary pattern curves
# - Cutouts (GH: Cutouts) | list[Rhino.Geometry.Curve] | Secondary/cutout curves
# - Centers (GH: Centers) | list[Rhino.Geometry.Point3d] | Cell centers
# - Report (GH: Report) | str | Execution summary

__author__ = "FHarker"
__version__ = "2025.10.01"

"""Cell Patternizer (MVP)
Inputs:
    Cells: list[Polyline]  # closed, from grid generator
    Mode: str              # 'concentric', 'star', 'spokes'
    Inset: float           # 0..1, amount toward centroid
    Steps: int             # rings for concentric, spike factor for star (>=1)
    Rotate: float          # degrees, per-cell rotation about centroid
Outputs:
    Curves: list[Rhino.Geometry.Curve]
    Cutouts: list[Rhino.Geometry.Curve]
    Centers: list[Rhino.Geometry.Point3d]
    Report: str
"""
import Rhino
from Rhino.Geometry import *
import math

def centroid_of_curve(crv):
    # For closed planar curves, use area mass properties
    if crv and crv.IsClosed:
        amp = Rhino.Geometry.AreaMassProperties.Compute(crv)
        if amp:
            return amp.Centroid
    # Fallback: bounding-box center
    bb = crv.GetBoundingBox(True)
    return bb.Center


def to_polycurve(pl):
    if isinstance(pl, Polyline):
        return pl.ToPolylineCurve()
    if isinstance(pl, PolylineCurve):
        return pl
    return None

def centroid_of_polyline(pl):
    pts = list(pl)
    if pts[0].DistanceTo(pts[-1]) < 1e-9: pts = pts[:-1]
    A = 0.0; cx = 0.0; cy = 0.0; z = pts[0].Z
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i].X, pts[i].Y
        x1, y1 = pts[(i+1)%n].X, pts[(i+1)%n].Y
        cross = x0*y1 - x1*y0
        A += cross
        cx += (x0 + x1)*cross
        cy += (y0 + y1)*cross
    if abs(A) < 1e-12:
        sx = sum(p.X for p in pts)/n
        sy = sum(p.Y for p in pts)/n
        return Point3d(sx, sy, z)
    A *= 0.5
    return Point3d(cx/(6.0*A), cy/(6.0*A), z)

def best_plane(crv):
    pln = Plane.Unset
    ok, pln = crv.TryGetPlane()
    if not ok:
        # fall back to world XY
        pln = Plane.WorldXY
    return pln

def rotate_about(pt, angle_deg):
    return Transform.Rotation(math.radians(angle_deg), pt)

def offset_in_plane(crv, pln, dist):
    tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    offs = crv.Offset(pln, dist, tol, CurveOffsetCornerStyle.Sharp)
    return offs or []

def polygon_vertices(pl):
    pts = list(pl)
    if pts[0].DistanceTo(pts[-1]) < 1e-9: pts = pts[:-1]
    return pts

def star_polygon(pl, t=0.25, spike=1, rot_deg=0.0):
    """General star: alternate vertices with points pulled toward centroid by t.
       spike: integer multiplier to permute vertex order (for more spikes)."""
    verts = polygon_vertices(pl)
    n = len(verts)
    if n < 3: return None
    c = centroid_of_polyline(pl)
    order = range(n)
    # spike factor: permute indices (mod n)
    order = [(i*spike) % n for i in range(n)]
    # build 2n point star
    pts = []
    for idx in order:
        v = verts[idx]
        pts.append(v)
        toward = Point3d(c.X + (v.X - c.X)*(1.0 - t), c.Y + (v.Y - c.Y)*(1.0 - t), v.Z)
        pts.append(toward)
    pts.append(pts[0])
    plc = Polyline(pts).ToPolylineCurve()
    if rot_deg:
        plc.Transform(rotate_about(c, rot_deg))
    return plc

def spoke_lines(pl, rot_deg=0.0):
    verts = polygon_vertices(pl)
    c = centroid_of_polyline(pl)
    ln = []
    for v in verts:
        a, b = c, v
        line = Line(a, b).ToNurbsCurve()
        if rot_deg:
            line.Transform(rotate_about(c, rot_deg))
        ln.append(line)
    # also mid-edge spokes for “plus-like” effect
    for i in range(len(verts)):
        a = verts[i]; b = verts[(i+1)%len(verts)]
        mid = Point3d((a.X+b.X)/2.0, (a.Y+b.Y)/2.0, a.Z)
        line = Line(c, mid).ToNurbsCurve()
        if rot_deg:
            line.Transform(rotate_about(c, rot_deg))
        ln.append(line)
    return ln

def concentric_insets(pl, k=0.15, steps=3, rot_deg=0.0):
    """Create inward offsets (concentric rings) of a polygonal cell.
       k: fraction of average edge length used as offset distance per ring.
    """
    plc = to_polycurve(pl)
    if plc is None:
        return []

    pln = best_plane(plc)

    # average edge length for a scale-aware offset distance
    verts = polygon_vertices(pl)
    avg = 0.0
    for i in range(len(verts)):
        avg += verts[i].DistanceTo(verts[(i+1) % len(verts)])
    avg /= max(1, len(verts))

    d = -k * avg  # inward offset

    tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    rings = []
    crvs = [plc]
    for _ in range(steps):
        next_crvs = []
        for c in crvs:
            offs = c.Offset(pln, d, tol, Rhino.Geometry.CurveOffsetCornerStyle.Sharp)
            if not offs:
                continue
            for oc in offs:
                if rot_deg:
                    ctr = centroid_of_curve(oc)
                    oc.Transform(Transform.Rotation(math.radians(rot_deg), ctr))
                next_crvs.append(oc)
                rings.append(oc)
        crvs = next_crvs
        if not crvs:
            break

    return rings

# defaults
if not Mode: Mode = "concentric"
if Inset is None: Inset = 0.2
if Steps is None or Steps < 1: Steps = 3
if Rotate is None: Rotate = 0.0

Curves, Cutouts, Centers = [], [], []
count = 0

for pl in Cells or []:
    if not isinstance(pl, Polyline): 
        # try convert from curve with points
        continue
    c = centroid_of_polyline(pl)
    Centers.append(c)
    if Mode == "concentric":
        rings = concentric_insets(pl, k=max(0.01, min(0.9, Inset)), steps=Steps, rot_deg=Rotate)
        Curves.extend(rings)
        # the innermost ring is typically a good cutout
        if rings: Cutouts.append(rings[-1])
        count += 1
    elif Mode == "star":
        spike = max(1, int(Steps))
        sc = star_polygon(pl, t=max(0.01, min(0.9, Inset)), spike=spike, rot_deg=Rotate)
        if sc: 
            Curves.append(sc)
            Cutouts.append(sc)  # closed curve suitable for perforation
            count += 1
    elif Mode == "spokes":
        ln = spoke_lines(pl, rot_deg=Rotate)
        Curves.extend(ln)
        count += 1
    else:
        # passthrough
        pc = to_polycurve(pl)
        if pc: Curves.append(pc)

Report = "Cells: {} | Mode: {} | Inset: {} | Steps: {} | Rot: {}°".format(
    len(Cells or []), Mode, round(Inset,3), Steps, round(Rotate,2)
)