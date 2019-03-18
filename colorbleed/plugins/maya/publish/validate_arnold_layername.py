import maya.cmds as cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateArnoldLayerName(pyblish.api.InstancePlugin):
    """Validate preserve layer name is enabled when rendering with Arnold"""

    order = colorbleed.api.ValidateContentsOrder
    label = "Arnold Preserve Layer Name"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]
    actions = [colorbleed.api.RepairAction]

    def process(self, instance):

        if instance.data.get("renderer", None) != "arnold":
            # If not rendering with Arnold, ignore..
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Invalid render settings found for '%s'!"
                             % instance.name)

    @classmethod
    def get_invalid(cls, instance):

        drivers = cmds.ls("defaultArnoldDriver", type="aiAOVDriver")
        assert len(drivers) == 1, "Must have one defaultArnoldDriver"

        driver = drivers[0]
        if not cmds.getAttr("{0}.preserveLayerName".format(driver)):
            return True

    @classmethod
    def repair(cls, instance):
        cmds.setAttr("defaultArnoldDriver.preserveLayerName", True)
