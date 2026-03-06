# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - Parts (GH: Crvs) | list[Rhino.Geometry.Curve] | Closed planar parts
# - SheetGeo (GH: Sheet) | Rhino.Geometry.GeometryBase | Rectangular sheet source
# - Spacing (GH: Spacing) | float | Part spacing
# - Rotations (GH: Rotations) | int | Rotation samples per part
# - Iterations (GH: Iterations) | int | Packing iterations
# - SortMode (GH: SortMode) | int | Part sorting strategy
# - HeuristicMode (GH: HeuristicMode) | int | Placement heuristic
# - ObjectiveMode (GH: ObjectiveMode) | int | Optimization objective
# - Run (GH: Run) | bool | Execution gate
# Outputs:
# - Nested (GH: Nested) | list[Rhino.Geometry.Curve] | Placed transformed parts
# - Sheets (GH: Sheets) | list[Rhino.Geometry.Rectangle3d] | Used sheet rectangles
# - NotNested (GH: NotNested) | list[Rhino.Geometry.Curve] | Unplaced parts

"""GhPython Component: Heuristic 2D nesting (Skyline packer + meta-heuristics)

What this does (practical + fast):
- Treats each closed curve as a planar 2D part.
- Nests using a Skyline (profile) rectangle packer.
- Meta-heuristics over multiple iterations:
  - varies ordering and placement heuristic (if enabled via -1 modes)
  - tests ALL rotation angles every iteration

IMPORTANT LIMITATIONS (explicit):
- This is NOT true polygon nesting (no No-Fit-Polygon / Minkowski). It nests *bounding boxes*.
- For production-grade polygon nesting, prefer OpenNest / NFP solvers.

Inputs (Grasshopper):
    Crvs            (list[Rhino.Geometry.Curve])  closed planar curves (2D parts)
    Sheet           (Curve or Surface or Brep or Rectangle3d) sheet boundary; must be rectangular
    Spacing         (float) clearance between parts (same units as model)
    Rotations       (int) number of rotation angles to test per part (>=1). ALL angles tested each iteration.
    Iterations      (int) number of randomized packing attempts (>=1)

    SortMode        (int)  -1=Explore, 0=AreaDesc, 1=MaxSideDesc, 2=PerimeterDesc, 3=RandomBiased
    HeuristicMode   (int)  -1=Explore, 0=BottomLeft, 1=MinYThenWaste, 2=MinWasteThenY
    ObjectiveMode   (int)  0=SheetsFirst, 1=UtilizationFirst, 2=CompactLastSheet
    
    Run             (bool) gate execution (False by default)

Outputs:
    Nested      (list[Rhino.Geometry.Curve]) transformed curves (nested on sheets)
    Sheets      (list[Rhino.Geometry.Rectangle3d]) sheet rectangles used
    NotNested   (list[Rhino.Geometry.Curve]) parts that could not be placed
"""

import Rhino
import scriptcontext as sc
import random
import math
import time

from Rhino.Geometry import (
    Curve, Brep, Surface, Rectangle3d, Plane, Transform, BoundingBox, Point3d, Vector3d, Interval
)

# -----------------------------
# Progress utilities (ALWAYS ON)
# -----------------------------

def rhino_log(msg):
    try:
        Rhino.RhinoApp.WriteLine(str(msg))
    except:
        pass

def gh_message(msg):
    try:
        ghenv.Component.Message = str(msg)
    except:
        pass

def ms_since(t0):
    return int(round((time.perf_counter() - t0) * 1000.0))

# -----------------------------
# Persistent storage across solutions
# -----------------------------

if "nest_last_run" not in sc.sticky:
    sc.sticky["nest_last_run"] = False

if "nest_last_results" not in sc.sticky:
    sc.sticky["nest_last_results"] = ([], [], [])  # (Nested, Sheets, NotNested)

run_now = False
if Run and not sc.sticky["nest_last_run"]:
    run_now = True
sc.sticky["nest_last_run"] = Run

# -----------------------------
# Helpers
# -----------------------------

def _tol(default=0.01):
    try:
        if sc.doc and hasattr(sc.doc, "ModelAbsoluteTolerance"):
            return sc.doc.ModelAbsoluteTolerance
        if Rhino.RhinoDoc.ActiveDoc:
            return Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    except:
        pass
    return default

def _is_curve_planar_closed(c, tol):
    if c is None or not isinstance(c, Curve):
        return False
    if not c.IsClosed:
        return False
    ok, _pl = c.TryGetPlane(tol)
    return ok

