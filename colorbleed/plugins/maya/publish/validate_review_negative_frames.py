import pyblish.api
import colorbleed.api


class ValidateReviewNegativeFrames(pyblish.api.InstancePlugin):
    """Review does not support negative frames (for encoding).

    Check with tech-department if you need this implemented now.

    """

    order = colorbleed.api.ValidatePipelineOrder
    label = 'Review Negative Frames'
    hosts = ['maya']
    families = ["colorbleed.review"]
    optional = False

    def process(self, instance):

        start_frame = instance.data["startFrame"]
        handles = instance.data.get("handles", 0)

        start = start_frame - handles
        if start < 0:
            raise RuntimeError("Review family currently does not support"
                               "negative frames. (This includes the 'handles'")
