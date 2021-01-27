from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action


class ValidateLookRenderPartition(pyblish.api.InstancePlugin):
    """Validate all shadingGroups are in the default 'renderPartition'

    Maya ShadingGroups should be in the default 'renderPartition', and if one
    shader is not in the partition you'll be running into errors like this:
        // Warning: line 1: Node 'shape.instObjGroups[0]' cannot
                            make assignment to 'SG' shader.
        // Error: line 1: Error while parsing arguments. //

    It all has to do with Maya Partitions.

    Maya uses partitions to decide what "sets" have exclusive membership, like
    for example renderPartition which is the default for any Shading Group.
    The way it works is that if something is inside that partition then
    whatever is inside those sets cannot be a member in other sets out of that
    partition or in other partitions.

    Imagine a single shader being accidentally removed from renderPartition.
    As such it may only be assigned to objects that are currently not in any
    set of the renderPartition , basically meaning "it may currently not have
    any shader assigned". As such, when you break the connection from other
    shaders then suddenly you can assign it. Funnily enough, once you've
    assigned the erroneous shader with that hack you then cannot assign any
    other shader that is inside the renderPartition. Even new shaders will be
    disallowed to get assigned until the Shape is not a member of a set in
    another partition.

    As such, the best fix is to have your shaders correctly in the
    renderPartition.

    """

    order = colorbleed.api.ValidateContentsOrder + 0.01
    families = ['colorbleed.look']
    hosts = ['maya']
    label = 'Look Shaders in RenderPartition'
    actions = [colorbleed.maya.action.SelectInvalidAction,
               colorbleed.api.RepairAction]

    def process(self, instance):
        """Process all the nodes in the instance"""

        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Shading Groups found that are not in "
                               "'renderPartition': {0}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):

        members = set(cmds.partition("renderPartition", query=True))

        # Get shading engine connections
        nodes = instance[:]
        shaders = set(cmds.listConnections(nodes, type="shadingEngine") or [])

        # Detect shadingEngines that are not a member of renderPartition
        invalid = shaders - members

        return list(invalid)

    @classmethod
    def repair(cls, instance):

        invalid = cls.get_invalid(instance)
        if invalid:
            cmds.partition(invalid, add="renderPartition")
