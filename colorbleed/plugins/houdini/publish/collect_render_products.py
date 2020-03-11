import re

import hou
import pxr.UsdRender

import avalon.io as io
import avalon.api as api
import pyblish.api


class CollectRenderProducts(pyblish.api.InstancePlugin):
    """Collect USD Render Products"""

    label = "Collect Render Products"
    order = pyblish.api.CollectorOrder + 0.4
    hosts = ["houdini"]
    families = ["colorbleed.usdrender"]

    def process(self, instance):

        node = instance.data.get("output_node")
        if not node:
            rop_path = instance[0].path()
            raise RuntimeError("No output node found. Make sure to connect an "
                               "input to the USD ROP: %s" % rop_path)

        stage = node.stage()

        filenames = []
        for prim in stage.Traverse():

            if not prim.IsA(pxr.UsdRender.Product):
                continue

            # Get Render Product Name
            product = pxr.UsdRender.Product(prim)
            name = product.GetProductNameAttr().Get()

            # Substitute $F
            def replace_f(match):
                """ Replace $F4 with padded for Deadline"""
                padding = int(match.group(2)) if match.group(2) else 1
                return "#" * padding

            filename = re.sub(r"(\$F([0-9]?))", replace_f, name)
            filenames.append(filename)

            prim_path = str(prim.GetPath())
            self.log.info("Collected %s name: %s" % (prim_path, filename))

        # Filenames for Deadline
        instance.data["filenames"] = filenames
