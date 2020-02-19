import os
import re
import shutil

import pyblish.api


class IntegrateUSDMasterFile(pyblish.api.InstancePlugin):
    """Create an unversioned master file that gets overwritten.

    For the nested referencing of USD and resolving those included layers,
    payloads or references as versioned data we will need to implement
    an ArResolver. Before that time, we'll use a static master file instead.

    This plug-in generates that master file.

    """

    order = pyblish.api.IntegratorOrder + 0.4
    label = "USD Master File"
    hosts = ["houdini", "maya"]
    targets = ["local"]
    families = ["colorbleed.usd",
                "colorbleed.usd.bootstrap",
                "colorbleed.usd.layered",
                "usdModel"]

    def process(self, instance):

        context = instance.context
        assert all(result["success"] for result in context.data["results"]), (
            "Atomicity not held, aborting.")

        self.create_master_file(instance)

        # Create master files for dependencies
        for dependency in instance.data.get("publishDependencies", list()):

            if not dependency.data.get("publish", True):
                continue

            if not dependency.data.get("_isExtracted", False):
                continue

            if dependency.data.get("_isMasterFileCreated", False):
                continue

            self.create_master_file(dependency)
            dependency.data["_isMasterFileCreated"] = True

    def create_master_file(self, instance):

        extensions = {"usd", "usda", "usdlc", "usdnc"}

        for src, dest in instance.data.get("transfers"):

            ext = dest.rsplit(".", 1)[-1]
            if ext not in extensions:
                continue

            # This is likely the file we will want to make
            # a master file of. Let's do a little check whether
            # it's directly in a version folder.
            version_folder = os.path.dirname(dest)
            if not re.match("^v[0-9]+$", os.path.basename(version_folder)):
                continue

            # Make sure the folder match the subset location
            subset_folder = os.path.dirname(version_folder)
            subset = instance.data["subset"]
            if not os.path.basename(subset_folder) == subset:
                continue

            # Generate a copy
            master_folder = os.path.join(subset_folder, "master")
            master_dest = os.path.join(master_folder,
                                       "{0}.{1}".format(subset, ext))

            self.log.info("Creating master file: %s" % master_dest)

            if not os.path.exists(master_folder):
                os.makedirs(master_folder)

            shutil.copy(dest, master_dest)
