import os
import re

import pyblish.api

from maya import cmds
from maya import mel

from colorbleed.maya import lib


def get_renderer_variables(renderlayer):
    """Retrieve the extension and padding from render settings.

    Args:
        renderlayer (str): the node name of the renderlayer.

    Returns:
        dict
    """

    renderer = lib.get_renderer(renderlayer)
    render_attrs = lib.RENDER_ATTRS.get(renderer, lib.RENDER_ATTRS["default"])
    padding = cmds.getAttr("{node}.{padding}".format(**render_attrs))

    if renderer == "vray":
        # Maya's renderSettings function does not return V-Ray file extension
        # so we get the extension from vraySettings
        extension = cmds.getAttr("vraySettings.imageFormatStr")

        # When V-Ray image format has not been switched once from default .png
        # the getAttr command above returns None. As such we explicitly set
        # it to `.png`
        if extension is None:
            extension = "png"

    else:

        # Get the extension, getAttr defaultRenderGlobals.imageFormat
        # only returns an index number.
        # todo: this should actually switch to the renderlayer to be accurate
        # todo: needs fix for file extension for Arnold (mtoa!)
        filename_0 = cmds.renderSettings(fullPath=True,
                                         firstImageName=True)[0]
        filename_base = os.path.basename(filename_0)
        extension = os.path.splitext(filename_base)[-1].strip(".")

    return {"ext": extension,
            "padding": padding}


class CollectRenderlayerFilenames(pyblish.api.InstancePlugin):
    """Collect the renderlayer's output filenames"""

    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Renderlayer Filenames"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    def process(self, instance):

        layer = instance.data["setMembers"]
        renderer = instance.data["renderer"]

        # Get the filename prefix attribute for current renderer
        attrs = lib.RENDER_ATTRS.get(renderer, lib.RENDER_ATTRS["default"])
        prefix_attr = "{node}.{prefix}".format(**attrs)
        prefix = lib.get_attr_in_layer(prefix_attr, layer=layer)

        # Use this mapping to resolve variables (case insensitive)
        tokens = {
            "<Camera>": "{camera}",
            "<Scene>": "{scene}",
            "<RenderLayer>": "{renderlayer}",
            "<RenderPass>": "{renderpass}",

            # V-Ray
            "<Layer>": "{renderlayer}",
        }

        context = instance.context
        filepath = context.data["currentFile"]
        filename = os.path.basename(filepath)
        scene = os.path.splitext(filename)[0]

        # The output produces a 'nice name' for a <Camera> using its
        # shortest unique path of the transform
        camera = instance.data["camera"]
        transform = cmds.ls(cmds.listRelatives(camera,
                                               parent=True,
                                               fullPath=True))[0]
        camera_name = transform.replace(":", "_").replace("|", "_")

        # Get the variables depending on the renderer
        render_variables = get_renderer_variables(layer)

        data = {
            "scene": scene,
            "renderlayer": instance.data["layername"],
            "camera": camera_name,
            "renderpass": "{renderpass}"    # We format this later per AOV
        }

        # Format prefix with the data
        prefix = prefix
        for src, to in tokens.items():
            prefix = re.sub(re.escape(src), to, prefix, flags=re.IGNORECASE)
        prefix = prefix.format(**data)
        has_pass_in_prefix = "{renderpass}" in prefix

        # Construct full file paths
        padding = "#" * render_variables["padding"]
        extension = render_variables["ext"]

        workspace = context.data["workspaceDir"]
        render_root = os.path.join(workspace, "renders")

        filenames = []
        for renderpass in [None] + instance.data.get("renderPasses", []):

            # The first entry is the "beauty" pass. (Main render)
            is_beauty_pass = renderpass is None
            if is_beauty_pass:
                renderpass = "beauty"

            # Base of the output filepath
            path = os.path.join(render_root,
                                prefix.format(renderpass=renderpass))

            if not has_pass_in_prefix and not is_beauty_pass:
                path += "." + renderpass

            # Add frame padding and extension
            path += "." + padding + "." + extension

            filenames.append(path)

        instance.data["filenames"] = filenames
