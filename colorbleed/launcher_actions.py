import os

from avalon import api, pipeline, lib

import acre


class FusionRenderNode(api.Action):

    name = "fusionrendernode"
    label = "F9 Render Node"
    icon = "object-group"
    order = 997

    def is_compatible(self, session):
        """Return whether the action is compatible with the session"""
        if "AVALON_PROJECT" in session:
            return False
        return True

    def process(self, session, **kwargs):
        """Implement the behavior for when the action is triggered

        Args:
            session (dict): environment dictionary

        Returns:
            Popen instance of newly spawned process

        """

        # Update environment with session and the current environment
        tools_env = acre.get_tools(["global", "fusionnode9"])
        env = acre.compute(tools_env)
        env = acre.merge(env, current_env=dict(os.environ))

        # Get executable by name
        executable = acre.which(self.name, env)
        if not executable:
            raise ValueError("Unable to find executable %s" % self.name)

        return acre.launch(executable=executable, args=[], environment=env)


class VrayRenderSlave(api.Action):

    name = "vrayrenderslave"
    label = "V-Ray Slave"
    icon = "object-group"
    order = 996

    def is_compatible(self, session):
        """Return whether the action is compatible with the session"""
        if "AVALON_PROJECT" in session:
            return False
        return True

    def process(self, session, **kwargs):
        """Implement the behavior for when the action is triggered

        Args:
            session (dict): environment dictionary

        Returns:
            Popen instance of newly spawned process

        """

        # Update environment with session
        tools_env = acre.get_tools(["global", "maya2018", "vrayrenderslave"])
        env = acre.compute(tools_env)
        env = acre.merge(env, current_env=dict(os.environ))

        # Get executable by name
        executable = acre.which("vray", env)

        # Run as server
        args = ["-server", "-portNumber=20207"]
        return acre.launch(executable=executable, args=args, environment=env)


def register_launcher_actions():
    """Register specific actions which should be accessible in the launcher"""

    pipeline.register_plugin(api.Action, FusionRenderNode)
    pipeline.register_plugin(api.Action, VrayRenderSlave)
