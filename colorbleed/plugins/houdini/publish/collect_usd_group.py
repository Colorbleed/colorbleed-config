import hou

import pyblish.api

from avalon import io
from avalon.houdini import lib
import colorbleed.houdini.usd as usdlib


def flatten_as_set(l):
    """Flatten iterator used to return a set"""
    return set(item for sublist in l for item in sublist)


class CollectUsdGroup(pyblish.api.InstancePlugin):
    """Collect whether this USD instance is a layer for an Asset or Shot.

    When the usd instance is a layer dependency for something else we add
    a "group" to it so that they are slightly stashed away in the Loader.

    """

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect USD Group"
    hosts = ["houdini"]
    families = ["colorbleed.usd"]

    # The predefined subset steps for a Shot and Asset
    lookup = flatten_as_set(usdlib.PIPELINE.values())

    def process(self, instance):

        is_layer = instance.data["subset"] in self.lookup
        if is_layer:
            instance.data["subsetGroup"] = "USD Layer"
