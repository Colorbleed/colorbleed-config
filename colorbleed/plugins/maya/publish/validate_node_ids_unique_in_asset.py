from collections import defaultdict

import pyblish.api
import colorbleed.api
import colorbleed.maya.action
import colorbleed.maya.lib as lib

from maya import cmds


def get_instance_node_ids(instance, ignore_intermediate_objects=True):
    instance_members = cmds.ls(instance,
                               noIntermediate=ignore_intermediate_objects,
                               long=True)

    # Collect each id with their members
    ids = defaultdict(list)
    for member in instance_members:
        object_id = lib.get_id(member)
        if not object_id:
            continue
        ids[object_id].append(member)

    return ids


def get_families(instance):
    """Get the instance's families"""
    families = instance.data.get("families", [])
    family = instance.data.get("family")
    if family:
        families.append(family)
    return set(families)


class ValidateNodeIdsUniqueInstanceClash(pyblish.api.InstancePlugin):
    """Validate nodes across model instances have a unique Colorbleed Id

    This validates whether the node ids to be published are unique across
    all model instances currently being published (even if those other
    instances are DISABLED currently for publishing).

    This will *NOT* validate against previous publishes or publishes being
    done from another scene than the current one. It will only validate for
    models that are being published from a single scene.

    """

    order = pyblish.api.ValidatorOrder - 0.1
    label = 'Clashing node ids across model instances'
    hosts = ['maya']
    families = ["colorbleed.model"]
    optional = True

    actions = [colorbleed.maya.action.SelectInvalidAction,
               colorbleed.maya.action.GenerateUUIDsOnInvalidAction]

    def process(self, instance):
        """Process all meshes"""

        # Ensure all nodes have a cbId
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Nodes found with non-unique "
                               "asset IDs: {0}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):
        """Return the member nodes that are invalid"""

        others = [i for i in list(instance.context) if
                  i is not instance and
                  set(cls.families) & get_families(instance)]
        if not others:
            return []

        other_ids = defaultdict(list)
        for other in others:
            for _id, members in get_instance_node_ids(other).items():
                other_ids[_id].extend(members)

        # Take only the ids with more than one member
        invalid = list()
        ids = get_instance_node_ids(instance)
        for _id, members in ids.iteritems():
            if _id in other_ids:
                cls.log.error("ID found on multiple nodes: '%s'" % members)
                cls.log.debug("Clashes with: %s" % (other_ids[_id],))
                invalid.extend(members)

        return invalid
