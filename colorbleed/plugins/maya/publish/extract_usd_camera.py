import os

from maya import cmds

import avalon.maya
import colorbleed.api

from colorbleed.maya.lib import get_highest_in_hierarchy


class ExtractUSDCamera(colorbleed.api.Extractor):
    """Extract USD

    This uses the Multiverse 6.0 plug-in.

    """

    label = "Extract Camera (USD)"
    hosts = ["maya"]
    families = ["usdCamera"]

    def process(self, instance):

        # TODO: Merge this with Extract USD where possible

        # Ensure the plugin is loaded
        cmds.loadPlugin("MultiverseForMaya", quiet=True)

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.usd".format(instance.name)
        path = os.path.join(dir_path, filename)

        write_ancestors = instance.data.get("includeParentHierarchy", False)

        # Use time samples when provided
        kwargs = {}
        if instance.data.get("startFrame") and instance.data.get("endFrame"):
            start = instance.data["startFrame"]
            end = instance.data["endFrame"]
            handles = instance.data.get("handles", 0)
            if handles:
                start -= handles
                end += handles

            kwargs["frameRange"] = [start, end]
            kwargs["numTimeSamples"] = 1
            kwargs["timeSamplesSpan"] = 0.0

            # Perform extraction
        self.log.info("Performing extraction..")
        with avalon.maya.maintained_selection():
            cmds.select(instance, noExpand=True)

            root = get_highest_in_hierarchy(instance)

            cmds.mvUsdWriteAsset(assetPath=path,
                                 dagRoot=root,
                                 writeAncestors=write_ancestors,
                                 writeCameras=True,
                                 writeTransformMatrix=True,
                                 writePositions=False,
                                 writeMeshes=False,
                                 writeNormals=False,
                                 writeUVs=False,
                                 writeDisplayColor=False,
                                 writeParticles=False,
                                 writeCurves=False,
                                 mergeTransformAndShape=True,
                                 **kwargs)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted instance '%s' to: %s" % (instance.name, path))
