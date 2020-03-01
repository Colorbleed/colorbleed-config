import os

from maya import cmds

import avalon.maya
import colorbleed.api

from colorbleed.maya.lib import get_highest_in_hierarchy


class ExtractUSDModel(colorbleed.api.Extractor):
    """Extract Model as USD

    This uses the Multiverse 6.0 plug-in.

    """

    label = "Extract Model (USD)"
    hosts = ["maya"]
    families = ["usdModel"]

    def process(self, instance):

        # Ensure the plugin is loaded
        cmds.loadPlugin("MultiverseForMaya", quiet=True)

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.usd".format(instance.name)
        path = os.path.join(dir_path, filename)

        write_ancestors = instance.data.get("includeParentHierarchy", False)

        # Perform extraction
        self.log.info("Performing extraction..")
        with avalon.maya.maintained_selection():
            cmds.select(instance, noExpand=True)

            root = get_highest_in_hierarchy(instance)

            cmds.mvUsdWriteAsset(assetPath=path,
                                 dagRoot=root,
                                 writeAncestors=write_ancestors,
                                 writeTransformMatrix=True,
                                 writePositions=True,
                                 writeMeshes=True,
                                 writeNormals=True,
                                 writeUVs=True,
                                 writeDisplayColor=False,
                                 mergeTransformAndShape=True)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted instance '%s' to: %s" % (instance.name, path))
