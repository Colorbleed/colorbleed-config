import os
import string

from avalon import api, lib, pipeline
from avalon.vendor import six


class BaseProjectAction(api.Action):
    """A Base Action that mimics avalon core Application action.

    However this one does not need an AVALON_WORKDIR or asset and task
    to operate on. It can run just on the base of the project and will
    not initialize any work folder.

    This allows to use the same .toml setup for defining the application
    environment, so we can mimic configuration but allow to run them in
    a different state.

    """

    def __init__(self):
        self.config = lib.get_application(self.name)

    def environ(self, session):
        """Build application environment"""

        session = session.copy()

        # Construct application environment from .toml config
        app_environment = self.config.get("environment", {})
        for key, value in app_environment.copy().items():
            if isinstance(value, list):
                # Treat list values as paths, e.g. PYTHONPATH=[]
                app_environment[key] = os.pathsep.join(value)

            elif isinstance(value, six.string_types):
                if lib.PY2:
                    # Protect against unicode in the environment
                    encoding = sys.getfilesystemencoding()
                    app_environment[key] = value.encode(encoding)
                else:
                    app_environment[key] = value
            else:
                log.error(
                    "%s: Unsupported environment reference in %s for %s"
                    % (value, self.name, key)
                )

        # Build environment
        env = os.environ.copy()
        env.update(session)
        app_environment = self._format(app_environment, **env)
        env.update(app_environment)

        return env

    def launch(self, environment):

        executable = lib.which(self.config["executable"],
                               env=environment)
        if executable is None:
            raise ValueError(
                "'%s' not found on your PATH\n%s"
                % (self.config["executable"], environment.get("PATH"))
            )

        args = self.config.get("args", [])
        return lib.launch(
            executable=executable,
            args=args,
            environment=environment
        )

    def process(self, session, **kwargs):
        """Process the full Application action"""

        environment = self.environ(session)

        if kwargs.get("launch", True):

            # todo(roy): Push this elsewhere
            # This is temporarily done here so it just directly works with
            # the current launcher's get_apps() function discovery upon
            # entering
            # a project.
            tools = environment.get("AVALON_TOOLS", "").split(";")
            if tools:
                # Launch through acre when AVALON TOOLS is provided.
                import acre

                # Build Application environment using Acre
                tools_env = acre.get_tools(tools)
                env = acre.compute(tools_env)
                environment = acre.merge(env, current_env=environment)

            return self.launch(environment)

    def _format(self, original, **kwargs):
        """Utility recursive dict formatting that logs the error clearly."""

        try:
            return lib.dict_format(original, **kwargs)
        except KeyError as e:
            log.error(
                "One of the {variables} defined in the application "
                "definition wasn't found in this session.\n"
                "The variable was %s " % e
            )
            log.error(json.dumps(kwargs, indent=4, sort_keys=True))

            raise ValueError(
                "This is typically a bug in the pipeline, "
                "ask your developer.")


class FusionRenderNode(BaseProjectAction):

    name = "fusion9rendernode"
    label = "F9 Render Node"
    icon = "object-group"
    order = 997
    color = "#AA9999"

    def is_compatible(self, session):
        # Only show outside of project for clean project view
        return "AVALON_PROJECT" not in session


class VrayRenderSlave(BaseProjectAction):

    name = "vrayrenderslave"
    label = "V-Ray Slave"
    icon = "object-group"
    order = 996
    color = "#AA9999"

    def is_compatible(self, session):
        # Only show outside of project for clean project view
        return "AVALON_PROJECT" not in session


class ExploreToCurrent(api.Action):
    name = "exploretocurrent"
    label = "Explore Here"
    icon = "external-link"
    color = "#e8770e"
    order = 7

    def is_compatible(self, session):
        return True

    def process(self, session, **kwargs):

        from avalon import io
        from avalon.vendor.Qt import QtCore, QtWidgets

        class FormatDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        def partial_format(s, mapping):

            formatter = string.Formatter()
            mapping = FormatDict(**mapping)

            return formatter.vformat(s, (), mapping)

        project = io.find_one({"type": "project"})
        template = project["config"]['template']['work']

        # Some data remapping
        values = dict(session)
        for key, value in {
            "AVALON_PROJECT": "project",
            "AVALON_PROJECTS": "root",
            "AVALON_ASSET": "asset",
            "AVALON_SILO": "silo",
            "AVALON_TASK": "task",
        }.items():
            if key in session:
                values[value] = session[key]

        path = partial_format(template, values)

        # Keep only the part of the path that was formatted
        path = os.path.normpath(path.split("{", 1)[0])

        app = QtWidgets.QApplication.instance()
        ctrl_pressed = QtCore.Qt.ControlModifier & app.keyboardModifiers()
        if ctrl_pressed:
            # Copy path to clipboard
            self.copy_path_to_clipboard(path)
        else:
            self.open_in_explorer(path)

    @staticmethod
    def open_in_explorer(path):
        import subprocess

        if os.path.exists(path):
            print("Opening Explorer: %s" % path)
            # todo(roy): Make this cross OS compatible (currently windows only)
            subprocess.Popen(r'explorer "{}"'.format(path))

        else:
            print("Path does not exist: %s" % path)

    @staticmethod
    def copy_path_to_clipboard(path):
        from avalon.vendor.Qt import QtCore, QtWidgets

        path = path.replace("\\", "/")
        print("Copyied to clipboard: %s" % path)
        app = QtWidgets.QApplication.instance()
        assert app, "Must have running QApplication instance"

        # Set to Clipboard
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(os.path.normpath(path))


def register_launcher_actions():
    """Register specific actions which should be accessible in the launcher"""

    pipeline.register_plugin(api.Action, FusionRenderNode)
    pipeline.register_plugin(api.Action, VrayRenderSlave)
    pipeline.register_plugin(api.Action, ExploreToCurrent)
