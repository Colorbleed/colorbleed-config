from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.action


class ValidateLookDefaultShadersConnections(pyblish.api.InstancePlugin):
    """Validate default shaders in the scene have their default connections.

    For example the lambert1 could potentially be disconnected from the
    initialShadingGroup. As such it's not lambert1 that will be identified
    as the default shader which can have unpredictable results.

    To fix the default connections need to be made again. See the logs for
    more details on which connections are missing or use the Repair action
    to fix the issue automatically.

    """

    order = colorbleed.api.ValidateContentsOrder
    families = ['colorbleed.look']
    hosts = ['maya']
    label = 'Look Default Shader Connections'
    actions = [colorbleed.action.RepairAction]

    # The default connections to check
    DEFAULTS = [
        ("initialShadingGroup.surfaceShader", "lambert1"),
        ("initialParticleSE.surfaceShader", "lambert1"),
        ("initialParticleSE.volumeShader", "particleCloud1")
    ]

    @classmethod
    def iter_invalid(cls):
        """Yield the invalid connections"""
        for plug, input_node in cls.DEFAULTS:
            inputs = cmds.listConnections(plug,
                                          source=True,
                                          destination=False) or None

            if not inputs or inputs[0] != input_node:
                yield plug, input_node

    def process(self, instance):

        # Ensure check is run only once. We don't use ContextPlugin because
        # of a bug where the ContextPlugin will always be visible. Even when
        # the family is not present in an instance.
        key = "__validate_look_default_shaders_connections_checked"
        context = instance.context
        is_run = context.data.get(key, False)
        if is_run:
            return
        else:
            context.data[key] = True

        # Process as usual
        invalid = list()
        for plug, input_node in self.iter_invalid():
                self.log.error("{0} is not connected to {1}. "
                               "This can result in unexpected behavior. "
                               "Please reconnect to continue.".format(
                                plug,
                                input_node))
                invalid.append(plug)

        if invalid:
            raise RuntimeError("Invalid connections.")

    @classmethod
    def repair(cls, instance):

        for plug, input_node in cls.iter_invalid():
            source_plug = input_node + ".outColor"
            cls.log.info("Repairing connection: "
                         "{0} -> {1}".format(source_plug, plug))
            cmds.connectAttr(source_plug, plug, force=True)
