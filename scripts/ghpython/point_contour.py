# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - SectionPts (GH: Points) | list[Rhino.Geometry.Point3d] | Points defining contour locations
# - TargetGeo (GH: Surface) | Rhino.Geometry.Brep|Rhino.Geometry.Surface | Target surface/brep
# Outputs:
# - Curves (GH: Curves) | list[Rhino.Geometry.Curve] | Contour curves at unique X

"""GhPython Component
Inputs:
    Points:  List[Rhino.Geometry.Point3d] (section locations; typically y=0)
    Surface: Rhino surface or brep to contour

Outputs:
    Curves:  List[Rhino.Geometry.Curve] resulting from cutting with YZ planes at each unique X
"""

import Rhino
import scriptcontext as sc
from Rhino.Geometry import Point3d, Plane, Brep

# --- Helpers ---------------------------------------------------------------

def get_model_tol(default=0.01):
    try:
        if sc.doc and hasattr(sc.doc, "ModelAbsoluteTolerance"):
            return sc.doc.ModelAbsoluteTolerance
        if Rhino.RhinoDoc.ActiveDoc:
            return Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    except:
        pass
    return default

def to_brep(geo):
    """Accept Brep or Surface; return Brep or None."""
    if isinstance(geo, Brep):
        return geo
    # Surfaces in GH often come in as Rhino.Geometry.Surface or BrepFace
    if hasattr(geo, "ToBrep"):
        try:
            return geo.ToBrep()
        except:
            return None
    return None

def unique_x_values(points, tol):
    """Cluster points by X within tolerance and return sorted representative X values."""
    if tol <= 0: tol = 1e-6
    scale = 1.0 / tol
    buckets = {}
    # Ensure iterable
    seq = points if isinstance(points, (list, tuple)) else [points]
    for p in seq:
        if not isinstance(p, Point3d):
            continue
        key = int(round(p.X * scale))
        if key in buckets:
            buckets[key] = min(buckets[key], p.X)
        else:
            buckets[key] = p.X
    return sorted(buckets.values())

def yz_plane_at_x(x):
    """YZ plane translated to given X."""
    pl = Plane.WorldYZ
    pl.Origin = Point3d(x, 0.0, 0.0)
    return pl

# --- Main ------------------------------------------------------------------

Curves = []

if Surface is None or Points is None:
    pass
else:
    tol = get_model_tol()
    brep = to_brep(Surface)

    if brep is None:
        # Nothing to contour
        Curves = []
    else:
        xs = unique_x_values(Points, tol)
        for x in xs:
            pl = yz_plane_at_x(x)
            try:
                # This reliably returns IEnumerable[Curve]
                crvs = Brep.CreateContourCurves(brep, pl)
            except Exception:
                crvs = None

            if crvs:
                # Filter tiny/invalid results
                for c in crvs:
                    if c and c.IsValid and c.GetLength() > tol:
                        Curves.append(c)
