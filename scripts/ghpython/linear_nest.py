# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - CutLengths (GH: L) | list[float] | Requested cut lengths
# - StockLength (GH: StockLen) | float | Per-stock bar length
# - RowSpacing (GH: Spacing) | float | Vertical spacing between rows
# Outputs:
# - StockLines (GH: StockLines) | list[Rhino.Geometry.Line] | Stock bar lines
# - CutLines (GH: CutLines) | list[Rhino.Geometry.Line] | Placed cuts as lines
# - StickIds (GH: StickIds) | list[int] | Stock index per cut

"""Cut stock nesting visualizer (1D) for Grasshopper

Inputs:
    L        : list[float]  - required cut lengths (same units as StockLen)
    StockLen : float        - stock length (e.g. 288 for 24')
    Spacing  : float        - vertical spacing between each stock bar in the drawing

Outputs:
    StockLines : list[rg.Line] - full-length stock bars
    CutLines   : list[rg.Line] - one line per cut, positioned on its stock bar
    StickIds   : list[int]     - index of stock bar for each cut (0-based)
"""

import Rhino.Geometry as rg

# ----------------------------------------------------------------------
# Initialize outputs
# ----------------------------------------------------------------------
StockLines = []
CutLines = []
StickIds = []

# ----------------------------------------------------------------------
# Coerce and validate inputs (no top-level returns)
# ----------------------------------------------------------------------

# Stock length
stock_len = 0.0
if StockLen is not None:
    try:
        stock_len = float(StockLen)
    except:
        stock_len = 0.0

# Spacing between stock bars
spacing = 0.0
if Spacing is not None:
    try:
        spacing = float(Spacing)
    except:
        spacing = 0.0

if spacing < 0.0:
    spacing = 0.0

# Collect valid cut lengths
cuts_raw = []
if L is not None:
    for x in L:
        if x is None:
            continue
        try:
            v = float(x)
        except:
            continue
        if v > 0.0:
            cuts_raw.append(v)

# If inputs are not usable, do nothing (outputs stay empty)
if stock_len <= 0.0:
    # invalid stock length
    pass
elif not cuts_raw:
    # no valid cuts
    pass
else:
    # ------------------------------------------------------------------
    # First-Fit Decreasing bin packing (no kerf)
    # ------------------------------------------------------------------

    # Sort cuts from longest to shortest
    cuts_sorted = sorted(cuts_raw, reverse=True)

    # Each stick = {'used': float, 'cuts': [lengths]}
    sticks = []

    for c_len in cuts_sorted:
        placed = False

        # Try to place in existing sticks
        for stick in sticks:
            if stick['used'] + c_len <= stock_len + 1e-6:
                stick['cuts'].append(c_len)
                stick['used'] += c_len
                placed = True
                break

        # If it did not fit anywhere, start a new stick
        if not placed:
            sticks.append({'cuts': [c_len], 'used': c_len})

    # ------------------------------------------------------------------
    # Generate 2D line geometry
    # ------------------------------------------------------------------

    for si, stick in enumerate(sticks):
        # Vertical position for this stock bar
        y = si * spacing

        # Full stock line
        stock_start = rg.Point3d(0.0, y, 0.0)
        stock_end   = rg.Point3d(stock_len, y, 0.0)
        StockLines.append(rg.Line(stock_start, stock_end))

        # Cuts laid out from left to right along this bar
        x = 0.0
        for c_len in stick['cuts']:
            p0 = rg.Point3d(x, y, 0.0)
            p1 = rg.Point3d(x + c_len, y, 0.0)
            CutLines.append(rg.Line(p0, p1))
            StickIds.append(si)
            x += c_len
