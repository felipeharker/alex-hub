# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - CenterCurves (GH: C) | list[Rhino.Geometry.Curve] | Center curves to shatter
# - ShatterPts (GH: Pts) | list[Rhino.Geometry.Point3d] | Requested shatter points
# - ObstacleCurves (GH: Obs) | list[Rhino.Geometry.Curve] | Obstacle boundaries
# - ObstacleTolerance (GH: ObsTol) | float | Centroid exclusion tolerance
# - Step (GH: Step) | float | Arc-length shift step
# Outputs:
# - SafeSegments (GH: CrvSeg) | Grasshopper.DataTree[Rhino.Geometry.Curve] | Safe shattered segments
# - CollidingSegments (GH: CrvColl) | Grasshopper.DataTree[Rhino.Geometry.Curve] | Colliding segments
# - AdjustedPts (GH: PtsFixed) | Grasshopper.DataTree[Rhino.Geometry.Point3d] | Adjusted shatter points

"""Shatter curves at user points while avoiding obstacles.

Inputs:
    C       : list of center curves (Rhino.Geometry.Curve)
    Pts     : list of user points where shatters are desired (Point3d)
    Obs     : list of obstacle curves (rectangles/slots, closed & coplanar)
    ObsTol  : minimum tolerance between the centroid of an obstacle and a shatter point
    Step    : arc-length step for shifting a bad point along the curve

Outputs:
    CrvSeg   : DataTree of safe shattered segments (one branch per curve)
    CrvColl  : DataTree of colliding segments (one branch per curve)
    PtsFixed : DataTree of adjusted points actually used for shattering
"""

import Rhino.Geometry as rg
import scriptcontext as sc
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

CrvSeg   = DataTree[object]()
CrvColl  = DataTree[object]()
PtsFixed = DataTree[object]()

tol = sc.doc.ModelAbsoluteTolerance

# Coerce curves list
if C is None:
    curves = []
else:
    try:
        curves = list(C)
    except TypeError:
        curves = [C]

if not curves:
    # nothing to do
    pass
else:
    # ------------- global plane + centroids -------------
    plane = rg.Plane.WorldXY
    plane_found = False

    # Try curves first
    for crv in curves:
        if crv is None or not crv.IsValid:
            continue
        success, pl = crv.TryGetPlane()
        if success:
            plane = pl
            plane_found = True
            break

    # Fallback: obstacles
    if not plane_found and Obs:
        for ob in Obs:
            if ob is None:
                continue
            success, pl = ob.TryGetPlane()
            if success:
                plane = pl
                break

    centroids = []
    if ObsTol > 0 and Obs:
        for ob in Obs:
            if ob is None:
                continue
            amp = rg.AreaMassProperties.Compute(ob)
            if amp:
                centroids.append(amp.Centroid)

    def point_forbidden(pt):
        """True if pt is inside an obstacle or within ObsTol of a centroid."""
        if Obs:
            for ob in Obs:
                if ob is None:
                    continue
                pc = ob.Contains(pt, plane, tol)
                if pc == rg.PointContainment.Inside or pc == rg.PointContainment.Coincident:
                    return True
        if ObsTol > 0 and centroids:
            for c in centroids:
                if pt.DistanceTo(c) <= ObsTol:
                    return True
        return False

    def endpoint_collides(pt):
        """True if endpoint lies inside any obstacle."""
        if not Obs:
            return False
        for ob in Obs:
            if ob is None:
                continue
            pc = ob.Contains(pt, plane, tol)
            if pc == rg.PointContainment.Inside or pc == rg.PointContainment.Coincident:
                return True
        return False

    # Step along curve when fixing a bad point
    step = abs(Step)
    if step <= 0:
        # fallback: 1/200 of typical length scale
        step = 1.0

    # per-curve parameter & fixed-point lists
    n = len(curves)
    curve_ts  = [[] for _ in range(n)]
    curve_pts = [[] for _ in range(n)]

    # ------------- assign and fix points -------------
    if Pts:
        for pt in Pts:
            # find nearest curve to this point
            best_i  = None
            best_t  = None
            best_d2 = None

            for i, crv in enumerate(curves):
                if crv is None or not crv.IsValid:
                    continue
                rc, t = crv.ClosestPoint(pt)
                if not rc:
                    continue
                cpt = crv.PointAt(t)
                d2 = cpt.DistanceToSquared(pt)
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    best_i  = i
                    best_t  = t

            if best_i is None:
                continue

            crv = curves[best_i]
            if crv is None or not crv.IsValid:
                continue

            dom = crv.Domain
            length = crv.GetLength()
            if length <= 0:
                continue

            t0 = best_t
            cpt0 = crv.PointAt(t0)

            if not point_forbidden(cpt0):
                # already good
                curve_ts[best_i].append(t0)
                curve_pts[best_i].append(cpt0)
            else:
                # slide along the curve in +/- arc length
                # first convert t0 -> arc length s0
                s0 = crv.GetLength(rg.Interval(dom.T0, t0))
                max_steps = int(length / step) + 2

                found = False
                for k in range(1, max_steps):
                    s_candidates = [s0 + k * step, s0 - k * step]
                    for s_c in s_candidates:
                        if s_c < 0.0 or s_c > length:
                            continue
                        rc2, t2 = crv.LengthParameter(s_c)
                        if not rc2:
                            continue
                        p2 = crv.PointAt(t2)
                        if not point_forbidden(p2):
                            curve_ts[best_i].append(t2)
                            curve_pts[best_i].append(p2)
                            found = True
                            break
                    if found:
                        break

                if not found:
                    # couldn't rescue: use original projection
                    curve_ts[best_i].append(t0)
                    curve_pts[best_i].append(cpt0)

    # ------------- per-curve shatter & classify -------------
    for i, crv in enumerate(curves):
        path = GH_Path(i)

        if crv is None or not crv.IsValid:
            continue

        dom = crv.Domain
        t_start = dom.T0
        t_end   = dom.T1

        # start + fixed params + end
        ts = [t_start] + curve_ts[i] + [t_end]

        # sort & clean duplicates
        ts = sorted(ts)
        clean_ts = [ts[0]]
        for t in ts[1:]:
            if abs(t - clean_ts[-1]) > tol:
                clean_ts.append(t)
        ts = clean_ts

        # output fixed points for this curve
        for p in curve_pts[i]:
            PtsFixed.Add(p, path)

        # shatter
        for j in range(len(ts) - 1):
            t0 = ts[j]
            t1 = ts[j + 1]
            if t1 - t0 <= tol:
                continue

            sub = crv.Trim(rg.Interval(t0, t1))
            if not sub or not sub.IsValid:
                continue

            p0 = crv.PointAt(t0)
            p1 = crv.PointAt(t1)

            if endpoint_collides(p0) or endpoint_collides(p1):
                CrvColl.Add(sub, path)
            else:
                CrvSeg.Add(sub, path)
