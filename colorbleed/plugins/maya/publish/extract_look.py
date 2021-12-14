import os
import json
import tempfile
import contextlib
from collections import OrderedDict

from maya import cmds

import pyblish.api
import avalon.maya

import colorbleed.api
import colorbleed.maya.lib as lib


@contextlib.contextmanager
def no_workspace_dir():
    """Force maya to a fake temporary workspace directory.

    Note: This is not maya.cmds.workspace 'rootDirectory' but the 'directory'

    This helps to avoid Maya automatically remapping image paths to files
    relative to the currently set directory.

    """

    # Store current workspace
    original = cmds.workspace(query=True, directory=True)

    # Set a fake workspace
    fake_workspace_dir = tempfile.mkdtemp()
    cmds.workspace(directory=fake_workspace_dir)

    try:
        yield
    finally:
        try:
            cmds.workspace(directory=original)
        except RuntimeError:
            # If the original workspace directory didn't exist either
            # ignore the fact that it fails to reset it to the old path
            pass

        # Remove the temporary directory
        os.rmdir(fake_workspace_dir)


class ExtractLook(colorbleed.api.Extractor):
    """Extract Look (Maya Ascii + JSON)

    Only extracts the sets (shadingEngines and alike) alongside a .json file
    that stores it relationships for the sets and "attribute" data for the
    instance members.

    """

    label = "Extract Look (Maya ASCII + JSON)"
    hosts = ["maya"]
    families = ["colorbleed.look"]
    order = pyblish.api.ExtractorOrder + 0.2

    def process(self, instance):

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        maya_fname = "{0}.ma".format(instance.name)
        json_fname = "{0}.json".format(instance.name)

        # Make texture dump folder
        maya_path = os.path.join(dir_path, maya_fname)
        json_path = os.path.join(dir_path, json_fname)

        self.log.info("Performing extraction..")

        # Remove all members of the sets so they are not included in the
        # exported file by accident
        self.log.info("Extract sets (Maya ASCII) ...")
        lookdata = instance.data["lookData"]
        relationships = lookdata["relationships"]
        sets = list(relationships.keys())

        resources = instance.data["resources"]

        remap = OrderedDict()  # needs to be ordered, see color space values
        for resource in resources:
            attr = resource['attribute']
            remap[attr] = resource['destination']

            # Preserve color space values (force value after filepath change)
            # This will also trigger in the same order at end of context to
            # ensure after context it's still the original value.
            # todo: would be even better if this uses 
            # "ignoreColorSpaceFileRules" instead?
            node = resource['node']
            if cmds.attributeQuery("colorSpace", node=node, exists=True):
                color_space_attr = node + ".colorSpace"
                remap[color_space_attr] = cmds.getAttr(color_space_attr)

        self.log.info("Finished remapping destinations ...")

        # Extract in correct render layer
        layer = instance.data.get("renderlayer", "defaultRenderLayer")
        with lib.renderlayer(layer):
            # TODO: Ensure membership edits don't become renderlayer overrides
            with lib.empty_sets(sets, force=True):
                # To avoid Maya trying to automatically remap the file
                # textures relative to the `workspace -directory` we force
                # it to a fake temporary workspace. This fixes textures
                # getting incorrectly remapped. (LKD-17, PLN-101)
                with no_workspace_dir():
                    with lib.attribute_values(remap):
                        with avalon.maya.maintained_selection():
                            cmds.select(sets, noExpand=True)
                            cmds.file(maya_path,
                                      force=True,
                                      typ="mayaAscii",
                                      exportSelected=True,
                                      preserveReferences=False,
                                      channels=True,
                                      constraints=True,
                                      expressions=True,
                                      constructionHistory=True)

        # Write the JSON data
        self.log.info("Extract json..")
        data = {"attributes": lookdata["attributes"],
                "relationships": relationships}

        with open(json_path, "w") as f:
            json.dump(data, f)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(maya_fname)
        instance.data["files"].append(json_fname)

        self.log.info("Extracted instance '%s' to: %s" % (instance.name,
                                                          maya_path))
