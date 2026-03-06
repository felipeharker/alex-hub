# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - Pts (GH: Pts) | list[Rhino.Geometry.Point3d] | Ordered source points
# - MaxGap (GH: MaxGap) | float | Max distance allowed inside segment
# Outputs:
# - Crvs (GH: Crvs) | list[Rhino.Geometry.Curve] | Interpolated segment curves
# - PtTree (GH: PtTree) | Grasshopper.DataTree[Rhino.Geometry.Point3d] | Points grouped by segment

"""
GhPython: split non-continuous point sets into curve segments.

Inputs:
    Pts:    list[Rhino.Geometry.Point3d]  - all points, in order
    MaxGap: float                         - max distance allowed inside a segment

Outputs:
    Crvs:   list[Rhino.Geometry.Curve]    - one curve per continuous segment
    PtTree: Grasshopper.DataTree[Point3d] - points grouped by segment (one branch per segment)
"""

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

Crvs = []
PtTree = DataTree[rg.Point3d]()

# Auto-estimate MaxGap if needed
if MaxGap <= 0:
    dists = []
    for i in range(1, len(Pts)):
        dists.append(Pts[i - 1].DistanceTo(Pts[i]))
    if dists:
        dists_sorted = sorted(dists)
        mid = len(dists_sorted) // 2
        median = dists_sorted[mid]
        MaxGap = 1.5 * median

# Split into continuous segments
segments = []
current = [Pts[0]]

for i in range(1, len(Pts)):
    a = Pts[i - 1]
    b = Pts[i]
    d = a.DistanceTo(b)

    if d <= MaxGap:
        # Still in the same continuous run
        current.append(b)
    else:
        # Gap detected: close current segment and start a new one
        if len(current) >= 2:
            segments.append(current)
        current = [b]

# Add the last segment
if len(current) >= 2:
    segments.append(current)

# Build curves + point tree for each segment
for seg_index, seg in enumerate(segments):
    # Interpolated curve, degree 3
    crv = rg.Curve.CreateInterpolatedCurve(seg, 3)
    if crv:
        Crvs.append(crv)

    # Add points to the DataTree, one branch per segment
    path = GH_Path(seg_index)
    for pt in seg:
        PtTree.Add(pt, path)