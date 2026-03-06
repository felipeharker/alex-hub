# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - ImagePath (GH: Path) | str | Image file path
# - UVPts (GH: UV) | list[Rhino.Geometry.Point2d] | UV sample coordinates (0..1)
# - Mode (GH: Mode) | str | Clamp/Repeat/Mirror mode
# - FlipV (GH: FlipV) | bool | Flip V direction
# Outputs:
# - Colors (GH: C) | list[System.Drawing.Color] | Sampled colors
# - Gray01 (GH: G) | list[float] | Luminance values 0..1
# - Size (GH: Size) | str | Image pixel size text
# - Report (GH: Report) | str | Execution summary

"""Image Sampler via File Path (UV in 0..1)
Author: FHarker + ChatGPT (2025.10)
"""

import System
import os, math
import scriptcontext  # ✅ must be imported first
from System.Drawing import Bitmap, Color
from Rhino.Geometry import Point2d

# ---------- helpers ----------
def _mirror_wrap(t):
    ti = math.floor(t)
    frac = t - ti
    if int(ti) % 2 != 0:
        frac = 1.0 - frac
    return frac

def wrap01(x, mode):
    if mode == 0:  # Clamp
        return max(0.0, min(1.0, x))
    elif mode == 1:  # Repeat
        return x - math.floor(x)
    else:  # Mirror
        return _mirror_wrap(x)

def bilinear_sample(bmp, x, y):
    """x,y in pixel space (float). Returns Color via bilinear filtering."""
    w, h = bmp.Width, bmp.Height
    x = max(0.0, min(w - 1.0, x))
    y = max(0.0, min(h - 1.0, y))

    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    x1 = min(x0 + 1, w - 1)
    y1 = min(y0 + 1, h - 1)

    fx = x - x0
    fy = y - y0

    c00 = bmp.GetPixel(x0, y0)
    c10 = bmp.GetPixel(x1, y0)
    c01 = bmp.GetPixel(x0, y1)
    c11 = bmp.GetPixel(x1, y1)

    def lerp(a, b, t): return a + (b - a) * t

    a0 = lerp(c00.A, c10.A, fx); a1 = lerp(c01.A, c11.A, fx); a = int(lerp(a0, a1, fy))
    r0 = lerp(c00.R, c10.R, fx); r1 = lerp(c01.R, c11.R, fx); r = int(lerp(r0, r1, fy))
    g0 = lerp(c00.G, c10.G, fx); g1 = lerp(c01.G, c11.G, fx); g = int(lerp(g0, g1, fy))
    b0 = lerp(c00.B, c10.B, fx); b1 = lerp(c01.B, c11.B, fx); b = int(lerp(b0, b1, fy))

    return Color.FromArgb(a, r, g, b)

def to_gray01(col):
    return (0.2126*col.R + 0.7152*col.G + 0.0722*col.B) / 255.0

def as_uv2(pt):
    return float(pt.X), float(pt.Y)

# ---------- sticky cache ----------
key = "img_cache_v1"
cache = scriptcontext.sticky.get(key, {})

def get_bitmap(path):
    if not path or not os.path.isfile(path):
        return None, "No file at path."
    try:
        mtime = os.path.getmtime(path)
    except:
        mtime = None
    entry = cache.get(path)
    if entry and entry.get("mtime") == mtime:
        return entry["bmp"], "Cached"
    try:
        bmp = Bitmap(path)
        cache[path] = {"bmp": bmp, "mtime": mtime}
        scriptcontext.sticky[key] = cache
        return bmp, "Loaded"
    except Exception as e:
        return None, "Load error: %s" % e

# ---------- main ----------
mode_map = {"clamp": 0, "repeat": 1, "mirror": 2}
m = mode_map.get((Mode or "Clamp").strip().lower(), 0)

bmp, status = get_bitmap(Path)
C, G = [], []

if bmp is None:
    Size = "0x0"
    Report = "Image not available. " + status
else:
    w, h = bmp.Width, bmp.Height
    Size = "{}x{}".format(w, h)
    for p in UV:
        u, v = as_uv2(p)
        u = wrap01(u, m)
        v = wrap01(v, m)
        if FlipV:
            v = 1.0 - v
        x = u * (w - 1)
        y = v * (h - 1)
        col = bilinear_sample(bmp, x, y)
        C.append(col)
        G.append(to_gray01(col))
    Report = "OK ({})".format(status)
