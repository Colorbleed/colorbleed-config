from collections import defaultdict

import maya.cmds as cmds

import pyblish.api
import colorbleed.maya.action


def strip_namespace(node):
    return "|".join(n.rsplit(":", 1)[-1] for n in node.split("|"))


class ValidateClashingNodeNames(pyblish.api.InstancePlugin):
    """Validate nodes names do not clash when stripping namespaces.

    Node names need to be unique under the same parent when "strip namespaces"
    is enabled for the instance. This validates nodes have unique names
    when written without their namespaces.

    For example:

        Invalid:
            A
            namespace:A

        Invalid:
            char:group|char:A
            char:group|A

        Invalid:
            group|hero:A
            group|villain:A

        Valid:
            group|namespace:A
            group|B

    Note how having a node name the same after stripping the namespace
    under one parent is considered invalid.

    The easiest way to resolve this is to either rename the nodes or regroup
    them to ensure a unique name under the parent.

    """

    order = pyblish.api.ValidatorOrder
    families = ['colorbleed.animation', "colorbleed.pointcache"]
    hosts = ['maya']
    label = 'Clashing Node Names'
    actions = [colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):
        """Process all meshes"""

        if not instance.data.get("stripNamespaces", False):
            self.log.debug("Skipping because strip namespaces is disabled..")
            return

        # Ensure all nodes have a cbId and a related ID to the original shapes
        # if a deformer has been created on the shape
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Clashing nodes found: {0}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):
        """Get all nodes which do not match the criteria"""

        # get asset id
        nodes = instance.data.get("outMembersHierarchy", instance[:])

        # Collect nodes by its path with namespaces stripped
        stripped = defaultdict(set)
        for node in nodes:
            stripped[strip_namespace(node)].add(node)

        invalid = []
        for stripped_name, nodes in stripped.items():
            if len(nodes) > 1:

                cls.log.error("Clashing nodes found for: %s" % stripped_name)
                for node in nodes:
                    cls.log.warning("---- %s" % node)

                invalid.extend(nodes)

        return invalid
