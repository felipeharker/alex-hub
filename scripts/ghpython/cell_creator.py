# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - PatternName (GH: Pattern) | str | Pattern keyword (square/tri/hex/weave/cairo)
# - PatternIndex (GH: Index) | int | Pattern fallback index
# - CountX (GH: X) | int | Cell count in X
# - CountY (GH: Y) | int | Cell count in Y
# - CellSize (GH: Size) | float | Base module size
# - OriginPt (GH: Origin) | Rhino.Geometry.Point3d | Grid origin point
# Outputs:
# - Cells (GH: Cells) | list[Rhino.Geometry.Polyline] | Closed cell boundaries
# - Edges (GH: Edges) | list[Rhino.Geometry.Line] | Unique undirected edges
# - Centers (GH: Centers) | list[Rhino.Geometry.Point3d] | Cell centroids
# - Info (GH: Info) | str | Status summary

__author__ = "FHarker"
__version__ = "2025.10.01"

"""Pattern Library Browser (Slider-driven)
Inputs:
    Pattern: optional text name: "square", "tri", "hex", "weave", "cairo"
    Index: integer index (0-based) to select pattern
    X: int, cells in X
    Y: int, cells in Y
    Size: float, base module size
    Origin: Point3d, base origin
Outputs:
    Cells: list[Polyline], closed cell boundaries
    Edges: list[Line], unique edges (undirected)
    Centers: list[Point3d], cell centroids
    Info: string summary
"""

import Rhino
from Rhino.Geometry import Point3d, Polyline, Line
import math

# -------------------------
# Utilities
# -------------------------

def polyline_from_points(pts, close=True):
    pl = Polyline(pts)
    if close and pts and pts[0].DistanceTo(pts[-1]) > 1e-9:
        pl.Add(pts[0])
    return pl

def poly_center(pl):
    """Area centroid for closed polygon; falls back to average if degenerate."""
    pts = list(pl)
    if len(pts) < 4:
        return pts[0]
    if pts[0].DistanceTo(pts[-1]) < 1e-9:
        pts = pts[:-1]
    A = 0.0
    Cx = 0.0
    Cy = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i].X, pts[i].Y
        x1, y1 = pts[(i+1)%len(pts)].X, pts[(i+1)%len(pts)].Y
        cross = x0*y1 - x1*y0
        A  += cross
        Cx += (x0 + x1)*cross
        Cy += (y0 + y1)*cross
    if abs(A) < 1e-12:
        sx = sum(p.X for p in pts)/len(pts)
        sy = sum(p.Y for p in pts)/len(pts)
        return Point3d(sx, sy, pts[0].Z)
    A *= 0.5
    return Point3d(Cx/(6.0*A), Cy/(6.0*A), pts[0].Z)

def add_edge_unique(edge_set, a, b):
    """Store undirected edges uniquely using rounded coordinate keys."""
    key = lambda p: (round(p.X,6), round(p.Y,6), round(p.Z,6))
    ka, kb = key(a), key(b)
    k = (ka, kb) if ka <= kb else (kb, ka)
    if k not in edge_set:
        edge_set[k] = Line(a, b)

# -------------------------
# Pattern generators
# -------------------------

def gen_square(X, Y, Size, Origin):
    cells = []
    ox, oy, oz = Origin.X, Origin.Y, Origin.Z
    for j in range(Y):
        for i in range(X):
            x0 = ox + i*Size
            y0 = oy + j*Size
            pts = [
                Point3d(x0,       y0,       oz),
                Point3d(x0+Size,  y0,       oz),
                Point3d(x0+Size,  y0+Size,  oz),
                Point3d(x0,       y0+Size,  oz)
            ]
            cells.append(polyline_from_points(pts, True))
    return cells

def gen_tri(X, Y, Size, Origin):
    # Equilateral triangles from staggered rows
    w = Size
    h = Size * math.sqrt(3)/2.0
    cells = []
    ox, oy, oz = Origin.X, Origin.Y, Origin.Z
    for r in range(Y):
        xoff = (w/2.0) if (r % 2) else 0.0
        for c in range(X):
            x0 = ox + c*w + xoff
            y0 = oy + r*h
            pA = Point3d(x0,     y0,    oz)
            pB = Point3d(x0+w/2, y0+h,  oz)
            pC = Point3d(x0+w,   y0,    oz)
            if (c + r) % 2 == 0:
                cells.append(polyline_from_points([pA, pB, pC], True))
            else:
                cells.append(polyline_from_points([pA, Point3d(x0+w/2, y0-h, oz), pC], True))
    return cells

