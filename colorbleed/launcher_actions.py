import os
import pprint

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

        # Update environment with session
        tools_env = acre.get_tools(["global", "fusionnode9"])

        env = acre.compute(tools_env)
        env = acre.merge(env, current_env=dict(os.environ))
        print("Environment %s" % pprint.pformat(env))

        exe = acre.which(self.name, env)
        if not exe:
            raise ValueError("Unable to find executable: %s" % self.name)

        print("Launching: %s" % exe)
        return lib.launch(exe, environment=env, args=[])


def register_launcher_actions():
    """Register specific actions which should be accessible in the launcher"""

    # Register fusion actions
    pipeline.register_plugin(api.Action, FusionRenderNode)
