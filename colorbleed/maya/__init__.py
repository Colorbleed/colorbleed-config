import os
import logging
import weakref
from functools import partial

from maya import utils
from maya import cmds

from avalon import api as avalon, pipeline, maya
from pyblish import api as pyblish

from ..lib import (
    update_task_from_path,
    any_outdated
)
from . import menu
from . import lib

log = logging.getLogger("colorbleed.maya")

PARENT_DIR = os.path.dirname(__file__)
PACKAGE_DIR = os.path.dirname(PARENT_DIR)
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")

PUBLISH_PATH = os.path.join(PLUGINS_DIR, "maya", "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "maya", "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "maya", "create")


def install():
    pyblish.register_plugin_path(PUBLISH_PATH)
    avalon.register_plugin_path(avalon.Loader, LOAD_PATH)
    avalon.register_plugin_path(avalon.Creator, CREATE_PATH)

    menu.install()

    log.info("Installing callbacks ... ")
    avalon.on("init", on_init)
    avalon.on("save", on_save)
    avalon.on("open", on_open)

    log.info("Overriding existing event 'taskChanged'")
    override_event("taskChanged", on_task_changed)


def uninstall():
    pyblish.deregister_plugin_path(PUBLISH_PATH)
    avalon.deregister_plugin_path(avalon.Loader, LOAD_PATH)
    avalon.deregister_plugin_path(avalon.Creator, CREATE_PATH)

    menu.uninstall()


def override_event(event, callback):
    """
    Override existing event callback
    Args:
        event (str): name of the event
        callback (function): callback to be triggered

    Returns:
        None

    """

    ref = weakref.WeakSet()
    ref.add(callback)

    pipeline._registered_event_handlers[event] = ref


def on_init(_):
    avalon.logger.info("Running callback on init..")

    def safe_deferred(fn):
        """Execute deferred the function in a try-except"""

        def _fn():
            """safely call in deferred callback"""
            try:
                fn()
            except Exception as exc:
                print(exc)

        try:
            utils.executeDeferred(_fn)
        except Exception as exc:
            print(exc)

    cmds.loadPlugin("AbcImport", quiet=True)
    cmds.loadPlugin("AbcExport", quiet=True)

    from .customize import override_component_mask_commands
    safe_deferred(override_component_mask_commands)


def on_save(_):
    """Automatically add IDs to new nodes
    Any transform of a mesh, without an existing ID,
    is given one automatically on file save.
    """

    avalon.logger.info("Running callback on save..")

    # Update current task for the current scene
    update_task_from_path(cmds.file(query=True, sceneName=True))

    # Generate ids of the current context on nodes in the scene
    nodes = lib.get_id_required_nodes(referenced_nodes=False)
    for node, new_id in lib.generate_ids(nodes):
        lib.set_id(node, new_id, overwrite=False)


def on_open(_):
    """On scene open let's assume the containers have changed."""

    from avalon.vendor.Qt import QtWidgets
    from ..widgets import popup

    # Update current task for the current scene
    update_task_from_path(cmds.file(query=True, sceneName=True))

    if any_outdated():
        log.warning("Scene has outdated content.")

        # Find maya main window
        top_level_widgets = {w.objectName(): w for w in
                             QtWidgets.QApplication.topLevelWidgets()}
        parent = top_level_widgets.get("MayaWindow", None)

        if parent is None:
            log.info("Skipping outdated content pop-up "
                     "because Maya window can't be found.")
        else:

            # Show outdated pop-up
            def _on_show_inventory():
                import avalon.tools.cbsceneinventory as tool
                tool.show(parent=parent)

            dialog = popup.Popup(parent=parent)
            dialog.setWindowTitle("Maya scene has outdated content")
            dialog.setMessage("There are outdated containers in "
                              "your Maya scene.")
            dialog.on_show.connect(_on_show_inventory)
            dialog.show()


def on_task_changed(*args):
    """Wrapped function of app initialize and maya's on task changed"""

    # Inputs (from the switched session and running app)
    session = avalon.Session.copy()
    app_name = os.environ["AVALON_APP_NAME"]

    # Find the application definition
    app_definition = pipeline.lib.get_application(app_name)

    App = type("app_%s" % app_name,
               (avalon.Application,),
               {"config": app_definition.copy()})

    # Initialize within the new session's environment
    app = App()
    env = app.environ(session)
    app.initialize(env)

    # Run
    maya.pipeline._on_task_changed()
