import pyblish.api
import colorbleed.api


class ValidateRenderIntegerFrames(pyblish.api.InstancePlugin):
    """Validates all rendered frames are integers.

    Make sure all you frames are rounded numbers, no decimal values.

    Due to the nature of decimal point precision it's hard to figure out how
    a specific renderer/application will save out e.g. frame 1.2597. As such,
    supporting decimal point frames would likely be very prone to breaking

    Plus, who are we kidding? We never really want to render it like that
    anyway, right? All hail the integer frames!

    """

    label = "Validate Render Integer Frames"
    order = colorbleed.api.ValidateContentsOrder
    families = ["colorbleed.review",
                "colorbleed.renderlayer"]

    def process(self, instance):

        start = instance.data.get("startFrame", None)
        end = instance.data.get("endFrame", None)
        handles = instance.data.get("handles", None)

        invalid = False
        if start is not None and round(start) != start:
            invalid = True
            self.log.error("Start frame is not an integer value: %s" % start)
        if end is not None and round(end) != end:
            invalid = True
            self.log.error("End frame is not an integer value: %s" % end)
        if handles is not None and round(handles) != handles:
            invalid = True
            self.log.error("Handles is not an integer value: %s" % handles)

        # If explicit frames are provided they are all collected as integers
        # but for sake of sanity let's validate them all.
        frames_explicit = instance.data.get("frames", None)
        if frames_explicit and any(round(f) != f for f in frames_explicit):
            invalid = True
            invalid_frames = [f for f in frames_explicit if round(f) != f]
            self.log.error("Not all frames are integer "
                           "frames: %s" % invalid_frames)

        if invalid:
            raise RuntimeError("Non-integer render frames found "
                               "for: %s" % instance.name)