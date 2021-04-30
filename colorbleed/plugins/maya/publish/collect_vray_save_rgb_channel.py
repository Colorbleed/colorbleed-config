import pyblish.api

from colorbleed.maya import lib


class CollectVraySaveRGBChannel(pyblish.api.InstancePlugin):
    """Collect whether Don't Save RGB Channel was enabled.
    
    When the Don't Save RGB Channel was enabled this will
    set `instance.data["renderNoMasterLayer"] = True`.
    
    Requires:
        instance    -> setMembers
        instance    -> renderer

    Provides:
        instance    -> renderNoMasterLayer

    """

    order = pyblish.api.CollectorOrder + 0.05
    label = "Collect V-Ray Save RGB Channel"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer.vray"]

    def process(self, instance):

        layer = instance.data["setMembers"]
        renderer = instance.data["renderer"]
        assert renderer == "vray", "Renderer must be V-Ray"
        
        attr = "vraySettings.dontSaveRgbChannel"
        dont_save_rgb = lib.get_attr_in_layer(attr, layer=layer)
        instance.data["renderNoMasterLayer"] = dont_save_rgb
        
        if dont_save_rgb:
            self.log.info("Beauty master of layer is excluded from rendering"
                          " as 'Don't Save RGB Channel' is enabled...")
