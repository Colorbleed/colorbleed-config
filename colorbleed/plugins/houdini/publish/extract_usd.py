import os

import pyblish.api
import colorbleed.api


class ExtractUSD(colorbleed.api.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract USD"
    hosts = ["houdini"]
    targets = ["local"]
    families = ["colorbleed.usd"]

    def process(self, instance):

        import hou

        ropnode = instance[0]

        # Get the filename from the filename parameter
        output = ropnode.evalParm("lopoutput")
        staging_dir = os.path.dirname(output)
        instance.data["stagingDir"] = staging_dir

        file_name = os.path.basename(output)

        self.log.info("Writing USD '%s' to '%s'" % (file_name, staging_dir))

        # Print verbose when in batch mode without UI
        verbose = not hou.isUIAvailable()

        # Render
        try:
            ropnode.render(verbose=verbose,
                           # Allow Deadline to capture completion percentage
                           output_progress=verbose)
        except hou.Error as exc:
            # The hou.Error is not inherited from a Python Exception class,
            # so we explicitly capture the houdini error, otherwise pyblish
            # will remain hanging.
            import traceback
            traceback.print_exc()
            raise RuntimeError("Render failed: {0}".format(exc))

        assert os.path.exists(output), "Output does not exist: %s" % output

        if "files" not in instance.data:
            instance.data["files"] = []

        instance.data["files"].append(file_name)