def gen_hex(X, Y, Size, Origin):
    # Pointy-top hex grid (side length = Size)
    s = Size
    w = math.sqrt(3)*s
    h = 1.5*s
    cells = []
    ox, oy, oz = Origin.X, Origin.Y, Origin.Z

    def hex_verts(cx, cy):
        pts = []
        for k in range(6):
            ang = math.radians(60*k - 30)
            pts.append(Point3d(cx + s*math.cos(ang), cy + s*math.sin(ang), oz))
        return pts

    for r in range(Y):
        xoff = 0.0 if (r % 2 == 0) else w/2.0
        for c in range(X):
            cx = ox + c*w + xoff
            cy = oy + r*h
            cells.append(polyline_from_points(hex_verts(cx, cy), True))
    return cells

def gen_weave(X, Y, Size, Origin, band_ratio=0.6):
    # Basket weave strips (horizontal/vertical alternating by row)
    t = max(0.05, min(0.95, band_ratio)) * Size
    cells = []
    ox, oy, oz = Origin.X, Origin.Y, Origin.Z
    for j in range(Y):
        for i in range(X):
            x0 = ox + i*Size
            y0 = oy + j*Size
            if (j % 2) == 0:
                ymid = y0 + 0.5*Size
                pts = [
                    Point3d(x0,        ymid - t/2, oz),
                    Point3d(x0+Size,   ymid - t/2, oz),
                    Point3d(x0+Size,   ymid + t/2, oz),
                    Point3d(x0,        ymid + t/2, oz)
                ]
            else:
                xmid = x0 + 0.5*Size
                pts = [
                    Point3d(xmid - t/2, y0,        oz),
                    Point3d(xmid + t/2, y0,        oz),
                    Point3d(xmid + t/2, y0+Size,   oz),
                    Point3d(xmid - t/2, y0+Size,   oz)
                ]
            cells.append(polyline_from_points(pts, True))
    return cells

def gen_cairo(X, Y, Size, Origin):
    ox, oy, oz = Origin.X, Origin.Y, Origin.Z
    s = Size
    w = math.sqrt(3)*s     # horizontal pitch
    h = 1.5*s              # vertical pitch
    a = 0.5*s
    b = 1.0*s

    def cell(cx, cy, z):
        p1 = Point3d(cx - a, cy - b, z)
        p2 = Point3d(cx + a, cy - b, z)
        p3 = Point3d(cx + b, cy,     z)
        p4 = Point3d(cx,     cy + b, z)
        p5 = Point3d(cx - b, cy,     z)
        return Polyline([p1,p2,p3,p4,p5,p1])

    cells = []
    for r in range(Y):
        xoff = 0.0 if (r % 2 == 0) else w/2.0
        for c in range(X):
            cx = ox + c*w + xoff
            cy = oy + r*h
            cells.append(cell(cx, cy, oz))
    return cells

# -------------------------
# Registry
# -------------------------

def registry_ordered():
    """Ordered pattern list: (key, factory) tuples in stable UI order."""
    return [
        ("square", lambda X,Y,S,O: gen_square(X,Y,S,O)),
        ("tri",    lambda X,Y,S,O: gen_tri(X,Y,S,O)),
        ("hex",    lambda X,Y,S,O: gen_hex(X,Y,S,O)),
        ("weave",  lambda X,Y,S,O: gen_weave(X,Y,S,O,band_ratio=0.6)),
        ("cairo",  lambda X,Y,S,O: gen_cairo(X,Y,S,O)),
    ]

def registry_dict():
    return {k:f for k,f in registry_ordered()}

# -------------------------
# Main
# -------------------------

# Defaults
if X is None or X < 1: X = 10
if Y is None or Y < 1: Y = 10
if Size is None or Size <= 0: Size = 1.0
if Origin is None: Origin = Point3d(0,0,0)

ordered = registry_ordered()
reg = registry_dict()

# Choose by Index if available, else by Pattern text
idx_in = locals().get('Index', None)
if idx_in is not None:
    try:
        i = int(idx_in)
    except:
        i = 0
    if len(ordered) == 0:
        raise Exception("Registry is empty.")
    # Clamp to valid range (change to modulo if wrap-around preferred)
    if i < 0: i = 0
    if i >= len(ordered): i = len(ordered)-1
    name = ordered[i][0]
else:
    token = Pattern or "square"
    try:
        name = str(token).strip().lower()
    except:
        name = "square"

if name not in reg:
    name = "square"

# Generate cells
Cells = reg[name](X, Y, Size, Origin)

# Centers & unique edges
Centers = [poly_center(pl) for pl in Cells]
edge_dict = {}
for pl in Cells:
    pts = list(pl)
    if len(pts) < 2: continue
    if pts[0].DistanceTo(pts[-1]) > 1e-9:
        pts.append(pts[0])
    for j in range(len(pts)-1):
        add_edge_unique(edge_dict, pts[j], pts[j+1])
Edges = list(edge_dict.values())

# Report
idx_lookup = {k:i for i,(k,_) in enumerate(ordered)}
idx = idx_lookup.get(name, -1)
Info = "Index: {} | Pattern: {} | Cells: {} | Edges: {} | Size: {} | Grid: {}x{}".format(
    idx, name, len(Cells), len(Edges), round(Size,3), X, Y
)
