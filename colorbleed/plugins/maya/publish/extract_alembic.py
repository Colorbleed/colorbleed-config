import os

from maya import cmds

import avalon.maya
import colorbleed.api
from colorbleed.maya.lib import extract_alembic, get_visible_in_frame_range


def get_roots(nodes):
    """Return the highest nodes in the hierarchies.

    This filters out nodes that are children of others in the input `nodes`.

    """
    nodes = sorted(cmds.ls(nodes, long=True), reverse=True)
    roots = set()

    if len(nodes) <= 1:
        # Don't search when just one node or none
        return nodes

    head = None
    while nodes:
        this = head or nodes.pop()
        that = nodes.pop()

        if that.startswith(this):
            head = this
        else:
            roots.add(this)
            head = that

        roots.add(head)

    return list(roots)


def _get_animation_members(instance):
    # todo: Move this family-specific workaround out of here

    # Collect the out set nodes
    out_sets = [node for node in instance if node.endswith("out_SET")]
    if len(out_sets) != 1:
        raise RuntimeError("Couldn't find exactly one out_SET: "
                           "{0}".format(out_sets))
    out_set = out_sets[0]
    roots = cmds.sets(out_set, query=True)
    nodes = roots + cmds.listRelatives(roots,
                                       allDescendents=True,
                                       fullPath=True) or []

    return roots, nodes


class ExtractAlembic(colorbleed.api.Extractor):
    """Produce an alembic of just point positions and normals.

    Positions and normals, uvs, creases are preserved, but nothing more,
    for plain and predictable point caches.

    """

    label = "Extract Alembic"
    hosts = ["maya"]
    families = ["colorbleed.pointcache",
                "colorbleed.animation",
                "colorbleed.model"]

    def process(self, instance):

        # todo: Move this family-specific workaround out of here
        if ("colorbleed.animation" == instance.data.get("family") or
                "colorbleed.animation" in instance.data.get("families", [])):
            # Animation family gets the members from the "out_SET" of the
            # loaded rig.
            roots, nodes = _get_animation_members(instance)
        else:
            roots = instance.data["setMembers"]
            nodes = instance[:]

        # Exclude constraint nodes as they are useless data in the export.
        # Somehow ls(excludeType) does not seem to work, so filter manually.
        exclude = set(cmds.ls(nodes, type="constraint", long=True))
        if exclude:
            nodes = [node for node in nodes if node not in exclude]

        # Collect the start and end including handles
        start = instance.data.get("startFrame", 1)
        end = instance.data.get("endFrame", 1)
        handles = instance.data.get("handles", 0)
        if handles:
            start -= handles
            end += handles

        attrs = instance.data.get("attr", [])
        attrs = [value for value in attrs if value.strip()]

        attr_prefixes = instance.data.get("attrPrefix", [])
        attr_prefixes = [value for value in attr_prefixes if value.strip()]

        self.log.info("Extracting Alembic..")
        dirname = self.staging_dir(instance)

        parent_dir = self.staging_dir(instance)
        filename = "{name}.abc".format(**instance.data)
        path = os.path.join(parent_dir, filename)

        options = {
            "step": instance.data.get("step", 1.0),
            "attr": attrs,
            "attrPrefix": attr_prefixes,
            "writeVisibility": True,
            "writeCreases": True,
            "uvWrite": True,
            "selection": True,
            "worldSpace": instance.data.get("worldSpace", True),
            "eulerFilter": instance.data.get("eulerFilter", True),
            "writeColorSets": instance.data.get("writeColorSets", False),
            "stripNamespaces": instance.data.get("stripNamespaces", False)
        }

        if not instance.data.get("includeParentHierarchy", True):
            # To avoid the issue of a child node being included as root node
            # too we solely use the highest root nodes only, otherwise Alembic
            # export will fail on "parent/child" relationships for the roots
            options["root"] = get_roots(roots)

        if int(cmds.about(version=True)) >= 2017:
            # Since Maya 2017 alembic supports multiple uv sets - write them.
            options["writeUVSets"] = True

        visible_in_frame_range_only = instance.data.get(
            "visibleOnlyInFrameRange",  # Backwards compatibility
            instance.data.get("visibleOnly", False)
        )
        if visible_in_frame_range_only:
            # If we only want to include nodes that are visible in the frame
            # range then we need to do our own check. Alembic's `visibleOnly`
            # flag does not filter out those that are only hidden on some
            # frames as it counts "animated" or "connected" visibilities as
            # if it's always visible.
            nodes = get_visible_in_frame_range(nodes,
                                               start=start,
                                               end=end)

        with avalon.maya.suspended_refresh():
            with avalon.maya.maintained_selection():
                cmds.select(nodes, noExpand=True)
                extract_alembic(file=path,
                                startFrame=start,
                                endFrame=end,
                                **options)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted {} to {}".format(instance, dirname))
