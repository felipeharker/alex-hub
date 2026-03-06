# SavedState Manager (Named View + Layer State)
# Rhino 7/8 Python (EditPythonScript / RunPythonScript)
# Stores mappings in the 3DM via doc.Strings as JSON.
#
# Commands provided via UI menu:
# - CreateState: pick 1 Named View + 1 Layer State, then name the combo
# - ViewSavedState: pick a combo and restore both
# - DeleteState: remove a combo

import json
import rhinoscriptsyntax as rs
import scriptcontext as sc

DOC_KEY = "SavedStates::ViewLayerState::v1"  # storage key inside 3DM

# -----------------------------
# Storage helpers
# -----------------------------
def _load_db():
    s = sc.doc.Strings.GetValue(DOC_KEY)
    if not s:
        return {}
    try:
        db = json.loads(s)
        return db if isinstance(db, dict) else {}
    except Exception:
        return {}

def _save_db(db):
    sc.doc.Strings.SetString(DOC_KEY, json.dumps(db, indent=2, sort_keys=True))

# -----------------------------
# Rhino tables helpers
# -----------------------------
def _get_named_view_names():
    names = rs.NamedViews()
    return sorted(names) if names else []

def _get_layer_state_table():
    """
    Rhino 8+: layer states are exposed via RhinoDoc.NamedLayerStates (NamedLayerStateTable)
    """
    doc = sc.doc
    if doc and hasattr(doc, "NamedLayerStates") and doc.NamedLayerStates:
        return doc.NamedLayerStates
    return None

def _get_layer_state_names():
    tbl = _get_layer_state_table()
    if not tbl:
        return []
    # Rhino 8: Names is a property (string[])
    if hasattr(tbl, "Names"):
        try:
            names = list(tbl.Names) or []
            return sorted([n for n in names if n])
        except Exception:
            return []
    # Fallback for older patterns (if present)
    if hasattr(tbl, "GetNames"):
        try:
            names = list(tbl.GetNames()) or []
            return sorted([n for n in names if n])
        except Exception:
            return []
    return []

def _restore_named_view(view_name):
    # Use command to avoid RhinoCommon signature differences
    rs.Command('_-NamedView _Restore "{}" _Enter'.format(view_name), echo=False)

def _restore_layer_state(state_name):
    tbl = _get_layer_state_table()
    if tbl:
        # Rhino 8: Restore(string) exists on NamedLayerStateTable
        try:
            tbl.Restore(state_name)
            return True
        except Exception:
            pass

    # Fallback to command line restore
    rs.Command('_-LayerStateManager _Restore "{}" _Enter'.format(state_name), echo=False)
    return True

# -----------------------------
# UI helpers
# -----------------------------
def _pick_one(title, items):
    if not items:
        return None
    return rs.ListBox(items, title=title, message=title)

# -----------------------------
# Actions
# -----------------------------
def create_state():
    view_names = _get_named_view_names()
    if not view_names:
        rs.MessageBox("No Named Views found. Create a Named View first.", 0, "SavedState")
        return

    layer_states = _get_layer_state_names()
    if not layer_states:
        rs.MessageBox(
            "No Layer States found.\n\n"
            "Open LayerStateManager and Save at least one Layer State, then run again.",
            0,
            "SavedState"
        )
        return

    v = _pick_one("Pick a Named View", view_names)
    if not v:
        return

    ls = _pick_one("Pick a Layer State", layer_states)
    if not ls:
        return

    name = rs.GetString("Name the new SavedState", "STATE_01")
    if not name:
        return

    db = _load_db()
    if name in db:
        yn = rs.MessageBox('SavedState "{}" already exists.\nOverwrite?'.format(name), 4, "SavedState")
        if yn != 6:  # 6 == Yes
            return

    db[name] = {"named_view": v, "layer_state": ls}
    _save_db(db)

    rs.MessageBox(
        'SavedState "{}" created:\n\n- View: {}\n- Layer State: {}'.format(name, v, ls),
        0,
        "SavedState"
    )

def view_saved_state():
    db = _load_db()
    if not db:
        rs.MessageBox("No SavedStates exist in this file yet.\nRun CreateState first.", 0, "SavedState")
        return

    state_names = sorted(db.keys())
    pick = _pick_one("Pick a SavedState to restore", state_names)
    if not pick:
        return

    rec = db.get(pick, {})
    v = rec.get("named_view")
    ls = rec.get("layer_state")

    if v:
        _restore_named_view(v)
    if ls:
        _restore_layer_state(ls)

    sc.doc.Views.Redraw()

def delete_state():
    db = _load_db()
    if not db:
        rs.MessageBox("No SavedStates to delete.", 0, "SavedState")
        return

    state_names = sorted(db.keys())
    pick = _pick_one("Pick a SavedState to delete", state_names)
    if not pick:
        return

    yn = rs.MessageBox('Delete SavedState "{}"?'.format(pick), 4, "SavedState")
    if yn != 6:
        return

    db.pop(pick, None)
    _save_db(db)
    rs.MessageBox('Deleted "{}".'.format(pick), 0, "SavedState")

def main():
    actions = ["CreateState", "ViewSavedState", "DeleteState"]
    pick = _pick_one("SavedState Manager: choose an action", actions)
    if pick == "CreateState":
        create_state()
    elif pick == "ViewSavedState":
        view_saved_state()
    elif pick == "DeleteState":
        delete_state()

if __name__ == "__main__":
    main()