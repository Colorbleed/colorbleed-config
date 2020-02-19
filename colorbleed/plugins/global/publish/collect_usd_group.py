import pyblish.api

from avalon import io

import colorbleed.usdlib as usdlib


def flatten_as_set(l):
    """Flatten iterator used to return a set"""
    return set(item for sublist in l for item in sublist)


class CollectUsdGroup(pyblish.api.InstancePlugin):
    """Collect whether this USD instance is a layer for an Asset or Shot.

    When the usd instance is a layer dependency for something else we add
    a "group" to it so that they are slightly stashed away in the Loader.

    """

    order = pyblish.api.CollectorOrder + 0.3
    label = "Collect USD Group"
    hosts = ["houdini", "maya"]
    families = ["colorbleed.usd", "usdModel"]

    # The predefined subset steps for a Shot and Asset
    lookup = flatten_as_set(usdlib.PIPELINE.values())

    def process(self, instance):

        group = "USD Layer"

        if instance.data["family"] == "usdModel":
            instance.data["subsetGroup"] = group
            return

        # Backwards compatibility
        # TODO Replace the lookup check by having more explicit instance
        #      families to avoid requiring lookups by subset.
        is_layer = instance.data["subset"] in self.lookup
        if is_layer:
            instance.data["subsetGroup"] = group
