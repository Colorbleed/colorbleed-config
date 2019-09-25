import maya.cmds as cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateArnoldLogVerbosity(pyblish.api.InstancePlugin):
    """Validate log verbosity is set to higher or equal to Info for Arnold.

    With a lower verbosity than "Info" Arnold will *not* report any progress
    of the render job. As such Deadline can't show the render percentage nor
    will the logs show any information about the state of the render.

    Available verbosity levels for Arnold are:
        - 0: Errors
        - 1: Warnings
        - 2: Info
        - 3: Debug

    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Arnold Log Verbosity"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer.arnold"]
    actions = [colorbleed.api.RepairAction]

    verbosity_attr = "defaultArnoldRenderOptions.log_verbosity"

    def process(self, instance):

        if instance.data.get("renderer", None) != "arnold":
            # If not rendering with Arnold, ignore..
            return

        attr = self.verbosity_attr
        assert cmds.ls(attr), (
            "Arnold render options node does not exist, missing %s" % attr
        )

        verbosity = cmds.getAttr(attr)
        if verbosity < 2:
            raise RuntimeError("Arnold log verbosity is lower than 'Info'. "
                               "Please set the logging to Info or higher so "
                               "the render job will report its progress.")

    @classmethod
    def repair(cls, instance):
        # Set verbosity level: Info
        cmds.setAttr(cls.verbosity_attr, 2)
