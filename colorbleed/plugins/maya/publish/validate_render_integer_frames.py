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

        invalid = False

        # Validate startFrame, endFrame, handles and byFrameStep
        for key in ["startFrame", "endFrame", "handles", "byFrameStep"]:
            value = instance.data.get(key, None)
            if value is not None and round(value) != value:
                invalid = True
                self.log.error("%s is not an integer value: %s" % (key, value))

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