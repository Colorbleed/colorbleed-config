import avalon.maya
from colorbleed.maya import lib


class CreateUSDCamera(avalon.maya.Creator):
    """Single baked USD camera"""

    label = "USD Camera"
    family = "usdCamera"
    icon = "video-camera"

    def __init__(self, *args, **kwargs):
        super(CreateUSDCamera, self).__init__(*args, **kwargs)

        # get basic animation data : start / end / handles / steps
        self.data.update(lib.collect_animation_data())
