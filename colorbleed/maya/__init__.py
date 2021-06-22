import os
import logging
import weakref

from maya import utils, cmds, mel

from avalon.maya.pipeline import (
    IS_HEADLESS,
    _menu as avalon_menu
)
from avalon import api as avalon, pipeline, maya
from pyblish import api as pyblish

from ..lib import (
    update_task_from_path,
    notify_loaded_representations
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

    # The `init` callback is required in headless mode to load referenced
    # Alembics correctly at rendertime without errors.
    log.info("Installing callbacks ... ")
    avalon.on("init", on_init)

    # The other Callbacks below are not required for headless mode
    # Also menus and other UI cosmetics can be ignored in batch mode.
    if IS_HEADLESS:
        log.info("Running in headless mode, skipping Colorbleed Maya "
                 "save/open/new callback installation..")
        return

    menu.install()

    avalon.on("save", on_save)
    avalon.on("open", on_open)
    avalon.on("new", on_new)
    avalon.before("save", on_before_save)

    log.info("Overriding existing event 'taskChanged'")
    override_event("taskChanged", on_task_changed)

    log.info("Setting default family states for loader..")
    avalon.data["familiesStateToggled"] = [
        "colorbleed.imagesequence",
        "colorbleed.review"
    ]


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

    # Force load Alembic so referenced alembics
    # work correctly on scene open
    cmds.loadPlugin("AbcImport", quiet=True)
    cmds.loadPlugin("AbcExport", quiet=True)

    try:
        # Try and load Maya Security tools by default
        print("Loading Maya Security tools..")
        cmds.loadPlugin("MayaScanner", quiet=True)
        cmds.loadPlugin("MayaScannerCB", quiet=True)
    except RuntimeError as exc:
        log.warning("Maya Security Scanning Tools could not be loaded: %s", exc)

    # Process everything below only when not in headless batch mode
    # since they are purely cosmetic UI changes for the artists.
    if IS_HEADLESS:
        return

    # Force load objExport plug-in (requested by artists)
    cmds.loadPlugin("objExport", quiet=True)

    from .customize import (
        override_component_mask_commands,
        override_toolbox_ui
    )
    safe_deferred(override_component_mask_commands)
    safe_deferred(override_toolbox_ui)

    # Add extra menu entry to Maya's Avalon Menu for "Remote Publish..."
    safe_deferred(_add_remote_publish_to_avalon_menu)


def on_before_save(return_code, _):
    """Run validation for scene's FPS prior to saving"""
    return lib.validate_fps()


def on_save(_):
    """Automatically add IDs to new nodes

    Any transform of a mesh, without an existing ID, is given one
    automatically on file save.
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

    # Update current task for the current scene
    update_task_from_path(cmds.file(query=True, sceneName=True))

    # Validate FPS after update_task_from_path to
    # ensure it is using correct FPS for the asset
    lib.validate_fps()

    # Find maya main window
    top_level_widgets = {w.objectName(): w for w in
                         QtWidgets.QApplication.topLevelWidgets()}
    parent = top_level_widgets.get("MayaWindow", None)
    notify_loaded_representations(parent=parent)


def on_new(_):
    """Set project resolution and fps when create a new file"""
    avalon.logger.info("Running callback on new..")
    with maya.suspended_refresh():
        lib.set_context_settings()


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


def _add_remote_publish_to_avalon_menu():
    """Add 'Remote Publish...' to Avalon menu"""

    log.info("Customize Avalon menu: Refactor publish menu items..")

    def _get_maya_menu_item_with_label(menu, label):
        """Return menu item in menu that matches label"""
        items = cmds.menu(avalon_menu, query=True, itemArray=True)
        for item in items:
            item_label = cmds.menuItem(item, query=True, label=True)
            if item_label == label:
                return item

    # Get "Publish..." menu item
    publish_menu_item = _get_maya_menu_item_with_label(
        menu=avalon_menu,
        label="Publish..."
    )

    # Copy icon from the Publish menu item..
    icon = cmds.menuItem(publish_menu_item,
                         query=True,
                         image=True)

    import pyblish_qml
    cmds.menuItem("Remote publish...",
                  command=lambda *args: pyblish_qml.show(
                      targets=["default", "deadline"]
                  ),
                  image=icon,
                  annotation="Submit scene to renderfarm to "
                             "be published there..",
                  insertAfter=publish_menu_item,
                  parent=avalon_menu)
