import os
import logging

import hou

from pyblish import api as pyblish

from avalon import api as avalon
from avalon.houdini import pipeline as houdini

from colorbleed.houdini import lib

from colorbleed.lib import (
    any_outdated,
    update_task_from_path
)

from ..lib import get_asset_fps


PARENT_DIR = os.path.dirname(__file__)
PACKAGE_DIR = os.path.dirname(PARENT_DIR)
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")

PUBLISH_PATH = os.path.join(PLUGINS_DIR, "houdini", "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "houdini", "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "houdini", "create")

log = logging.getLogger("colorbleed.houdini")


def install():

    pyblish.register_plugin_path(PUBLISH_PATH)
    avalon.register_plugin_path(avalon.Loader, LOAD_PATH)
    avalon.register_plugin_path(avalon.Creator, CREATE_PATH)

    log.info("Installing callbacks ... ")
    avalon.before("save", before_save)
    avalon.on("save", on_save)
    avalon.on("open", on_open)
    avalon.on("new", on_new)

    pyblish.register_callback("instanceToggled", on_pyblish_instance_toggled)

    log.info("Setting default family states for loader..")
    avalon.data["familiesStateToggled"] = ["colorbleed.imagesequence"]

    # Set asset FPS for the empty scene directly after launch of Houdini
    # so it initializes into the correct scene FPS
    _set_asset_fps()


def before_save(*args):
    return lib.validate_fps()


def on_save(*args):

    avalon.logger.info("Running callback on save..")

    update_task_from_path(hou.hipFile.path())

    nodes = lib.get_id_required_nodes()
    for node, new_id in lib.generate_ids(nodes):
        lib.set_id(node, new_id, overwrite=False)


def on_open(*args):

    avalon.logger.info("Running callback on open..")

    update_task_from_path(hou.hipFile.path())

    # Validate FPS after update_task_from_path to
    # ensure it is using correct FPS for the asset
    lib.validate_fps()

    if any_outdated():
        from ..widgets import popup

        log.warning("Scene has outdated content.")

        # Get main window
        parent = hou.ui.mainQtWindow()
        if parent is None:
            log.info("Skipping outdated content pop-up "
                     "because Maya window can't be found.")
        else:

            # Show outdated pop-up
            def _on_show_inventory():
                import avalon.tools.sceneinventory as tool
                tool.show(parent=parent)

            dialog = popup.Popup(parent=parent)
            dialog.setWindowTitle("Houdini scene has outdated content")
            dialog.setMessage("There are outdated containers in "
                              "your Houdini scene.")
            dialog.on_clicked.connect(_on_show_inventory)
            dialog.show()


def on_new(_):
    """Set project resolution and fps when create a new file"""
    avalon.logger.info("Running callback on new..")
    _set_asset_fps()


def _set_asset_fps():
    """Set Houdini scene FPS to the default required for current asset"""

    # Set new scene fps
    fps = get_asset_fps()
    print("Setting scene FPS to %i" % fps)
    lib.set_scene_fps(fps)


def on_pyblish_instance_toggled(instance, new_value, old_value):
    """Toggle saver tool passthrough states on instance toggles."""

    nodes = instance[:]
    if not nodes:
        return

    # Assume instance node is first node
    instance_node = nodes[0]

    if instance_node.isBypassed() != (not old_value):
        print("%s old bypass state didn't match old instance state, "
              "updating anyway.." % instance_node.path())

    instance_node.bypass(not new_value)
