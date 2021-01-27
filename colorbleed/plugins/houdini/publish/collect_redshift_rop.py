import re
import os

import hou
import avalon.io as io
import avalon.api as api
import pyblish.api


def evalParmNoFrame(node, parm, pad_character="#"):

    parameter = node.parm(parm)
    assert parameter, "Parameter does not exist: %s.%s" % (node, parm)

    # Substitute out the frame numbering with padded characters
    raw = parameter.unexpandedString()

    def replace(match):
        padding = 1
        n = match.group(2)
        if n and int(n):
            padding = int(n)
        return pad_character * padding

    expression = re.sub(r"(\$F([0-9]*))", replace, raw)

    with hou.ScriptEvalContext(parameter):
        return hou.expandStringAtFrame(expression, 0)


class CollectRedshiftROPRenderProducts(pyblish.api.InstancePlugin):
    """Collect USD Render Products

    Collects the instance.data["files"] for the render products.

    Provides:
        instance    -> files

    """

    label = "Redshift ROP Render Products"
    order = pyblish.api.CollectorOrder + 0.4
    hosts = ["houdini"]
    families = ["redshift_rop"]

    def process(self, instance):

        rop = instance[0]
        default_prefix = evalParmNoFrame(rop, "RS_outputFileNamePrefix")
        beauty_suffix = rop.evalParm("RS_outputBeautyAOVSuffix")
        render_products = []

        # Default beauty AOV
        beauty_product = self.get_render_product_name(prefix=default_prefix,
                                                      suffix=beauty_suffix)
        render_products.append(beauty_product)

        num_aovs = rop.evalParm("RS_aov")
        for index in range(num_aovs):
            i = index + 1
            aov_suffix = rop.evalParm("RS_aovSuffix_%s" % i)
            aov_prefix = evalParmNoFrame(rop, "RS_aovCustomPrefix_%s" % i)
            if not aov_prefix:
                aov_prefix = default_prefix

            aov_product = self.get_render_product_name(aov_prefix, aov_suffix)
            render_products.append(aov_product)

        for product in render_products:
            self.log.debug("Found render product: %s" % product)

        filenames = list(render_products)
        instance.data["files"] = filenames

        import pprint
        pprint.pprint(render_products)

    def get_render_product_name(self, prefix, suffix):
        """Return the output filename using the AOV prefix and suffix"""

        # When AOV is explicitly defined in prefix we just swap it out
        # directly with the AOV suffix to embed it.
        # Note: ${AOV} seems to be evaluated in the parameter as %AOV%
        has_aov_in_prefix = "%AOV%" in prefix
        if has_aov_in_prefix:
            # It seems that when some special separator characters are present
            # before the %AOV% token that Redshift will secretly remove it if
            # there is no suffix for the current product, for example:
            # foo_%AOV% -> foo.exr
            pattern = "%AOV%" if suffix else "[._-]?%AOV%"
            product_name = re.sub(pattern,
                                  suffix,
                                  prefix,
                                  flags=re.IGNORECASE)
        else:
            if suffix:
                # Add ".{suffix}" before the extension
                prefix_base, ext = os.path.splitext(prefix)
                product_name = prefix_base + "." + suffix + ext
            else:
                product_name = prefix

        return product_name
