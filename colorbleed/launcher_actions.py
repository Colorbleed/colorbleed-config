import os
import pprint

import avalon.pipeline as pipeline
import avalon.api as avalon

from env_prototype import api


class FusionRenderNode(avalon.Action):

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
        tools_env = api.get_tools(["global", "fusionnode9"])

        env = api.compute(tools_env)
        env = api.merge(env, current_env=dict(os.environ))
        print("Environment %s" % pprint.pformat(env))

        exe = api.which(self.name, env)
        if not exe:
            raise ValueError("Unable to find executable: %s" % self.name)

        print("Launching: %s" % exe)
        return api.execute(exe, environment=env, args=[])


def register_launcher_actions():
    """Register specific actions which should be accessible in the launcher"""

    # Register fusion actions
    pipeline.register_plugin(avalon.Action, FusionRenderNode)
