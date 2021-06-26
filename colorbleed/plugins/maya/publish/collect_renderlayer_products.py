import os
import re

import pyblish.api

from maya import cmds
from maya import mel

from colorbleed.maya import lib_renderproducts


class CollectRenderlayerProducts(pyblish.api.InstancePlugin):
    """Collect the renderlayer's output filenames from the render passes.

    Requires:
        instance    -> setMembers (renderlayer)

    Provides:
        instance    -> files

    """

    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Renderlayer Products"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    def process(self, instance):

        layer = instance.data["setMembers"]

        # Define output render root
        maya_project_root = cmds.workspace(query=True, rootDirectory=True)
        images_folder = cmds.workspace(fileRuleEntry="images")
        render_root = os.path.join(maya_project_root, images_folder)

        # Get output files for all render products
        files = []

        renderer = lib_renderproducts.get(layer)
        layer_data = renderer.layer_data
        for product in sorted(layer_data.products):
            self.log.debug("Found Render Product: %s" % product)
            for camera in layer_data.cameras:

                # Get filename within render root with the frame number as
                # placeholder #### with the right padding.
                pattern = renderer.get_file_pattern(product, camera)

                # Make absolute output paths
                path = os.path.normpath(os.path.join(render_root, pattern))
                path = path.replace("\\", "/")

                self.log.debug("Expected path: %s" % path)

                files.append(path)

        # todo: Exclude Arnold Denoise AOVs from Publishing!
        # todo: Remap Arnold N_noice back to N, etc. whenever the user did have
        #       a N, Z, diffuse_albedo AOV enabled.

        instance.data["files"] = files

        # Store the Render Products on the instance
        instance.data["products"] = layer_data.products
