from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action
import colorbleed.maya.lib as lib


class ValidateJointsHidden(pyblish.api.InstancePlugin):
    """Validate all joints are hidden visually.

    This includes being hidden:
        - visibility off,
        - in a display layer that has visibility off,
        - having hidden parents or
        - being an intermediate object.

    """

    order = colorbleed.api.ValidateContentsOrder
    hosts = ['maya']
    families = ['colorbleed.rig']
    category = 'rig'
    version = (0, 1, 0)
    label = "Joints Hidden"
    actions = [colorbleed.maya.action.SelectInvalidAction,
               colorbleed.api.RepairAction]

    @staticmethod
    def get_invalid(instance):
    
        def _bone_draws(j):
            """Return whether joint has not set Draw Style to None.
            
            Because when set to None the bone basically is invisible.
            """
            return cmds.getAttr(j + ".drawStyle") != 2
    
        joints = cmds.ls(instance, type='joint', long=True)
        return [j for j in joints if _bone_draws(j) and lib.is_visible(j, displayLayer=True)]

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""
        invalid = self.get_invalid(instance)

        if invalid:
            raise ValueError("Visible joints found: {0}".format(invalid))

    @classmethod
    def repair(cls, instance):
        invalid = cls.get_invalid(instance)
        cmds.hide(invalid)