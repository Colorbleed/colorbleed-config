import os

import pyblish.api

import avalon.api as api
import colorbleed.vendor.speedcopy as speedcopy


class IntegrateDailies(pyblish.api.InstancePlugin):
    """Integrate a copy of the content to the /dailies folder.

    This is a temporary plug-in to allow quick reviewing and a constant file
    location for the very latest version.

    """

    label = "Integrate Dailies"
    order = pyblish.api.IntegratorOrder + 0.05
    families = ["colorbleed.review"]

    def process(self, instance):

        context = instance.context
        # Atomicity
        #
        # Guarantee atomic publishes - each asset contains
        # an identical set of members.
        #     __
        #    /     o
        #   /       \
        #  |    o    |
        #   \       /
        #    o   __/
        #
        assert all(result["success"] for result in context.data["results"]), (
            "Atomicity not held, aborting.")

        # Define filepath for dailies
        root = "{AVALON_PROJECTS}/{AVALON_PROJECT}/" \
               "resources/dailies".format(**api.Session)
        prefix = "{AVALON_ASSET}_{AVALON_TASK}".format(**api.Session)

        for filename in instance.data["files"]:
            staging = instance.data["stagingDir"]
            source = os.path.join(staging, filename)

            destination = os.path.join(root, "{0}_{1}".format(prefix,
                                                              filename))

            self.log.info("Copy daily: {0} -> {1}".format(source, destination))

            if os.path.exists(destination) and os.path.isfile(destination):
                # Remove existing file
                self.log.debug("Overwriting existing file..")
                #    os.remove(destination)

            speedcopy.copyfile(source, destination)
