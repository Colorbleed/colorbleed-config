import os

import pyblish.api
import colorbleed.api


class ExtractComposite(colorbleed.api.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Composite (Image Sequence)"
    hosts = ["houdini"]
    targets = ["local"]
    families = ["colorbleed.imagesequence"]

    def process(self, instance):

        import hou

        ropnode = instance[0]

        # Get the filename from the copoutput parameter
        # `.evalParm(parameter)` will make sure all tokens are resolved
        output = ropnode.evalParm("copoutput")
        staging_dir = os.path.dirname(output)
        instance.data["stagingDir"] = staging_dir
        file_name = os.path.basename(output)

        self.log.info("Writing comp '%s' to '%s'" % (file_name, staging_dir))

        # Print verbose when in batch mode without UI
        verbose = not hou.isUIAvailable()

        # Render
        try:
            ropnode.render(verbose=verbose)
        except hou.Error as exc:
            # The hou.Error is not inherited from a Python Exception class,
            # so we explicitly capture the houdini error, otherwise pyblish
            # will remain hanging.
            import traceback
            traceback.print_exc()
            raise RuntimeError("Render failed: {0}".format(exc))

        if "files" not in instance.data:
            instance.data["files"] = []

        frames = instance.data["frames"]
        instance.data["files"].append(frames)
