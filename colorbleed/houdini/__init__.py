import os
import sys
import logging
import contextlib

import hou

from pyblish import api as pyblish

from avalon import api as avalon
from avalon.houdini import pipeline as houdini

from colorbleed.houdini import lib

from colorbleed.lib import (
    notify_loaded_representations,
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
    avalon.data["familiesStateToggled"] = [
        "colorbleed.imagesequence",
        "colorbleed.review"
    ]

    # Expose Houdini husdoutputprocessors
    hou_setup_pythonpath = os.path.join(os.path.dirname(PACKAGE_DIR),
                                        "setup", "houdini", "pythonpath")
    print("Adding PYTHONPATH: %s" % hou_setup_pythonpath)
    sys.path.append(hou_setup_pythonpath)

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

    if not hou.isUIAvailable():
        log.debug("Batch mode detected, ignoring `on_open` callbacks..")
        return

    avalon.logger.info("Running callback on open..")

    update_task_from_path(hou.hipFile.path())

    # Validate FPS after update_task_from_path to
    # ensure it is using correct FPS for the asset
    lib.validate_fps()

    parent = hou.ui.mainQtWindow()
    notify_loaded_representations(parent=parent)


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

    @contextlib.contextmanager
    def main_take(no_update=True):
        """Enter root take during context"""
        original_take = hou.takes.currentTake()
        original_update_mode = hou.updateModeSetting()
        root = hou.takes.rootTake()
        has_changed = False
        try:
            if original_take != root:
                has_changed = True
                if no_update:
                    hou.setUpdateMode(hou.updateMode.Manual)
                hou.takes.setCurrentTake(root)
                yield
        finally:
            if has_changed:
                if no_update:
                    hou.setUpdateMode(original_update_mode)
                hou.takes.setCurrentTake(original_take)

    if not instance.data.get("_allowToggleBypass", True):
        return

    nodes = instance[:]
    if not nodes:
        return

    # Assume instance node is first node
    instance_node = nodes[0]

    if not hasattr(instance_node, "isBypassed"):
        # Likely not a node that can actually be bypassed
        log.debug("Can't bypass node: %s", instance_node.path())
        return

    if instance_node.isBypassed() != (not old_value):
        print("%s old bypass state didn't match old instance state, "
              "updating anyway.." % instance_node.path())

    try:
        # Go into the main take, because when in another take changing
        # the bypass state of a note cannot be done due to it being locked
        # by default.
        with main_take(no_update=True):
            instance_node.bypass(not new_value)
    except hou.PermissionError as exc:
        log.warning("%s - %s", instance_node.path(), exc)
