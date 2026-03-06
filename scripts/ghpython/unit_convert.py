# ALEXANDRIA IO SPEC (standardized)
# Inputs:
# - InputValue (GH: StartValue) | float|list[float] | Input value(s)
# - FromUnit (GH: From) | str | Source unit label
# - ToUnit (GH: To) | str | Target unit label
# Outputs:
# - OutputValue (GH: NewValue) | float|list[float] | Converted value(s)
# - Factor (GH: Factor) | float | Applied multiplier
# - Info (GH: Info) | str | Conversion summary
# - ValidUnits (GH: Valid) | list[str] | Accepted unit labels

"""
GhPython: Inch/Foot/Yard converter for length, area, and volume.

Inputs:
    StartValue:  float or list[float] — value(s) to convert
    From:        str — starting unit label
    To:          str — target unit label

Outputs:
    NewValue:    converted value(s)
    Factor:      scalar multiplier so that NewValue = StartValue * Factor
    Info:        message describing the conversion
    Valid:       list of accepted unit labels
"""

import re

# ---------------------- Canonical Units ----------------------
CANONICAL_LABELS = [
    "inch", "foot", "yard",
    "sq inch", "sq foot", "sq yard",
    "cu inch", "cu foot", "cu yard"
]

# ---------------------- Conversion Tables --------------------
LENGTH_FACTORS = { "inch": 1.0, "foot": 12.0, "yard": 36.0 }
AREA_FACTORS   = { "sq inch": 1.0, "sq foot": 144.0, "sq yard": 1296.0 }
VOLUME_FACTORS = { "cu inch": 1.0, "cu foot": 1728.0, "cu yard": 46656.0 }

# ---------------------- Helper Functions ---------------------
def _normalize_label(label):
    if not isinstance(label, str):
        raise ValueError("Unit label must be text")
    s = label.strip().lower().replace(".", "").replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s

def parse_unit(label):
    """Match user input to canonical unit"""
    s = _normalize_label(label)
    # length
    if s in ["in", "inch", "inches"]: return "inch"
    if s in ["ft", "foot", "feet"]: return "foot"
    if s in ["yd", "yard", "yards"]: return "yard"
    # area
    if s in ["sq inch", "square inch", "square inches", "in^2", "in2"]: return "sq inch"
    if s in ["sq foot", "square foot", "square feet", "ft^2", "ft2"]: return "sq foot"
    if s in ["sq yard", "square yard", "square yards", "yd^2", "yd2"]: return "sq yard"
    # volume
    if s in ["cu inch", "cubic inch", "cubic inches", "in^3", "in3"]: return "cu inch"
    if s in ["cu foot", "cubic foot", "cubic feet", "ft^3", "ft3"]: return "cu foot"
    if s in ["cu yard", "cubic yard", "cubic yards", "yd^3", "yd3"]: return "cu yard"
    raise ValueError("Unrecognized unit label: '{}'".format(label))

def factor_from_to(u_from, u_to):
    """Get multiplicative factor (same dimensional group only)"""
    if u_from in LENGTH_FACTORS and u_to in LENGTH_FACTORS:
        f = LENGTH_FACTORS[u_from] / LENGTH_FACTORS[u_to]
    elif u_from in AREA_FACTORS and u_to in AREA_FACTORS:
        f = AREA_FACTORS[u_from] / AREA_FACTORS[u_to]
    elif u_from in VOLUME_FACTORS and u_to in VOLUME_FACTORS:
        f = VOLUME_FACTORS[u_from] / VOLUME_FACTORS[u_to]
    else:
        raise ValueError("Dimension mismatch between '{}' and '{}'".format(u_from, u_to))
    return f

# ---------------------- Main Execution -----------------------
try:
    u_from = parse_unit(From)
    u_to   = parse_unit(To)
    Factor = factor_from_to(u_from, u_to)

    if isinstance(StartValue, (list, tuple)):
        NewValue = [float(v) * Factor for v in StartValue]
    else:
        NewValue = float(StartValue) * Factor

    Info = "Converted {} → {}  (multiplied by {:.6f})".format(u_from, u_to, Factor)
    Valid = CANONICAL_LABELS[:]

except Exception as e:
    NewValue = None
    Factor = None
    Info = "Error: {}".format(e)
    Valid = CANONICAL_LABELS[:]
