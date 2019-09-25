import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib

from maya import cmds


class ValidateVRayCacheSettings(pyblish.api.InstancePlugin):
    """Validate V-Ray Plug-in Geometry and Bitmap cache.

    In some rare scenarios the caching can mess up batch rendering where it
    "holds" geometry from a different frame ending up with a render in a new
    frame that does not have updated geometry (for some meshes). However,
    this happens very rarely and is hard to reproduce.

    For sake of clarity, we will raise a warning with this validator however.

    These settings are in Render Settings > Overrides > Rendering.

    """

    order = colorbleed.api.ValidateContentsOrder
    label = "VRay Cache Geometry/Bitmaps"
    families = ["colorbleed.renderlayer.vray"]

    def process(self, instance):

        vray_settings = cmds.ls("vraySettings", type="VRaySettingsNode")
        assert vray_settings, "Please ensure a VRay Settings Node is present"

        node = vray_settings[0]

        # Cache geometry plug-ins between renders
        if cmds.getAttr("{0}.globopt_cache_geom_plugins".format(node)):
            self.log.warning("V-Ray Overrides: Cache Geometry Plug-ins "
                             "is currently enabled..")

        # Cache bitmaps between renders
        if cmds.getAttr("{0}.globopt_cache_bitmaps".format(node)):
            self.log.warning("V-Ray Overrides: Cache Bitmaps "
                             "is currently enabled..")
