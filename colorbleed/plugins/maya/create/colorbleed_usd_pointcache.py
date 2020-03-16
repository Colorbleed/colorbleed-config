import avalon.maya
from colorbleed.maya import lib


class CreateUSDPointcache(avalon.maya.Creator):
    """USD Pointcache"""

    label = "USD Pointcache"
    family = "usdPointcache"
    icon = "gears"

    def __init__(self, *args, **kwargs):
        super(CreateUSDPointcache, self).__init__(*args, **kwargs)

        # Add animation data
        self.data.update(lib.collect_animation_data())

        self.data["writeColorSets"] = False  # Vertex colors with the geometry.

        self.data["includeParentHierarchy"] = False  # Include parent groups

        # Whether to strip namespaces
        self.data["stripNamespaces"] = True
