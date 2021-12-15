import maya.cmds as cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateRenderFilenamePrefix(pyblish.api.InstancePlugin):
    """Validate the render filename prefix is set as required.

    Note:
        The required filename prefix differs when you are rendering more
        than a single camera from a renderlayer.

    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Render Filename Prefix"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]
    actions = [colorbleed.api.RepairAction]

    settings = {
        # Single Camera renders
        "single": {
            "vray": "<Scene>/<Scene>_<Layer>/<Layer>",
            "arnold": "<Scene>/<Scene>_<RenderLayer>/"
                      "<RenderLayer>.<RenderPass>",
            "default": "<Scene>/<Scene>_<RenderLayer>/<RenderLayer>"
        },
        # Multi Camera renders
        "multi": {
            "vray": "<Scene>/<Scene>_<Camera>_<Layer>/<Camera>_<Layer>",
            "arnold": "<Scene>/<Scene>_<Camera>_<RenderLayer>/"
                      "<Camera>_<RenderLayer>.<RenderPass>",
            "default": "<Scene>/<Scene>_<Camera>_<RenderLayer>/"
                       "<Camera>_<RenderLayer>"
        }
    }

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Invalid render settings found for '%s'!"
                             % instance.name)

    @classmethod
    def get_invalid(cls, instance):

        renderer = instance.data["renderer"]
        layer = instance.data["setMembers"]

        # Get the current prefix value for the current renderer
        attrs = lib.RENDER_ATTRS.get(renderer, lib.RENDER_ATTRS["default"])
        prefix = lib.get_attr_in_layer("{node}.{prefix}".format(**attrs),
                                       layer=layer)

        required_prefix = cls._get_required_prefix(instance)
        if prefix != required_prefix:
            cls.log.error("Found: %s  - Expected: %s" % (prefix,
                                                         required_prefix))
            return [layer]

    @classmethod
    def repair(cls, instance):
        """Set the required filename prefix"""

        renderer = instance.data['renderer']
        layer_node = instance.data['setMembers']

        with lib.renderlayer(layer_node):

            defaults = lib.RENDER_ATTRS['default']
            attrs = lib.RENDER_ATTRS.get(renderer, defaults)
            prefix_attr = "{node}.{prefix}".format(**attrs)

            required_prefix = cls._get_required_prefix(instance)
            cmds.setAttr(prefix_attr, required_prefix, type="string")

    @classmethod
    def _get_required_prefix(cls, instance):
        """Helper method to get the correct prefix value from `settings`"""

        renderer = instance.data["renderer"]
        count = len(instance.data["cameras"])
        key = "multi" if count > 1 else "single"
        prefixes = cls.settings[key]

        prefix = prefixes.get(renderer, prefixes["default"])

        # For arnold whenever Merge AOVS is enabled make sure that
        # .<RenderPass> is removed from the file path prefix, otherwise
        # AOVs will still never get merged.
        if renderer == "arnold":
            layer = instance.data["setMembers"]
            merge_aovs = lib.get_attr_in_layer("defaultArnoldDriver.mergeAOVs",
                                               layer=layer)
            if merge_aovs:
                prefix = prefix.replace(".<RenderPass>", "")

        return prefix