def _curve_area(c):
    amp = Rhino.Geometry.AreaMassProperties.Compute(c)
    return amp.Area if amp else 0.0

def _sheet_to_rect(sheet, tol):
    """
    Accept Rectangle3d, planar Curve, or Brep/Surface.
    Returns (rect_local_in_WXY, sheet_plane_world) or (None, None).
    Packing is done in local WXY, then mapped back to sheet_plane.
    """
    if sheet is None:
        return None, None

    if isinstance(sheet, Rectangle3d):
        w = sheet.Width
        h = sheet.Height
        if w <= tol or h <= tol:
            return None, None
        rect_local = Rectangle3d(Plane.WorldXY, Interval(0, w), Interval(0, h))
        return rect_local, sheet.Plane

    if isinstance(sheet, Curve):
        ok, pl = sheet.TryGetPlane(tol)
        if not ok:
            return None, None
        xform = Transform.PlaneToPlane(pl, Plane.WorldXY)
        bb = sheet.GetBoundingBox(xform)
        w = bb.Max.X - bb.Min.X
        h = bb.Max.Y - bb.Min.Y
        if w > tol and h > tol:
            rect_local = Rectangle3d(Plane.WorldXY, Interval(0, w), Interval(0, h))
            return rect_local, pl
        return None, None

    if isinstance(sheet, Surface):
        b = sheet.ToBrep()
        if b is None:
            return None, None
        sheet = b

    if isinstance(sheet, Brep):
        pl = Plane.WorldXY
        try:
            if sheet.Faces and sheet.Faces.Count > 0:
                ok, pl2 = sheet.Faces[0].TryGetPlane(tol)
                if ok:
                    pl = pl2
        except:
            pass

        xform = Transform.PlaneToPlane(pl, Plane.WorldXY)
        bb = sheet.GetBoundingBox(xform)
        w = bb.Max.X - bb.Min.X
        h = bb.Max.Y - bb.Min.Y
        if w > tol and h > tol:
            rect_local = Rectangle3d(Plane.WorldXY, Interval(0, w), Interval(0, h))
            return rect_local, pl

    return None, None

def _angles(rotations):
    r = max(1, int(rotations))
    if r == 1:
        return [0.0]
    if r == 2:
        return [0.0, 0.5 * math.pi]
    step = 2.0 * math.pi / float(r)
    return [i * step for i in range(r)]

def _bbox_data_local(crv_world, world_to_local, rot_angle, spacing):
    """
    Precompute local bbox and rotation transform for a curve.
    Returns dict:
        w, h include spacing inflation.
    """
    c = crv_world.DuplicateCurve()
    c.Transform(world_to_local)  # world -> local WXY

    bb0 = c.GetBoundingBox(True)
    center = bb0.Center

    rot = Transform.Rotation(rot_angle, Vector3d.ZAxis, center)
    c.Transform(rot)

    bb = c.GetBoundingBox(True)
    w0 = (bb.Max.X - bb.Min.X)
    h0 = (bb.Max.Y - bb.Min.Y)

    w = w0 + spacing
    h = h0 + spacing
    perim = 2.0 * (w0 + h0)

    return {
        "w": w,
        "h": h,
        "bbmin": bb.Min,
        "rot": rot,
        "bbox_area": w * h,
        "bbox_perim": perim,
        "max_side": max(w, h)
    }

# -----------------------------
# Skyline packer
# -----------------------------
# Segments are tuples (x, y, w) covering [0, sheet_w] without gaps.

def _skyline_init(sheet_w):
    return [(0.0, 0.0, float(sheet_w))]

def _skyline_merge(segments, tol=1e-9):
    if not segments:
        return []
    segments.sort(key=lambda s: s[0])
    merged = [segments[0]]
    for x, y, w in segments[1:]:
        px, py, pw = merged[-1]
        if abs((px + pw) - x) <= tol and abs(py - y) <= tol:
            merged[-1] = (px, py, pw + w)
        else:
            merged.append((x, y, w))
    return merged

def _skyline_y_and_waste(segments, start_i, rect_w):
    x = segments[start_i][0]
    x_end = x + rect_w

    y = 0.0
    i = start_i
    cur_x = x
    remaining = rect_w

    while remaining > 1e-12:
        if i >= len(segments):
            return None, None
        sx, sy, sw = segments[i]
        seg_end = sx + sw
        overlap = min(seg_end, x_end) - cur_x
        if overlap <= 0.0:
            i += 1
            continue
        if sy > y:
            y = sy
        remaining -= overlap
        cur_x += overlap
        if cur_x >= x_end - 1e-12:
            break
        i += 1

    waste = 0.0
    i = start_i
    cur_x = x
    while cur_x < x_end - 1e-12:
        sx, sy, sw = segments[i]
        seg_end = sx + sw
        overlap = min(seg_end, x_end) - cur_x
        if overlap > 0.0 and y > sy:
            waste += (y - sy) * overlap
        cur_x += overlap
        if cur_x >= x_end - 1e-12:
            break
        i += 1
        if i >= len(segments):
            return None, None

    return y, waste

