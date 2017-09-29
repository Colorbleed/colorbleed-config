import pyblish.api
import colorbleed.maya.lib as lib


class CollectRenderer(pyblish.api.InstancePlugin):

    """Gather the renderer for each renderlayer instance"""

    order = pyblish.api.CollectorOrder + 0.4
    hosts = ["maya"]
    label = "Renderer"
    families = ["colorbleed.renderlayer"]

    def process(self, instance):

        renderlayer_node = instance.name
        renderer = lib.get_renderer(renderlayer_node)
        renderer_family = "colorbleed.renderer.{}".format(renderer)
        instance.data['families'].append(renderer_family)
        instance.data['renderer'] = renderer