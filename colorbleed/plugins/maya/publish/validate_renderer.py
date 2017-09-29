import pyblish.api as api
from colorbleed.maya import lib


class ValidateRenderer(api.Validator):
    """Validate if all renderlayers use the same renderer"""

    order = api.CollectorOrder + 0.4
    hosts = ['maya']
    families = ['colorbleed.renderlayer']
    label = 'Validate Layer Renderer'
    optional = True

    def process(self, instance):

        default_renderer = lib.get_renderer("defaultRenderLayer")
        if instance.data["renderer"] != default_renderer:
            renderlayer_node = instance.data["setMembers"]
            raise RuntimeError("Renderer for renderlayer '{}' diverges from "
                               "the masterLayer".format(renderlayer_node))

