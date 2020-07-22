from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action


class ValidateUsdCameraScale(pyblish.api.Validator):
    """Validate the Camera's scale is [1, 1, 1]

    If the global scale of the camera is not one than the camera mismatches
    in USD in Houdini. This validation makes sure the camera has not been
    scaled up or down.

    Note that this is the *World Space Scale*! As such, the camera might
    have scale [1, 1, 1] but one of its parents have an invalid scale.
    It's important that the final scale ends up at 1, 1, 1.

    """

    order = pyblish.api.ValidatorOrder
    hosts = ["maya"]
    families = ["usdCamera"]
    label = "Camera not scaled"
    actions = [colorbleed.maya.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):

        tolerance = 1e-6
        cameras = cmds.ls(instance, type="camera", long=True)

        invalid = []
        for camera in cameras:

            transform = cmds.listRelatives(camera,
                                           parent=True,
                                           fullPath=True)[0]
            scale = cmds.xform(transform,
                               query=True,
                               scale=True,
                               worldSpace=True)

            if any(abs(1 - x) > tolerance for x in scale):
                cls.log.error("Camera has invalid scale: "
                              "{0} -> {1}".format(scale, camera))
                invalid.append(camera)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""

        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Nodes found with transform "
                             "values: {0}".format(invalid))
