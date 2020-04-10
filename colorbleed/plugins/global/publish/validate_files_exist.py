import pyblish.api

import os


class ValidateFilesExist(pyblish.api.InstancePlugin):
    """Ensure files exist on disk.

    Requires:
        instance    -> files
        instance    -> stagingDir

    """

    order = pyblish.api.ValidatorOrder
    label = "Files Exist"
    families = ["colorbleed.imagesequence"]
    hosts = ["shell"]

    def process(self, instance):

        stagingdir = instance.data["stagingDir"]

        invalid = False
        for representation in instance.data["files"]:

            # If representation is a single file treat
            # it as collection so we can iterate both
            # the same way.
            if not isinstance(representation, (list, tuple)):
                representation = [representation]

            for path in representation:

                if not os.path.isabs(path):
                    path = os.path.join(stagingdir, path)

                if not os.path.exists(path):
                    self.log.error("File does not exist: %s" % path)
                    invalid = True

        if invalid:
            raise RuntimeError("Missing files.")
