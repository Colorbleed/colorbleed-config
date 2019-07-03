import pyblish.api
import colorbleed.api
import colorbleed.maya.action


class ValidateRenderSingleCamera(pyblish.api.InstancePlugin):
    """Ensure at least a single camera is renderable."""

    order = colorbleed.api.ValidateContentsOrder
    label = "Render Single Camera"
    hosts = ['maya']
    families = ["colorbleed.renderlayer",
                "colorbleed.vrayscene"]
    actions = [colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):
        """Process all the cameras in the instance"""
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Invalid cameras for render.")

    @classmethod
    def get_invalid(cls, instance):

        cameras = instance.data.get("cameras", [])

        if len(cameras) > 1:
            cls.log.warning("Multiple renderable cameras found for %s: %s " %
                            (instance.data["setMembers"], cameras))

        elif len(cameras) < 1:
            cls.log.error("No renderable cameras found for %s " %
                          instance.data["setMembers"])
            return [instance.data["setMembers"]]

