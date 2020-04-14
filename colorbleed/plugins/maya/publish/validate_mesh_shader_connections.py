from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action

from colorbleed.lib import pairwise


def disconnect(node_a, node_b):
    """Remove all connections between node a and b."""

    # Disconnect outputs
    outputs = cmds.listConnections(node_a,
                                   plugs=True,
                                   connections=True,
                                   source=False,
                                   destination=True)
    for output, destination in pairwise(outputs):
        if destination.split(".", 1)[0] == node_b:
            cmds.disconnectAttr(output, destination)

    # Disconnect inputs
    inputs = cmds.listConnections(node_a,
                                  plugs=True,
                                  connections=True,
                                  source=True,
                                  destination=False)
    for input, source in pairwise(inputs):
        if source.split(".", 1)[0] == node_b:
            cmds.disconnectAttr(source, input)


def get_invalid_sets(shapes):
    """Return invalid sets for the given shapes.

    This takes a list of shape nodes to cache the set members for overlapping
    sets in the queries. This avoids many Maya set member queries.

    Returns:
        dict: Dictionary of shapes and their invalid sets, e.g.
            {"pCubeShape": ["set1", "set2"]}

    """

    cache = dict()
    invalid = dict()

    # Collect the sets from the shape
    for shape in shapes:
        invalid_sets = []
        sets = cmds.listSets(object=shape, t=1, extendToShape=False) or []
        for set_ in sets:

            members = cache.get(set_, None)
            if members is None:
                members = set(cmds.ls(cmds.sets(set_,
                                                query=True,
                                                nodesOnly=True), long=True))
                cache[set_] = set()

            # If the shape is not actually present as a member of the set
            # consider it invalid
            if shape not in members:
                invalid_sets.append(set_)

        if invalid_sets:
            invalid[shape] = invalid_sets

    return invalid


class ValidateMeshShaderConnections(pyblish.api.InstancePlugin):
    """Ensure mesh shading engine connections are valid.

    In some scenarios Maya keeps connections to multiple shaders even if just
    a single one is assigned on the shape. This can happen for example when
    a Shader is assigned to a face of a mesh and then the face is deleted.
    These are related sets returned by `maya.cmds.listSets` that don't
    actually have the shape as member anymore.

    """

    order = colorbleed.api.ValidateMeshOrder
    hosts = ['maya']
    families = ['colorbleed.model']
    label = "Mesh Shader Connections"
    actions = [colorbleed.maya.action.SelectInvalidAction,
               colorbleed.api.RepairAction]

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""

        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Shapes found with invalid shader "
                               "connections: {0}".format(invalid))

    @staticmethod
    def get_invalid(instance):

        nodes = instance[:]
        shapes = cmds.ls(nodes, noIntermediate=True, long=True, type="mesh")
        invalid = get_invalid_sets(shapes).keys()

        return invalid

    @classmethod
    def repair(cls, instance):

        shapes = cls.get_invalid(instance)
        invalid = get_invalid_sets(shapes)
        for shape, invalid_sets in invalid.items():
            for set_node in invalid_sets:
                disconnect(shape, set_node)
