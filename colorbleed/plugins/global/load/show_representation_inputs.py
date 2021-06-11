from avalon.vendor.Qt import QtWidgets, QtCore
from avalon import api
from avalon.tools import representationinput


def get_main_window():
    """Return top level QMainWindow"""
    top_widgets = QtWidgets.QApplication.topLevelWidgets()
    main_window = next((widget for widget in top_widgets if
                       widget.inherits("QMainWindow")), None)
    return main_window


class ShowRepresentationInputs(api.Loader):
    """Show Inputs/Outputs"""

    families = ["*"]
    representations = ["*"]

    label = "Show Inputs/Outputs"
    order = 999
    icon = "play-circle"
    color = "#444444"

    def load(self, context, name, namespace, data):

        representation = context["representation"]["_id"]

        parent = get_main_window()
        widget = representationinput.RepresentationWidget(parent=parent)
        widget.model.load([representation])
        widget.on_mode_changed()

        widget.setWindowTitle("List inputs/outputs for %s" % name)
        widget.resize(850, 400)
        widget.show()
