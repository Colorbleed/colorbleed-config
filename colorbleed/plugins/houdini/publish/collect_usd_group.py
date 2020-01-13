import hou

import pyblish.api

from avalon import io
from avalon.houdini import lib
import colorbleed.houdini.usd as usdlib


class CollectUsdGroups(pyblish.api.InstancePlugin):
    """Collect whether this USD instance is a layer for an Asset or Shot.

    When the usd instance is a layer dependency for something else we add
    a "group" to it so that they are slightly stashed away in the Loader.

    """

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect USD Bootstrap"
    hosts = ["houdini"]
    families = ["colorbleed.usd"]

    # The predefined subset steps for a Shot and Asset
    lookup = set(usdlib.SHOT_PIPELINE_SUBSETS + usdlib.ASSET_PIPELINE_SUBSETS)

    def process(self, instance):

        is_layer = instance.data["subset"] in self.lookup
        if is_layer:
            instance.data["group"] = "USD Layer"
