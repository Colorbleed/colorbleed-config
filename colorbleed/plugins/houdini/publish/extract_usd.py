import os

import pyblish.api
import colorbleed.api
from colorbleed.houdini.lib import render_rop


class ExtractUSD(colorbleed.api.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract USD"
    hosts = ["houdini"]
    targets = ["local"]
    families = ["colorbleed.usd",
                "usdModel",
                "usdSetDress"]

    def process(self, instance):

        import hou

        ropnode = instance[0]

        # Get the filename from the filename parameter
        output = ropnode.evalParm("lopoutput")
        staging_dir = os.path.dirname(output)
        instance.data["stagingDir"] = staging_dir
        file_name = os.path.basename(output)

        self.log.info("Writing USD '%s' to '%s'" % (file_name, staging_dir))

        render_rop(ropnode)

        assert os.path.exists(output), "Output does not exist: %s" % output

        if "files" not in instance.data:
            instance.data["files"] = []

        instance.data["files"].append(file_name)
