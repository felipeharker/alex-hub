# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - AttractorPts (GH: Attractors) | list[Rhino.Geometry.Point3d] | Attractor points
# - GeoPts (GH: GeoPts) | list[Rhino.Geometry.Point3d] | Evaluated geometry points
# - ScaleClosest (GH: ScaleClosest) | float | Value at nearest attractor distance
# - ScaleFarthest (GH: ScaleFarthest) | float | Value at farthest attractor distance
# Outputs:
# - Remapped (GH: Remapped) | list[float] | Remapped value per GeoPt

"""GhPython: Multi-point attractor with remapped values

Inputs:
    Attractors   : list[Rhino.Geometry.Point3d] - attractor points
    GeoPts       : list[Rhino.Geometry.Point3d] - geometry / evaluation points
    ScaleClosest : float - value when point is closest to any attractor
    ScaleFarthest: float - value when point is farthest from all attractors

Output:
    Remapped     : list[float] - remapped values per geometry point
"""

import Rhino.Geometry as rg

Remapped = []

# Safety checks
if not Attractors or not GeoPts:
    # Nothing to compute
    Remapped = []
else:
    # ------------------------------------------------------------
    # 1. Compute minimum distance from each GeoPt to all Attractors
    # ------------------------------------------------------------
    min_dists = []
    for p in GeoPts:
        # Compute distance to each attractor and take the minimum
        d_min = None
        for a in Attractors:
            d = p.DistanceTo(a)
            if d_min is None or d < d_min:
                d_min = d
        min_dists.append(d_min)

    # ------------------------------------------------------------
    # 2. Find global min/max distance for normalization
    # ------------------------------------------------------------
    d_min_global = min(min_dists)
    d_max_global = max(min_dists)

    # ------------------------------------------------------------
    # 3. Remap distances -> [ScaleClosest ... ScaleFarthest]
    #    Closest distance  -> ScaleClosest
    #    Farthest distance -> ScaleFarthest
    # ------------------------------------------------------------
    Remapped = []

    # Avoid division by zero if all distances are identical
    if d_max_global == d_min_global:
        # All points are at the same distance; use ScaleClosest for all
        Remapped = [ScaleClosest for _ in min_dists]
    else:
        span = float(d_max_global - d_min_global)
        for d in min_dists:
            # Normalize to [0, 1]
            t = (d - d_min_global) / span
            # Linear interpolation between ScaleClosest and ScaleFarthest
            value = ScaleClosest + t * (ScaleFarthest - ScaleClosest)
            Remapped.append(value)
