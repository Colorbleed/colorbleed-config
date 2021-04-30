import os

from maya import cmds

import avalon.maya
import colorbleed.api
from colorbleed.maya.lib import (
    get_visible_in_frame_range
)


class ExtractGpuCache(colorbleed.api.Extractor):
    """Produce a Maya gpuCache Alembic"""

    label = "Extract GPU Cache"
    hosts = ["maya"]
    families = ["gpuCache"]

    def process(self, instance):

        cmds.loadPlugin("gpuCache", quiet=True)
    
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

        self.log.info("Extracting GpuCache..")
        dirname = self.staging_dir(instance)

        parent_dir = self.staging_dir(instance)
        filename = "{name}".format(**instance.data)
        path = os.path.join(parent_dir, filename)

        options = {
            # TODO: use step
            #"step": instance.data.get("step", 1.0),  
            "writeMaterials": instance.data.get("writeMaterials", True),
            "writeUVs": instance.data.get("writeUVs", True),
            "useBaseTessellation": instance.data.get("useBaseTessellation", True)
        }
        
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
            cmds.gpuCache(nodes,
                          fileName=filename,
                          directory=dirname,
                          startTime=start,
                          endTime=end,
                          saveMultipleFiles=False,
                          dataFormat="ogawa",
                          **options)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename + ".abc")

        self.log.info("Extracted {} to {}".format(instance, dirname))
