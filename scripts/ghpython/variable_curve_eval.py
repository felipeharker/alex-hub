# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - Curve (GH: Crv) | Rhino.Geometry.Curve | Curve to sample
# - FocusRatio (GH: Focus) | float | Density focus ratio 0..1
# - MinSpacing (GH: MinS) | float | Minimum spacing
# - MaxSpacing (GH: MaxS) | float | Maximum spacing
# - Radius (GH: Radius) | float | Influence radius
# - FalloffMode (GH: FalloffMode) | int | 0 Gaussian / 1 Smooth / 2 Linear
# Outputs:
# - Pts (GH: Pts) | list[Rhino.Geometry.Point3d] | Sampled points
# - Params (GH: t) | list[float] | Curve parameters at sampled points

"""GhPython Component: Variable-density curve sampling (focus as ratio, falloff as slider)

Inputs:
    Crv:          Rhino.Geometry.Curve
    Focus:        float in [0..1] — where density is highest (reparameterized along length)
    MinS:         float > 0 — minimum spacing (most dense)
    MaxS:         float >= MinS — maximum spacing (least dense)
    Radius:       float > 0 — influence radius in length units
    FalloffMode:  int in {0,1,2} — 0:Gaussian, 1:Smooth, 2:Linear

Outputs:
    Pts:          list[Rhino.Geometry.Point3d]
    t:            list[float] curve parameters at sampled points
"""

import math
from Rhino.Geometry import Curve, Point3d, Interval

# -------------------------- Utilities --------------------------------------

def clamp(x, a, b):
    return a if x < a else (b if x > b else x)

def length_to_param(crv, s):
    rc, tt = crv.LengthParameter(s)
    if rc: return tt
    # Edge clamp fallback
    return crv.Domain.T0 if s <= 0.0 else crv.Domain.T1

def param_to_length(crv, tt):
    return crv.GetLength(Interval(crv.Domain.T0, tt))

def falloff_weight(u, mode):
    """u = normalized distance d/Radius >=0. Return weight in [0..1]."""
    if mode == 0:  # Gaussian
        return math.exp(-0.5 * u * u)
    elif mode == 1:  # Smooth (compact C1, falls to 0 at u>=1)
        u = clamp(u, 0.0, 1.0)
        s = u*u*(3.0 - 2.0*u)  # smoothstep
        return 1.0 - s
    elif mode == 2:  # Linear (compact)
        return max(0.0, 1.0 - u)
    # default to Gaussian
    return math.exp(-0.5 * u * u)

def spacing_at_length(s, s_focus, minS, maxS, radius, mode):
    """Local spacing field s(l) given arc-length l and focus location."""
    if radius <= 0.0:
        return maxS
    d = abs(s - s_focus)
    w = falloff_weight(d / radius, mode)
    return maxS - (maxS - minS) * w

def march(crv, start_len, direction, minS, maxS, radius, mode, end_len):
    """Step from start_len toward end_len (direction = +1 or -1) with variable spacing."""
    pts, ts = [], []
    t0 = length_to_param(crv, start_len)
    pts.append(crv.PointAt(t0))
    ts.append(t0)

    s_focus = start_len
    s = start_len
    L = crv.GetLength()
    max_iters = 100000
    it = 0

    while True:
        it += 1
        if it > max_iters:
            break

        local = spacing_at_length(s, s_focus, minS, maxS, radius, mode)
        local = max(local, 1e-9)

        s_next = s + direction * local
        if direction > 0 and s_next > end_len: break
        if direction < 0 and s_next < end_len: break

        t_next = length_to_param(crv, s_next)
        pts.append(crv.PointAt(t_next))
        ts.append(t_next)
        s = s_next

    return pts, ts

# -------------------------- Main -------------------------------------------

Pts, t = [], []

if Crv is None or not isinstance(Crv, Curve):
    pass
else:
    L = Crv.GetLength()
    if L > 0:
        # Sanitize inputs
        Focus = 0.0 if Focus is None else clamp(float(Focus), 0.0, 1.0)
        MinS = 0.1 if (MinS is None or MinS <= 0.0) else float(MinS)
        MaxS = float(MaxS) if (MaxS is not None and MaxS >= MinS) else MinS
        Radius = float(Radius) if (Radius is not None and Radius > 0.0) else (0.25 * L)
        mode = int(FalloffMode) if FalloffMode is not None else 0
        if mode not in (0,1,2): mode = 0

        # Resolve focus as arc length (ratio * total length)
        s_focus = Focus * L

        # March outwards from focus in both directions
        f_pts, f_ts = march(Crv, s_focus, +1, MinS, MaxS, Radius, mode, L)
        b_pts, b_ts = march(Crv, s_focus, -1, MinS, MaxS, Radius, mode, 0.0)

        # Ensure curve ends included
        # Start
        if not b_ts or abs(b_ts[-1] - Crv.Domain.T0) > 1e-12:
            b_pts.append(Crv.PointAt(Crv.Domain.T0))
            b_ts.append(Crv.Domain.T0)
        # End
        if not f_ts or abs(f_ts[-1] - Crv.Domain.T1) > 1e-12:
            f_pts.append(Crv.PointAt(Crv.Domain.T1))
            f_ts.append(Crv.Domain.T1)

        # Merge: backward (from start -> focus), then forward (focus -> end)
        b_pts = list(reversed(b_pts))
        b_ts  = list(reversed(b_ts))

        # Avoid duplicate focus point if both sides share it
        if b_ts and f_ts and abs(b_ts[-1] - f_ts[0]) < 1e-12:
            Pts = b_pts + f_pts[1:]
            t   = b_ts  + f_ts[1:]
        else:
            Pts = b_pts + f_pts
            t   = b_ts  + f_ts
