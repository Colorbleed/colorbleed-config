import avalon.maya
from colorbleed.maya import lib


class CreateFBX(avalon.maya.Creator):
    """FBX Export"""

    label = "FBX"
    family = "colorbleed.fbx"
    icon = "plug"

    def __init__(self, *args, **kwargs):
        super(CreateFBX, self).__init__(*args, **kwargs)

        # get basic animation data : start / end / handles / steps
        for key, value in lib.collect_animation_data().items():
            self.data[key] = value

        # Whether to include tangents and binormals
        self.data["tangents"] = False

        # Whether to triangulate the mesh in the output
        self.data["triangulate"] = False

        # Special option to support a custom baking of keys "just before" the
        # FBX extraction so the FBX exporter picks up these custom animation
        # layers. This will currently *only* bake joints. This is used by
        # Lens Studio importer to import clips correctly.
        self.data["bakeAnimLayers"] = ""

        # When enabled the FBX Export will use all Timeline Bookmarks to
        # define named takes in a single FBX file.
        self.data["useTimelineBookmarksAsTakes"] = False

        # Whether to preserve instances in the export
        self.data["instances"] = False

        # Add output options for specific elements in the export
        self.data["cameras"] = False
        self.data["shapes"] = True
        self.data["skins"] = True
        self.data["constraints"] = False
        self.data["lights"] = True
