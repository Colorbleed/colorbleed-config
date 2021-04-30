import avalon.maya
from colorbleed.maya import lib


class CreateGpuCache(avalon.maya.Creator):
    """Maya Alembic GPU Cache for preview"""

    label = "GPU Cache"
    family = "gpuCache"
    icon = "gears"

    def __init__(self, *args, **kwargs):
        super(CreateGpuCache, self).__init__(*args, **kwargs)

        # Add animation data
        self.data.update(lib.collect_animation_data())

        self.data["optimizeHierarchy"] = True
        self.data["optimizationThreshold"] = 40000
        self.data["optimizeAnimationsForMotionBlur"] = False  
        self.data["writeMaterials"] = True
        self.data["writeUVs"] = True
        self.data["useBaseTessellation"] = True  
