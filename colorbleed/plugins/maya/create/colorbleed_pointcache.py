import avalon.maya
from colorbleed.maya import lib


class CreatePointCache(avalon.maya.Creator):
    """Alembic pointcache for animated data"""

    label = "Point Cache"
    family = "colorbleed.pointcache"
    icon = "gears"

    def __init__(self, *args, **kwargs):
        super(CreatePointCache, self).__init__(*args, **kwargs)

        # Add animation data
        self.data.update(lib.collect_animation_data())

        self.data["writeColorSets"] = False  # Vertex colors with the geometry.
        self.data["renderableOnly"] = False  # Only renderable visible shapes

        # Include a more thorough check to ensure only nodes that are
        # are at least visible once throughout the frame range are included
        self.data["visibleOnly"] = False

        self.data["includeParentHierarchy"] = False  # Include parent groups
        self.data["worldSpace"] = True       # Default to exporting world-space

        # Whether to strip namespaces
        self.data["stripNamespaces"] = True

        # Add options for custom attributes
        self.data["attr"] = ""
        self.data["attrPrefix"] = ""
