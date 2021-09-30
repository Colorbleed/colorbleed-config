import pyblish.api

import maya.cmds as cmds
import maya.api.OpenMaya as om


def get_all_children(nodes):
    """Return all children of `nodes` including each instanced child.

    Using maya.cmds.listRelatives(allDescendents=True) includes only the first
    instance. As such, this function acts as an optimal replacement with a
    focus on a fast query.

    """

    sel = om.MSelectionList()
    traversed = set()
    iterator = om.MItDag(om.MItDag.kDepthFirst)
    for node in nodes:

        if node in traversed:
            # Ignore if already processed as a child
            # before
            continue

        sel.clear()
        sel.add(node)
        dag = sel.getDagPath(0)

        iterator.reset(dag)
        iterator.next()  # ignore self
        while not iterator.isDone():

            path = iterator.fullPathName()

            if path in traversed:
                iterator.prune()
                iterator.next()
                continue

            traversed.add(path)
            iterator.next()

    return list(traversed)


class CollectAnimationOutputGeometry(pyblish.api.InstancePlugin):
    """Collect out hierarchy data for instance.

    Collect all hierarchy nodes which reside in the out_SET of the animation
    instance or point cache instance. This is to unify the logic of retrieving
    that specific data. This eliminates the need to write two separate pieces
    of logic to fetch all hierarchy nodes.

    Results in a list of nodes from the content of the instances

    """

    order = pyblish.api.CollectorOrder + 0.4
    families = ["colorbleed.animation"]
    label = "Collect Animation Output Geometry"
    hosts = ["maya"]

    ignore_type = ["constraint"]

    def process(self, instance):
        """Collect the hierarchy nodes"""

        family = instance.data["family"]
        out_set = next((i for i in instance.data["setMembers"] if
                        i.endswith("out_SET")), None)

        if out_set is None:
            warning = "Expecting out_SET for instance of family '%s'" % family
            self.log.warning(warning)
            return

        members = cmds.ls(cmds.sets(out_set, query=True), long=True)

        # Get all the relatives of the members
        descendants = get_all_children(members)
        descendants = cmds.ls(descendants, noIntermediate=True, long=True)

        # Add members and descendants together for a complete overview
        hierarchy = members + descendants

        # Ignore certain node types (e.g. constraints)
        ignore = cmds.ls(hierarchy, type=self.ignore_type, long=True)
        if ignore:
            ignore = set(ignore)
            hierarchy = [node for node in hierarchy if node not in ignore]

        # Store data in the instance for the validator
        instance.data["outMembers"] = members
        instance.data["outMembersHierarchy"] = hierarchy

