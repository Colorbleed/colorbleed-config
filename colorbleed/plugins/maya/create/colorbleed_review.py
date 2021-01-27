from collections import OrderedDict
import avalon.maya

from colorbleed.maya import lib


class CreateReview(avalon.maya.Creator):
    """Create a quicktime .mov reviewable"""

    name = "reviewDefault"
    label = "Review"
    family = "colorbleed.review"
    icon = "video-camera"

    def __init__(self, *args, **kwargs):
        super(CreateReview, self).__init__(*args, **kwargs)

        # Get basic animation data (start frame, end frame, etc.)
        for key, value in lib.collect_animation_data().items():
            self.data[key] = value

        # Remove substeps
        self.data.pop("step", None)

        self.data["include_alpha"] = False

        # todo: overridable resolution per instance
        # todo: overridable viewport settings per instance