def _skyline_find_position(segments, sheet_w, sheet_h, rect_w, rect_h, heuristic_mode):
    """
    heuristic_mode:
      0 = BottomLeft            (min y, then min x)
      1 = MinYThenWaste         (min y, then min waste, then min x)
      2 = MinWasteThenY         (min waste, then min y, then min x)
    """
    if rect_w > sheet_w or rect_h > sheet_h:
        return None, None, None

    best = None  # (score, x, y)
    for i, (x, _y, _w) in enumerate(segments):
        if x + rect_w > sheet_w + 1e-9:
            continue

        y, waste = _skyline_y_and_waste(segments, i, rect_w)
        if y is None:
            continue
        if y + rect_h > sheet_h + 1e-9:
            continue

        if heuristic_mode == 0:
            score = (y, x)
        elif heuristic_mode == 2:
            score = (waste, y, x)
        else:
            score = (y, waste, x)

        if best is None or score < best[0]:
            best = (score, x, y)

    if best is None:
        return None, None, None

    return best[1], best[2], best[0]

def _skyline_add_rect(segments, x, rect_w, new_top_y):
    x_end = x + rect_w
    new_segments = []

    for sx, sy, sw in segments:
        seg_end = sx + sw

        if seg_end <= x or sx >= x_end:
            new_segments.append((sx, sy, sw))
            continue

        if sx < x:
            new_segments.append((sx, sy, x - sx))

        if seg_end > x_end:
            new_segments.append((x_end, sy, seg_end - x_end))

    new_segments.append((x, new_top_y, rect_w))
    return _skyline_merge(new_segments)

def _skyline_height_used(segments):
    return max((s[1] for s in segments), default=0.0)

# -----------------------------
# Meta-heuristic packing
# -----------------------------

def _sort_items(items, stats, sort_mode, rnd):
    if sort_mode == 3:
        # Random-biased: start from area-desc then shuffle a bit
        items2 = sorted(items, key=lambda it: stats[it["id"]]["area"], reverse=True)
        return _random_biased_shuffle(items2, rnd)

    if sort_mode == 1:
        keyf = lambda it: stats[it["id"]]["max_side"]
    elif sort_mode == 2:
        keyf = lambda it: stats[it["id"]]["bbox_perim"]
    else:
        keyf = lambda it: stats[it["id"]]["area"]

    items2 = sorted(items, key=keyf, reverse=True)
    return _random_biased_shuffle(items2, rnd)

