import os
import sys

from Qt import QtWidgets, QtCore

from .pipeline import (
    publish
)

from avalon import api
from avalon.tools import (
    creator,
    loader,
    sceneinventory,
    workfiles
)


def load_stylesheet():
    path = os.path.join(os.path.dirname(__file__), "menu_style.qss")
    if not os.path.exists(path):
        print("Unable to load stylesheet, file not found in resources")
        return ""

    with open(path, "r") as file_stream:
        stylesheet = file_stream.read()
    return stylesheet


class Spacer(QtWidgets.QWidget):
    def __init__(self, height, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

        self.setFixedHeight(height)

        real_spacer = QtWidgets.QWidget(self)
        real_spacer.setObjectName("Spacer")
        real_spacer.setFixedHeight(height)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(real_spacer)

        self.setLayout(layout)


class Menu(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

        self.setObjectName("AvalonMenu")

        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.CustomizeWindowHint
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.render_mode_widget = None
        self.setWindowTitle("Avalon")
        
        asset_label = QtWidgets.QLabel("Context", self)
        asset_label.setStyleSheet("""QLabel {
            font-size: 14px;
            font-weight: 600;
            color: #ffaf24;
        }""")
        asset_label.setAlignment(QtCore.Qt.AlignHCenter)
        
        workfiles_btn = QtWidgets.QPushButton("Workfiles", self)
        create_btn = QtWidgets.QPushButton("Create...", self)
        load_btn = QtWidgets.QPushButton("Load...", self)
        publish_btn = QtWidgets.QPushButton("Publish...", self)
        inventory_btn = QtWidgets.QPushButton("Manage...", self)
        #rendermode_btn = QtWidgets.QPushButton("Set render mode", self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)
        
        layout.addWidget(asset_label)

        layout.addWidget(Spacer(15, self))
        
        layout.addWidget(workfiles_btn)

        layout.addWidget(Spacer(15, self))

        layout.addWidget(create_btn)
        layout.addWidget(load_btn)
        layout.addWidget(publish_btn)
        layout.addWidget(inventory_btn)

        #layout.addWidget(Spacer(15, self))

        #layout.addWidget(rendermode_btn)

        self.setLayout(layout)
        
        self.asset_label = asset_label

        self.resize(250, 100)

        workfiles_btn.clicked.connect(self.on_workfile_clicked)
        create_btn.clicked.connect(self.on_create_clicked)
        publish_btn.clicked.connect(self.on_publish_clicked)
        load_btn.clicked.connect(self.on_load_clicked)
        inventory_btn.clicked.connect(self.on_inventory_clicked)
        #rendermode_btn.clicked.connect(self.on_rendermode_clicked)
        
        self._callbacks = []
        self.register_callback("taskChanged", self.on_task_changed)
        self.on_task_changed()
        
    def on_task_changed(self):
        # Update current context label
        label = api.Session["AVALON_ASSET"]
        self.asset_label.setText(label)
        
    def register_callback(self, name, fn):
        
        # Create a wrapper callback that we only store
        # for as long as we want it to persist as callback
        callback = lambda *args: fn()
        self._callbacks.append(callback)
        api.on(name, callback)
    
    def deregister_all_callbacks(self):
        self._callbacks[:] = []

    def on_workfile_clicked(self):
        print("Clicked Workfile")
        workfiles.show()

    def on_create_clicked(self):
        print("Clicked Create")
        creator.show()

    def on_publish_clicked(self):
        print("Clicked Publish")
        publish()

    def on_load_clicked(self):
        print("Clicked Load")
        loader.show(use_context=True)

    def on_inventory_clicked(self):
        print("Clicked Inventory")
        sceneinventory.show()

    def on_rendermode_clicked(self):
        from avalon import style
        print("Clicked Set Render Mode")
        if self.render_mode_widget is None:
            window = set_rendermode.SetRenderMode()
            window.setStyleSheet(style.load_stylesheet())
            window.show()
            self.render_mode_widget = window
        else:
            self.render_mode_widget.show()
        
    def closeEvent(self, event):
        self.deregister_all_callbacks()
        super(Menu, self).closeEvent(event)


def launch_menu():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    menu = Menu()

    stylesheet = load_stylesheet()
    menu.setStyleSheet(stylesheet)

    menu.show()

    sys.exit(app.exec_())

