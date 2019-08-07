import os

from maya import cmds

import avalon.maya
import colorbleed.api
from colorbleed.maya.lib import extract_alembic, get_visible_in_frame_range


class ExtractColorbleedAnimation(colorbleed.api.Extractor):
    """Produce an alembic of just point positions and normals.

    Positions and normals, uvs, creases are preserved, but nothing more,
    for plain and predictable point caches.

    """

    label = "Extract Animation"
    hosts = ["maya"]
    families = ["colorbleed.animation"]

    def process(self, instance):

        # Collect the out set nodes
        out_sets = [node for node in instance if node.endswith("out_SET")]
        if len(out_sets) != 1:
            raise RuntimeError("Couldn't find exactly one out_SET: "
                               "{0}".format(out_sets))
        out_set = out_sets[0]
        roots = cmds.sets(out_set, query=True)

        # Include all descendants
        nodes = roots + cmds.listRelatives(roots,
                                           allDescendents=True,
                                           fullPath=True) or []

        # Exclude constraint nodes as they are useless data in the export.
        # Somehow ls(excludeType) does not seem to work, so filter manually.
        exclude = set(cmds.ls(nodes, type="constraint", long=True))
        if exclude:
            nodes = [node for node in nodes if node not in exclude]

        # Collect the start and end including handles
        start = instance.data["startFrame"]
        end = instance.data["endFrame"]
        handles = instance.data.get("handles", 0)
        if handles:
            start -= handles
            end += handles

        self.log.info("Extracting animation..")
        dirname = self.staging_dir(instance)

        parent_dir = self.staging_dir(instance)
        filename = "{name}.abc".format(**instance.data)
        path = os.path.join(parent_dir, filename)

        options = {
            "step": instance.data.get("step", 1.0),
            "attr": ["cbId"],
            "attrPrefix": ["cb_"],
            "writeVisibility": True,
            "writeCreases": True,
            "uvWrite": True,
            "selection": True,
            "worldSpace": instance.data.get("worldSpace", True),
            "eulerFilter": instance.data.get("eulerFilter", True),
        }

        if not instance.data.get("includeParentHierarchy", True):
            # Set the root nodes if we don't want to include parents
            # The roots are to be considered the ones that are the actual
            # direct members of the set
            options["root"] = roots

        if int(cmds.about(version=True)) >= 2017:
            # Since Maya 2017 alembic supports multiple uv sets - write them.
            options["writeUVSets"] = True

        if instance.data.get("visibleOnlyInFrameRange", False):
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
