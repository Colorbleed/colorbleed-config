import os

import pyblish.api
import avalon.api

from .launcher_actions import register_launcher_actions
from .lib import collect_container_metadata

PACKAGE_DIR = os.path.dirname(__file__)
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")

# Global plugin paths
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "global", "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "global", "load")


def install():
    print("Registering global plug-ins..")
    pyblish.api.register_plugin_path(PUBLISH_PATH)
    avalon.api.register_plugin_path(avalon.api.Loader, LOAD_PATH)

    # Register default "local" target
    print("Registering pyblish target: local")
    pyblish.api.register_target("local")


def uninstall():
    print("Deregistering global plug-ins..")
    pyblish.api.deregister_plugin_path(PUBLISH_PATH)
    avalon.api.deregister_plugin_path(avalon.api.Loader, LOAD_PATH)

    pyblish.api.deregister_target("local")
