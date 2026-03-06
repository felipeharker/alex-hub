# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - CenterCurves (GH: C) | list[Rhino.Geometry.Curve] | Center curves to shatter
# - ObstacleCurves (GH: Obs) | list[Rhino.Geometry.Curve] | Obstacle boundaries
# - MinSpacing (GH: dMin) | float | Minimum shatter spacing
# - MaxSpacing (GH: dMax) | float | Maximum shatter spacing
# - ObstacleTolerance (GH: ObsTol) | float | Centroid exclusion tolerance
# - Step (GH: Step) | float | Arc-length shift step
# - EdgeFactor (GH: EdgeFactor) | float | Cleanup merge factor
# Outputs:
# - SafeSegments (GH: CrvSeg) | Grasshopper.DataTree[Rhino.Geometry.Curve] | Safe shattered segments
# - CollidingSegments (GH: CrvColl) | Grasshopper.DataTree[Rhino.Geometry.Curve] | Colliding segments

"""Adaptive shatter for multiple curves, avoiding obstacle regions.

Inputs:
    C          : list of center curves to shatter (Rhino.Geometry.Curve)
    Obs        : list of obstacle curves (rectangles/slots, closed & coplanar)
    dMin       : minimum distance between shatter points (arc length)
    dMax       : maximum distance between shatter points (arc length)
    ObsTol     : minimum tolerance between the center (area centroid) of the Obs and a shatter point
    Step       : arc-length step for testing +/- away from a forbidden point
    EdgeFactor : cleanup factor in [0, 1]; segments shorter than
                 EdgeFactor * dMin will try to merge with a neighbor.
                 CLEANUP IGNORES dMax, so some segments may end up > dMax.

Outputs:
    CrvSeg  : DataTree of safe shattered segments (one branch per curve)
    CrvColl : DataTree of colliding segments (one branch per curve)
"""

import Rhino.Geometry as rg
import scriptcontext as sc
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# --------------------------------------------------------
# Per-curve logic (single-curve shatter)
# --------------------------------------------------------

