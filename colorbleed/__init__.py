import os
import json

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

    # Set a Pyblish QML post collector order: pyblish-qml#356
    post_collector_order = str(pyblish.api.CollectorOrder + 0.3)
    os.environ["PYBLISH_QML_POST_COLLECT"] = post_collector_order

    # Try and set project specific environment if it has implemented any
    # todo: implement better project-specific settings
    template = "{AVALON_PROJECTS}/{AVALON_PROJECT}/resources/pipeline/env.json"
    override_path = template.format(**avalon.api.Session)
    if os.path.isfile(override_path):
        print("Loading project env override: %s" % override_path)
        try:
            with open(override_path, "r") as f:
                override = json.load(f)
                override = {str(key): str(value) for key, value in
                            override.items()}
                os.environ.update(override)
        except Exception as exc:
            print(exc)


def uninstall():
    print("Deregistering global plug-ins..")
    pyblish.api.deregister_plugin_path(PUBLISH_PATH)
    avalon.api.deregister_plugin_path(avalon.api.Loader, LOAD_PATH)

    pyblish.api.deregister_target("local")
