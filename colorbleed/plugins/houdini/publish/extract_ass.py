import os

import pyblish.api
import colorbleed.api
from colorbleed.houdini.lib import render_rop


class ExtractAss(colorbleed.api.Extractor):

    order = pyblish.api.ExtractorOrder + 0.1
    label = "Extract Ass"
    families = ["ass"]
    targets = ["local"]
    hosts = ["houdini"]

    def process(self, instance):

        import hou

        ropnode = instance[0]

        # Get the filename from the filename parameter
        # `.evalParm(parameter)` will make sure all tokens are resolved
        output = ropnode.evalParm("ar_ass_file")
        staging_dir = os.path.dirname(output)
        instance.data["stagingDir"] = staging_dir
        file_name = os.path.basename(output)

        # We run the render
        self.log.info("Writing ASS '%s' to '%s'" % (file_name, staging_dir))

        render_rop(ropnode)

        if "files" not in instance.data:
            instance.data["files"] = []

        frames = instance.data["frames"]
        instance.data["files"].append(frames)
