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
        # layers. This will currently *only* bake joints.
        self.data["bakeAnimLayers"] = ""
