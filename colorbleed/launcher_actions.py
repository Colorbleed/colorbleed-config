import os

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

        executable = lib.which(self.config["executable"])
        if executable is None:
            raise ValueError(
                "'%s' not found on your PATH\n%s"
                % (self.config["executable"], os.getenv("PATH"))
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

    name = "fusionrendernode9"
    label = "F9 Render Node"
    icon = "object-group"
    order = 997


class VrayRenderSlave(BaseProjectAction):

    name = "vrayrenderslave"
    label = "V-Ray Slave"
    icon = "object-group"
    order = 996


def register_launcher_actions():
    """Register specific actions which should be accessible in the launcher"""

    pipeline.register_plugin(api.Action, FusionRenderNode)
    pipeline.register_plugin(api.Action, VrayRenderSlave)
