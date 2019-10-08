from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.action
import colorbleed.maya.action


class RepairAction(colorbleed.action.RepairAction):
    # todo: allow this to only show on warning when pyblish allows it
    on = "processed"


class SelectAction(colorbleed.maya.action.SelectInvalidAction):
    # todo: allow this to only show on warning when pyblish allows it
    label = "Select"
    on = "processed"


class ValidateInheritsTransform(pyblish.api.InstancePlugin):
    """Validates whether transforms have 'inherit transforms' enabled.

    It is technically allowed to disable "Inherit Transforms" however in most
    scenarios it's unwanted. As such we will show a warning whenever transform
    nodes have it disabled.

    """

    order = colorbleed.api.ValidateContentsOrder
    families = ["colorbleed.model",
                "colorbleed.pointcache"]
    hosts = ["maya"]
    label = "Inherits Transforms"
    actions = [SelectAction, RepairAction]

    @classmethod
    def get_invalid(cls, instance):

        invalid = []
        transforms = cmds.ls(instance[:], type="transform", long=True)
        for transform in transforms:
            inherit_transform = cmds.getAttr(transform + ".inheritsTransform")
            if not inherit_transform:
                invalid.append(transform)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance"""

        invalid = self.get_invalid(instance)
        if invalid:
            self.log.warning("Transforms found with inherit "
                             "transform disabled: {0}".format(invalid))

    @classmethod
    def repair(cls, instance):

        for transform in cls.get_invalid(instance):
            cls.log.info("Enabling inherits transform on: "
                         "{0}".format(transform))
            cmds.setAttr(transform + ".inheritsTransform", True)
