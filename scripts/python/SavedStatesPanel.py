import Eto.Forms as forms
import Eto.Drawing as drawing
import scriptcontext as sc
import rhinoscriptsyntax as rs
import json

KEY = "SavedStatesPanelDB"


def load_states():
    data = sc.doc.Strings.GetValue(KEY)
    if not data:
        return {}
    try:
        return json.loads(data)
    except:
        return {}


def save_states(db):
    sc.doc.Strings.SetString(KEY, json.dumps(db))


class SavedStatesPanel(forms.Panel):

    def __init__(self):

        self.db = load_states()

        self.listbox = forms.ListBox()
        self.refresh()

        create_btn = forms.Button(Text="Create")
        activate_btn = forms.Button(Text="Activate")
        delete_btn = forms.Button(Text="Delete")

        create_btn.Click += self.create_state
        activate_btn.Click += self.activate_state
        delete_btn.Click += self.delete_state

        layout = forms.DynamicLayout()
        layout.AddRow(self.listbox)
        layout.AddRow(create_btn, activate_btn, delete_btn)

        self.Content = layout


    def refresh(self):
        self.db = load_states()
        self.listbox.DataStore = list(self.db.keys())


    def create_state(self, sender, e):

        views = rs.NamedViews()
        view = rs.ListBox(views, "Pick Named View")

        states = list(sc.doc.NamedLayerStates.Names)
        layer = rs.ListBox(states, "Pick Layer State")

        name = rs.GetString("Name Saved State")

        if not name:
            return

        self.db[name] = {
            "view": view,
            "layer": layer
        }

        save_states(self.db)
        self.refresh()


    def activate_state(self, sender, e):

        name = self.listbox.SelectedValue

        if not name:
            return

        data = self.db[name]

        rs.Command('_-NamedView _Restore "{}"'.format(data["view"]), False)
        rs.Command('_-LayerStateManager _Restore "{}"'.format(data["layer"]), False)


    def delete_state(self, sender, e):

        name = self.listbox.SelectedValue

        if not name:
            return

        del self.db[name]

        save_states(self.db)
        self.refresh()