import maya.cmds as cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateArnoldLayerName(pyblish.api.InstancePlugin):
    """Validate frame/animation ext formatting with Arnold"""

    order = colorbleed.api.ValidateContentsOrder
    label = "Arnold Frame/Animation Ext"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer.arnold"]
    actions = [colorbleed.api.RepairAction]

    # This combination of attribute values results in name.#.ext output files
    settings = {
        "outFormatControl": 0,
        "animation": 1,
        "putFrameBeforeExt": 1,
        "extensionPadding": 4,
        "periodInExt": 1,
    }

    def process(self, instance):

        if instance.data.get("renderer", None) != "arnold":
            # If not rendering with Arnold, ignore..
            return

        node = "defaultRenderGlobals"
        for attr, value in self.settings.items():
            plug = "{0}.{1}".format(node, attr)
            current = cmds.getAttr(plug)
            if current != value:
                raise RuntimeError("Frame/Animation formatting not set "
                                   "correctly, should be: name.#.ext")

    @classmethod
    def repair(cls, instance):

        node = "defaultRenderGlobals"
        for attr, value in cls.settings.items():
            plug = "{0}.{1}".format(node, attr)
            current = cmds.getAttr(plug)
            if current != value:
                print("Changing %s: %s -> %s" % (plug, current, value))
                cmds.setAttr(plug, value)