def _random_biased_shuffle(items, rnd):
    out = list(items)
    n = len(out)
    if n < 2:
        return out
    swaps = max(1, n // 5)
    for _ in range(swaps):
        a = rnd.randint(0, n - 1)
        b = rnd.randint(0, n - 1)
        out[a], out[b] = out[b], out[a]
    return out

def _pack_skyline_once(items, precomp, sheet_w, sheet_h, angles, heuristic_mode):
    placements = {}  # id -> (sheet_idx, angle, x, y)
    skylines = [ _skyline_init(sheet_w) ]
    bbox_area_used = 0.0

    for it in items:
        pid = it["id"]

        best = None  # (sheet_idx, angle, x, y, score, bbox_area)
        for si, skyline in enumerate(skylines):
            for ang in angles:
                bd = precomp[pid].get(ang, None)
                if bd is None:
                    continue

                w = bd["w"]
                h = bd["h"]

                x, y, score = _skyline_find_position(skyline, sheet_w, sheet_h, w, h, heuristic_mode)
                if x is None:
                    continue

                # Prefer earlier sheets as a tie-break
                cand_score = tuple(score) + (si,)
                if best is None or cand_score < best[4]:
                    best = (si, ang, x, y, cand_score, bd["bbox_area"])

        if best is None:
            # add a new sheet (no cap)
            skylines.append(_skyline_init(sheet_w))
            si = len(skylines) - 1
            skyline = skylines[si]

            for ang in angles:
                bd = precomp[pid].get(ang, None)
                if bd is None:
                    continue
                w = bd["w"]
                h = bd["h"]
                x, y, score = _skyline_find_position(skyline, sheet_w, sheet_h, w, h, heuristic_mode)
                if x is None:
                    continue
                best = (si, ang, x, y, tuple(score) + (si,), bd["bbox_area"])
                break

        if best is None:
            continue

        si, ang, x, y, _score, a_bbox = best
        bd = precomp[pid][ang]
        w = bd["w"]
        h = bd["h"]

        skylines[si] = _skyline_add_rect(skylines[si], x, w, y + h)
        placements[pid] = (si, ang, x, y)
        bbox_area_used += a_bbox

    unplaced_ids = [it["id"] for it in items if it["id"] not in placements]
    last_h = _skyline_height_used(skylines[-1]) if skylines else 0.0
    return placements, skylines, unplaced_ids, bbox_area_used, last_h

def _apply_placement_world(crv_world, sheet_plane_world, world_to_local, bbox_data, placement_xy, spacing):
    x, y = placement_xy
    bbmin = bbox_data["bbmin"]
    rot = bbox_data["rot"]

    c2 = crv_world.DuplicateCurve()
    c2.Transform(world_to_local)
    c2.Transform(rot)

    target = Point3d(x + 0.5 * spacing, y + 0.5 * spacing, 0.0)
    delta = target - Point3d(bbmin.X, bbmin.Y, 0.0)
    c2.Transform(Transform.Translation(delta))

    to_world = Transform.PlaneToPlane(Plane.WorldXY, sheet_plane_world)
    c2.Transform(to_world)
    return c2

# -----------------------------
# Main
# -----------------------------

Nested = []
Sheets = []
NotNested = []

if not run_now:
    Nested, Sheets, NotNested = sc.sticky["nest_last_results"]
else:
    try:
        tol = _tol()

        # Required-by-default inputs (safe defaults if None)
        sort_mode = -1 if SortMode is None else int(SortMode)
        heuristic_mode = -1 if HeuristicMode is None else int(HeuristicMode)
        objective_mode = 0 if ObjectiveMode is None else int(ObjectiveMode)

        spacing = 0.0 if Spacing is None else float(Spacing)
        spacing = max(0.0, spacing)

        rect_local, sheet_plane = _sheet_to_rect(Sheet, tol)
        if rect_local is None or sheet_plane is None:
            Nested, Sheets, NotNested = [], [], (Crvs if Crvs else [])
            sc.sticky["nest_last_results"] = (Nested, Sheets, NotNested)
        else:
            sheet_w = rect_local.Width
            sheet_h = rect_local.Height
            sheet_area = sheet_w * sheet_h

            Crvs = [] if Crvs is None else Crvs

            valid = []
            invalid = []
            for c in Crvs:
                if c is None or not isinstance(c, Curve):
                    continue
                if not _is_curve_planar_closed(c, tol):
                    invalid.append(c)
                    continue
                valid.append(c)

            world_to_local = Transform.PlaneToPlane(sheet_plane, Plane.WorldXY)

            rots = max(1, int(Rotations) if Rotations is not None else 2)
            angles = _angles(rots)  # ALL angles tested each iteration

            iters = max(1, int(Iterations) if Iterations is not None else 50)

            rhino_log("Nesting Utility activated (Skyline). Iterations: {} | Rotations tested: {}".format(iters, len(angles)))
            gh_message("Nesting: running...")

            # Precompute bbox data for all (part, angle)
            precomp = {}
            stats = {}
            items_base = []

            for pid, crv in enumerate(valid):
                precomp[pid] = {}
                area = _curve_area(crv)

                bbox_perim = 0.0
                max_side = 0.0
                for ang in angles:
                    bd = _bbox_data_local(crv, world_to_local, ang, spacing)
                    precomp[pid][ang] = bd
                    if bd["bbox_perim"] > bbox_perim:
                        bbox_perim = bd["bbox_perim"]
                    if bd["max_side"] > max_side:
                        max_side = bd["max_side"]

                stats[pid] = {
                    "area": area,
                    "bbox_perim": bbox_perim,
                    "max_side": max_side
                }
                items_base.append({"id": pid, "crv": crv})

            def bbox_util_pct(bbox_area_used, sheets_used):
                if sheets_used <= 0 or sheet_area <= 1e-12:
                    return 0.0
                return 100.0 * bbox_area_used / (sheet_area * float(sheets_used))

            def true_util_pct(placed_ids, sheets_used):
                if sheets_used <= 0 or sheet_area <= 1e-12:
                    return 0.0
                a = 0.0
                for pid in placed_ids:
                    a += stats[pid]["area"]
                return 100.0 * a / (sheet_area * float(sheets_used))

            def objective_tuple(objective_mode, unplaced_count, sheets_used, bbox_util, last_sheet_height):
                # Lower is better.
                if objective_mode == 1:
                    # UtilizationFirst
                    return (unplaced_count, sheets_used, -bbox_util, last_sheet_height)
                if objective_mode == 2:
                    # CompactLastSheet
                    return (unplaced_count, sheets_used, last_sheet_height, -bbox_util)
                # SheetsFirst
                return (unplaced_count, sheets_used, -bbox_util, last_sheet_height)

            heuristic_pool = [0, 1, 2]
            sort_pool = [0, 1, 2, 3]

            best = None

            for k in range(iters):
                iter_t0 = time.perf_counter()
                rnd = random.Random(12345 + k)

                hm = heuristic_mode
                sm = sort_mode

                # Explore modes if set to -1
                if hm == -1:
                    hm = rnd.choice(heuristic_pool)
                if sm == -1:
                    sm = rnd.choice(sort_pool)

                items_iter = _sort_items(items_base, stats, sm, rnd)

                placements, skylines, unplaced_ids, bbox_area_used, last_h = _pack_skyline_once(
                    items_iter, precomp, sheet_w, sheet_h, angles, hm
                )

                sheets_used = len(skylines)
                placed_ids = set(placements.keys())
                bbox_util = bbox_util_pct(bbox_area_used, sheets_used)
                true_util = true_util_pct(placed_ids, sheets_used)
                unplaced_count = len(unplaced_ids)

                score = objective_tuple(objective_mode, unplaced_count, sheets_used, bbox_util, last_h)

                elapsed = ms_since(iter_t0)

                # ALWAYS LOG EACH ITERATION
                rhino_log(
                    "iter {:>3}/{:<3} | hm {} sm {} | {:>4} ms | sheets {:>2} | unplaced {:>3} | bbox {:>5.1f}% | true {:>5.1f}% | lastH {:>6.1f}".format(
                        k + 1, iters, hm, sm, elapsed, sheets_used, unplaced_count, bbox_util, true_util, last_h
                    )
                )
                gh_message("Iter {}/{} | sheets {} | bbox {:.0f}% | {} ms".format(k + 1, iters, sheets_used, bbox_util, elapsed))

                if best is None or score < best["score"]:
                    best = {
                        "score": score,
                        "placements": placements,
                        "skylines": skylines,
                        "unplaced_ids": unplaced_ids,
                        "bbox_util": bbox_util,
                        "true_util": true_util,
                        "sheets_used": sheets_used,
                        "hm": hm,
                        "sm": sm
                    }

                if unplaced_count == 0 and sheets_used == 1:
                    break

            if best is None:
                Nested, Sheets, NotNested = [], [], (valid + invalid)
                sc.sticky["nest_last_results"] = (Nested, Sheets, NotNested)
            else:
                placements = best["placements"]
                sheets_used = best["sheets_used"]

                # Build sheet rectangles in world (stacked in +X for visualization)
                offset_dx = sheet_w * 1.10
                for si in range(sheets_used):
                    pl = Plane(sheet_plane)
                    pl.Origin = sheet_plane.Origin + (sheet_plane.XAxis * (offset_dx * si))
                    rect_world = Rectangle3d(pl, rect_local.X, rect_local.Y)
                    Sheets.append(rect_world)

                # Build nested curves
                for it in items_base:
                    pid = it["id"]
                    if pid not in placements:
                        continue
                    si, ang, x, y = placements[pid]

                    pl = Plane(sheet_plane)
                    pl.Origin = sheet_plane.Origin + (sheet_plane.XAxis * (offset_dx * si))

                    bbox_data = precomp[pid][ang]
                    c_out = _apply_placement_world(it["crv"], pl, world_to_local, bbox_data, (x, y), spacing)
                    Nested.append(c_out)

                NotNested = [valid[pid] for pid in best["unplaced_ids"]] + list(invalid)

                rhino_log(
                    "Nesting complete (Skyline). Sheets: {} | BBox util: {:.1f}% | True util: {:.1f}% | hm {} sm {}".format(
                        sheets_used, best["bbox_util"], best["true_util"], best["hm"], best["sm"]
                    )
                )
                gh_message("Done | Sheets {} | bbox {:.0f}%".format(sheets_used, best["bbox_util"]))

                sc.sticky["nest_last_results"] = (Nested, Sheets, NotNested)

    except Exception as e:
        rhino_log("Nesting failed: {}".format(e))
        gh_message("Nesting: failed")
        Nested, Sheets, NotNested = sc.sticky["nest_last_results"]