def process_curve(curve, Obs, dMin, dMax, ObsTol, Step, EdgeFactor, tol):
    """Return (safe_segments, colliding_segments) for a single curve."""
    CrvSeg  = []
    CrvColl = []

    if curve is None or not curve.IsValid:
        return CrvSeg, CrvColl

    length = curve.GetLength()
    if length <= 0:
        return CrvSeg, CrvColl

    # Reference plane for Contains
    success, plane = curve.TryGetPlane()
    if not success:
        plane = rg.Plane.WorldXY

    # Obstacle centroids (for ObsTol keep-out radius)
    centroids = []
    if ObsTol > 0 and Obs:
        for ob in Obs:
            if ob is None:
                continue
            amp = rg.AreaMassProperties.Compute(ob)
            if amp:
                centroids.append(amp.Centroid)

    # Normalize dMin / dMax
    if dMin < 0: dMin = 0.0
    if dMax < 0: dMax = 0.0
    if dMax > 0 and dMin > dMax:
        dMin, dMax = dMax, dMin

    # Clamp EdgeFactor to [0, 1]
    if EdgeFactor is None:
        EdgeFactor = 0.5
    try:
        ef = float(EdgeFactor)
    except:
        ef = 0.5
    if ef < 0.0: ef = 0.0
    if ef > 1.0: ef = 1.0

    # Target spacing
    if dMin > 0 and dMax > 0:
        target = 0.5 * (dMin + dMax)   # avg of dMin/dMax
    elif dMin > 0:
        target = dMin
    elif dMax > 0:
        target = dMax
    else:
        target = length / 20.0         # fallback

    # Step in arc-length units
    step = abs(Step)
    if step <= 0:
        step = target * 0.1

    dom = curve.Domain
    t_start = dom.T0
    t_end   = dom.T1

    ts = [t_start]
    s_last = 0.0
    max_iter = 10000
    iter_count = 0

    # ----- inline helpers, bound to this curve/plane/centroids -----

    def point_forbidden(pt):
        """True if pt is inside any obstacle OR within ObsTol of any centroid."""
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
        """True if endpoint lies inside any obstacle region."""
        if not Obs:
            return False
        for ob in Obs:
            if ob is None:
                continue
            pc = ob.Contains(pt, plane, tol)
            if pc == rg.PointContainment.Inside or pc == rg.PointContainment.Coincident:
                return True
        return False

    # ----- place shatter points along this curve (dMax-priority stepping) -----

    while True:
        iter_count += 1
        if iter_count > max_iter:
            break

        remaining = length - s_last

        # dMax priority for stepping:
        if dMax > 0 and remaining <= dMax + tol:
            break

        # If no dMax given, fall back to dMin-based stopping
        if dMax <= 0 and dMin > 0 and remaining <= dMin + tol:
            break

        # Window [s_min, s_max] for next shatter (arc length)
        if dMin > 0:
            s_min = s_last + dMin
        else:
            s_min = s_last + tol

        if dMax > 0:
            s_max = s_last + dMax
        else:
            s_max = s_last + remaining

        if s_min >= length - tol:
            break
        if s_max > length:
            s_max = length

        # Initial target position
        s_target = s_last + target
        if s_target < s_min:
            s_target = s_min
        if s_target > s_max:
            s_target = s_max

        window = s_max - s_min
        if window <= tol:
            # Degenerate window: force a cut at s_max (still honors dMax in stepping)
            rc, t_force = curve.LengthParameter(s_max)
            if rc:
                ts.append(t_force)
                s_last = s_max
            break

        found = False
        max_steps = int(window / step) + 2

        for k in range(max_steps):
            # Test s_target first, then ± k*step
            if k == 0:
                candidates = [s_target]
            else:
                candidates = [s_target + k*step, s_target - k*step]

            for s_candidate in candidates:
                if s_candidate < s_min - tol or s_candidate > s_max + tol:
                    continue

                rc, t_candidate = curve.LengthParameter(s_candidate)
                if not rc:
                    continue

                pt = curve.PointAt(t_candidate)
                if not point_forbidden(pt):
                    ts.append(t_candidate)
                    s_last = s_candidate
                    found = True
                    break

            if found:
                break

        if not found:
            # No safe point found in [dMin, dMax] → force a cut at s_max.
            rc, t_force = curve.LengthParameter(s_max)
            if not rc:
                break
            ts.append(t_force)
            s_last = s_max
            # continue to next segment

    # Always include curve end
    if abs(ts[-1] - t_end) > tol:
        ts.append(t_end)

    # Clean near-duplicate parameters
    ts = sorted(ts)
    clean_ts = [ts[0]]
    for t in ts[1:]:
        if abs(t - clean_ts[-1]) > tol:
            clean_ts.append(t)
    ts = clean_ts

    # ----------------------------------------------------------
    # GLOBAL small-segment cleanup (Soft-dMax):
    # Try to remove ANY segment shorter than EdgeFactor * dMin
    # by merging with a neighbor. This cleanup IGNORES dMax, so
    # merged segments may end up longer than dMax.
    # ----------------------------------------------------------
    if dMin > 0 and ef > 0.0 and len(ts) > 2:
        min_len = ef * dMin

        while True:
            n_segments = len(ts) - 1
            if n_segments <= 1:
                break

            # Find smallest segment below min_len
            idx_small = -1
            smallest = None
            for i in range(n_segments):
                L_i = curve.GetLength(rg.Interval(ts[i], ts[i + 1]))
                if L_i < min_len:
                    if smallest is None or L_i < smallest:
                        smallest = L_i
                        idx_small = i

            # No more segments below threshold → done
            if idx_small == -1:
                break

            # Decide which neighbor to merge with
            if idx_small == 0:
                # Only merge with next (delete ts[1])
                del ts[1]
            elif idx_small == n_segments - 1:
                # Only merge with previous (delete ts[-2])
                del ts[-2]
            else:
                # Can merge left or right. Choose the merge that gives
                # the shorter combined segment length (purely heuristic).
                L_prev = curve.GetLength(rg.Interval(ts[idx_small - 1], ts[idx_small + 1]))
                L_next = curve.GetLength(rg.Interval(ts[idx_small], ts[idx_small + 2]))
                if L_prev <= L_next:
                    # Merge with previous: drop ts[idx_small]
                    del ts[idx_small]
                else:
                    # Merge with next: drop ts[idx_small + 1]
                    del ts[idx_small + 1]
            # Loop again and re-evaluate smallest

    # ----- shatter & classify segments for this curve -----

    for i in range(len(ts) - 1):
        t0 = ts[i]
        t1 = ts[i + 1]
        if t1 - t0 <= tol:
            continue

        sub = curve.Trim(rg.Interval(t0, t1))
        if not sub or not sub.IsValid:
            continue

        p0 = curve.PointAt(t0)
        p1 = curve.PointAt(t1)

        if endpoint_collides(p0) or endpoint_collides(p1):
            CrvColl.append(sub)
        else:
            CrvSeg.append(sub)

    return CrvSeg, CrvColl

# --------------------------------------------------------
# Multi-curve wrapper -> DataTree outputs
# --------------------------------------------------------

CrvSeg  = DataTree[object]()
CrvColl = DataTree[object]()

tol = sc.doc.ModelAbsoluteTolerance

# Ensure we always have an iterable for C
if C is None:
    curves = []
else:
    try:
        curves = list(C)
    except TypeError:
        curves = [C]

for i, crv in enumerate(curves):
    path = GH_Path(i)
    safe_segments, coll_segments = process_curve(
        crv, Obs, dMin, dMax, ObsTol, Step, EdgeFactor, tol
    )

    for seg in safe_segments:
        CrvSeg.Add(seg, path)

    for col in coll_segments:
        CrvColl.Add(col, path)