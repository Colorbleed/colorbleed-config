import os
import site
import glob
import logging

import avalon.io as io
import avalon.api as api
import avalon.pipeline as pipeline
import avalon.fusion
import avalon.style as style
from avalon.vendor.Qt import QtWidgets, QtCore
from avalon.vendor import qtawesome as qta


log = logging.getLogger("Fusion Switch Shot")


class App(QtWidgets.QWidget):

    def __init__(self, parent=None):

        ################################################
        # |---------------------| |------------------| #
        # |Comp                 | |Asset             | #
        # |[..][              v]| |[               v]| #
        # |---------------------| |------------------| #
        # | Update existing comp [ ]                 | #
        # |------------------------------------------| #
        # |                Switch                    | #
        # |------------------------------------------| #
        ################################################

        QtWidgets.QWidget.__init__(self, parent)

        layout = QtWidgets.QVBoxLayout()

        # Comp related input
        comp_hlayout = QtWidgets.QHBoxLayout()
        comp_label = QtWidgets.QLabel("Comp file")
        comp_label.setFixedWidth(50)
        comp_box = QtWidgets.QComboBox()

        button_icon = qta.icon("fa.folder", color="white")
        open_from_dir = QtWidgets.QPushButton()
        open_from_dir.setIcon(button_icon)

        comp_box.setFixedHeight(25)
        open_from_dir.setFixedWidth(25)
        open_from_dir.setFixedHeight(25)

        comp_hlayout.addWidget(comp_label)
        comp_hlayout.addWidget(comp_box)
        comp_hlayout.addWidget(open_from_dir)

        # Asset related input
        asset_hlayout = QtWidgets.QHBoxLayout()
        asset_label = QtWidgets.QLabel("Shot")
        asset_label.setFixedWidth(50)

        asset_box = QtWidgets.QComboBox()
        asset_box.setLineEdit(QtWidgets.QLineEdit())
        asset_box.setFixedHeight(25)

        refresh_icon = qta.icon("fa.refresh", color="white")
        refresh_btn = QtWidgets.QPushButton()
        refresh_btn.setIcon(refresh_icon)

        asset_box.setFixedHeight(25)
        refresh_btn.setFixedWidth(25)
        refresh_btn.setFixedHeight(25)

        asset_hlayout.addWidget(asset_label)
        asset_hlayout.addWidget(asset_box)
        asset_hlayout.addWidget(refresh_btn)

        # Options
        options = QtWidgets.QHBoxLayout()
        options.setAlignment(QtCore.Qt.AlignLeft)

        current_comp_check = QtWidgets.QCheckBox()
        current_comp_check.setChecked(True)
        current_comp_label = QtWidgets.QLabel("Use current comp")

        options.addWidget(current_comp_label)
        options.addWidget(current_comp_check)

        accept_btn = QtWidgets.QPushButton("Switch")

        layout.addLayout(options)
        layout.addLayout(comp_hlayout)
        layout.addLayout(asset_hlayout)
        layout.addWidget(accept_btn)

        self._open_from_dir = open_from_dir
        self._comps = comp_box
        self._assets = asset_box
        self._use_current = current_comp_check
        self._accept_btn = accept_btn
        self._refresh_btn = refresh_btn

        self.setWindowTitle("Fusion Switch Shot")
        self.setLayout(layout)

        self.resize(260, 140)
        self.setMinimumWidth(260)
        self.setFixedHeight(140)

        self.connections()

        # Update ui to correct state
        self._on_use_current_comp()
        self._refresh()

    def connections(self):
        self._use_current.clicked.connect(self._on_use_current_comp)
        self._open_from_dir.clicked.connect(self._on_open_from_dir)
        self._refresh_btn.clicked.connect(self._refresh)
        self._accept_btn.clicked.connect(self._on_switch)

    def _on_use_current_comp(self):
        state = self._use_current.isChecked()
        self._open_from_dir.setEnabled(not state)
        self._comps.setEnabled(not state)

    def _on_open_from_dir(self):

        start_dir = self._get_context_directory()
        comp_file, _ = QtWidgets.QFileDialog.getOpenFileName(
                            self, "Choose comp", start_dir)

        if not comp_file:
            return

        # Create completer
        self.populate_comp_box([comp_file])
        self._refresh()

    def _refresh(self):
        # Clear any existing items
        self._assets.clear()

        asset_names = [a["name"] for a in self.collect_assets()]
        completer = QtWidgets.QCompleter(asset_names)

        self._assets.setCompleter(completer)
        self._assets.addItems(asset_names)

    def _on_switch(self):

        def _get_script_dir():
            """Get path to the image sequence script"""
            try:
                import colorbleed
                scriptdir = os.path.dirname(colorbleed.__file__)
                fusion_scripts = os.path.join(scriptdir,
                                              "scripts",
                                              "fusion")
            except:
                raise RuntimeError("This is a bug")

            assert os.path.isdir(fusion_scripts), "Config is incomplete"
            fusion_scripts = fusion_scripts.replace(os.sep, "/")

            return fusion_scripts

        if not self._use_current.isChecked():
            file_name = self._comps.itemData(self._comps.currentIndex())
        else:
            comp = avalon.fusion.get_current_comp()
            file_name = comp.GetAttrs("COMPS_FileName")

        asset = self._assets.currentText()

        # Get  switch and submit module
        script_dir = _get_script_dir()
        site.addsitedir(script_dir)

        import switch_and_submit as switch_shot
        switch_shot.switch(asset_name=asset, file_path=file_name, new=True)

    def _get_context_directory(self):

        project = io.find_one({"type": "project",
                               "name": api.Session["AVALON_PROJECT"]},
                              projection={"config": True})

        template = project["config"]["template"]["work"]
        dir = pipeline._format_work_template(template, api.Session)

        return dir

    def collect_slap_comps(self, directory):
        items = glob.glob("{}/*.comp".format(directory))
        return items

    def collect_assets(self):
        return list(io.find({"type": "asset", "silo": "film"}))

    def populate_comp_box(self, files):
        """Ensure we display the filename only but the path is stored as well

        Args:
            files (list): list of full file path [path/to/item/item.ext,]

        Returns:
            None
        """

        for f in files:
            filename = os.path.basename(f)
            self._comps.addItem(filename, userData=f)


if __name__ == '__main__':
    import sys
    api.install(avalon.fusion)

    app = QtWidgets.QApplication(sys.argv)
    window = App()
    window.setStyleSheet(style.load_stylesheet())
    window.show()
    sys.exit(app.exec_())
