import os

from maya import cmds

import avalon.maya
import colorbleed.api

from colorbleed.lib import clean_filename
from colorbleed.maya.lib import get_highest_in_hierarchy


class ExtractUSD(colorbleed.api.Extractor):
    """Extract USD

    This uses the Multiverse 6.3.0+ plug-in.

    """

    label = "Extract USD"
    hosts = ["maya"]
    families = ["usdModel",
                "usdCamera",
                "usdPointcache",
                "colorbleed.animation.usd"]

    def process(self, instance):

        if ("outMembers" in instance.data and
                "outMembersHierarchy" in instance.data):
            # The animation family collects members using the out_SET
            roots = instance.data["outMembers"]
            nodes = instance.data["outMembersHierarchy"]
        else:
            roots = instance.data["setMembers"]
            nodes = instance[:]

        # Ensure the plugin is loaded
        cmds.loadPlugin("MultiverseForMaya", quiet=True)

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = clean_filename("{0}.usd".format(instance.name))
        path = os.path.join(dir_path, filename)

        # Use time samples when provided
        kwargs = {}
        if "startFrame" in instance.data and "endFrame" in instance.data:
            start = instance.data["startFrame"]
            end = instance.data["endFrame"]
            handles = instance.data.get("handles", 0)
            if handles:
                start -= handles
                end += handles

            kwargs["frameRange"] = [start, end]
            kwargs["numTimeSamples"] = 1
            kwargs["timeSamplesSpan"] = 0.0

        # Add some kwargs that are customizable options as instance data
        options = {
            "writeMeshes": True,
            "writePositions": True,
            "writeUVs": True,
            "writeNormals": True,
            "writeTransformMatrix": True,
            "writeCameras": False,
            "writeColorSets": False,
            "writeDisplayColor": False,
            "stripNamespaces": True
        }
        for key in options:
            if key in instance.data:
                options[key] = instance.data[key]
        kwargs.update(options)

        # Apply family specific forced overrides
        overrides = self._get_family_overrides(instance)
        kwargs.update(overrides)

        roots = get_highest_in_hierarchy(roots)
        write_ancestors = instance.data.get("includeParentHierarchy", False)

        # Perform extraction
        self.log.info("Performing extraction..")
        with avalon.maya.suspended_refresh():
            with avalon.maya.maintained_selection():
                cmds.select(nodes, noExpand=True)
                cmds.mvUsdWriteAsset(assetPath=path,
                                     dagRoot=roots,
                                     writeAncestors=write_ancestors,
                                     mergeTransformAndShape=True,
                                     **kwargs)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted instance '%s' to: %s" % (instance.name, path))

    def _get_family_overrides(self, instance):

        families = {instance.data.get("family", None)}
        families.update(instance.data.get("families", []))

        overrides = {}

        if "colorbleed.animation" in families:
            # No UVs for animation caches
            self.log.debug("Disabling UV write for Animation cache..")
            overrides["writeUVs"] = False

        elif "colorbleed.camera" in families:
            self.log.debug("Writing Camera only..")
            # Only include camera
            overrides["writeCameras"] = True
            overrides["writePositions"] = False
            overrides["writeCurves"] = False
            overrides["writeParticles"] = False
            overrides["writePositions"] = False
            overrides["writeUVs"] = False
            overrides["writeNormals"] = False
            overrides["writeColorSets"] = False
            overrides["writeDisplayColor"] = False

        return overrides
