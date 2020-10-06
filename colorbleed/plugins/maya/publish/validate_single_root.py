import pyblish.api
import colorbleed.api

import colorbleed.maya.action
import colorbleed.maya.lib as lib


class ValidateSingleRoot(pyblish.api.InstancePlugin):
    """Ensure the content of the instance is grouped in a single hierarchy

    The instance must have a single root node containing all the content.

    Example outliner:
        root_GRP
            -- geometry_GRP
               -- mesh_GEO
            -- controls_GRP
               -- control_CTL

    Note: This could include nodes that are not directly in the member set
          but are "input connections" to those members as History. If you
          find invalid nodes in the output make sure they are not a member
          of the instance set nor have connections to members.

    """

    order = colorbleed.api.ValidateContentsOrder
    hosts = ['maya']
    families = ['colorbleed.yetiRig']
    label = 'Single Root Hierarchy'
    actions = [colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):

        roots = self.get_invalid(instance)
        assert len(roots) > 0, (
            "One hierarchy required for: %s (currently empty?)" % instance)
        assert len(roots) < 2, (
            'Multiple hierarchies found: %s' % list(roots))

    @classmethod
    def get_invalid(cls, instance):
        """Get all nodes which do not match the criteria"""

        from maya import cmds

        dag = cmds.ls(instance, type="dagNode", long=True)
        roots = lib.get_highest_in_hierarchy(dag)
        return list(set(roots))
