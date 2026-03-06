import Rhino
import scriptcontext as sc
from Rhino.Geometry import Plane, Rectangle3d, Interval

# Inputs:
#   Bnd        : Curve
#   SheetX     : float
#   SheetY     : float
#   UseWorldXY : bool
#
# Output:
#   Panels     : list[Curve]


def _doc_tol():
    if sc.doc:
        return sc.doc.ModelAbsoluteTolerance
    if Rhino.RhinoDoc.ActiveDoc:
        return Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    return 1e-3


def sizes_1d(L, S, tol):
    """
    Fills length L with:
    - as many full sheets S as possible
    - remainder split equally into two end caps
    - full sheets centered between caps
    """
    if S <= tol:
        return [L]

    n_full = int(L // S)
    rem = L - (n_full * S)

    if abs(rem) <= tol:
        return [S] * n_full

    cap = 0.5 * rem

    if cap <= tol:
        return [S] * n_full

    return [cap] + ([S] * n_full) + [cap]


Panels = []

if Bnd is None:
    Panels = []
else:
    tol = _doc_tol()

    # Choose working plane
    if UseWorldXY:
        pl = Plane.WorldXY
    else:
        ok, pl = Bnd.TryGetPlane(tol)
        if not ok:
            pl = Plane.WorldXY

    # Bounding box in chosen plane
    bb = Bnd.GetBoundingBox(pl)

    Lx = bb.Max.X - bb.Min.X
    Ly = bb.Max.Y - bb.Min.Y

    x_sizes = sizes_1d(Lx, float(SheetX), tol)
    y_sizes = sizes_1d(Ly, float(SheetY), tol)

    x0 = bb.Min.X
    for sx in x_sizes:
        y0 = bb.Min.Y
        for sy in y_sizes:
            rect = Rectangle3d(
                pl,
                Interval(x0, x0 + sx),
                Interval(y0, y0 + sy)
            )
            Panels.append(rect.ToNurbsCurve())
            y0 += sy
        x0 += sx
