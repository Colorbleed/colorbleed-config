import os
import re

from maya import cmds

import pyblish.api

from colorbleed.maya import lib
from colorbleed.lib import pairwise


SETTINGS = {"renderDensity",
            "renderWidth",
            "renderLength",
            "increaseRenderBounds",
            "imageSearchPath",
            "cbId"}


class CollectYetiRig(pyblish.api.InstancePlugin):
    """Collect all information of the Yeti Rig"""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Yeti Rig"
    families = ["colorbleed.yetiRig"]
    hosts = ["maya"]

    def process(self, instance):

        assert "input_SET" in instance.data["setMembers"], (
            "Yeti Rig must have an input_SET")

        input_connections = self.collect_input_connections(instance)
        instance.data["rigsettings"] = {"inputs": input_connections}

        # Collect any textures if used
        yeti_resources = []
        yeti_nodes = cmds.ls(instance[:], type="pgYetiMaya", long=True)
        failed = False
        for node in yeti_nodes:
            # Get Yeti resources (textures)
            try:
                resources = self.get_yeti_resources(node)
            except RuntimeError as exc:
                # Allow each resource collection to fail so the user
                # gets the warning messages for all resources
                failed = True
                continue
            yeti_resources.extend(resources)

        if failed:
            raise RuntimeError("Failed to collect yeti resources.")

        instance.data["resources"] = yeti_resources

        # Force frame range for export
        instance.data["startFrame"] = 1
        instance.data["endFrame"] = 1

    def collect_input_connections(self, instance):
        """Collect the inputs for all nodes in the input_SET"""

        # Get the input meshes information
        input_content = cmds.ls(cmds.sets("input_SET", query=True), long=True)

        # Include children
        input_content += cmds.listRelatives(input_content,
                                            allDescendents=True,
                                            fullPath=True) or []

        # Ignore intermediate objects
        input_content = cmds.ls(input_content, long=True, noIntermediate=True)
        if not input_content:
            return []

        # Store all connections
        connections = cmds.listConnections(input_content,
                                           source=True,
                                           destination=False,
                                           connections=True,
                                           # Only allow inputs from dagNodes
                                           # (avoid display layers, etc.)
                                           type="dagNode",
                                           plugs=True) or []
        connections = cmds.ls(connections, long=True)      # Ensure long names

        inputs = []
        for dest, src in pairwise(connections):
            source_node, source_attr = src.split(".", 1)
            dest_node, dest_attr = dest.split(".", 1)

            # Ensure the source of the connection is not included in the
            # current instance's hierarchy. If so, we ignore that connection
            # as we will want to preserve it even over a publish.
            if source_node in instance:
                self.log.debug("Ignoring input connection between nodes "
                               "inside the instance: %s -> %s" % (src, dest))
                continue

            inputs.append({"connections": [source_attr, dest_attr],
                           "sourceID": lib.get_id(source_node),
                           "destinationID": lib.get_id(dest_node)})

        return inputs

    def get_yeti_resources(self, node):
        """Get all resource file paths

        If a texture is a sequence it gathers all sibling files to ensure
        the texture sequence is complete.

        References can be used in the Yeti graph, this means that it is
        possible to load previously caches files. The information will need
        to be stored and, if the file not publish, copied to the resource
        folder.

        Args:
            node (str): node name of the pgYetiMaya node

        Returns:
            list
        """
        self.log.info("Collecting resources for %s" % node)

        # Get the image search path value (this can return None if not set)
        attr = "{}.imageSearchPath".format(node)
        image_search_paths = cmds.getAttr(attr) or ""

        # TODO: Somehow this uses OS environment path separator, `:` vs `;`
        # Later on check whether this is pipeline OS cross-compatible.
        image_search_paths = [p for p in
                              image_search_paths.split(os.path.pathsep) if p]

        # List all related textures
        texture_filenames = cmds.pgYetiCommand(node, listTextures=True)
        self.log.debug("Found %i texture node(s)" % len(texture_filenames))

        if texture_filenames and not image_search_paths:
            raise ValueError("pgYetiMaya node '%s' is missing the path to the "
                             "files in the 'imageSearchPath attribute'" % node)

        # Collect all texture files
        resources = []
        for texture in texture_filenames:

            files = []
            if os.path.isabs(texture):
                self.log.debug("Texture is absolute path, ignoring "
                               "image search paths for: %s" % texture)
                files = self.search_textures(texture)
                if not files:
                    self.log.error(
                        "No texture at absolute path: %s" % texture)
            else:
                for root in image_search_paths:
                    filepath = os.path.join(root, texture)
                    files = self.search_textures(filepath)
                    if files:
                        # Break out on first match in search paths..
                        break
                    else:
                        self.log.warning("No texture at path: %s" % filepath)
                else:
                    # Found no files..
                    self.log.error("No texture found for "
                                   "relative path: %s" % texture)

            item = {
                "files": files,
                "source": texture,
                "node": node
            }

            resources.append(item)

        # For now validate that every texture has at least a single file
        # resolved. Since a 'resource' does not have the requirement of having
        # a `files` explicitly mapped it's not explicitly validated.
        # TODO: Validate this as a validator
        invalid_resources = []
        for resource in resources:
            if not resource['files']:
                invalid_resources.append(resource)
        if invalid_resources:
            raise RuntimeError("Invalid texture resources")

        # Collect all referenced files
        reference_nodes = cmds.pgYetiGraph(node,
                                           listNodes=True,
                                           type="reference")
        self.log.debug("Found %i reference node(s)" % len(reference_nodes))

        for reference_node in reference_nodes:
            ref_file = cmds.pgYetiGraph(node,
                                        node=reference_node,
                                        param="reference_file",
                                        getParamValue=True)

            # Create resource dict
            item = {
                "source": ref_file,
                "node": node,
                "graphnode": reference_node,
                "param": "reference_file",
                "files": []
            }

            ref_file_name = os.path.basename(ref_file)
            if "%04d" in ref_file_name:
                item["files"] = self.get_sequence(ref_file)
            else:
                if os.path.exists(ref_file) and os.path.isfile(ref_file):
                    item["files"] = [ref_file]

            if not item["files"]:
                self.log.warning("Reference node '%s' has no valid file "
                                 "path set: %s" % (reference_node, ref_file))
                # TODO: This should allow to pass and fail in Validator instead
                raise RuntimeError("Reference node  must be a full file path!")

            resources.append(item)

        return resources

    def search_textures(self, filepath):
        """Search all texture files on disk.

        This also parses to full sequences for those with dynamic patterns
        like <UDIM> and %04d in the filename.

        Args:
            filepath (str): The full path to the file, including any
                dynamic patterns like <UDIM> or %04d

        Returns:
            list: The files found on disk

        """
        filename = os.path.basename(filepath)

        # Collect full sequence if it matches a sequence pattern
        # For UDIM based textures (tiles)
        if "<UDIM>" in filename:
            sequences = self.get_sequence(filepath,
                                          pattern="<UDIM>")
            if sequences:
                return sequences

        # Frame/time - Based textures (animated masks f.e)
        elif "%04d" in filename:
            sequences = self.get_sequence(filepath,
                                          pattern="%04d")
            if sequences:
                return sequences

        # Assuming it is a fixed name (single file)
        if os.path.exists(filepath):
            return [filepath]

        return []

    def get_sequence(self, filepath, pattern="%04d"):
        """Get sequence from filename.

        This will only return files if they exist on disk as it tries
        to collect the sequence using the filename pattern and searching
        for them on disk.

        Supports negative frame ranges like -001, 0000, 0001 and -0001,
        0000, 0001.

        Arguments:
            filepath (str): The full path to filename containing the given
            pattern.
            pattern (str): The pattern to swap with the variable frame number.

        Returns:
            list: file sequence.

        """

        escaped = re.escape(os.path.basename(filepath))
        re_pattern = escaped.replace(re.escape(pattern), "-?[0-9]+")
        source_dir = os.path.dirname(filepath)
        if not os.path.exists(source_dir):
            return []

        files = [os.path.join(source_dir, f) for f in os.listdir(source_dir)
                 if re.match(re_pattern, f)]

        return files
