import pyblish.api
import colorbleed.api

from maya import cmds


class ValidateVRayRegionRenderingDisabled(pyblish.api.InstancePlugin):
    """Validate V-Ray Frame Buffer Render Region is disabled.

    It seems that V-Ray 5.0 has a bug that when batch rendering through
    Deadline that it will not ignore the V-Ray Frame Buffer region rendering
    settings even when the "Disable region rendering in batch mode" is enabled.

    """

    order = pyblish.api.ValidatorOrder
    label = "VRay Render Region Disabled Rendering"
    families = ["colorbleed.renderlayer.vray"]
    actions = [colorbleed.api.RepairAction]

    def process(self, instance):

        # Only check when running V-Ray 5+
        version = cmds.vray("version")
        major_version = int(cmds.vray("version").split(".")[0])
        if major_version != 5:
            self.log.debug("Skipping check for V-Ray version: %s. Issue is "
                           "only detected in V-Ray 5+" % version)
            return

        region = cmds.vray("vfbControl", "-getregion")
        has_region_enabled = any(int(x) != 0 for x in region)
        if has_region_enabled:
            raise RuntimeError("V-Ray Frame Buffer has region rendering "
                               "enabled. Please disable it.")

    @classmethod
    def repair(cls, instance):

        # Disable V-Ray Frame Buffer Region Render
        cmds.vray("vfbControl", "-setregionenabled", "0")
