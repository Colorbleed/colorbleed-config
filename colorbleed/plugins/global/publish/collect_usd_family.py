import pyblish.api


class CollectUSDFamily(pyblish.api.InstancePlugin):
    """Collect usd publish family"""

    order = pyblish.api.CollectorOrder + 0.25
    label = "Collect USD Family"
    families = ["usdModel", "usdSetDress"]
    hosts = ["houdini", "maya"]

    def process(self, instance):
        instance.data["publishFamilies"] = ["colorbleed.usd"]
