import pyblish.api
import colorbleed.api

import os


class ValidateResources(pyblish.api.InstancePlugin):
    """Validates mapped resources.

    These are external files to the current application, for example
    these could be textures, image planes, cache files or other linked
    media.

    This validates:
        - The resources are existing files.
        - The resources["files"] must only contain (existing) files
        - The resources have correctly collected the data.

    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Resources"

    def process(self, instance):

        for resource in instance.data.get('resources', []):

            # Ensure required "source" in resource
            assert "source" in resource, (
                    "No source found in resource: %s" % resource
            )

            # Ensure required "files" in resource
            assert "files" in resource, (
                "No files from resource: %s" % resource
            )

            # Detect paths that are not a file or don't exist
            not_files = [f for f in resource["files"] if not os.path.isfile(f)]
            assert not not_files, (
                "Found non-files or non-existing files: %s (resource: %s)" % (
                    not_files, resource
                )
            )
